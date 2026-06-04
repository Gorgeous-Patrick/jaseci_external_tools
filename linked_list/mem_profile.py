#!/usr/bin/env python3
"""
Analyze a jac server .prof file and report cumulative time broken down by memory tier.

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
    raw = stats.stats

    # Find _jac_walker_execute and BFS to get its subtree
    entry_key = next((k for k in raw if k[2] == "_jac_walker_execute"), None)
    subtree = reachable_from(entry_key, raw) if entry_key else set(raw.keys())
    entry_cumtime = (raw[entry_key][3] / trials) if entry_key else 0.0

    # Accumulate tottime per tier and track individual functions — subtree only
    tier_tottime: dict[str, float] = defaultdict(float)
    tier_funcs: dict[str, list] = defaultdict(list)
    mongo_request_calls: dict[str, int] = {}
    mongo_request_cumtime: dict[str, float] = {}

    # Key function tracking
    key_funcs: dict[str, dict] = {}
    KEY_FUNC_NAMES = {
        "get_ttg_prefetch_list", "ScaleTieredMemory.prefetch",
        "MongoBackend.find_raw", "RedisBackend.bulk_put_raw",
        "RedisBackend.bulk_exists",
        "deserialize", "_compute_hash", "_snapshot_field_hashes",
        "_get_field_types", "get_type_hints",
        "osp_spawn", "_visit_recursive", "_build_plan_from_path",
        "_filter_has_predicates", "_filter_type_name", "getclosurevars",
        "plan_chain_ordered", "resolve_chain_ordered", "_materialize_ids",
        "_sv_on_complete",
    }

    for key in subtree:
        filename, lineno, funcname = key
        cc, nc, tt, ct, _callers = raw[key]
        tier = classify(filename)
        tier_tottime[tier] += tt / trials
        tier_funcs[tier].append((ct / trials, tt / trials, nc, funcname, filename, lineno))

        short_funcname = funcname.split(".")[-1]
        if tier == "L3 MongoDB" and short_funcname in MONGO_REQUEST_FUNCS and "memory_hierarchy.mongo" in filename:
            mongo_request_calls[short_funcname] = mongo_request_calls.get(short_funcname, 0) + nc
            mongo_request_cumtime[short_funcname] = mongo_request_cumtime.get(short_funcname, 0.0) + ct

        if funcname in KEY_FUNC_NAMES:
            # Skip super.prefetch entry (memory.impl), keep only override (main.impl)
            if funcname == "ScaleTieredMemory.prefetch" and "memory.impl" in filename:
                continue
            if funcname not in key_funcs:
                key_funcs[funcname] = {"nc": 0, "tt": 0.0, "ct": 0.0}
            key_funcs[funcname]["nc"] += nc
            key_funcs[funcname]["tt"] += tt / trials
            key_funcs[funcname]["ct"] += ct / trials

    total_ref = entry_cumtime if entry_cumtime > 0 else sum(entry[2] for entry in raw.values()) / trials

    def kf_ct(fn):
        return key_funcs.get(fn, {"ct": 0})["ct"] * 1000

    def kf_nc(fn):
        return key_funcs.get(fn, {"nc": 0})["nc"]

    # -----------------------------------------------------------------------
    # Summary table
    # -----------------------------------------------------------------------
    print(f"\n{'='*65}")
    print(f"  Memory tier breakdown  —  {prof_path}")
    print(f"  averaged over {trials} trials (per-request)")
    print(f"{'='*65}")
    print(f"{'Tier':<22}  {'Avg self-time/req':>17}  {'% of profiled':>13}")
    print(f"{'-'*65}")

    total_self = sum(tier_tottime.values())
    ordered_tiers = ["L2 Redis", "L3 MongoDB", "coordination", "other"]
    for tier in ordered_tiers:
        tt = tier_tottime.get(tier, 0.0)
        pct = (tt / total_self * 100) if total_self > 0 else 0.0
        label = tier if tier != "coordination" else "L1 + coordination"
        print(f"  {label:<20}  {format_ms(tt)}  {pct:>12.1f}%")

    print(f"{'-'*65}")
    ref_label = "Total (_jac_walker_execute)" if entry_cumtime > 0 else "Total profiled"
    print(f"  {ref_label:<20}  {format_ms(total_ref)}")
    print(f"{'='*65}\n")

    # -----------------------------------------------------------------------
    # Prefetch pipeline breakdown
    # -----------------------------------------------------------------------
    prefetch_ct = kf_ct("ScaleTieredMemory.prefetch")
    if prefetch_ct > 0:
        print(f"  Prefetch Pipeline ({prefetch_ct:.0f}ms)")
        print(f"  {'-'*55}")
        print(f"    {'MongoDB find_raw':<35}  {kf_ct('MongoBackend.find_raw'):>8.1f}ms")
        print(f"    {'Redis bulk_put_raw':<35}  {kf_ct('RedisBackend.bulk_put_raw'):>8.1f}ms")
        bulk_exists = kf_ct("RedisBackend.bulk_exists")
        if bulk_exists > 0:
            print(f"    {'Redis bulk_exists':<35}  {bulk_exists:>8.1f}ms")
        print(f"    {'Deserialize':<35}  {kf_ct('deserialize'):>8.1f}ms  ({kf_nc('deserialize')} calls)")
        print(f"      {'get_type_hints':<33}  {kf_ct('get_type_hints'):>8.1f}ms  ({kf_nc('get_type_hints')} calls)")
        print(f"      {'_compute_hash':<33}  {kf_ct('_compute_hash'):>8.1f}ms  ({kf_nc('_compute_hash')} calls)")
        snapshot = kf_ct("_snapshot_field_hashes")
        if snapshot > 0:
            print(f"    {'_snapshot_field_hashes':<35}  {snapshot:>8.1f}ms  ({kf_nc('_snapshot_field_hashes')} calls)")
        ttg = kf_ct("get_ttg_prefetch_list")
        if ttg > 0:
            print(f"    {'TTG (get_ttg_prefetch_list)':<35}  {ttg:>8.1f}ms")
        print()

    # -----------------------------------------------------------------------
    # Walker runtime breakdown
    # -----------------------------------------------------------------------
    walker_ct = kf_ct("osp_spawn")
    if walker_ct > 0:
        print(f"  Walker Runtime ({walker_ct:.0f}ms)")
        print(f"  {'-'*55}")
        # User code: visit_item self-time
        for key in subtree:
            fn = key[2]
            if "visit_item" in fn or fn in ("visit_item", "Traverse.visit_item"):
                user_tt = raw[key][2] / trials * 1000
                user_nc = raw[key][1]
                print(f"    {'User code (self-time)':<35}  {user_tt:>8.1f}ms  ({user_nc} calls)")
                break
        print(f"    {'Plan building':<35}  {kf_ct('_build_plan_from_path'):>8.1f}ms  ({kf_nc('_build_plan_from_path')} calls)")
        filter_total = kf_ct("_filter_has_predicates") + kf_ct("_filter_type_name") + kf_ct("getclosurevars")
        print(f"      {'Filter analysis (bytecode+inspect)':<33}  {filter_total:>8.1f}ms")
        print(f"    {'Topology index resolution':<35}  {kf_ct('plan_chain_ordered'):>8.1f}ms  ({kf_nc('plan_chain_ordered')} calls)")
        print(f"    {'Materialize from L1':<35}  {kf_ct('_materialize_ids'):>8.1f}ms  ({kf_nc('_materialize_ids')} calls)")
        print(f"    {'Commit (_sv_on_complete)':<35}  {kf_ct('_sv_on_complete'):>8.1f}ms")
        print()

    # -----------------------------------------------------------------------
    # MongoDB request counts
    # -----------------------------------------------------------------------
    if mongo_request_calls:
        total_mongo_calls = sum(mongo_request_calls.values())
        print(f"  MongoDB requests (total: {total_mongo_calls},  avg/req: {total_mongo_calls/trials:.1f})")
        print(f"  {'function':<12}  {'total calls':>11}  {'avg/req':>9}  {'cum/req':>12}  {'avg/call':>12}")
        print(f"  {'-'*62}")
        for funcname in sorted(mongo_request_calls, key=lambda f: mongo_request_calls[f], reverse=True):
            calls = mongo_request_calls[funcname]
            ct = mongo_request_cumtime.get(funcname, 0.0)
            avg_call = ct / calls if calls else 0.0
            print(f"  {funcname:<12}  {calls:>11}  {calls/trials:>9.1f}  {format_ms(ct/trials)}  {format_ms(avg_call)}")
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
        print(f"  {'cum-time':>12}  {'self-time':>12}  {'calls':>8}  function")
        print(f"  {'-'*60}")
        for ct, tt, nc, funcname, filename, lineno in funcs[:top_n]:
            short_file = filename.split("/")[-1] if "/" in filename else filename
            loc = f"{short_file}:{lineno}"
            print(f"  {format_ms(ct)}  {format_ms(tt)}  {nc:>8}  {funcname}  [{loc}]")
        print()


def main() -> None:
    parser = argparse.ArgumentParser(description="Memory tier profiling summary")
    parser.add_argument("prof", help="Path to .prof file")
    parser.add_argument("--top", type=int, default=10, help="Top N functions per tier")
    parser.add_argument("--trials", type=int, default=1, help="Number of trials to average over")
    args = parser.parse_args()
    analyze(args.prof, args.top, args.trials)


if __name__ == "__main__":
    main()
