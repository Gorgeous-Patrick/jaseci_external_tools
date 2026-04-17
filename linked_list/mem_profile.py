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


def analyze(prof_path: str, top_n: int, trials: int) -> None:
    stats = pstats.Stats(prof_path, stream=open("/dev/null", "w"))
    raw = stats.stats

    # Use self-time (tottime) for the tier summary — avoids double-counting
    # callee time that would inflate cumtime across the call stack.
    total_tottime = sum(entry[2] for entry in raw.values()) / trials

    tier_tottime: dict[str, float] = defaultdict(float)
    tier_funcs: dict[str, list] = defaultdict(list)

    for (filename, lineno, funcname), (cc, nc, tt, ct, _callers) in raw.items():
        tier = classify(filename)
        tier_tottime[tier] += tt / trials
        # Per-function table shows cumtime (useful) alongside self-time
        tier_funcs[tier].append((ct / trials, tt / trials, nc, funcname, filename, lineno))

    print(f"\n{'='*65}")
    print(f"  Memory tier breakdown  —  {prof_path}")
    print(f"  averaged over {trials} trials (per-request)")
    print(f"{'='*65}")
    print(f"{'Tier':<22}  {'Avg self-time/req':>17}  {'% of profiled':>13}")
    print(f"{'-'*65}")

    ordered_tiers = ["L2 Redis", "L3 MongoDB", "coordination", "other"]
    for tier in ordered_tiers:
        tt = tier_tottime.get(tier, 0.0)
        pct = (tt / total_tottime * 100) if total_tottime > 0 else 0.0
        label = tier if tier != "coordination" else "L1 + coordination"
        print(f"  {label:<20}  {format_ms(tt)}  {pct:>12.1f}%")

    print(f"{'-'*65}")
    print(f"  {'Total profiled':<20}  {format_ms(total_tottime)}")
    print(f"{'='*65}\n")

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
    parser.add_argument("--trials", type=int, default=10, help="Number of trials to average over")
    args = parser.parse_args()
    analyze(args.prof, args.top, args.trials)


if __name__ == "__main__":
    main()
