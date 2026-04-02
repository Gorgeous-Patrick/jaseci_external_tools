#!/usr/bin/env python3
"""Plot sweep_results_e2e.csv profiling data for littlex3."""

import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
import sys

def main():
    csv_file = sys.argv[1] if len(sys.argv) > 1 else "sweep_results_e2e.csv"

    df = pd.read_csv(csv_file)

    # Group by ttg_enabled, average across trials
    grouped = df.groupby("ttg_enabled").agg({
        "e2e_ms": "mean",
        "walker_ms": "mean",
        "ttg_total_ms": "mean",
        "topo_idx_ms": "mean",
        "ttg_ms": "mean",
        "prefetch_ms": "mean",
    }).reset_index()

    # Separate TTG enabled and disabled
    ttg_enabled = grouped[grouped["ttg_enabled"] == "enabled"].iloc[0]
    ttg_disabled = grouped[grouped["ttg_enabled"] == "disabled"].iloc[0]

    fig, ax = plt.subplots(figsize=(10, 6))

    x = np.array([0, 1])
    width = 0.5

    # TTG enabled - stacked bar
    enabled_walker = ttg_enabled["walker_ms"]
    enabled_topo_idx = ttg_enabled["topo_idx_ms"]
    enabled_ttg = ttg_enabled["ttg_ms"]
    enabled_prefetch = ttg_enabled["prefetch_ms"]
    enabled_e2e = ttg_enabled["e2e_ms"]
    enabled_misc = max(0, enabled_e2e - (enabled_walker + enabled_prefetch + enabled_ttg + enabled_topo_idx))

    ax.bar(0, enabled_walker, width, label="Walker", color="steelblue")
    ax.bar(0, enabled_prefetch, width, bottom=enabled_walker, label="Prefetcher", color="orange")
    ax.bar(0, enabled_ttg, width, bottom=enabled_walker + enabled_prefetch, label="TTG Generator", color="green")
    ax.bar(0, enabled_topo_idx, width, bottom=enabled_walker + enabled_prefetch + enabled_ttg, label="Load graph topology", color="purple")
    ax.bar(0, enabled_misc, width, bottom=enabled_walker + enabled_prefetch + enabled_ttg + enabled_topo_idx, label="Misc", color="gray")

    # TTG disabled - stacked bar
    disabled_walker = ttg_disabled["walker_ms"]
    disabled_e2e = ttg_disabled["e2e_ms"]
    disabled_misc = max(0, disabled_e2e - disabled_walker)

    ax.bar(1, disabled_walker, width, color="steelblue")
    ax.bar(1, disabled_misc, width, bottom=disabled_walker, color="gray")

    ax.set_xlabel("Mode")
    ax.set_ylabel("Time (ms)")
    ax.set_xticks(x)
    ax.set_xticklabels(["TTG Enabled", "TTG Disabled"])
    ax.legend(loc="upper right")
    ax.grid(axis="y", alpha=0.3)

    # Add e2e time labels on bars
    ax.text(0, enabled_e2e + 5, f"{enabled_e2e:.1f}ms", ha="center", fontweight="bold")
    ax.text(1, disabled_e2e + 5, f"{disabled_e2e:.1f}ms", ha="center", fontweight="bold")

    ax.set_title("Execution Time: TTG Enabled vs Disabled")

    plt.tight_layout()

    output_file = csv_file.replace(".csv", ".png")
    plt.savefig(output_file, dpi=150)
    print(f"Saved plot to {output_file}")

    plt.show()

if __name__ == "__main__":
    main()
