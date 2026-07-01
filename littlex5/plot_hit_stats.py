#!/usr/bin/env python3
"""Plot L1 hit rate at each checkpoint, grouped by prefetch_limit.

One plot, X grouped by prefetch_limit, one bar per checkpoint within
each group. Missing checkpoints (e.g. no prefetch phase at limit=0)
render as 0. Trials are median-aggregated.

Parses `[HIT-STATS-SERIES]` info lines emitted by the memory system
after each walker completes. Log filenames must match:

    jac_server_<walker>_limit<N>_trial<I>.log

Usage:
    python3 plot_hit_stats.py logs/jac_server_*.log
    python3 plot_hit_stats.py --out hit_stats.png logs/jac_server_*.log
"""

from __future__ import annotations

import argparse
import ast
import glob
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

TIERS = ["L1", "L2", "L3", "MISS"]
_MARKER = "[HIT-STATS-SERIES] "
_FILE_RE = re.compile(r"limit(\d+)_trial(\d+)\.log$")


def parse_series_from_line(line: str):
    """Return the list-of-(label, dict) if the line has our marker."""
    try:
        rec = json.loads(line)
        msg = rec.get("msg", "")
    except Exception:
        msg = line
    idx = msg.find(_MARKER)
    if idx < 0:
        return None
    payload = msg[idx + len(_MARKER):].rstrip("\"'} \n")
    try:
        return ast.literal_eval(payload)
    except Exception:
        return None


def collect(paths: list[str]):
    """Return {prefetch_limit: [ series ]}, one entry per parsed line."""
    by_limit = defaultdict(list)
    for p in paths:
        m = _FILE_RE.search(p)
        if not m:
            continue
        limit = int(m.group(1))
        for line in Path(p).read_text().splitlines():
            s = parse_series_from_line(line)
            if s:
                by_limit[limit].append(s)
    return by_limit


def _canonicalize_label(label: str) -> str:
    """prefetch_pre_write_shard=<N>  ->  pw (all shard sizes fold together)."""
    if label.startswith("prefetch_pre_write_shard="):
        return "pw"
    return label


def _hit_rate(snap: dict) -> float:
    """L1 / total. 0 when total == 0."""
    total = sum(snap.get(t, 0) for t in TIERS)
    if total == 0:
        return 0.0
    return snap.get("L1", 0) / total * 100.0


def _build_hit_rate_matrix(by_limit):
    """Return (limits, checkpoint_labels, matrix) where matrix[i, j] is
    the median L1 hit rate for limits[i] at checkpoint_labels[j]. Missing
    checkpoints are 0."""
    limits = sorted(by_limit.keys())

    # Discover the union of canonicalised checkpoint labels, preserving
    # the natural request-lifecycle order: any number of "pw" (folded
    # into pw1, pw2, pw3, ... by position within a series), then
    # walker_done, then request_done. We find the max pw count across
    # all series and lay out pw1..pwK, then any post-prefetch labels.
    max_pw = 0
    post_labels: list[str] = []
    for series_list in by_limit.values():
        for series in series_list:
            pw_count = sum(
                1
                for lab, _ in series
                if _canonicalize_label(lab) == "pw"
            )
            max_pw = max(max_pw, pw_count)
            for lab, _ in series:
                clab = _canonicalize_label(lab)
                if clab != "pw" and clab not in post_labels:
                    post_labels.append(clab)

    checkpoint_labels = [f"pw{i+1}" for i in range(max_pw)] + post_labels

    mat = np.zeros((len(limits), len(checkpoint_labels)))
    for i, lim in enumerate(limits):
        # For each column, collect the hit rate across trials, then median.
        col_values: list[list[float]] = [[] for _ in checkpoint_labels]
        for series in by_limit[lim]:
            pw_idx = 0
            for lab, snap in series:
                clab = _canonicalize_label(lab)
                if clab == "pw":
                    col = pw_idx
                    pw_idx += 1
                else:
                    col = max_pw + post_labels.index(clab)
                if col < len(checkpoint_labels):
                    col_values[col].append(_hit_rate(snap))
        for j, values in enumerate(col_values):
            mat[i, j] = float(np.median(values)) if values else 0.0

    return limits, checkpoint_labels, mat


def plot(by_limit, out: str | None):
    if not by_limit:
        print("No [HIT-STATS-SERIES] lines found.", file=sys.stderr)
        sys.exit(1)

    limits, cps, mat = _build_hit_rate_matrix(by_limit)
    n_lim, n_cp = mat.shape

    fig, ax = plt.subplots(figsize=(max(8, 1.5 * n_lim + 2), 5))

    # X positions: one group per prefetch_limit; bars for each checkpoint
    # within a group.
    bar_w = 0.8 / max(n_cp, 1)
    group_x = np.arange(n_lim)
    cmap = plt.get_cmap("viridis")
    colors = [cmap(k / max(n_cp - 1, 1)) for k in range(n_cp)]

    for j, cp in enumerate(cps):
        offsets = (j - (n_cp - 1) / 2) * bar_w
        ax.bar(
            group_x + offsets,
            mat[:, j],
            width=bar_w,
            color=colors[j],
            edgecolor="white",
            linewidth=0.4,
            label=cp,
        )

    # Annotate walker_done bar (usually the interesting one) with its %.
    if "walker_done" in cps:
        j = cps.index("walker_done")
        offsets = (j - (n_cp - 1) / 2) * bar_w
        for i, val in enumerate(mat[:, j]):
            ax.text(
                group_x[i] + offsets,
                val + 1,
                f"{val:.0f}",
                ha="center",
                va="bottom",
                fontsize=7,
                color="black",
            )

    ax.set_xticks(group_x)
    ax.set_xticklabels([str(l) for l in limits])
    ax.set_xlabel("prefetch_limit")
    ax.set_ylabel("L1 hit rate  (#L1 / #total accesses, %)")
    ax.set_ylim(0, 105)
    ax.set_title(
        "L1 hit rate at each checkpoint, grouped by prefetch_limit  "
        f"·  median over trials",
        fontsize=11,
    )
    ax.grid(axis="y", alpha=0.25)
    ax.legend(
        title="checkpoint",
        loc="lower right",
        ncol=1,
        fontsize=8,
    )
    fig.tight_layout()

    if out:
        fig.savefig(out, dpi=140, bbox_inches="tight")
        print(f"wrote {out}")
    else:
        plt.show()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("logs", nargs="+", help="jac server log files (globs OK)")
    ap.add_argument("--out", help="write PNG instead of interactive show")
    args = ap.parse_args()
    paths = sorted({p for g in args.logs for p in glob.glob(g)})
    by_limit = collect(paths)
    plot(by_limit, args.out)


if __name__ == "__main__":
    main()
