#!/usr/bin/env python3
"""Plot e2e time distribution as a dot plot per prefetch limit."""

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

    limits = sorted(df["prefetch_limit"].unique())
    n = len(limits)
    limit_to_x = {lim: i for i, lim in enumerate(limits)}

    fig, ax = plt.subplots(figsize=(13, 6))

    rng = np.random.default_rng(42)
    for lim in limits:
        subset = df[df["prefetch_limit"] == lim]["e2e_ms"].values
        xi = limit_to_x[lim]
        jitter = rng.uniform(-0.18, 0.18, size=len(subset))
        ax.scatter(xi + jitter, subset, s=28, alpha=0.7, color="steelblue", zorder=3)

        median = np.median(subset)
        ax.hlines(median, xi - 0.3, xi + 0.3, colors="tomato", linewidths=2, zorder=4)

    ax.set_xticks(range(n))
    ax.set_xticklabels([str(int(lim)) for lim in limits])
    ax.set_xlabel("Prefetch Limit (max nodes prefetched)")
    ax.set_ylabel("E2E Time (ms)")
    ax.set_title(
        "E2E Time Distribution per Prefetch Limit\n"
        "(each dot = one trial; red line = median)"
    )
    ax.grid(axis="y", alpha=0.3)

    # Legend proxies
    dot_handle = plt.scatter([], [], s=28, color="steelblue", alpha=0.7, label="Trial")
    line_handle = plt.Line2D([0], [0], color="tomato", linewidth=2, label="Median")
    ax.legend(handles=[dot_handle, line_handle], loc="upper right")

    plt.tight_layout()

    output_file = csv_file.replace(".csv", "_distribution.png")
    plt.savefig(output_file, dpi=150)
    print(f"Saved plot to {output_file}")

    # plt.show()


if __name__ == "__main__":
    main()
