#!/usr/bin/env python3
"""Visualize the prefetch pipeline as a timeline (waterfall) chart.

Each step starts where the previous one ends, showing the sequential
flow of time through the prefetch pipeline.

Steps:
  1. MongoDB find_raw
  2. Redis (bulk_exists + bulk_put_raw)
  3. Deserialize + _compute_hash
  4. Promote to L1
  5. Snapshot field hashes

Usage:
    python plot_prefetch_timeline.py [path/to/jac_server.prof]
"""

import pstats
import sys

import matplotlib.pyplot as plt


def load_stats(prof_path):
    stats = pstats.Stats(prof_path, stream=open("/dev/null", "w"))
    result = {}
    for (filename, lineno, funcname), (cc, nc, tt, ct, caller_dict) in stats.stats.items():
        # For ScaleTieredMemory.prefetch, keep only the override (main.impl)
        # not the super call (memory.impl) — the super is already inside it.
        if funcname == "ScaleTieredMemory.prefetch" and "memory.impl" in filename:
            continue
        if funcname not in result:
            result[funcname] = {"nc": 0, "tt": 0.0, "ct": 0.0}
        result[funcname]["nc"] += nc
        result[funcname]["tt"] += tt
        result[funcname]["ct"] += ct
    return result


def ct(s, fn):
    return s.get(fn, {"ct": 0})["ct"] * 1000


def nc(s, fn):
    return s.get(fn, {"nc": 0})["nc"]


def main():
    prof_path = sys.argv[1] if len(sys.argv) > 1 else "profiles/limit_1000/trial_9/jac_server.prof"
    s = load_stats(prof_path)

    total_prefetch = ct(s, "ScaleTieredMemory.prefetch") or ct(s, "prefetch")
    n_snapshot = nc(s, "_snapshot_field_hashes")
    n_deser = nc(s, "deserialize")

    # Step 1: MongoDB find_raw
    mongo_ms = ct(s, "MongoBackend.find_raw") or ct(s, "find_raw")

    # Step 2: Redis bulk_put_raw (MSET)
    redis_ms = ct(s, "RedisBackend.bulk_put_raw") or ct(s, "bulk_put_raw") or ct(s, "bulk_exists")

    # Step 3: Deserialize + _compute_hash
    # Approximate prefetch's share of deserialize by snapshot count
    deser_total = ct(s, "deserialize")
    if n_deser > 0 and n_snapshot > 0:
        deser_ms = deser_total * (n_snapshot / n_deser)
    else:
        deser_ms = deser_total

    # Step 4: Snapshot field hashes
    snapshot_ms = ct(s, "_snapshot_field_hashes")

    # Build timeline
    steps = [
        ("MongoDB\nfind_raw", mongo_ms, "#4e79a7"),
        ("Redis\nMSET", redis_ms, "#f28e2b"),
        ("Deserialize", deser_ms, "#59a14f"),
        ("Snapshot\nfield hashes", snapshot_ms, "#e15759"),
    ]

    accounted = sum(w for _, w, _ in steps)
    other = max(0, total_prefetch - accounted)
    if other > 1:
        steps.append(("Other", other, "#bab0ac"))

    # Filter out zero-width steps
    steps = [(l, w, c) for l, w, c in steps if w > 0.01]

    # Draw waterfall
    fig, ax = plt.subplots(figsize=(16, 3))

    offset = 0.0
    for label, width, color in steps:
        ax.barh(0, width, left=offset, height=0.5, color=color, edgecolor="white", linewidth=0.5)
        if width > total_prefetch * 0.03:
            ax.text(
                offset + width / 2, 0,
                f"{label}\n{width:.0f}ms",
                ha="center", va="center", fontsize=8, fontweight="bold",
            )
        else:
            ax.text(
                offset + width / 2, -0.35,
                f"{label}\n{width:.0f}ms",
                ha="center", va="top", fontsize=7,
            )
        offset += width

    ax.set_xlim(0, offset * 1.02)
    ax.set_yticks([])
    ax.set_xlabel("Time (ms)")
    ax.set_title(
        f"Prefetch Pipeline Timeline ({total_prefetch:.0f}ms total, {n_snapshot} anchors)",
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
