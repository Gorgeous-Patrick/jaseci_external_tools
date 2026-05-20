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
    "L2 bulk_put (Redis)":    "RedisBackend.bulk_put",
    "L3 batch_get (MongoDB)": "MongoBackend.batch_get",
    "TTG generator":          "get_ttg_prefetch_list",
    "Prefetcher":             "ScaleTieredMemory.prefetch",
}

# (funcname, caller_funcname) -> only count ct from a specific caller
CALLER_TRACKED = {
    "Prefetch: deserialize": ("deserialize", "ScaleTieredMemory.prefetch"),
}


def load_stats(prof_path: Path) -> dict:
    stats = pstats.Stats(str(prof_path), stream=io.StringIO())
    cumtimes = defaultdict(float)
    caller_cumtimes = defaultdict(float)
    for (_file, _line, funcname), (_cc, _nc, _tt, ct, callers) in stats.stats.items():
        cumtimes[funcname] += ct
        for (_cf, _cl, cfn), caller_stats in callers.items():
            caller_cumtimes[(funcname, cfn)] += caller_stats[3]
    return dict(cumtimes), dict(caller_cumtimes)


def tier_times(cumtimes: dict, caller_cumtimes: dict) -> dict:
    result = {label: cumtimes.get(func, 0.0) for label, func in TRACKED.items()}
    for label, (func, caller) in CALLER_TRACKED.items():
        result[label] = caller_cumtimes.get((func, caller), 0.0)
    return result


def collect(profiles_dir: Path) -> dict:
    data = defaultdict(list)
    for prof_path in sorted(profiles_dir.glob("limit_*/trial_*/jac_server.prof")):
        m = re.search(r"limit_(\d+)", str(prof_path))
        if not m:
            continue
        limit = int(m.group(1))
        try:
            cumtimes, caller_cumtimes = load_stats(prof_path)
            data[limit].append(tier_times(cumtimes, caller_cumtimes))
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
    tiers = list(TRACKED.keys()) + list(CALLER_TRACKED.keys())
    colors = {
        "L2 batch_get (Redis)":   "orange",
        "L2 bulk_put (Redis)":    "goldenrod",
        "L3 batch_get (MongoDB)": "tomato",
        "TTG generator":          "steelblue",
        "Prefetcher":             "green",
        "Prefetch: deserialize":  "mediumpurple",
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
