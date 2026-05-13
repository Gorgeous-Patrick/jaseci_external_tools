#!/usr/bin/env python3
"""
Plot per-tier timing (L1, L2, L3) vs prefetch_limit as line plots with std band.

Reads .prof files from:  profiles/limit_<N>/trial_<M>/jac_server.prof

Usage:
    python plot_prof_lines.py [profiles_dir]
"""

import pstats
import sys
import re
import io
from pathlib import Path
from collections import defaultdict

import numpy as np
import matplotlib.pyplot as plt


TRACKED = {
    "L2 batch_get (Redis)":   "RedisBackend.batch_get",
    "L2 put (Redis)":         "RedisBackend.put",
    "L3 batch_get (MongoDB)": "MongoBackend.batch_get",
    "TTG generator":          "get_ttg_prefetch_list",
    "Prefetcher":             "ScaleTieredMemory.prefetch",
}


def load_cumtimes(prof_path: Path) -> dict:
    stats = pstats.Stats(str(prof_path), stream=io.StringIO())
    result = defaultdict(float)
    for (_file, _line, funcname), (_cc, _nc, _tt, ct, _callers) in stats.stats.items():
        result[funcname] += ct
    return dict(result)


def tier_times(cumtimes: dict) -> dict:
    return {label: cumtimes.get(func, 0.0) for label, func in TRACKED.items()}


def collect(profiles_dir: Path) -> dict:
    data = defaultdict(list)
    for prof_path in sorted(profiles_dir.glob("limit_*/trial_*/jac_server.prof")):
        m = re.search(r"limit_(\d+)", str(prof_path))
        if not m:
            continue
        limit = int(m.group(1))
        try:
            data[limit].append(tier_times(load_cumtimes(prof_path)))
        except Exception as e:
            print(f"Warning: could not load {prof_path}: {e}", file=sys.stderr)
    return dict(data)


def main():
    profiles_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("profiles")

    data = collect(profiles_dir)
    if not data:
        print(f"No .prof files found under {profiles_dir}", file=sys.stderr)
        sys.exit(1)

    limits = sorted(data.keys())
    tiers = list(TRACKED.keys())
    colors = {
        "L2 batch_get (Redis)":   "orange",
        "L2 put (Redis)":         "goldenrod",
        "L3 batch_get (MongoDB)": "tomato",
        "TTG generator":          "steelblue",
        "Prefetcher":             "green",
    }

    x = np.array(limits)
    fig, ax = plt.subplots(figsize=(12, 6))

    mu_at = {}  # tier -> array of means
    for tier in tiers:
        vals_per_limit = [[t[tier] * 1000 for t in data[lim]] for lim in limits]
        mu = np.array([np.mean(v) for v in vals_per_limit])
        sd = np.array([np.std(v, ddof=1) if len(v) > 1 else 0.0 for v in vals_per_limit])
        mu_at[tier] = mu
        ax.plot(x, mu, color=colors[tier], linewidth=2, marker="o", markersize=4, label=tier)
        ax.fill_between(x, mu - sd, mu + sd, color=colors[tier], alpha=0.15)

    # Annotate slope (limit=2000 - limit=0) / 2000 at the limit=2000 point
    slopes = {}
    if 0 in limits and 2000 in limits:
        idx0    = limits.index(0)
        idx2000 = limits.index(2000)
        for tier in tiers:
            v0    = mu_at[tier][idx0]
            v2000 = mu_at[tier][idx2000]
            slope = (v2000 - v0) / 2000
            slopes[tier] = slope
            ax.annotate(
                f"{slope:+.3f}ms/limit",
                xy=(x[idx2000], v2000),
                xytext=(4, 4), textcoords="offset points",
                color=colors[tier], fontsize=8, fontweight="bold",
            )

    if slopes:
        print("\nSlopes (ms per prefetch_limit unit):")
        for tier, slope in slopes.items():
            print(f"  {tier:<30} {slope:+.4f}")
        print(f"  {'SUM':<30} {sum(slopes.values()):+.4f}")

    ax.set_xlabel("Prefetch Limit (max nodes prefetched)")
    ax.set_ylabel("Time (ms)")
    ax.set_title(
        "Per-Tier Timing vs Prefetch Limit\n"
        "(mean ± 1 std across trials; cold Redis + server restart each trial)"
    )
    ax.set_xticks(x)
    ax.set_xticklabels([str(lim) for lim in limits], rotation=45, ha="right")
    ax.legend(loc="upper right")
    ax.grid(alpha=0.3)
    plt.tight_layout()

    output_file = "profiles_tier_lines.png"
    plt.savefig(output_file, dpi=150)
    print(f"Saved plot to {output_file}")

    # plt.show()


if __name__ == "__main__":
    main()
