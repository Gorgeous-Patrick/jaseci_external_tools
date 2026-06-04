#!/usr/bin/env python3
"""Plot prefetch limit sweep results for littlex5 (sweep_prefetch_limit.csv).

CSV format: walker,prefetch_limit,trial,e2e_ms,topo_idx_ms,ttg_ms,prefetch_ms,walker_ms
"""

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

    walkers = sorted(df["walker"].unique())
    has_breakdown = all(c in df.columns for c in ["topo_idx_ms", "ttg_ms", "prefetch_ms", "walker_ms"])

    fig, axes = plt.subplots(1, len(walkers), figsize=(7 * len(walkers), 6), sharey=True)
    if len(walkers) == 1:
        axes = [axes]

    for ax, walker in zip(axes, walkers):
        wdf = df[df["walker"] == walker]
        grouped = wdf.groupby("prefetch_limit").mean(numeric_only=True).reset_index()
        grouped = grouped.sort_values("prefetch_limit")

        x = np.arange(len(grouped))
        width = 0.6

        if has_breakdown and not grouped["walker_ms"].isna().all():
            ew = grouped["walker_ms"].fillna(0).values
            ep = grouped["prefetch_ms"].fillna(0).values
            eg = grouped["ttg_ms"].fillna(0).values
            et = grouped["topo_idx_ms"].fillna(0).values
            ee = grouped["e2e_ms"].fillna(0).values
            em = np.maximum(ee - (ew + ep + eg + et), 0)

            ax.bar(x, ew, width,                     label="Walker",        color="steelblue")
            ax.bar(x, ep, width, bottom=ew,          label="Prefetcher",    color="orange")
            ax.bar(x, eg, width, bottom=ew+ep,       label="TTG Generator", color="green")
            ax.bar(x, et, width, bottom=ew+ep+eg,    label="Load topology", color="purple")
            ax.bar(x, em, width, bottom=ew+ep+eg+et, label="Misc",          color="lightgray")

            for i, total in enumerate(ee):
                ax.text(x[i], total + 5, f"{total:.0f}ms", ha="center", va="bottom", fontsize=9, fontweight="bold")
        else:
            # Fallback: just e2e bars
            ee = grouped["e2e_ms"].fillna(0).values
            ax.bar(x, ee, width, color="steelblue", alpha=0.85)
            for i, total in enumerate(ee):
                ax.text(x[i], total + 5, f"{total:.0f}ms", ha="center", va="bottom", fontsize=9, fontweight="bold")

        ax.set_xlabel("Prefetch Limit")
        ax.set_xticks(x)
        ax.set_xticklabels([str(int(v)) for v in grouped["prefetch_limit"].values])
        ax.set_title(f"Walker: {walker}")
        ax.grid(axis="y", alpha=0.3)

    axes[0].set_ylabel("Time (ms)")
    if has_breakdown:
        axes[-1].legend(loc="upper right")
    fig.suptitle("LittleX E2E Time vs Prefetch Limit\n(cold Redis, 10 trials each, averaged)",
                 fontsize=13, fontweight="bold")
    plt.tight_layout()

    output_file = csv_file.replace(".csv", ".png")
    plt.savefig(output_file, dpi=150)
    print(f"Saved plot to {output_file}")


if __name__ == "__main__":
    main()
