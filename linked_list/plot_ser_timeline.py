#!/usr/bin/env python3
"""Visualize serialize/deserialize timeline per anchor from profiling data."""

import pstats
import sys

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np


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


def main():
    prof_path = sys.argv[1] if len(sys.argv) > 1 else "profiles/limit_0/trial_1/jac_server.prof"
    s, cal = load_stats(prof_path)

    n_anchors = s["deserialize"]["nc"]

    # Per-anchor times (ms)
    def ct(fn):
        return s.get(fn, {"ct": 0})["ct"] * 1000 / n_anchors

    def tt(fn):
        return s.get(fn, {"tt": 0})["tt"] * 1000 / n_anchors

    def caller_ct(fn, caller):
        return cal.get(fn, {}).get(caller, {"ct": 0})["ct"] * 1000 / n_anchors

    # Deserialize breakdown
    total_deser = ct("deserialize")
    compute_hash = ct("_compute_hash")
    hash_serialize = caller_ct("serialize", "_compute_hash")
    hash_json = compute_hash - hash_serialize
    uuid_creation = ct("UUID.__init__") * 2 / (s["UUID.__init__"]["nc"] / n_anchors)  # approximate
    deser_permission = ct("_deserialize_permission")
    deser_archetype = ct("_deserialize_archetype")
    id_to_stub = ct("_id_to_stub")
    deser_anchor_self = tt("_deserialize_anchor")
    deser_other = total_deser - compute_hash - deser_permission - deser_archetype - id_to_stub - deser_anchor_self

    # Serialize breakdown (for Redis write path)
    ser_for_redis = caller_ct("serialize", "RedisBackend.bulk_put")
    ser_value_tt = tt("_serialize_value")
    ser_attrs_tt = tt("_serialize_attrs")

    # Build waterfall data for deserialize
    deser_steps = [
        ("UUID creation", uuid_creation if uuid_creation > 0 else deser_other, "#4e79a7"),
        ("_deserialize_permission", deser_permission, "#59a14f"),
        ("_deserialize_archetype", deser_archetype, "#76b7b2"),
        ("_id_to_stub (edges)", id_to_stub, "#edc948"),
        ("_anchor self work", deser_anchor_self, "#b07aa1"),
        ("_compute_hash:\n  serialize", hash_serialize, "#e15759"),
        ("_compute_hash:\n  json.dumps+hash", hash_json, "#ff9d9a"),
    ]

    fig, axes = plt.subplots(1, 2, figsize=(14, 6))

    # --- Deserialize waterfall ---
    ax = axes[0]
    y_pos = 0
    starts = []
    widths = []
    colors = []
    labels = []
    offset = 0.0

    for label, width, color in deser_steps:
        starts.append(offset)
        widths.append(width)
        colors.append(color)
        labels.append(label)
        offset += width

    y_positions = range(len(deser_steps))
    bars = ax.barh(y_positions, widths, left=starts, color=colors, height=0.6, edgecolor="white")

    ax.set_yticks(list(y_positions))
    ax.set_yticklabels(labels, fontsize=9)
    ax.invert_yaxis()
    ax.set_xlabel("Time (ms)")
    ax.set_title(f"Deserialize 1 anchor ({total_deser:.3f}ms total)")

    # Add time labels on bars
    for bar, w in zip(bars, widths):
        if w > 0.003:
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_y() + bar.get_height() / 2,
                f"{w:.3f}",
                ha="center", va="center", fontsize=8, fontweight="bold",
            )

    # Add percentage annotation
    hash_total = hash_serialize + hash_json
    ax.axvline(x=total_deser - hash_total, color="red", linestyle="--", alpha=0.5)
    ax.text(
        total_deser - hash_total + 0.001, len(deser_steps) - 0.5,
        f"← _compute_hash: {hash_total / total_deser * 100:.0f}% of total",
        fontsize=8, color="red",
    )

    # --- Stacked bar: overall comparison ---
    ax2 = axes[1]

    actual_deser = total_deser - compute_hash
    categories = {
        "deserialize\n(per anchor)": [
            ("Actual deserialization", actual_deser, "#4e79a7"),
            ("_compute_hash\n(re-serialize+json+hash)", compute_hash, "#e15759"),
        ],
        "serialize\n(for Redis, per anchor)": [
            ("_serialize_value", ser_for_redis, "#f28e2b"),
        ],
        "serialize\n(for hash, per anchor)": [
            ("_serialize_value (inside hash)", hash_serialize, "#e15759"),
        ],
    }

    x_pos = 0
    x_ticks = []
    x_labels = []
    for cat_label, parts in categories.items():
        bottom = 0
        for part_label, val, color in parts:
            bar = ax2.bar(x_pos, val, bottom=bottom, color=color, width=0.5, edgecolor="white")
            if val > 0.005:
                ax2.text(
                    x_pos, bottom + val / 2,
                    f"{val:.3f}ms",
                    ha="center", va="center", fontsize=8, fontweight="bold",
                )
            bottom += val
        ax2.text(x_pos, bottom + 0.002, f"{bottom:.3f}ms", ha="center", fontsize=9, fontweight="bold")
        x_ticks.append(x_pos)
        x_labels.append(cat_label)
        x_pos += 1

    ax2.set_xticks(x_ticks)
    ax2.set_xticklabels(x_labels, fontsize=9)
    ax2.set_ylabel("Time (ms)")
    ax2.set_title("Per-anchor cost breakdown")

    # Legend
    legend_patches = [
        mpatches.Patch(color="#4e79a7", label="Actual deser work"),
        mpatches.Patch(color="#e15759", label="_compute_hash (redundant serialize)"),
        mpatches.Patch(color="#f28e2b", label="Serialize for Redis"),
    ]
    ax2.legend(handles=legend_patches, fontsize=8, loc="upper right")

    plt.tight_layout()
    out = "ser_deser_timeline.png"
    plt.savefig(out, dpi=300, bbox_inches="tight")
    print(f"Saved to {out}")
    plt.close()


if __name__ == "__main__":
    main()
