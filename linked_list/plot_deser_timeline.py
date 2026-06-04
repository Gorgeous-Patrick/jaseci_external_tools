#!/usr/bin/env python3
"""Visualize the deserialization pipeline as a timeline (waterfall) chart.

Each step starts where the previous one ends, showing the sequential
flow of time through deserializing all anchors during prefetch.

Usage:
    python plot_deser_timeline.py [path/to/jac_server.prof]
"""

import pstats
import sys

import matplotlib.pyplot as plt


def load_stats(prof_path):
    stats = pstats.Stats(prof_path, stream=open("/dev/null", "w"))
    result = {}
    for (filename, lineno, funcname), (cc, nc, tt, ct, caller_dict) in stats.stats.items():
        if funcname not in result:
            result[funcname] = {"nc": 0, "tt": 0.0, "ct": 0.0}
        result[funcname]["nc"] += nc
        result[funcname]["tt"] += tt
        result[funcname]["ct"] += ct
    return result


def ct(s, fn):
    return s.get(fn, {"ct": 0})["ct"] * 1000


def tt(s, fn):
    return s.get(fn, {"tt": 0})["tt"] * 1000


def nc(s, fn):
    return s.get(fn, {"nc": 0})["nc"]


def main():
    prof_path = sys.argv[1] if len(sys.argv) > 1 else "profiles/limit_1000/trial_9/jac_server.prof"
    s = load_stats(prof_path)

    total_deser = ct(s, "deserialize")
    n_deser = nc(s, "deserialize")

    # _compute_hash: 999 of N calls are from deserialize (1 per anchor)
    compute_hash_total = ct(s, "_compute_hash")
    n_hash = nc(s, "_compute_hash")
    if n_hash > 0 and n_deser > 0:
        hash_in_deser = compute_hash_total * (n_deser / n_hash)
    else:
        hash_in_deser = compute_hash_total

    # UUID construction (self-time)
    uuid_ms = tt(s, "UUID.__init__")

    # Permission deserialization
    permission_ms = ct(s, "_deserialize_permission")

    # _id_to_stub (edge stubs)
    stub_ms = ct(s, "_id_to_stub")

    # Archetype reconstruction (self-time only, excluding get_type_hints)
    arch_self = tt(s, "_deserialize_archetype")

    # Anchor-level self-time
    anchor_self = tt(s, "_deserialize_anchor")

    # get_type_hints: compute by subtraction to avoid double-counting
    non_typing = hash_in_deser + uuid_ms + permission_ms + stub_ms + arch_self + anchor_self
    typing_in_deser = max(0, total_deser - non_typing)

    # Build timeline
    steps = [
        ("get_type_hints\n(typing reflection)", typing_in_deser, "#b07aa1"),
        ("_compute_hash\n(re-serialize+hash)", hash_in_deser, "#e15759"),
        ("UUID\nconstruction", uuid_ms, "#f28e2b"),
        ("Permission\ndeserialize", permission_ms, "#76b7b2"),
        ("Edge stub\ncreation", stub_ms, "#edc948"),
        ("Archetype\nreconstruction", arch_self, "#59a14f"),
        ("Anchor\nsetup", anchor_self, "#4e79a7"),
    ]

    accounted = sum(w for _, w, _ in steps)
    other = max(0, total_deser - accounted)
    if other > 1:
        steps.append(("Other", other, "#bab0ac"))

    # Filter out zero-width steps
    steps = [(l, w, c) for l, w, c in steps if w > 0.01]

    # Draw waterfall
    fig, ax = plt.subplots(figsize=(16, 5))

    bar_y = 2.0
    offset = 0.0
    small_labels = []
    for label, width, color in steps:
        ax.barh(bar_y, width, left=offset, height=0.6, color=color, edgecolor="white", linewidth=0.5)
        if width > total_deser * 0.06:
            ax.text(
                offset + width / 2, bar_y,
                f"{label}\n{width:.0f}ms",
                ha="center", va="center", fontsize=8, fontweight="bold",
            )
        else:
            small_labels.append((offset, width, label, color))
        offset += width

    # Stagger small labels below the bar at different y levels
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
        f"Deserialization Breakdown ({total_deser:.0f}ms total, {n_deser} anchors)",
        fontsize=11, fontweight="bold",
    )
    ax.grid(axis="x", alpha=0.3)

    plt.tight_layout()

    out = prof_path.rsplit("/", 1)[0] + "/deser_timeline.png" if "/" in prof_path else "deser_timeline.png"
    plt.savefig(out, dpi=200, bbox_inches="tight")
    print(f"Saved to {out}")
    plt.close()


if __name__ == "__main__":
    main()
