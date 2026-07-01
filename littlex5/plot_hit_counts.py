#!/usr/bin/env python3
"""Plot cumulative tier-hit counts, grouped by prefetch_limit.

Two panels sharing the same X grouping:

  TOP    — request_done only.  One stacked bar per prefetch_limit,
           height = total accesses over the whole request, split by tier
           (L1/L2/L3/MISS).  The headline "how much did the walker read
           and from where" number.

  BOTTOM — pw phase only.  Each pw checkpoint is its own stacked bar
           within the group.  Reveals what tier the walker's early
           reads landed on while the prefetch workers were still
           writing L1.  Under thread mode with fast workers the pw bars
           are often tiny and very similar; that's expected and itself
           informative.

Both panels drop any tier that is always zero from their legend
(usually L2 and MISS on load_feed).  Trials are median-aggregated per
tier so noise doesn't smear the picture.

Log filenames must match:

    jac_server_<walker>_limit<N>_trial<I>.log

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
    if label.startswith("prefetch_pre_write_shard="):
        return "pw"
    return label


def _build_count_matrix(by_limit):
    """Return (limits, checkpoint_labels, mat[i, j, k])."""
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
        cell_vals = [[[] for _ in TIERS] for _ in checkpoint_labels]
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


def _draw_stacked_group(
    ax,
    group_x,
    limits,
    checkpoints,
    counts_3d,
    tier_active,
    annotate_totals: bool,
    color_by_tier: bool = True,
):
    """counts_3d shape: (n_limits, n_checkpoints, len(TIERS))."""
    n_lim = counts_3d.shape[0]
    n_cp = counts_3d.shape[1]
    bar_w = 0.8 / max(n_cp, 1)
    labelled_tiers = set()

    for j in range(n_cp):
        offset = (j - (n_cp - 1) / 2) * bar_w
        bottom = np.zeros(n_lim)
        for k, tier in enumerate(TIERS):
            heights = counts_3d[:, j, k]
            label = None
            if color_by_tier and tier_active[tier] and tier not in labelled_tiers:
                label = tier
                labelled_tiers.add(tier)
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

        if annotate_totals:
            for i, total in enumerate(bottom):
                if total > 0:
                    ax.text(
                        group_x[i] + offset,
                        total + bottom.max() * 0.015,
                        f"{int(total)}",
                        ha="center",
                        va="bottom",
                        fontsize=7,
                    )

    ax.set_xticks(group_x)
    ax.set_xticklabels([str(l) for l in limits])
    ax.set_xlabel("prefetch_limit")
    ax.grid(axis="y", alpha=0.25)


def plot(by_limit, out: str | None):
    if not by_limit:
        print("No [HIT-STATS-SERIES] lines found.", file=sys.stderr)
        sys.exit(1)

    limits, cps, mat = _build_count_matrix(by_limit)
    n_lim = mat.shape[0]

    # Which tiers actually show data anywhere? Skip empty ones from legends.
    tier_active = {tier: bool(mat[:, :, k].max() > 0) for k, tier in enumerate(TIERS)}

    # Separate the checkpoint matrix into (a) request_done column and
    # (b) the pw* columns.
    if "request_done" in cps:
        rd_idx = cps.index("request_done")
        rd_mat = mat[:, rd_idx : rd_idx + 1, :]  # (n_lim, 1, len(TIERS))
    else:
        rd_mat = np.zeros((n_lim, 0, len(TIERS)))

    pw_indices = [j for j, c in enumerate(cps) if c.startswith("pw")]
    pw_mat = mat[:, pw_indices, :]
    pw_labels = [cps[j] for j in pw_indices]

    # Two-panel figure: top = request_done totals, bottom = pw phase.
    fig, (ax_top, ax_bot) = plt.subplots(
        2, 1,
        figsize=(max(9, 1.6 * n_lim + 2), 8),
        gridspec_kw={"height_ratios": [1, 1]},
    )
    group_x = np.arange(n_lim)

    # ---- top panel: request_done ----
    _draw_stacked_group(
        ax_top,
        group_x,
        limits,
        ["request_done"],
        rd_mat,
        tier_active,
        annotate_totals=True,
    )
    ax_top.set_ylabel("Cumulative accesses at request_done")
    ax_top.set_title("Total accesses per request, by tier", fontsize=10, pad=18)
    if any(tier_active[t] for t in TIERS):
        ax_top.legend(title="tier", loc="upper left", fontsize=9)

    # ---- bottom panel: pw phase ----
    _draw_stacked_group(
        ax_bot,
        group_x,
        limits,
        pw_labels,
        pw_mat,
        tier_active,
        annotate_totals=False,
    )
    ax_bot.set_ylabel("Cumulative accesses at each pw checkpoint")
    ax_bot.set_title(
        f"Prefetch-phase accesses — {len(pw_labels)} pw checkpoint(s) per group",
        fontsize=10,
    )

    # Add per-bar pw labels directly under each bar, sitting between the
    # bars and the major prefetch_limit tick label.  We use ax.text with
    # axis coordinates on X and figure coordinates on Y so the labels sit
    # at a fixed vertical offset regardless of Y-scale.  Minor xticks
    # would collide with major xticks at the same position (that's why
    # pw3 was invisible — the group-center major tick hid it).
    if pw_labels:
        bar_w = 0.8 / max(len(pw_labels), 1)
        # Push the major (prefetch_limit) tick label down to make room.
        ax_bot.tick_params(axis="x", which="major", pad=22, length=0)
        # Text annotations for each pw bar.
        from matplotlib.transforms import blended_transform_factory
        trans = blended_transform_factory(ax_bot.transData, ax_bot.transAxes)
        for i in range(n_lim):
            for j, lab in enumerate(pw_labels):
                offset = (j - (len(pw_labels) - 1) / 2) * bar_w
                ax_bot.text(
                    group_x[i] + offset,
                    -0.02,             # slightly below the axis, in axes coords
                    lab,
                    ha="center",
                    va="top",
                    fontsize=6,
                    rotation=90,
                    transform=trans,
                    clip_on=False,
                )

    if any(tier_active[t] for t in TIERS):
        ax_bot.legend(title="tier", loc="upper left", fontsize=9)

    fig.suptitle(
        "Hit-stats counts, grouped by prefetch_limit  ·  median over trials",
        fontsize=11,
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
