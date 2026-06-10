#!/usr/bin/env python3
"""Visualize the prefetch pipeline as a timeline (waterfall) chart.

Each step starts where the previous one ends, showing the sequential
flow of time through prefetch execution.

Steps:
  1. TTG AST analysis
  2. TTG BFS (resolve_chain calls)
  3. MongoDB find_raw (bulk L3 fetch)
  4. Redis bulk_put_raw (L2 write)
  5. Deserialize + promote to L1

Usage:
    python plot_prefetch_timeline.py [path/to/jac_server.prof]
"""

import pstats
import sys

import matplotlib.pyplot as plt


def load_stats(prof_path):
    stats = pstats.Stats(prof_path, stream=open("/dev/null", "w"))
    result = {}
    callers = {}
    for (filename, lineno, funcname), (cc, nc, tt, ct, caller_dict) in stats.stats.items():
        if funcname not in result:
            result[funcname] = {"nc": 0, "tt": 0.0, "ct": 0.0}
            callers[funcname] = {}
        result[funcname]["nc"] += nc
        result[funcname]["tt"] += tt
        result[funcname]["ct"] += ct
        for (cf, cl, cfn), (ccc, cnc, ctt, cct) in caller_dict.items():
            if cfn not in callers[funcname]:
                callers[funcname][cfn] = {"nc": 0, "ct": 0.0}
            callers[funcname][cfn]["nc"] += cnc
            callers[funcname][cfn]["ct"] += cct
    return result, callers


def ct(s, fn):
    return s.get(fn, {"ct": 0})["ct"] * 1000


def tt(s, fn):
    return s.get(fn, {"tt": 0})["tt"] * 1000


def nc(s, fn):
    return s.get(fn, {"nc": 0})["nc"]


def caller_ct(cal, fn, caller):
    return cal.get(fn, {}).get(caller, {"ct": 0})["ct"] * 1000


def main():
    prof_path = sys.argv[1] if len(sys.argv) > 1 else "profiles/limit_5000/load_feed/trial_1/jac_server.prof"
    s, cal = load_stats(prof_path)

    # mem.prefetch() — includes both main prefetch and TTG foreign root prefetch.
    # ScaleTieredMemory.prefetch may appear twice in yappi (nc=2), so use
    # total cumulative time.
    total_prefetch = ct(s, "ScaleTieredMemory.prefetch") or ct(s, "TieredMemory.prefetch")

    # Breakdown uses actual yappi function names.
    # These are global cumulative times (both prefetch calls), but
    # find_raw and bulk_put_raw are only called from prefetch, so safe.
    find_raw_ms = ct(s, "MongoBackend.find_raw")
    bulk_put_raw_ms = ct(s, "RedisBackend.bulk_put_raw")
    # Deserialize: only count calls from the prefetch path
    prefetch_deser_ms = caller_ct(cal, "deserialize", "ScaleTieredMemory.prefetch")

    # Build timeline
    steps = [
        ("MongoDB\nfind_raw", find_raw_ms, "#4e79a7"),
        ("Redis\nbulk_put_raw", bulk_put_raw_ms, "#f28e2b"),
        ("Deserialize\n(to L1)", prefetch_deser_ms, "#59a14f"),
    ]

    total_prefetch = sum(w for _, w, _ in steps)

    # Filter out zero-width steps
    steps = [(l, w, c) for l, w, c in steps if w > 0.01]

    if not steps:
        print(f"No prefetch data found in {prof_path}")
        return

    # Draw waterfall
    fig, ax = plt.subplots(figsize=(16, 5))

    bar_y = 2.0
    offset = 0.0
    small_labels = []
    for label, width, color in steps:
        ax.barh(bar_y, width, left=offset, height=0.6, color=color, edgecolor="white", linewidth=0.5)
        if width > total_prefetch * 0.06:
            ax.text(
                offset + width / 2, bar_y,
                f"{label}\n{width:.0f}ms",
                ha="center", va="center", fontsize=8, fontweight="bold",
            )
        else:
            small_labels.append((offset, width, label, color))
        offset += width

    for i, (x, w, label, color) in enumerate(small_labels):
        mid = x + w / 2
        y_text = 0.8 - (i % 3) * 0.7
        ax.annotate(
            f"{label} ({w:.0f}ms)",
            xy=(mid, bar_y - 0.3), xytext=(mid, y_text),
            ha="center", va="top", fontsize=7,
            arrowprops=dict(arrowstyle="-", color=color, lw=0.8),
        )

    ax.set_ylim(-1.5, bar_y + 0.8)
    ax.set_xlim(0, offset * 1.02)
    ax.set_yticks([])
    ax.set_xlabel("Time (ms)")
    ax.set_title(
        f"Prefetch Pipeline Timeline ({total_prefetch:.0f}ms total)",
        fontsize=11, fontweight="bold",
    )
    ax.grid(axis="x", alpha=0.3)

    plt.tight_layout()

    out = prof_path.rsplit("/", 1)[0] + "/prefetch_timeline.png" if "/" in prof_path else "prefetch_timeline.png"
    plt.savefig(out, dpi=200, bbox_inches="tight")
    print(f"Saved to {out}")
    plt.close()


if __name__ == "__main__":
    main()
