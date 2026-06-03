#!/usr/bin/env python3
"""Plot prefetch limit sweep results for littlex5 (sweep_prefetch_limit.csv).

CSV format: walker,prefetch_limit,trial,e2e_ms,http_status,resp_size
"""

import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
import sys


def main():
    csv_file = sys.argv[1] if len(sys.argv) > 1 else "sweep_prefetch_limit.csv"

    df = pd.read_csv(csv_file)
    for col in ["prefetch_limit", "trial", "e2e_ms", "resp_size"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["e2e_ms"])

    walkers = sorted(df["walker"].unique())
    limits = sorted(df["prefetch_limit"].unique())

    fig, axes = plt.subplots(1, len(walkers), figsize=(7 * len(walkers), 6), sharey=True)
    if len(walkers) == 1:
        axes = [axes]

    colors = ["#4e79a7", "#f28e2b", "#59a14f", "#e15759", "#76b7b2"]

    for ax, walker in zip(axes, walkers):
        wdf = df[df["walker"] == walker]
        grouped = wdf.groupby("prefetch_limit")["e2e_ms"].agg(["mean", "std", "median"]).reset_index()
        grouped = grouped.sort_values("prefetch_limit")

        x = np.arange(len(grouped))
        width = 0.5

        bars = ax.bar(x, grouped["mean"].values, width,
                       yerr=grouped["std"].values, capsize=4,
                       color=colors[:len(grouped)], alpha=0.85, edgecolor="black", linewidth=0.5)

        # Annotate mean on top
        for i, (mean, median) in enumerate(zip(grouped["mean"].values, grouped["median"].values)):
            ax.text(x[i], mean + grouped["std"].values[i] + 5,
                    f"{mean:.0f}ms", ha="center", va="bottom", fontsize=9, fontweight="bold")

        ax.set_xlabel("Prefetch Limit")
        ax.set_xticks(x)
        ax.set_xticklabels([str(int(v)) for v in grouped["prefetch_limit"].values])
        ax.set_title(f"Walker: {walker}")
        ax.grid(axis="y", alpha=0.3)

    axes[0].set_ylabel("E2E Time (ms)")
    fig.suptitle("LittleX E2E Time vs Prefetch Limit\n(cold Redis, 10 trials each, mean ± std)",
                 fontsize=13, fontweight="bold")
    plt.tight_layout()

    output_file = csv_file.replace(".csv", ".png")
    plt.savefig(output_file, dpi=150)
    print(f"Saved plot to {output_file}")


if __name__ == "__main__":
    main()
