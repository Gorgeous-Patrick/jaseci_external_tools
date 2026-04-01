#!/usr/bin/env python3
"""Plot sweep_results_e2e.csv profiling data."""

import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
import sys

def main():
    csv_file = sys.argv[1] if len(sys.argv) > 1 else "sweep_results_e2e.csv"

    df = pd.read_csv(csv_file)

    # Group by edge_num and ttg_enabled, average across trials
    grouped = df.groupby(["edge_num", "ttg_enabled"]).agg({
        "ttg_ms": "mean",
        "prefetch_ms": "mean",
        "walker_ms": "mean",
        "node_num": "first",
        "tweet_num": "first",
    }).reset_index()

    # Separate TTG enabled and disabled
    ttg_enabled = grouped[grouped["ttg_enabled"] == "enabled"].sort_values("edge_num")
    ttg_disabled = grouped[grouped["ttg_enabled"] == "disabled"].sort_values("edge_num")

    fig, axes = plt.subplots(2, 2, figsize=(14, 10))

    # Plot 1: Total time comparison (stacked bar)
    ax1 = axes[0, 0]
    x = np.arange(len(ttg_enabled))
    width = 0.35

    # TTG enabled - stacked
    enabled_ttg = ttg_enabled["ttg_ms"].values
    enabled_prefetch = ttg_enabled["prefetch_ms"].values
    enabled_walker = ttg_enabled["walker_ms"].values

    ax1.bar(x - width/2, enabled_walker, width, label="Walker (TTG)", color="steelblue")
    ax1.bar(x - width/2, enabled_prefetch, width, bottom=enabled_walker, label="Prefetch", color="orange")
    ax1.bar(x - width/2, enabled_ttg, width, bottom=enabled_walker + enabled_prefetch, label="TTG Gen", color="green")

    # TTG disabled
    disabled_walker = ttg_disabled["walker_ms"].values
    ax1.bar(x + width/2, disabled_walker, width, label="Walker (No TTG)", color="lightcoral")

    ax1.set_xlabel("Edge Count")
    ax1.set_ylabel("Time (ms)")
    ax1.set_title("Total Execution Time: TTG vs No TTG")
    ax1.set_xticks(x)
    ax1.set_xticklabels(ttg_enabled["edge_num"].values)
    ax1.legend()
    ax1.grid(axis="y", alpha=0.3)

    # Plot 2: Walker time comparison (line)
    ax2 = axes[0, 1]
    ax2.plot(ttg_enabled["edge_num"], enabled_walker, "o-", label="TTG Enabled", color="steelblue", linewidth=2)
    ax2.plot(ttg_disabled["edge_num"], disabled_walker, "s--", label="TTG Disabled", color="lightcoral", linewidth=2)
    ax2.set_xlabel("Edge Count")
    ax2.set_ylabel("Walker Time (ms)")
    ax2.set_title("Walker Execution Time Comparison")
    ax2.legend()
    ax2.grid(alpha=0.3)

    # Plot 3: TTG overhead breakdown (stacked area)
    ax3 = axes[1, 0]
    ax3.fill_between(ttg_enabled["edge_num"], 0, enabled_walker, alpha=0.7, label="Walker", color="steelblue")
    ax3.fill_between(ttg_enabled["edge_num"], enabled_walker, enabled_walker + enabled_prefetch, alpha=0.7, label="Prefetch", color="orange")
    ax3.fill_between(ttg_enabled["edge_num"], enabled_walker + enabled_prefetch, enabled_walker + enabled_prefetch + enabled_ttg, alpha=0.7, label="TTG Gen", color="green")
    ax3.set_xlabel("Edge Count")
    ax3.set_ylabel("Time (ms)")
    ax3.set_title("TTG Enabled: Time Breakdown")
    ax3.legend()
    ax3.grid(alpha=0.3)

    # Plot 4: Speedup ratio
    ax4 = axes[1, 1]
    total_enabled = enabled_walker + enabled_prefetch + enabled_ttg
    total_disabled = disabled_walker
    speedup = total_disabled / total_enabled

    colors = ["green" if s > 1 else "red" for s in speedup]
    bars = ax4.bar(x, speedup, color=colors, alpha=0.7)
    ax4.axhline(y=1, color="black", linestyle="--", linewidth=1, label="Break-even")
    ax4.set_xlabel("Edge Count")
    ax4.set_ylabel("Speedup (No TTG / TTG)")
    ax4.set_title("TTG Speedup Ratio (>1 = TTG faster)")
    ax4.set_xticks(x)
    ax4.set_xticklabels(ttg_enabled["edge_num"].values)
    ax4.grid(axis="y", alpha=0.3)

    # Add value labels on bars
    for bar, val in zip(bars, speedup):
        ax4.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.02,
                f"{val:.2f}x", ha="center", va="bottom", fontsize=8)

    # Title with config info
    node_num = ttg_enabled["node_num"].iloc[0]
    tweet_num = ttg_enabled["tweet_num"].iloc[0]
    fig.suptitle(f"Sweep Results: {node_num} nodes, {tweet_num} tweets/node", fontsize=14, fontweight="bold")

    plt.tight_layout()

    output_file = csv_file.replace(".csv", ".png")
    plt.savefig(output_file, dpi=150)
    print(f"Saved plot to {output_file}")

    plt.show()

if __name__ == "__main__":
    main()
