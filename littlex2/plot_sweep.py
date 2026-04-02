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
    agg_dict = {
        "e2e_ms": "mean",
        "walker_ms": "mean",
        "node_num": "first",
        "tweet_num": "first",
    }
    # Add optional columns if they exist
    for col in ["ttg_total_ms", "topo_idx_ms", "ttg_ms", "prefetch_ms"]:
        if col in df.columns:
            agg_dict[col] = "mean"
    grouped = df.groupby(["edge_num", "ttg_enabled"]).agg(agg_dict).reset_index()

    # Separate TTG enabled and disabled
    ttg_enabled = grouped[grouped["ttg_enabled"] == "enabled"].sort_values("edge_num")
    ttg_disabled = grouped[grouped["ttg_enabled"] == "disabled"].sort_values("edge_num")

    fig, ax = plt.subplots(figsize=(12, 6))

    x = np.arange(len(ttg_enabled))
    width = 0.35

    # TTG enabled - stacked
    enabled_walker = ttg_enabled["walker_ms"].values
    enabled_topo_idx = ttg_enabled["topo_idx_ms"].values if "topo_idx_ms" in ttg_enabled.columns else np.zeros_like(enabled_walker)
    enabled_ttg = ttg_enabled["ttg_ms"].values if "ttg_ms" in ttg_enabled.columns else np.zeros_like(enabled_walker)
    enabled_prefetch = ttg_enabled["prefetch_ms"].values if "prefetch_ms" in ttg_enabled.columns else np.zeros_like(enabled_walker)
    enabled_e2e = ttg_enabled["e2e_ms"].values
    enabled_misc = enabled_e2e - (enabled_walker + enabled_prefetch + enabled_ttg + enabled_topo_idx)
    enabled_misc = np.maximum(enabled_misc, 0)  # Ensure non-negative

    ax.bar(x - width/2, enabled_walker, width, label="Walker (TTG)", color="steelblue")
    ax.bar(x - width/2, enabled_prefetch, width, bottom=enabled_walker, label="Prefetcher", color="orange")
    ax.bar(x - width/2, enabled_ttg, width, bottom=enabled_walker + enabled_prefetch, label="TTG Generator", color="green")
    ax.bar(x - width/2, enabled_topo_idx, width, bottom=enabled_walker + enabled_prefetch + enabled_ttg, label="Load graph topology (adjacency matrix)", color="purple")
    ax.bar(x - width/2, enabled_misc, width, bottom=enabled_walker + enabled_prefetch + enabled_ttg + enabled_topo_idx, label="Misc (TTG)", color="gray")

    # TTG disabled - stacked
    disabled_walker = ttg_disabled["walker_ms"].values
    disabled_e2e = ttg_disabled["e2e_ms"].values
    disabled_misc = disabled_e2e - disabled_walker
    disabled_misc = np.maximum(disabled_misc, 0)  # Ensure non-negative

    ax.bar(x + width/2, disabled_walker, width, label="Walker (No TTG)", color="lightcoral")
    ax.bar(x + width/2, disabled_misc, width, bottom=disabled_walker, label="Misc (No TTG)", color="darkgray")

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
