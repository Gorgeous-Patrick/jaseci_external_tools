#!/usr/bin/env python3
"""
Analyze a jac server .prof file and report time broken down by memory tier.

Tiers:
  L1  - in-process dict (VolatileMemory / app address space)
  L2  - Redis (RedisBackend + redis-py client)
  L3  - MongoDB (MongoBackend + pymongo client)
  coordination - ScaleTieredMemory / TieredMemory orchestration
  other - everything else

Usage:
    python mem_profile.py <path/to/jac_server.prof>
    python mem_profile.py <path/to/jac_server.prof> --top 20
"""

import pstats
import sys
import argparse
from collections import defaultdict

# ---------------------------------------------------------------------------
# MongoBackend request functions — each call = one MongoDB round-trip.
# ---------------------------------------------------------------------------
MONGO_REQUEST_FUNCS = {
    "get", "put", "delete", "has", "query",
    "find", "find_raw", "batch_get", "bulk_put",
}

# ---------------------------------------------------------------------------
# Tier classification rules — checked in order, first match wins.
# Each rule is (tier_label, list_of_substrings_to_match_against_filename).
# ---------------------------------------------------------------------------
TIER_RULES = [
    ("L2 Redis",    ["memory_hierarchy.redis", "/redis/", "\\redis\\"]),
    ("L3 MongoDB",  ["memory_hierarchy.mongo", "/pymongo/", "\\pymongo\\", "bson"]),
    ("coordination",["memory_hierarchy.main",  "memory.impl", "topo_utils"]),
]

def classify(filename: str) -> str:
    for tier, patterns in TIER_RULES:
        if any(p in filename for p in patterns):
            return tier
    return "other"


def format_ms(seconds: float) -> str:
    return f"{seconds * 1000:>10.3f} ms"


def reachable_from(entry_key, raw: dict) -> set:
    """BFS from entry_key following callee edges; returns set of reachable keys."""
    # Build callee map: caller -> [callees]
    callee_map: dict = defaultdict(list)
    for callee_key, (cc, nc, tt, ct, callers) in raw.items():
        for caller_key in callers:
            callee_map[caller_key].append(callee_key)

    visited = set()
    frontier = [entry_key]
    while frontier:
        key = frontier.pop()
        if key in visited:
            continue
        visited.add(key)
        frontier.extend(callee_map.get(key, []))
    return visited


def analyze(prof_path: str, top_n: int, trials: int) -> None:
    stats = pstats.Stats(prof_path, stream=open("/dev/null", "w"))
    # stats.stats: {(file, lineno, func): (prim_calls, total_calls, tottime, cumtime, callers)}
    raw = stats.stats

    # Find _jac_walker_execute and BFS to get its subtree
    entry_key = next((k for k in raw if k[2] == "_jac_walker_execute"), None)
    subtree = reachable_from(entry_key, raw) if entry_key else set(raw.keys())
    entry_cumtime = (raw[entry_key][3] / trials) if entry_key else 0.0

    # Accumulate tottime per tier and track individual functions — subtree only
    tier_tottime: dict[str, float] = defaultdict(float)
    tier_funcs: dict[str, list] = defaultdict(list)
    mongo_request_calls: dict[str, int] = {}
    ttg_cumtime = 0.0
    prefetch_cumtime = 0.0

    for key in subtree:
        filename, lineno, funcname = key
        cc, nc, tt, ct, _callers = raw[key]
        tier = classify(filename)
        tier_tottime[tier] += tt / trials
        tier_funcs[tier].append((tt / trials, ct / trials, nc, funcname, filename, lineno))
        short_funcname = funcname.split(".")[-1]
        if tier == "L3 MongoDB" and short_funcname in MONGO_REQUEST_FUNCS and "memory_hierarchy.mongo" in filename:
            mongo_request_calls[short_funcname] = mongo_request_calls.get(short_funcname, 0) + nc
        if funcname == "get_ttg_prefetch_list":
            ttg_cumtime = ct / trials
        elif funcname == "ScaleTieredMemory.prefetch":
            prefetch_cumtime = ct / trials

    total_ref = entry_cumtime if entry_cumtime > 0 else sum(entry[2] for entry in raw.values()) / trials

    # Derive L1 time: coordination tottime minus what it spent calling L2/L3.
    # Since tottime already excludes called functions, L1 dict ops are embedded
    # in coordination tottime (they are inlined / not separate function calls).
    # We label the coordination tier as "L1 + coordination overhead" accordingly.

    # -----------------------------------------------------------------------
    # Summary table
    # -----------------------------------------------------------------------
    print(f"\n{'='*65}")
    print(f"  Memory tier breakdown  —  {prof_path}")
    print(f"  averaged over {trials} trials (per-request)")
    print(f"{'='*65}")
    print(f"{'Tier':<22}  {'Avg self-time/req':>17}  {'% of profiled':>13}")
    print(f"{'-'*65}")

    ordered_tiers = ["L2 Redis", "L3 MongoDB", "coordination", "other"]
    for tier in ordered_tiers:
        tt = tier_tottime.get(tier, 0.0)
        pct = (tt / total_ref * 100) if total_ref > 0 else 0.0
        label = tier if tier != "coordination" else "L1 + coordination"
        print(f"  {label:<20}  {format_ms(tt)}  {pct:>12.1f}%")

    print(f"{'-'*65}")
    ref_label = "Total (_jac_walker_execute)" if entry_cumtime > 0 else "Total profiled"
    print(f"  {ref_label:<20}  {format_ms(total_ref)}")
    if ttg_cumtime > 0 or prefetch_cumtime > 0:
        print(f"{'='*65}")
        print(f"  TTG breakdown (cum-time/req):")
        if ttg_cumtime > 0:
            print(f"    {'get_ttg_prefetch_list':<22}  {format_ms(ttg_cumtime)}")
        if prefetch_cumtime > 0:
            print(f"    {'prefetch':<22}  {format_ms(prefetch_cumtime)}")
    print(f"{'='*65}\n")

    # -----------------------------------------------------------------------
    # MongoDB request counts
    # -----------------------------------------------------------------------
    if mongo_request_calls:
        total_mongo_calls = sum(mongo_request_calls.values())
        print(f"  MongoDB requests (total across {trials} trials: {total_mongo_calls},  avg/req: {total_mongo_calls/trials:.1f})")
        print(f"  {'function':<12}  {'total calls':>11}  {'avg/req':>9}")
        print(f"  {'-'*38}")
        for funcname in sorted(mongo_request_calls, key=lambda f: mongo_request_calls[f], reverse=True):
            calls = mongo_request_calls[funcname]
            note = "  (generator: counts docs yielded, not queries)" if funcname == "find_raw" else ""
            print(f"  {funcname:<12}  {calls:>11}  {calls/trials:>9.1f}{note}")
        print()

    # -----------------------------------------------------------------------
    # Per-tier top-N breakdown
    # -----------------------------------------------------------------------
    for tier in ["L2 Redis", "L3 MongoDB", "coordination"]:
        funcs = tier_funcs.get(tier, [])
        if not funcs:
            continue
        funcs.sort(key=lambda x: x[0], reverse=True)
        tier_total = tier_tottime.get(tier, 0.0)
        print(f"  Top {top_n} functions in [{tier}]  (avg self-time/req: {tier_total*1000:.3f} ms)")
        print(f"  {'self-time':>12}  {'cum-time':>12}  {'calls':>8}  function")
        print(f"  {'-'*60}")
        for tt, ct, nc, funcname, filename, lineno in funcs[:top_n]:
            short_file = filename.split("/")[-1] if "/" in filename else filename
            loc = f"{short_file}:{lineno}"
            print(f"  {format_ms(tt)}  {format_ms(ct)}  {nc:>8}  {funcname}  [{loc}]")
        print()


def main() -> None:
    parser = argparse.ArgumentParser(description="Memory tier profiling summary")
    parser.add_argument("prof", help="Path to .prof file")
    parser.add_argument("--top", type=int, default=10, help="Top N functions per tier")
    parser.add_argument("--trials", type=int, default=10, help="Number of trials to average over")
    args = parser.parse_args()
    analyze(args.prof, args.top, args.trials)


if __name__ == "__main__":
    main()
