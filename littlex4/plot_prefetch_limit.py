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
        "ttg_bfs_ms", "bulk_exists_ms", "find_raw_ms", "bulk_put_raw_ms", "batch_load_ms",
    ]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    grouped = df.groupby("prefetch_limit").mean(numeric_only=True).reset_index()
    grouped = grouped.sort_values("prefetch_limit")

    x = np.arange(len(grouped))
    width = 0.6

    batch_load   = grouped["batch_load_ms"].values
    bulk_put_raw = grouped["bulk_put_raw_ms"].values
    find_raw     = grouped["find_raw_ms"].values
    bulk_exists  = grouped["bulk_exists_ms"].values
    ttg_bfs      = grouped["ttg_bfs_ms"].values
    e2e          = grouped["e2e_ms"].values
    other        = np.maximum(e2e - (batch_load + bulk_put_raw + find_raw + bulk_exists + ttg_bfs), 0)

    fig, ax = plt.subplots(figsize=(12, 6))

    b0 = batch_load
    b1 = b0 + bulk_put_raw
    b2 = b1 + find_raw
    b3 = b2 + bulk_exists
    b4 = b3 + ttg_bfs

    ax.bar(x, batch_load,   width,           label="batch_load_nodes (walker)",  color="steelblue")
    ax.bar(x, bulk_put_raw, width, bottom=b0, label="bulk_put_raw (L2 write)",    color="orange")
    ax.bar(x, find_raw,     width, bottom=b1, label="find_raw (L3 fetch)",        color="tomato")
    ax.bar(x, bulk_exists,  width, bottom=b2, label="bulk_exists (L2 check)",     color="gold")
    ax.bar(x, ttg_bfs,      width, bottom=b3, label="TTG BFS",                    color="green")
    ax.bar(x, other,        width, bottom=b4, label="Other",                      color="lightgray")

    # Annotate total e2e on top of each bar
    for i, total in enumerate(e2e):
        ax.text(x[i], total + 5, f"{total:.0f}ms", ha="center", va="bottom", fontsize=8)

    ax.set_xlabel("Prefetch Limit (max nodes prefetched)")
    ax.set_ylabel("Time (ms)")
    ax.set_xticks(x)
    ax.set_xticklabels(grouped["prefetch_limit"].astype(int).values)
    ax.set_title("E2E Time vs Prefetch Limit\n(cold Redis cache per trial, averaged over trials)")
    ax.legend()
    ax.grid(axis="y", alpha=0.3)

    plt.tight_layout()

    output_file = csv_file.replace(".csv", ".png")
    plt.savefig(output_file, dpi=150)
    print(f"Saved plot to {output_file}")

    plt.show()


if __name__ == "__main__":
    main()
