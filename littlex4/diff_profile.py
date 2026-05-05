#!/usr/bin/env python3
"""
Compare two .prof files and show where performance differences come from.

Usage:
    python diff_profile.py <baseline.prof> <compare.prof>
    python diff_profile.py <baseline.prof> <compare.prof> --trials 10
"""

import pstats
import argparse
from collections import defaultdict


# ---------------------------------------------------------------------------
# Top-level functions called sequentially from _jac_walker_execute.
# Their cumtimes are additive (not nested), so deltas sum to the total delta.
# ---------------------------------------------------------------------------
TOP_LEVEL = [
    "get_ttg_prefetch_list",
    "ScaleTieredMemory.prefetch",
    "batch_load_nodes",
]

# ---------------------------------------------------------------------------
# L3 MongoDB entry-point functions — each call = one round-trip.
# ---------------------------------------------------------------------------
L3_REQUEST_FUNCS = [
    "MongoBackend.batch_get",
    "MongoBackend.find_raw",
    "MongoBackend.get",
    "MongoBackend.put",
    "MongoBackend.delete",
]

# ---------------------------------------------------------------------------
# Detailed functions to show in the per-tier breakdown table.
# ---------------------------------------------------------------------------
TRACKED = [
    # (funcname,                       label,                          tier)
    ("_jac_walker_execute",            "Total request",                "total"),
    ("get_ttg_prefetch_list",          "TTG: build prefetch list",     "ttg"),
    ("ScaleTieredMemory.prefetch",     "TTG: prefetch (L3→L2)",        "ttg"),
    ("RedisBackend.bulk_exists",       "  prefetch: bulk_exists (L2)", "ttg"),
    ("MongoBackend.find_raw",          "  prefetch: find_raw (L3)",    "ttg"),
    ("RedisBackend.bulk_put_raw",      "  prefetch: bulk_put_raw (L2)","ttg"),
    ("batch_load_nodes",               "batch_load_nodes",             "coordination"),
    ("ScaleTieredMemory.batch_get",    "  ScaleTieredMemory.batch_get","coordination"),
    ("plan_query",                     "  plan_query",                 "coordination"),
    ("RedisBackend.batch_get",         "  L2: RedisBackend.batch_get", "l2"),
    ("RedisBackend.put",               "  L2: RedisBackend.put",       "l2"),
    ("MongoBackend.batch_get",         "  L3: MongoBackend.batch_get", "l3"),
    ("MongoBackend.find_raw",          "  L3: MongoBackend.find_raw",  "l3"),
    ("MongoBackend.get",               "  L3: MongoBackend.get",       "l3"),
]


def load_stats(prof_path: str) -> dict:
    stats = pstats.Stats(prof_path, stream=open("/dev/null", "w"))
    result: dict = defaultdict(lambda: {"nc": 0, "tt": 0.0, "ct": 0.0})
    for (filename, lineno, funcname), (cc, nc, tt, ct, callers) in stats.stats.items():
        result[funcname]["nc"] += nc
        result[funcname]["tt"] += tt
        result[funcname]["ct"] += ct
    return dict(result)


def ct(stats: dict, funcname: str, trials: int) -> float:
    return stats.get(funcname, {}).get("ct", 0.0) / trials


def nc(stats: dict, funcname: str, trials: int) -> float:
    return stats.get(funcname, {}).get("nc", 0) / trials


def fmt(s: float) -> str:
    return f"{s * 1000:>10.3f} ms"


def fmt_delta(s: float) -> str:
    ms = s * 1000
    sign = "+" if ms > 0 else ""
    return f"{sign}{ms:>10.3f} ms"


def fmt_pct(delta: float, base: float) -> str:
    if base == 0:
        return "(new)" if delta > 0 else ""
    pct = delta / base * 100
    sign = "+" if pct > 0 else ""
    return f"({sign}{pct:.1f}%)"


def analyze(baseline_path: str, compare_path: str, trials: int) -> None:
    B = load_stats(baseline_path)
    C = load_stats(compare_path)

    def b(fn): return ct(B, fn, trials)
    def c(fn): return ct(C, fn, trials)
    def d(fn): return c(fn) - b(fn)

    total_b = b("_jac_walker_execute")
    total_c = c("_jac_walker_execute")
    total_delta = total_c - total_b

    W = 88
    print(f"\n{'='*W}")
    print(f"  Profile diff")
    print(f"  baseline : {baseline_path}")
    print(f"  compare  : {compare_path}")
    print(f"  trials   : {trials}")
    print(f"{'='*W}")

    # -----------------------------------------------------------------------
    # Detailed comparison table
    # -----------------------------------------------------------------------
    print(f"  {'Function':<42}  {'baseline':>12}  {'compare':>12}  {'delta':>13}  {'':>8}")
    print(f"  {'-'*W}")

    prev_tier = None
    for funcname, label, tier in TRACKED:
        bv, cv = b(funcname), c(funcname)
        if bv == 0.0 and cv == 0.0:
            continue
        if tier != prev_tier:
            print()
            prev_tier = tier
        dv = cv - bv
        print(f"  {label:<42}  {fmt(bv)}  {fmt(cv)}  {fmt_delta(dv)}  {fmt_pct(dv, bv):>8}")

    # -----------------------------------------------------------------------
    # L3 request counts
    # -----------------------------------------------------------------------
    print(f"\n  L3 MongoDB requests (avg per request):\n")
    print(f"  {'Function':<42}  {'baseline':>10}  {'compare':>10}  {'delta':>10}")
    print(f"  {'-'*60}")
    for fn in L3_REQUEST_FUNCS:
        bn = nc(B, fn, trials)
        cn = nc(C, fn, trials)
        if bn == 0.0 and cn == 0.0:
            continue
        dn = cn - bn
        sign = "+" if dn > 0 else ""
        print(f"  {fn:<42}  {bn:>10.1f}  {cn:>10.1f}  {sign}{dn:>9.1f}")
    total_bn = sum(nc(B, fn, trials) for fn in L3_REQUEST_FUNCS)
    total_cn = sum(nc(C, fn, trials) for fn in L3_REQUEST_FUNCS)
    total_dn = total_cn - total_bn
    sign = "+" if total_dn > 0 else ""
    print(f"  {'-'*60}")
    print(f"  {'TOTAL L3 requests':<42}  {total_bn:>10.1f}  {total_cn:>10.1f}  {sign}{total_dn:>9.1f}")

    print(f"\n  {'-'*W}")

    # -----------------------------------------------------------------------
    # Breakdown: top-level contributions that sum to total delta
    # -----------------------------------------------------------------------
    # batch_load_nodes, get_ttg_prefetch_list, and ScaleTieredMemory.prefetch
    # are called sequentially from _jac_walker_execute (not nested in each other),
    # so their cumtime deltas are additive.
    # -----------------------------------------------------------------------
    print(f"\n  Breakdown of {fmt_delta(total_delta).strip()}  (avg per request):\n")

    accounted = 0.0
    rows = []
    for fn in TOP_LEVEL:
        dv = d(fn)
        if b(fn) == 0.0 and c(fn) == 0.0:
            continue
        accounted += dv
        rows.append((fn, b(fn), c(fn), dv))

    other_delta = total_delta - accounted

    for fn, bv, cv, dv in rows:
        marker = "saved" if dv < 0 else "cost"
        print(f"  {fn:<42}  {fmt_delta(dv).strip():>14}  [{marker}]")

    print(f"  {'other (walker logic, etc.)':<42}  {fmt_delta(other_delta).strip():>14}")
    print(f"  {'-'*60}")
    print(f"  {'NET':<42}  {fmt_delta(total_delta).strip():>14}  {fmt_pct(total_delta, total_b):>8}")
    print(f"  {'  baseline: _jac_walker_execute':<42}  {fmt(total_b).strip():>14}")
    print(f"  {'  compare:  _jac_walker_execute':<42}  {fmt(total_c).strip():>14}")
    print(f"\n{'='*W}\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare two .prof files")
    parser.add_argument("baseline", help="Baseline .prof file")
    parser.add_argument("compare", help="Comparison .prof file")
    parser.add_argument("--trials", type=int, default=10, help="Number of trials (default: 10)")
    args = parser.parse_args()
    analyze(args.baseline, args.compare, args.trials)


if __name__ == "__main__":
    main()
