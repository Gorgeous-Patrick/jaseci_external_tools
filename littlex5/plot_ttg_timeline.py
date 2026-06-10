#!/usr/bin/env python3
"""Visualize TTG generation as a timeline (waterfall) chart.

Steps:
  1. AST analysis (_extract_visits_from_ast)
  2. Foreign root prefetch (mem.prefetch for cross-root roots)
  3. BFS resolve_chain calls (the remaining time in get_ttg_prefetch_list)

Usage:
    python plot_ttg_timeline.py [path/to/jac_server.prof]
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
    prof_path = sys.argv[1] if len(sys.argv) > 1 else "profiles/limit_20000/load_feed/trial_1/jac_server.prof"
    s, cal = load_stats(prof_path)

    total_ttg = ct(s, "get_ttg_prefetch_list")

    # Step 1: AST analysis (extract visit types from walker)
    ast_ms = ct(s, "_extract_visits_from_ast")

    # Step 2: Foreign root prefetch (mem.prefetch called from TTG)
    foreign_prefetch_ms = caller_ct(cal, "ScaleTieredMemory.prefetch", "get_ttg_prefetch_list") \
        or caller_ct(cal, "TieredMemory.prefetch", "get_ttg_prefetch_list") \
        or caller_ct(cal, "prefetch", "get_ttg_prefetch_list")

    # Step 3: resolve_chain_cross_root (called from TTG BFS)
    ttg_resolve_ms = ct(s, "TopologyIndex.resolve_chain_cross_root")
    # Cap at what's left after ast + foreign prefetch
    ttg_resolve_ms = min(ttg_resolve_ms, max(0, total_ttg - ast_ms - foreign_prefetch_ms))

    # Build timeline
    steps = [
        ("AST analysis\n(extract visits)", ast_ms, "#b07aa1"),
        ("Foreign root\nprefetch", foreign_prefetch_ms, "#4e79a7"),
        ("BFS resolve\n(cross-root)", ttg_resolve_ms, "#f28e2b"),
    ]

    accounted = sum(w for _, w, _ in steps)
    other = max(0, total_ttg - accounted)
    if other > total_ttg * 0.02:
        steps.append(("Other", other, "#bab0ac"))

    # Filter out zero-width steps
    steps = [(l, w, c) for l, w, c in steps if w > 0.01]

    if not steps:
        print(f"No TTG data found in {prof_path}")
        return

    total_display = sum(w for _, w, _ in steps)
    n_resolve = nc(s, "resolve_chain") + nc(s, "resolve_chain_cross_root")

    # Draw waterfall
    fig, ax = plt.subplots(figsize=(16, 5))

    bar_y = 2.0
    offset = 0.0
    small_labels = []
    for label, width, color in steps:
        ax.barh(bar_y, width, left=offset, height=0.6, color=color, edgecolor="white", linewidth=0.5)
        if width > total_display * 0.06:
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
        f"TTG Generation Timeline ({total_ttg:.0f}ms total, {n_resolve} resolve calls)",
        fontsize=11, fontweight="bold",
    )
    ax.grid(axis="x", alpha=0.3)

    plt.tight_layout()

    out = prof_path.rsplit("/", 1)[0] + "/ttg_timeline.png" if "/" in prof_path else "ttg_timeline.png"
    plt.savefig(out, dpi=200, bbox_inches="tight")
    print(f"Saved to {out}")
    plt.close()


if __name__ == "__main__":
    main()
