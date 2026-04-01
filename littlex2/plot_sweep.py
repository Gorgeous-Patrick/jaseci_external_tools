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

    fig, ax = plt.subplots(figsize=(12, 6))

    x = np.arange(len(ttg_enabled))
    width = 0.35

    # TTG enabled - stacked
    enabled_ttg = ttg_enabled["ttg_ms"].values
    enabled_prefetch = ttg_enabled["prefetch_ms"].values
    enabled_walker = ttg_enabled["walker_ms"].values

    ax.bar(x - width/2, enabled_walker, width, label="Walker (TTG)", color="steelblue")
    ax.bar(x - width/2, enabled_prefetch, width, bottom=enabled_walker, label="Prefetch", color="orange")
    ax.bar(x - width/2, enabled_ttg, width, bottom=enabled_walker + enabled_prefetch, label="TTG Gen", color="green")

    # TTG disabled
    disabled_walker = ttg_disabled["walker_ms"].values
    ax.bar(x + width/2, disabled_walker, width, label="Walker (No TTG)", color="lightcoral")

    ax.set_xlabel("# of Followings")
    ax.set_ylabel("Time (ms)")
    ax.set_xticks(x)
    ax.set_xticklabels(ttg_enabled["edge_num"].values)
    ax.legend()
    ax.grid(axis="y", alpha=0.3)

    # Title with config info
    user_num = ttg_enabled["node_num"].iloc[0]
    tweet_num = ttg_enabled["tweet_num"].iloc[0]
    ax.set_title(f"Execution Time: TTG vs No TTG ({user_num} users, {tweet_num} tweets/user)")

    plt.tight_layout()

    output_file = csv_file.replace(".csv", ".png")
    plt.savefig(output_file, dpi=150)
    print(f"Saved plot to {output_file}")

    plt.show()

if __name__ == "__main__":
    main()
