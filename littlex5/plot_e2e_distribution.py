#!/usr/bin/env python3
"""Plot e2e time distribution as a dot plot per prefetch limit for littlex5.

CSV format: walker,prefetch_limit,trial,e2e_ms,http_status,resp_size
"""

import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
import sys


def main():
    csv_file = sys.argv[1] if len(sys.argv) > 1 else "sweep_prefetch_limit.csv"

    df = pd.read_csv(csv_file)
    df["prefetch_limit"] = pd.to_numeric(df["prefetch_limit"], errors="coerce")
    df["e2e_ms"] = pd.to_numeric(df["e2e_ms"], errors="coerce")
    df = df.dropna(subset=["prefetch_limit", "e2e_ms"])

    walkers = sorted(df["walker"].unique())
    limits = sorted(df["prefetch_limit"].unique())

    fig, axes = plt.subplots(1, len(walkers), figsize=(7 * len(walkers), 6), sharey=True)
    if len(walkers) == 1:
        axes = [axes]

    rng = np.random.default_rng(42)
    walker_colors = {"get_profile": "#4e79a7", "load_feed": "#f28e2b",
                     "get_trending": "#59a14f", "get_all_profiles": "#e15759"}

    for ax, walker in zip(axes, walkers):
        wdf = df[df["walker"] == walker]
        n = len(limits)
        limit_to_x = {lim: i for i, lim in enumerate(limits)}
        color = walker_colors.get(walker, "steelblue")

        for lim in limits:
            subset = wdf[wdf["prefetch_limit"] == lim]["e2e_ms"].values
            xi = limit_to_x[lim]
            jitter = rng.uniform(-0.18, 0.18, size=len(subset))
            ax.scatter(xi + jitter, subset, s=32, alpha=0.7, color=color, zorder=3)

            if len(subset) > 0:
                median = np.median(subset)
                ax.hlines(median, xi - 0.3, xi + 0.3, colors="tomato",
                          linewidths=2, zorder=4)
                ax.text(xi + 0.35, median, f"{median:.0f}ms",
                        va="center", fontsize=8, color="tomato")

        ax.set_xticks(range(n))
        ax.set_xticklabels([str(int(lim)) for lim in limits])
        ax.set_xlabel("Prefetch Limit")
        ax.set_title(f"Walker: {walker}")
        ax.grid(axis="y", alpha=0.3)

    axes[0].set_ylabel("E2E Time (ms)")

    # Legend
    dot_handle = plt.scatter([], [], s=32, color="steelblue", alpha=0.7, label="Trial")
    line_handle = plt.Line2D([0], [0], color="tomato", linewidth=2, label="Median")
    axes[-1].legend(handles=[dot_handle, line_handle], loc="upper right")

    fig.suptitle("LittleX E2E Distribution per Prefetch Limit\n"
                 "(each dot = one trial; red line = median)",
                 fontsize=13, fontweight="bold")
    plt.tight_layout()

    output_file = csv_file.replace(".csv", "_distribution.png")
    plt.savefig(output_file, dpi=150)
    print(f"Saved plot to {output_file}")


if __name__ == "__main__":
    main()
