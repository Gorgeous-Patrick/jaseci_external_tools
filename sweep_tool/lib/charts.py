"""Plotly chart builders (interactive versions of the matplotlib plots
in each app's own plot_* scripts)."""

from __future__ import annotations

from collections import defaultdict

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from .parsers import TrialLog

TIERS = ["L1", "L2", "L3", "MISS"]
TIER_COLOR = {"L1": "#2ca02c", "L2": "#e6b800", "L3": "#ff7f0e", "MISS": "#d62728"}


def e2e_stack(df: pd.DataFrame) -> go.Figure:
    """Grouped stacked-vs-side-by-side bar: for each prefetch_limit,
    left bar is e2e stack (walker + ttg + topo + misc), right bar is the
    honest prefetcher wall time."""
    if df.empty:
        return go.Figure()
    med = (
        df.groupby("prefetch_limit")
        .median(numeric_only=True)
        .reset_index()
        .sort_values("prefetch_limit")
    )
    limits = med["prefetch_limit"].astype(int).astype(str).tolist()
    walker = med.get("walker_ms", pd.Series(dtype=float)).fillna(0)
    ttg = med.get("ttg_ms", pd.Series(dtype=float)).fillna(0)
    topo = med.get("topo_idx_ms", pd.Series(dtype=float)).fillna(0)
    prefetch = med.get("prefetch_ms", pd.Series(dtype=float)).fillna(0)
    e2e = med.get("e2e_ms", pd.Series(dtype=float)).fillna(0)
    misc = np.maximum(e2e - (walker + ttg + topo), 0)
    hit_rate = med["l1_hit_rate"].fillna(0) if "l1_hit_rate" in med.columns else None

    fig = go.Figure()
    # E2E stack (left bar of each pair).
    fig.add_bar(
        x=limits, y=walker, name="Walker",
        marker_color="steelblue", offsetgroup="e2e",
        hovertemplate="walker: %{y:.0f} ms<extra></extra>",
    )
    fig.add_bar(
        x=limits, y=ttg, name="TTG",
        marker_color="seagreen", offsetgroup="e2e",
        hovertemplate="ttg: %{y:.0f} ms<extra></extra>",
    )
    fig.add_bar(
        x=limits, y=topo, name="Topology",
        marker_color="mediumpurple", offsetgroup="e2e",
        hovertemplate="topology: %{y:.0f} ms<extra></extra>",
    )
    fig.add_bar(
        x=limits, y=misc, name="Misc",
        marker_color="lightgray", offsetgroup="e2e",
        hovertemplate="misc: %{y:.0f} ms<extra></extra>",
    )
    # Prefetcher wall (right bar).  Distinct offsetgroup to sit alongside.
    fig.add_bar(
        x=limits, y=prefetch, name="Prefetcher (wall)",
        marker_color="orange", offsetgroup="prefetch",
        hovertemplate="prefetch wall: %{y:.0f} ms<extra></extra>",
    )
    # L1 hit rate overlay on secondary y-axis when present.
    if hit_rate is not None:
        fig.add_scatter(
            x=limits, y=hit_rate, name="L1 hit rate",
            mode="lines+markers", yaxis="y2",
            line=dict(color="crimson", width=2),
            marker=dict(color="crimson", size=7),
            hovertemplate="L1 hit: %{y:.1f}%<extra></extra>",
        )
    layout_kwargs = dict(
        barmode="stack",
        title="E2E vs Prefetch Limit — left bar = e2e stack, right bar = prefetch wall (median over trials)",
        xaxis_title="prefetch_limit",
        yaxis_title="Time (ms)",
        legend_title="",
        template="plotly_white",
        margin=dict(l=60, r=20, t=60, b=60),
    )
    if hit_rate is not None:
        layout_kwargs["yaxis2"] = dict(
            title=dict(text="L1 hit rate (%)", font=dict(color="crimson")),
            tickfont=dict(color="crimson"),
            overlaying="y", side="right", range=[0, 105],
            showgrid=False,
        )
    fig.update_layout(**layout_kwargs)
    return fig


def hit_counts_request_done(logs: list[TrialLog]) -> go.Figure:
    """Cumulative tier hits at request_done, stacked, grouped by limit."""
    if not logs:
        return go.Figure()
    by_limit_tier: dict[int, dict[str, list[int]]] = defaultdict(lambda: {t: [] for t in TIERS})
    for tl in logs:
        for label, snap in tl.hit_stats_series:
            if label == "request_done":
                for t in TIERS:
                    by_limit_tier[tl.limit][t].append(snap.get(t, 0))
    if not by_limit_tier:
        return go.Figure()
    limits = sorted(by_limit_tier.keys())
    x = [str(l) for l in limits]

    fig = go.Figure()
    for tier in TIERS:
        y = [
            int(np.median(by_limit_tier[l][tier])) if by_limit_tier[l][tier] else 0
            for l in limits
        ]
        if max(y) == 0:
            continue  # skip always-zero tiers
        fig.add_bar(
            x=x, y=y, name=tier,
            marker_color=TIER_COLOR[tier],
            hovertemplate=f"{tier}: %{{y}} accesses<extra></extra>",
        )
    fig.update_layout(
        barmode="stack",
        title="Cumulative accesses per request at request_done, by tier",
        xaxis_title="prefetch_limit",
        yaxis_title="Accesses (median over trials)",
        template="plotly_white",
        margin=dict(l=60, r=20, t=60, b=60),
    )
    return fig


def hit_counts_pw_phase(logs: list[TrialLog]) -> go.Figure:
    """One stacked bar per (limit, pw checkpoint) — bar height = cumulative
    accesses at that pw, tier-split.  Grouped by limit, pw checkpoints
    side-by-side within a group."""
    if not logs:
        return go.Figure()

    def _folded(label: str) -> str:
        return "pw" if label.startswith("prefetch_pre_write_shard=") else label

    def _pw_index(series):
        n = 0
        for lab, _ in series:
            if _folded(lab) == "pw":
                n += 1
        return n

    limits = sorted({tl.limit for tl in logs})
    max_pw = max((_pw_index(tl.hit_stats_series) for tl in logs), default=0)
    if max_pw == 0:
        return go.Figure()

    # (limit, pw_idx) -> tier -> list of counts
    cell: dict[tuple[int, int], dict[str, list[int]]] = defaultdict(
        lambda: {t: [] for t in TIERS}
    )
    for tl in logs:
        idx = 0
        for lab, snap in tl.hit_stats_series:
            if _folded(lab) != "pw":
                continue
            for t in TIERS:
                cell[(tl.limit, idx)][t].append(snap.get(t, 0))
            idx += 1

    x_limits = [str(l) for l in limits]
    fig = go.Figure()
    added_tier_legend: set[str] = set()
    for pw in range(max_pw):
        offset_group = f"pw{pw+1}"
        for tier in TIERS:
            y = [
                int(np.median(cell[(l, pw)][tier])) if cell[(l, pw)][tier] else 0
                for l in limits
            ]
            if max(y) == 0:
                continue
            show_legend = tier not in added_tier_legend
            added_tier_legend.add(tier)
            fig.add_bar(
                x=x_limits, y=y, name=tier,
                offsetgroup=offset_group,
                marker_color=TIER_COLOR[tier],
                legendgroup=tier,
                showlegend=show_legend,
                hovertemplate=(
                    f"{tier} @ pw{pw+1}: "
                    "%{y} accesses<extra></extra>"
                ),
            )
    fig.update_layout(
        barmode="stack",
        title=f"Prefetch-phase accesses ({max_pw} pw checkpoint(s) per limit, side-by-side)",
        xaxis_title="prefetch_limit",
        yaxis_title="Accesses at each pw (median)",
        template="plotly_white",
        margin=dict(l=60, r=20, t=60, b=60),
    )
    return fig


def worker_times(logs: list[TrialLog]) -> go.Figure:
    """Box plot of per-worker prefetch durations per prefetch_limit."""
    if not logs:
        return go.Figure()
    rows = []
    for tl in logs:
        for i, ms in enumerate(tl.worker_times_ms):
            rows.append({"limit": tl.limit, "worker_idx": i, "ms": ms})
    if not rows:
        return go.Figure()
    df = pd.DataFrame(rows)
    fig = go.Figure()
    for lim in sorted(df["limit"].unique()):
        s = df[df["limit"] == lim]
        fig.add_box(
            y=s["ms"], name=str(int(lim)),
            boxmean=True,
            hovertemplate="%{y:.1f} ms<extra>limit=" + str(int(lim)) + "</extra>",
        )
    fig.update_layout(
        title="Per-worker prefetch wall time (max of the box ≈ prefetch_ms CSV column)",
        xaxis_title="prefetch_limit",
        yaxis_title="Worker duration (ms)",
        template="plotly_white",
        showlegend=False,
        margin=dict(l=60, r=20, t=60, b=60),
    )
    return fig


def csv_raw(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    return df.sort_values(["prefetch_limit", "trial"])
