#!/usr/bin/env python3
"""Plot sweep_results_e2e.csv profiling data."""

import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
import sys


def main():
    csv_file = sys.argv[1] if len(sys.argv) > 1 else "sweep_results_e2e.csv"

    df = pd.read_csv(csv_file)

    numeric_cols = [
        "tweet_num", "trial", "e2e_ms", "ttg_total_ms", "topo_idx_ms",
        "ttg_ms", "prefetch_ms", "walker_ms",
        "ast_ms", "resolve_total_ms", "resolve_calls", "avg_resolve_ms", "adj_list_size",
    ]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df[df["tweet_num"] <= 50]

    grouped = df.groupby(["tweet_num", "ttg_enabled"]).mean(numeric_only=True).reset_index()

    ttg_on  = grouped[grouped["ttg_enabled"] == "enabled"].sort_values("tweet_num")
    ttg_off = grouped[grouped["ttg_enabled"] == "disabled"].sort_values("tweet_num")

    has_breakdown = "resolve_total_ms" in df.columns and ttg_on["resolve_total_ms"].sum() > 0
    n_plots = 2 if has_breakdown else 1
    fig, axes = plt.subplots(1, n_plots, figsize=(12 * n_plots, 6))
    if n_plots == 1:
        axes = [axes]

    # --- Plot 1: E2E stacked bar comparison ---
    ax = axes[0]
    x = np.arange(len(ttg_on))
    width = 0.35

    ew = ttg_on["walker_ms"].values
    et = ttg_on["topo_idx_ms"].values
    eg = ttg_on["ttg_ms"].values
    ep = ttg_on["prefetch_ms"].values
    ee = ttg_on["e2e_ms"].values
    em = np.maximum(ee - (ew + et + eg + ep), 0)

    ax.bar(x - width/2, ew, width, label="Walker (TTG)", color="steelblue")
    ax.bar(x - width/2, ep, width, bottom=ew,          label="Prefetcher", color="orange")
    ax.bar(x - width/2, eg, width, bottom=ew+ep,       label="TTG Generator", color="green")
    ax.bar(x - width/2, et, width, bottom=ew+ep+eg,    label="Load topology", color="purple")
    ax.bar(x - width/2, em, width, bottom=ew+ep+eg+et, label="Misc (TTG)", color="gray")

    dw = ttg_off["walker_ms"].values
    de = ttg_off["e2e_ms"].values
    dm = np.maximum(de - dw, 0)

    ax.bar(x + width/2, dw, width, label="Walker (No TTG)", color="lightcoral")
    ax.bar(x + width/2, dm, width, bottom=dw, label="Misc (No TTG)", color="darkgray")

    ax.set_xlabel("# of Tweets per User")
    ax.set_ylabel("Time (ms)")
    ax.set_xticks(x)
    ax.set_xticklabels(ttg_on["tweet_num"].astype(int).values)
    ax.set_title("E2E Time: TTG vs No TTG")
    ax.legend()
    ax.grid(axis="y", alpha=0.3)

    # --- Plot 2: TTG internal breakdown (resolve_chain vs rest) ---
    if has_breakdown:
        ax2 = axes[1]

        ttg_ms      = ttg_on["ttg_ms"].values
        resolve_ms  = ttg_on["resolve_total_ms"].fillna(0).values
        ast_ms      = ttg_on["ast_ms"].fillna(0).values
        other_ms    = np.maximum(ttg_ms - resolve_ms - ast_ms, 0)

        ax2.bar(x, resolve_ms, width*1.5, label="resolve_chain() total", color="tomato")
        ax2.bar(x, ast_ms,     width*1.5, bottom=resolve_ms,              label="AST extraction", color="gold")
        ax2.bar(x, other_ms,   width*1.5, bottom=resolve_ms+ast_ms,       label="Other", color="lightgray")

        # Annotate with resolve_calls
        if "resolve_calls" in ttg_on.columns:
            for i, (rc, am) in enumerate(zip(ttg_on["resolve_calls"].values, ttg_on["adj_list_size"].fillna(0).values)):
                if np.isnan(rc) or np.isnan(am):
                    continue
                ax2.text(x[i], ttg_ms[i] + 0.5, f"calls={int(rc)}\nadj={int(am)}", ha="center", fontsize=7)

        ax2.set_xlabel("# of Tweets per User")
        ax2.set_ylabel("TTG Generator time (ms)")
        ax2.set_xticks(x)
        ax2.set_xticklabels(ttg_on["tweet_num"].astype(int).values)
        ax2.set_title("TTG Generator Breakdown\n(what's inside ttg_ms)")
        ax2.legend()
        ax2.grid(axis="y", alpha=0.3)

    plt.tight_layout()

    output_file = csv_file.replace(".csv", ".png")
    plt.savefig(output_file, dpi=150)
    print(f"Saved plot to {output_file}")

    plt.show()


if __name__ == "__main__":
    main()
