#!/usr/bin/env python3
"""Plot cache hit rate from access_log.csv files across prefetch limits.

Expects the sweep to produce access logs at:
  profiles/limit_{N}/{walker}/trial_{i}/access_log.csv

Each CSV has columns: id,tier,type

Usage:
    python plot_hit_rate.py [profiles_dir]
"""

import csv
import os
import sys
from collections import Counter, defaultdict

import matplotlib.pyplot as plt
import numpy as np


def load_access_log(path):
    """Load access log and return list of (id, tier, type) tuples."""
    with open(path) as f:
        return [(r["id"], r["tier"], r["type"]) for r in csv.DictReader(f)]


def main():
    profiles_dir = sys.argv[1] if len(sys.argv) > 1 else "profiles"

    limit_dirs = sorted(
        [d for d in os.listdir(profiles_dir) if d.startswith("limit_")],
        key=lambda d: int(d.split("_")[1]),
    )
    if not limit_dirs:
        print(f"No limit_* directories found in {profiles_dir}")
        return

    # Collect data: {walker: {limit: [{tier_counts}, ...]}}
    data = defaultdict(lambda: defaultdict(list))

    for limit_dir in limit_dirs:
        limit = int(limit_dir.split("_")[1])
        limit_path = os.path.join(profiles_dir, limit_dir)

        for walker in sorted(os.listdir(limit_path)):
            walker_path = os.path.join(limit_path, walker)
            if not os.path.isdir(walker_path):
                continue

            for trial_dir in sorted(os.listdir(walker_path)):
                log_path = os.path.join(walker_path, trial_dir, "access_log.csv")
                if not os.path.exists(log_path):
                    continue

                try:
                    rows = load_access_log(log_path)
                except Exception:
                    continue

                tier_counts = Counter(r[1] for r in rows)
                type_tier = Counter((r[2], r[1]) for r in rows)
                data[walker][limit].append({
                    "tier_counts": tier_counts,
                    "type_tier": type_tier,
                    "total": len(rows),
                })

    walkers = sorted(data.keys())
    if not walkers:
        print("No access log data found")
        return

    fig, axes = plt.subplots(2, len(walkers), figsize=(8 * len(walkers), 10))
    if len(walkers) == 1:
        axes = axes.reshape(2, 1)

    for col, walker in enumerate(walkers):
        limits = sorted(data[walker].keys())
        x = np.arange(len(limits))

        # Top row: hit rate by tier
        ax1 = axes[0, col]
        l1_rates = []
        l2_rates = []
        l3_rates = []
        for lim in limits:
            trials = data[walker][lim]
            rates = []
            for t in trials:
                total = t["total"]
                if total > 0:
                    l1 = t["tier_counts"].get("L1", 0)
                    rates.append(l1 / total * 100)
            l1_rates.append(np.mean(rates) if rates else 0)

            rates_l2 = []
            for t in trials:
                total = t["total"]
                if total > 0:
                    l2 = t["tier_counts"].get("L2", 0)
                    rates_l2.append(l2 / total * 100)
            l2_rates.append(np.mean(rates_l2) if rates_l2 else 0)

            rates_l3 = []
            for t in trials:
                total = t["total"]
                if total > 0:
                    l3 = t["tier_counts"].get("L3", 0)
                    rates_l3.append(l3 / total * 100)
            l3_rates.append(np.mean(rates_l3) if rates_l3 else 0)

        width = 0.6
        ax1.bar(x, l1_rates, width, label="L1 (memory)", color="#59a14f")
        ax1.bar(x, l2_rates, width, bottom=l1_rates, label="L2 (Redis)", color="#f28e2b")
        ax1.bar(x, l3_rates, width,
                bottom=[a + b for a, b in zip(l1_rates, l2_rates)],
                label="L3 (MongoDB)", color="#e15759")
        ax1.set_xticks(x)
        ax1.set_xticklabels([str(lim) for lim in limits])
        ax1.set_xlabel("Prefetch Limit")
        ax1.set_ylabel("% of accesses")
        ax1.set_title(f"{walker}")
        ax1.set_ylim(0, 105)
        ax1.legend(loc="lower right", fontsize=8)
        ax1.grid(axis="y", alpha=0.3)

        for i, (r1, r3) in enumerate(zip(l1_rates, l3_rates)):
            ax1.text(i, 101, f"L1={r1:.0f}%", ha="center", va="bottom", fontsize=8, color="#59a14f")

        # Bottom row: L3 misses by type
        ax2 = axes[1, col]
        # Collect all types across limits
        all_types = set()
        for lim in limits:
            for t in data[walker][lim]:
                for (tp, tier), cnt in t["type_tier"].items():
                    if tier == "L3":
                        all_types.add(tp)
        all_types = sorted(all_types)
        type_colors = {
            "Root": "#4e79a7", "Profile": "#f28e2b", "Tweet": "#59a14f",
            "Post": "#e15759", "Follow": "#76b7b2", "GenericEdge": "#9c755f",
            "Channel": "#b07aa1",
        }

        bottom = np.zeros(len(limits))
        for tp in all_types:
            counts = []
            for lim in limits:
                trials = data[walker][lim]
                trial_counts = [
                    t["type_tier"].get((tp, "L3"), 0) for t in trials
                ]
                counts.append(np.mean(trial_counts) if trial_counts else 0)
            color = type_colors.get(tp, "#bab0ac")
            ax2.bar(x, counts, width, bottom=bottom, label=tp, color=color)
            bottom += np.array(counts)

        ax2.set_xticks(x)
        ax2.set_xticklabels([str(lim) for lim in limits])
        ax2.set_xlabel("Prefetch Limit")
        ax2.set_ylabel("L3 fetches (count)")
        ax2.set_title(f"{walker} — L3 misses by type")
        ax2.legend(loc="upper right", fontsize=8)
        ax2.grid(axis="y", alpha=0.3)

        for i, total in enumerate(bottom):
            if total > 0:
                ax2.text(i, total + max(bottom) * 0.02, f"{total:.0f}",
                         ha="center", va="bottom", fontsize=8, fontweight="bold")

    fig.suptitle("Cache Hit Rate & L3 Misses vs Prefetch Limit\n(from access_log.csv)",
                 fontsize=13, fontweight="bold")
    plt.tight_layout()

    output_file = "hit_rate.png"
    plt.savefig(output_file, dpi=150)
    print(f"Saved plot to {output_file}")


if __name__ == "__main__":
    main()
