#!/usr/bin/env python3
"""Plot MongoDB call counts across prefetch limits.

Scans .prof files from the sweep directory structure and plots the number
of MongoDB calls (batch_get, get, find_one) per prefetch limit.

Directory structure expected:
  profiles/limit_{N}/{walker}/trial_{i}/jac_server.prof

Usage:
    python plot_mongo_calls.py [profiles_dir]
"""

import os
import pstats
import sys
from collections import defaultdict

import matplotlib.pyplot as plt
import numpy as np


MONGO_FUNCTIONS = [
    "MongoBackend.batch_get",
    "MongoBackend.get",
]


def load_stats(prof_path):
    stats = pstats.Stats(prof_path, stream=open(os.devnull, "w"))
    result = {}
    for (filename, lineno, funcname), (cc, nc, tt, ct, caller_dict) in stats.stats.items():
        if funcname not in result:
            result[funcname] = {"nc": 0, "tt": 0.0, "ct": 0.0}
        result[funcname]["nc"] += nc
        result[funcname]["tt"] += tt
        result[funcname]["ct"] += ct
    return result


def main():
    profiles_dir = sys.argv[1] if len(sys.argv) > 1 else "profiles"

    # Discover all limit dirs
    limit_dirs = sorted(
        [d for d in os.listdir(profiles_dir) if d.startswith("limit_")],
        key=lambda d: int(d.split("_")[1]),
    )

    if not limit_dirs:
        print(f"No limit_* directories found in {profiles_dir}")
        return

    # Collect data: {walker: {limit: [total_mongo_calls_per_trial]}}
    data = defaultdict(lambda: defaultdict(list))
    mongo_time_data = defaultdict(lambda: defaultdict(list))

    for limit_dir in limit_dirs:
        limit = int(limit_dir.split("_")[1])
        limit_path = os.path.join(profiles_dir, limit_dir)

        for walker in sorted(os.listdir(limit_path)):
            walker_path = os.path.join(limit_path, walker)
            if not os.path.isdir(walker_path):
                continue

            for trial_dir in sorted(os.listdir(walker_path)):
                prof_path = os.path.join(walker_path, trial_dir, "jac_server.prof")
                if not os.path.exists(prof_path):
                    continue

                try:
                    s = load_stats(prof_path)
                except Exception:
                    continue

                total_calls = 0
                total_ms = 0.0
                for fn in MONGO_FUNCTIONS:
                    if fn in s:
                        total_calls += s[fn]["nc"]
                        total_ms += s[fn]["ct"] * 1000

                data[walker][limit].append(total_calls)
                mongo_time_data[walker][limit].append(total_ms)

    walkers = sorted(data.keys())
    if not walkers:
        print("No profiling data found")
        return

    fig, axes = plt.subplots(2, len(walkers), figsize=(7 * len(walkers), 10))
    if len(walkers) == 1:
        axes = axes.reshape(2, 1)

    for col, walker in enumerate(walkers):
        limits = sorted(data[walker].keys())
        x = np.arange(len(limits))

        # Top row: call counts
        ax1 = axes[0, col]
        means = [np.mean(data[walker][lim]) for lim in limits]
        stds = [np.std(data[walker][lim]) for lim in limits]
        ax1.bar(x, means, yerr=stds, width=0.6, color="steelblue", capsize=4)
        for i, m in enumerate(means):
            ax1.text(i, m + stds[i] + max(means) * 0.02, f"{m:.0f}",
                     ha="center", va="bottom", fontsize=9, fontweight="bold")
        ax1.set_xticks(x)
        ax1.set_xticklabels([str(lim) for lim in limits])
        ax1.set_xlabel("Prefetch Limit")
        ax1.set_ylabel("MongoDB Calls")
        ax1.set_title(f"{walker}")
        ax1.grid(axis="y", alpha=0.3)

        # Bottom row: time spent in MongoDB
        ax2 = axes[1, col]
        time_means = [np.mean(mongo_time_data[walker][lim]) for lim in limits]
        time_stds = [np.std(mongo_time_data[walker][lim]) for lim in limits]
        ax2.bar(x, time_means, yerr=time_stds, width=0.6, color="#e15759", capsize=4)
        for i, m in enumerate(time_means):
            ax2.text(i, m + time_stds[i] + max(time_means) * 0.02, f"{m:.0f}ms",
                     ha="center", va="bottom", fontsize=9, fontweight="bold")
        ax2.set_xticks(x)
        ax2.set_xticklabels([str(lim) for lim in limits])
        ax2.set_xlabel("Prefetch Limit")
        ax2.set_ylabel("MongoDB Time (ms)")
        ax2.set_title(f"{walker}")
        ax2.grid(axis="y", alpha=0.3)

    fig.suptitle("MongoDB Calls & Time vs Prefetch Limit\n(per trial, averaged)",
                 fontsize=13, fontweight="bold")
    plt.tight_layout()

    output_file = "mongo_calls.png"
    plt.savefig(output_file, dpi=150)
    print(f"Saved plot to {output_file}")


if __name__ == "__main__":
    main()
