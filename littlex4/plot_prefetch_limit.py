#!/usr/bin/env python3
"""Plot prefetch limit sweep results (sweep_prefetch_limit.csv)."""

import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
import sys


def main():
    csv_file = sys.argv[1] if len(sys.argv) > 1 else "sweep_prefetch_limit.csv"

    df = pd.read_csv(csv_file)

    numeric_cols = [
        "prefetch_limit", "trial", "e2e_ms",
        "topo_idx_ms", "ttg_ms", "prefetch_ms", "walker_ms",
    ]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    grouped = df.groupby("prefetch_limit").mean(numeric_only=True).reset_index()
    grouped = grouped.sort_values("prefetch_limit")

    x = np.arange(len(grouped))
    width = 0.6

    ew = grouped["walker_ms"].values
    ep = grouped["prefetch_ms"].values
    eg = grouped["ttg_ms"].values
    et = grouped["topo_idx_ms"].values
    ee = grouped["e2e_ms"].values
    em = np.maximum(ee - (ew + ep + eg + et), 0)

    fig, ax = plt.subplots(figsize=(12, 6))

    ax.bar(x, ew, width,                     label="Walker",        color="steelblue")
    ax.bar(x, ep, width, bottom=ew,          label="Prefetcher",    color="orange")
    ax.bar(x, eg, width, bottom=ew+ep,       label="TTG Generator", color="green")
    ax.bar(x, et, width, bottom=ew+ep+eg,    label="Load topology", color="purple")
    ax.bar(x, em, width, bottom=ew+ep+eg+et, label="Misc",          color="lightgray")

    # Annotate total e2e on top of each bar
    for i, total in enumerate(ee):
        ax.text(x[i], total + 5, f"{total:.0f}ms", ha="center", va="bottom", fontsize=8)

    ax.set_xlabel("Prefetch Limit (max nodes prefetched)")
    ax.set_ylabel("Time (ms)")
    ax.set_xticks(x)
    ax.set_xticklabels(grouped["prefetch_limit"].astype(int).values)
    ax.set_title("E2E Time vs Prefetch Limit\n(cold Redis cache per trial, averaged over trials)")
    ax.legend(loc="upper right")
    ax.grid(axis="y", alpha=0.3)

    plt.tight_layout()

    output_file = csv_file.replace(".csv", ".png")
    plt.savefig(output_file, dpi=150)
    print(f"Saved plot to {output_file}")

    # plt.show()


if __name__ == "__main__":
    main()
