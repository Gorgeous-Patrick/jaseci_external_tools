#!/usr/bin/env python3
"""
Analyze a jac server .prof file and report spawn_call / async_spawn_call
breakdown with walker entry/exit function execution counts and timing.

Usage:
    python spawn_profile.py <path/to/jac_server.prof>
    python spawn_profile.py <path/to/jac_server.prof> --top 20
"""

import pstats
import sys
import argparse
from collections import defaultdict

SPAWN_FUNCS = ("_execute_entries", "_visit_node_recursive")

INTERNAL_PREFIXES = (
    "jaclang/",
    "jaclang\\",
    "site-packages/",
    "<built-in>",
    "<string>",
)


def is_internal(filename: str) -> bool:
    return any(p in filename for p in INTERNAL_PREFIXES)


def short_loc(filename: str, lineno: int) -> str:
    part = filename.split("/")[-1] if "/" in filename else filename
    return f"{part}:{lineno}"


def format_ms(seconds: float) -> str:
    return f"{seconds * 1000:>10.3f} ms"


def format_us(seconds: float) -> str:
    return f"{seconds * 1_000_000:>10.1f} µs"


def build_callee_map(raw: dict) -> dict:
    callee_map: dict = defaultdict(list)
    for callee_key, (cc, nc, tt, ct, callers) in raw.items():
        for caller_key in callers:
            callee_map[caller_key].append(callee_key)
    return callee_map


def transitive_callees(
    seed_keys: list, callee_map: dict, max_depth: int = 6
) -> dict:
    visited: dict = {}
    frontier = [(k, 0) for k in seed_keys]
    while frontier:
        key, depth = frontier.pop(0)
        if key in visited or depth > max_depth:
            continue
        visited[key] = depth
        for child in callee_map.get(key, []):
            if child not in visited:
                frontier.append((child, depth + 1))
    return visited


def analyze(prof_path: str, top_n: int) -> None:
    stats = pstats.Stats(prof_path, stream=open("/dev/null", "w"))
    raw = stats.stats

    callee_map = build_callee_map(raw)

    spawn_keys = [k for k in raw if k[2] in SPAWN_FUNCS]

    print(f"\n{'='*70}")
    print(f"  Walker execution summary  —  {prof_path}")
    print(f"{'='*70}")
    print(f"  {'function':<25}  {'calls':>8}  {'total self':>12}  {'total cum':>12}  {'avg cum/call':>14}")
    print(f"  {'-'*68}")

    for key in sorted(spawn_keys, key=lambda k: k[2]):
        cc, nc, tt, ct = raw[key][:4]
        avg = ct / nc if nc else 0.0
        print(
            f"  {key[2]:<25}  {nc:>8}  {format_ms(tt)}  {format_ms(ct)}  {format_ms(avg)}"
        )
        print(f"    [{short_loc(key[0], key[1])}]")

    if not spawn_keys:
        print("  (no _execute_entries / _visit_node_recursive found in profile)")
        print(f"{'='*70}\n")
        return

    print(f"{'='*70}\n")

    reachable = transitive_callees(spawn_keys, callee_map, max_depth=10)

    internal_entries = []
    user_entries = []

    for key, depth in reachable.items():
        if key in spawn_keys:
            continue
        cc, nc, tt, ct, _ = raw[key]
        if is_internal(key[0]):
            internal_entries.append((nc, tt, ct, depth, key))
        else:
            user_entries.append((nc, tt, ct, depth, key))

    print(f"  Walker functions in spawn_call subtree (user-defined, top {top_n} by cum-time)")
    print(f"  {'calls':>8}  {'self-time':>12}  {'cum-time':>12}  {'avg cum/call':>14}  function  [location]")
    print(f"  {'-'*70}")
    user_entries.sort(key=lambda x: x[2], reverse=True)
    for nc, tt, ct, depth, key in user_entries[:top_n]:
        avg = ct / nc if nc else 0.0
        fname = key[2]
        loc = short_loc(key[0], key[1])
        print(
            f"  {nc:>8}  {format_ms(tt)}  {format_ms(ct)}  {format_ms(avg)}"
            f"  {fname}  [{loc}]"
        )
    if not user_entries:
        print("  (none found — walker functions may be in jaclang-compiled paths)")

    print()

    INTERESTING = {
        "_execute_entries", "_visit_node_recursive",
        "batch_load_nodes", "plan_query", "refs",
        "prefetch", "batch_get", "get_ttg_prefetch_list",
        "resolve_chain", "visit",
    }
    interesting_internal = [
        e for e in internal_entries if e[4][2] in INTERESTING
    ]
    interesting_internal.sort(key=lambda x: x[2], reverse=True)

    print(f"  Key jaclang functions in spawn_call subtree")
    print(f"  {'calls':>8}  {'self-time':>12}  {'cum-time':>12}  {'avg cum/call':>14}  function  [location]")
    print(f"  {'-'*70}")
    for nc, tt, ct, depth, key in interesting_internal:
        avg = ct / nc if nc else 0.0
        fname = key[2]
        loc = short_loc(key[0], key[1])
        print(
            f"  {nc:>8}  {format_ms(tt)}  {format_ms(ct)}  {format_ms(avg)}"
            f"  {fname}  [{loc}]"
        )

    print()

    print(f"  Top {top_n} jaclang internals in spawn_call subtree (by self-time)")
    print(f"  {'calls':>8}  {'self-time':>12}  {'cum-time':>12}  {'avg cum/call':>14}  function  [location]")
    print(f"  {'-'*70}")
    internal_entries.sort(key=lambda x: x[1], reverse=True)
    for nc, tt, ct, depth, key in internal_entries[:top_n]:
        avg = ct / nc if nc else 0.0
        fname = key[2]
        loc = short_loc(key[0], key[1])
        print(
            f"  {nc:>8}  {format_ms(tt)}  {format_ms(ct)}  {format_ms(avg)}"
            f"  {fname}  [{loc}]"
        )

    print(f"\n{'='*70}\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="spawn_call profiling breakdown")
    parser.add_argument("prof", help="Path to .prof file")
    parser.add_argument("--top", type=int, default=10, help="Top N functions per section")
    args = parser.parse_args()
    analyze(args.prof, args.top)


if __name__ == "__main__":
    main()
