#!/usr/bin/env python3
"""Plot cumulative tier-hit counts at each checkpoint, grouped by prefetch_limit.

Companion to plot_hit_stats.py. Where plot_hit_stats.py shows the L1
hit-rate percentage per bar, this one shows the *absolute number* of
tier accesses at each checkpoint, stacked by tier (L1 / L2 / L3 / MISS).

Bar height at a checkpoint = total accesses accumulated up to that
event. Stack colours reveal *which tier* answered those accesses.

Parses `[HIT-STATS-SERIES]` info lines from jac server logs. Log
filenames must match:

    jac_server_<walker>_limit<N>_trial<I>.log

Missing checkpoints (e.g. no prefetch phase at limit=0) render as an
empty stack. Trials are median-aggregated per tier so noise doesn't
smear the picture.

Usage:
    python3 plot_hit_counts.py logs/jac_server_*.log
    python3 plot_hit_counts.py --out hit_counts.png logs/jac_server_*.log
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
COLORS = {"L1": "#2ca02c", "L2": "#e6b800", "L3": "#ff7f0e", "MISS": "#d62728"}
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
    """prefetch_pre_write_shard=<N>  ->  pw (order preserved within series)."""
    if label.startswith("prefetch_pre_write_shard="):
        return "pw"
    return label


def _build_count_matrix(by_limit):
    """Return (limits, checkpoint_labels, mat[i, j, k]) where k indexes
    the four TIERS. Median across trials per tier."""
    limits = sorted(by_limit.keys())

    max_pw = 0
    post_labels: list[str] = []
    for series_list in by_limit.values():
        for series in series_list:
            pw_count = sum(
                1 for lab, _ in series
                if _canonicalize_label(lab) == "pw"
            )
            max_pw = max(max_pw, pw_count)
            for lab, _ in series:
                clab = _canonicalize_label(lab)
                if clab != "pw" and clab not in post_labels:
                    post_labels.append(clab)

    checkpoint_labels = [f"pw{i+1}" for i in range(max_pw)] + post_labels

    mat = np.zeros((len(limits), len(checkpoint_labels), len(TIERS)))
    for i, lim in enumerate(limits):
        # For each (checkpoint, tier), collect values across trials then median.
        cell_vals = [
            [[] for _ in TIERS] for _ in checkpoint_labels
        ]
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
                    for k, tier in enumerate(TIERS):
                        cell_vals[col][k].append(snap.get(tier, 0))
        for j in range(len(checkpoint_labels)):
            for k in range(len(TIERS)):
                vals = cell_vals[j][k]
                mat[i, j, k] = float(np.median(vals)) if vals else 0.0

    return limits, checkpoint_labels, mat


def plot(by_limit, out: str | None):
    if not by_limit:
        print("No [HIT-STATS-SERIES] lines found.", file=sys.stderr)
        sys.exit(1)

    limits, cps, mat = _build_count_matrix(by_limit)
    n_lim, n_cp, _ = mat.shape

    fig, ax = plt.subplots(figsize=(max(9, 1.6 * n_lim + 2), 5.5))

    bar_w = 0.8 / max(n_cp, 1)
    group_x = np.arange(n_lim)

    # Skip tiers that are always zero from the legend so a viewer isn't
    # told about L2/MISS on runs where they never fire. Still draw the
    # zero-height bar so all stacks stay aligned; just don't register
    # the label.
    tier_active = {tier: bool(mat[:, :, k].max() > 0) for k, tier in enumerate(TIERS)}

    # Draw one stacked bar per (limit, checkpoint). Register each active
    # tier's label exactly once.
    labelled = set()
    for j, cp in enumerate(cps):
        offset = (j - (n_cp - 1) / 2) * bar_w
        bottom = np.zeros(n_lim)
        for k, tier in enumerate(TIERS):
            heights = mat[:, j, k]
            label = None
            if tier_active[tier] and tier not in labelled:
                label = tier
                labelled.add(tier)
            ax.bar(
                group_x + offset,
                heights,
                width=bar_w,
                bottom=bottom,
                color=COLORS[tier],
                edgecolor="white",
                linewidth=0.3,
                label=label,
            )
            bottom += heights

        # Small caption naming the checkpoint under the bar cluster,
        # rotated so it doesn't collide with neighbours.
        # Only annotate the middle group to avoid clutter.
        if n_lim > 0:
            mid = n_lim // 2
            ax.text(
                group_x[mid] + offset,
                -mat[mid].sum(axis=1).max() * 0.02,
                cp,
                rotation=90,
                ha="center",
                va="top",
                fontsize=6.5,
                color="dimgray",
            )

    # Annotate final (request_done) bar with the total accesses.
    if "request_done" in cps:
        j = cps.index("request_done")
        offset = (j - (n_cp - 1) / 2) * bar_w
        totals = mat[:, j, :].sum(axis=1)
        for i, t in enumerate(totals):
            if t > 0:
                ax.text(
                    group_x[i] + offset,
                    t + totals.max() * 0.01,
                    f"{int(t)}",
                    ha="center",
                    va="bottom",
                    fontsize=7,
                )

    ax.set_xticks(group_x)
    ax.set_xticklabels([str(l) for l in limits])
    ax.set_xlabel("prefetch_limit")
    ax.set_ylabel("Cumulative accesses  (count)")
    ax.set_title(
        "Tier-hit counts at each checkpoint, grouped by prefetch_limit  "
        "·  median over trials  ·  "
        f"{n_cp} checkpoints per group",
        fontsize=10,
    )
    ax.grid(axis="y", alpha=0.25)
    ax.legend(title="tier", loc="upper left", fontsize=9)
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
