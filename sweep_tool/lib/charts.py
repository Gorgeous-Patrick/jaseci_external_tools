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
POLICY_COLOR = {
    "oracle": "#2ca02c",
    "ttg": "#1f77b4",
    "none": "#7f7f7f",
    "markov": "#9467bd",
    "markov1-pooled": "#8c564b",
    "coaccess": "#e377c2",
    "coaccess-pooled": "#bcbd22",
    "history": "#ff7f0e",
    "manual": "#17becf",
}
POLICY_ORDER = {
    "oracle": 0,
    "none": 1,
    "ttg": 2,
    "markov": 3,
    "markov1-pooled": 4,
    "coaccess": 5,
    "coaccess-pooled": 6,
    "history": 7,
    "manual": 8,
}

JACORD_TTG_HIDDEN_ROOT_PREFETCH = 200


def _df_group_cols(df: pd.DataFrame) -> list[str]:
    if "policy" in df.columns:
        return ["policy", "prefetch_limit"]
    return ["prefetch_limit"]


def _df_labels(df: pd.DataFrame) -> list[str]:
    if "policy" in df.columns:
        return [
            f"{row.policy}:{int(row.prefetch_limit)}"
            for row in df[["policy", "prefetch_limit"]].itertuples(index=False)
        ]
    return df["prefetch_limit"].astype(int).astype(str).tolist()


def _log_key(tl: TrialLog) -> tuple[str, int]:
    return (tl.policy or "", tl.limit)


def _log_label(key: tuple[str, int]) -> str:
    policy, limit = key
    return f"{policy}:{limit}" if policy else str(limit)


def _sort_log_keys(keys) -> list[tuple[str, int]]:
    return sorted(keys, key=lambda k: (k[0], k[1]))


def _policy_sort_key(policy: str) -> tuple[int, str]:
    base = _policy_base(policy)
    return (POLICY_ORDER.get(base, len(POLICY_ORDER)), policy)


def _policy_color(policy: str) -> str | None:
    return POLICY_COLOR.get(policy) or POLICY_COLOR.get(_policy_base(policy))


def _policy_base(policy: str) -> str:
    if policy.startswith("markov1-pooled"):
        return "markov1-pooled"
    if policy.startswith("coaccess-pooled"):
        return "coaccess-pooled"
    return policy


def _format_limit(value: float) -> str:
    value = float(value)
    return str(int(value)) if value.is_integer() else f"{value:g}"


def _jacord_ttg_overfetch_adjustment(tl: TrialLog) -> int:
    if tl.policy != "ttg":
        return 0
    if not any(parent.name == "jacord" for parent in tl.source.parents):
        return 0
    return JACORD_TTG_HIDDEN_ROOT_PREFETCH


def _hide_repeated_none_baseline(df: pd.DataFrame) -> pd.DataFrame:
    if "policy" not in df.columns:
        return df
    is_none = df["policy"].astype(str).str.lower() == "none"
    is_nonzero_limit = pd.to_numeric(df["prefetch_limit"], errors="coerce").fillna(0) > 0
    return df[~(is_none & is_nonzero_limit)]


def _positioned_policy_limit_bars(
    df: pd.DataFrame,
) -> tuple[pd.DataFrame, list[float], float]:
    """Add compact numeric x positions for per-limit grouped policy bars."""
    out = df.copy()
    limits = sorted(out["prefetch_limit"].unique())
    limit_index = {limit: i for i, limit in enumerate(limits)}
    policies_by_limit = {
        limit: sorted(
            out.loc[out["prefetch_limit"] == limit, "policy"].unique(),
            key=_policy_sort_key,
        )
        for limit in limits
    }
    max_bars = max((len(policies) for policies in policies_by_limit.values()), default=1)
    bar_width = min(0.30, 0.78 / max_bars)

    x = []
    for row in out.itertuples(index=False):
        policies_at_limit = policies_by_limit[row.prefetch_limit]
        rank = policies_at_limit.index(row.policy)
        offset = (rank - (len(policies_at_limit) - 1) / 2) * bar_width
        x.append(limit_index[row.prefetch_limit] + offset)

    out["_x"] = x
    out["_limit_order"] = out["prefetch_limit"].map(limit_index)
    out["_policy_order"] = out["policy"].map(
        lambda policy: POLICY_ORDER.get(_policy_base(policy), len(POLICY_ORDER))
    )
    out = out.sort_values(["_limit_order", "_policy_order", "policy"]).reset_index(drop=True)
    return out, limits, bar_width


def l1_hit_rate_by_policy(df: pd.DataFrame) -> go.Figure:
    """Grouped bars of median L1 hit rate by prefetch limit and policy."""
    if df.empty or "l1_hit_rate" not in df.columns or "prefetch_limit" not in df.columns:
        return go.Figure()

    work = df.copy()
    work["l1_hit_rate"] = pd.to_numeric(work["l1_hit_rate"], errors="coerce")
    work["prefetch_limit"] = pd.to_numeric(work["prefetch_limit"], errors="coerce")
    work = work.dropna(subset=["l1_hit_rate", "prefetch_limit"])
    if work.empty:
        return go.Figure()
    if "policy" not in work.columns:
        work["policy"] = "default"
    work["policy"] = work["policy"].fillna("default").astype(str).str.lower()
    work = _hide_repeated_none_baseline(work)
    if work.empty:
        return go.Figure()

    stats = (
        work.groupby(["policy", "prefetch_limit"])["l1_hit_rate"]
        .agg(
            median="median",
            p25=lambda s: s.quantile(0.25),
            p75=lambda s: s.quantile(0.75),
            trials="count",
        )
        .reset_index()
        .sort_values(["policy", "prefetch_limit"])
    )
    if stats.empty:
        return go.Figure()

    fig = go.Figure()
    stats, limits, bar_width = _positioned_policy_limit_bars(stats)
    policies = sorted(stats["policy"].unique(), key=_policy_sort_key)
    for policy in policies:
        s = stats[stats["policy"] == policy].sort_values("prefetch_limit")
        upper = np.maximum(s["p75"] - s["median"], 0)
        lower = np.maximum(s["median"] - s["p25"], 0)
        custom = np.stack(
            [s["prefetch_limit"], s["p25"], s["p75"], s["trials"]],
            axis=-1,
        )
        fig.add_bar(
            x=s["_x"],
            y=s["median"],
            width=[bar_width * 0.86] * len(s),
            name=policy,
            marker_color=_policy_color(policy),
            error_y=dict(
                type="data",
                array=upper,
                arrayminus=lower,
                visible=bool((upper > 0).any() or (lower > 0).any()),
                thickness=1.2,
                width=3,
            ),
            customdata=custom,
            hovertemplate=(
                "policy=%{fullData.name}<br>"
                "prefetch_limit=%{customdata[0]:.0f}<br>"
                "median L1=%{y:.1f}%<br>"
                "IQR=%{customdata[1]:.1f}%-"
                "%{customdata[2]:.1f}%<br>"
                "trials=%{customdata[3]:.0f}"
                "<extra></extra>"
            ),
        )

    fig.update_layout(
        title="L1 hit rate by policy (median over trials)",
        barmode="overlay",
        xaxis=dict(
            title="prefetch_limit",
            tickmode="array",
            tickvals=list(range(len(limits))),
            ticktext=[_format_limit(limit) for limit in limits],
        ),
        yaxis_title="L1 hit rate (%)",
        yaxis=dict(range=[0, 105], ticksuffix="%"),
        legend_title="policy",
        template="plotly_white",
        margin=dict(l=60, r=20, t=60, b=60),
    )
    return fig


def cache_tier_mix(df: pd.DataFrame) -> go.Figure:
    """100% stacked tier mix bars by prefetch limit and policy."""
    tier_cols = {"L1": "l1", "L2": "l2", "L3": "l3", "MISS": "miss"}
    required = {"prefetch_limit", *tier_cols.values()}
    if df.empty or not required.issubset(df.columns):
        return go.Figure()

    work = df.copy()
    for col in required:
        work[col] = pd.to_numeric(work[col], errors="coerce")
    work = work.dropna(subset=["prefetch_limit"])
    if work.empty:
        return go.Figure()
    if "policy" not in work.columns:
        work["policy"] = "default"
    work["policy"] = work["policy"].fillna("default").astype(str).str.lower()
    work = _hide_repeated_none_baseline(work)
    if work.empty:
        return go.Figure()

    med = (
        work.groupby(["policy", "prefetch_limit"])[list(tier_cols.values())]
        .median()
        .reset_index()
        .sort_values(["policy", "prefetch_limit"])
    )
    med["total"] = med[list(tier_cols.values())].fillna(0).sum(axis=1)
    med = med[med["total"] > 0].copy()
    if med.empty:
        return go.Figure()

    for tier, col in tier_cols.items():
        med[f"{tier}_pct"] = med[col].fillna(0) * 100.0 / med["total"]

    med, _limits, bar_width = _positioned_policy_limit_bars(med)
    fig = go.Figure()
    for tier, col in tier_cols.items():
        custom = [
            [row.policy, row.prefetch_limit, getattr(row, col), row.total]
            for row in med.itertuples(index=False)
        ]
        fig.add_bar(
            x=med["_x"],
            y=med[f"{tier}_pct"],
            width=[bar_width * 0.86] * len(med),
            name=tier,
            marker_color=TIER_COLOR[tier],
            customdata=custom,
            hovertemplate=(
                "policy=%{customdata[0]}<br>"
                "prefetch_limit=%{customdata[1]:.0f}<br>"
                f"{tier}=%{{customdata[2]:.0f}} / "
                "%{customdata[3]:.0f}<br>"
                "share=%{y:.1f}%"
                "<extra></extra>"
            ),
        )

    fig.update_layout(
        title="Cache tier mix by policy (median counts, normalized to 100%)",
        barmode="stack",
        xaxis=dict(
            title="prefetch_limit / policy",
            tickmode="array",
            tickvals=med["_x"],
            ticktext=[
                f"{_format_limit(row.prefetch_limit)}<br>{row.policy}"
                for row in med.itertuples(index=False)
            ],
            tickangle=0,
        ),
        yaxis=dict(title="Share of tier touches", range=[0, 100], ticksuffix="%"),
        legend_title="tier",
        template="plotly_white",
        margin=dict(l=60, r=20, t=60, b=80),
    )
    return fig


def hit_rate_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Compact per-policy summary for the Analyze tab."""
    required = {"prefetch_limit", "l1_hit_rate", "l1", "l2", "l3", "miss"}
    if df.empty or not required.issubset(df.columns):
        return pd.DataFrame()

    work = df.copy()
    if "policy" not in work.columns:
        work["policy"] = "default"
    work["policy"] = work["policy"].fillna("default").astype(str).str.lower()
    for col in required:
        work[col] = pd.to_numeric(work[col], errors="coerce")
    work = work.dropna(subset=["prefetch_limit", "l1_hit_rate"])
    if work.empty:
        return pd.DataFrame()
    work["undercoverage"] = work["l3"].fillna(0) + work["miss"].fillna(0)

    med = (
        work.groupby(["policy", "prefetch_limit"])
        .agg(
            l1_hit_rate=("l1_hit_rate", "median"),
            undercoverage=("undercoverage", "median"),
            l1=("l1", "median"),
            l2=("l2", "median"),
            l3=("l3", "median"),
            miss=("miss", "median"),
            trials=("trial", "count") if "trial" in work.columns else ("l1_hit_rate", "count"),
        )
        .reset_index()
    )
    if med.empty:
        return pd.DataFrame()

    rows = []
    for policy in sorted(med["policy"].unique(), key=_policy_sort_key):
        p = med[med["policy"] == policy].sort_values("prefetch_limit")
        best_hit = p.sort_values(
            ["l1_hit_rate", "undercoverage", "prefetch_limit"],
            ascending=[False, True, True],
        ).iloc[0]
        best_under = p.sort_values(
            ["undercoverage", "l1_hit_rate", "prefetch_limit"],
            ascending=[True, False, True],
        ).iloc[0]
        rows.append(
            {
                "policy": policy,
                "best_l1_hit_rate": f"{best_hit.l1_hit_rate:.1f}%",
                "best_l1_limit": int(best_hit.prefetch_limit),
                "lowest_undercoverage": int(best_under.undercoverage),
                "lowest_undercoverage_limit": int(best_under.prefetch_limit),
                "median_L1_at_best": int(best_hit.l1),
                "median_L3_at_best": int(best_hit.l3),
                "trials_at_best": int(best_hit.trials),
            }
        )
    return pd.DataFrame(rows)


def e2e_stack(df: pd.DataFrame) -> go.Figure:
    """Grouped stacked-vs-side-by-side bar: for each prefetch_limit,
    left bar is e2e stack (walker + ttg + topo + misc), right bar is the
    honest prefetcher wall time."""
    if df.empty:
        return go.Figure()
    group_cols = _df_group_cols(df)
    med = (
        df.groupby(group_cols)
        .median(numeric_only=True)
        .reset_index()
        .sort_values(group_cols)
    )
    limits = _df_labels(med)
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
    by_limit_tier: dict[tuple[str, int], dict[str, list[int]]] = defaultdict(lambda: {t: [] for t in TIERS})
    for tl in logs:
        for label, snap in tl.hit_stats_series:
            if label == "request_done":
                for t in TIERS:
                    by_limit_tier[_log_key(tl)][t].append(snap.get(t, 0))
    if not by_limit_tier:
        return go.Figure()
    limits = _sort_log_keys(by_limit_tier.keys())
    x = [_log_label(l) for l in limits]

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

    limits = _sort_log_keys({_log_key(tl) for tl in logs})
    max_pw = max((_pw_index(tl.hit_stats_series) for tl in logs), default=0)
    if max_pw == 0:
        return go.Figure()

    # (limit, pw_idx) -> tier -> list of counts
    cell: dict[tuple[tuple[str, int], int], dict[str, list[int]]] = defaultdict(
        lambda: {t: [] for t in TIERS}
    )
    for tl in logs:
        idx = 0
        for lab, snap in tl.hit_stats_series:
            if _folded(lab) != "pw":
                continue
            for t in TIERS:
                cell[(_log_key(tl), idx)][t].append(snap.get(t, 0))
            idx += 1

    x_limits = [_log_label(l) for l in limits]
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
            rows.append({"case": _log_label(_log_key(tl)), "worker_idx": i, "ms": ms})
    if not rows:
        return go.Figure()
    df = pd.DataFrame(rows)
    fig = go.Figure()
    for case in sorted(df["case"].unique()):
        s = df[df["case"] == case]
        fig.add_box(
            y=s["ms"], name=str(case),
            boxmean=True,
            hovertemplate="%{y:.1f} ms<extra>" + str(case) + "</extra>",
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


def coverage(df: pd.DataFrame, logs: list[TrialLog]) -> go.Figure:
    """Overfetch and undercoverage per prefetch limit.

    Overfetch = plan_size - distinct_covered, the plan slots that never
    served a walker read from L1/L2.  distinct_covered is the count of
    unique anchor IDs in the sibling access_log with tier L1 or L2
    (i.e. served from a TTG-populated cache tier), so a walker that reads
    the same node twice doesn't inflate coverage.

    Undercoverage = l3 + miss, the walker's tier touches that fell
    through the plan to the on-demand cache-through path.

    Both are counts per request (median over trials).  If the log-side
    coverage info is missing (older runs, or the access_log wasn't
    written), the overfetch trace is skipped.
    """
    if df.empty:
        return go.Figure()

    # Undercoverage from the CSV.
    if "l3" not in df.columns or "miss" not in df.columns:
        return go.Figure()
    group_cols = _df_group_cols(df)
    under = (
        df.assign(under=lambda d: d["l3"].fillna(0) + d["miss"].fillna(0))
        .groupby(group_cols)["under"]
        .median()
        .reset_index()
        .sort_values(group_cols)
    )

    # Overfetch from the per-trial coverage log + access_log.
    over_rows = [
        {
            "prefetch_limit": tl.limit,
            "policy": tl.policy,
            "overfetch": (
                max(tl.plan_size - tl.distinct_covered, 0)
                + _jacord_ttg_overfetch_adjustment(tl)
            ),
        }
        for tl in logs
        if tl.plan_size > 0 and tl.distinct_ids_by_tier
    ]
    if over_rows:
        over = (
            pd.DataFrame(over_rows)
            .groupby(["policy", "prefetch_limit"] if "policy" in df.columns else ["prefetch_limit"])["overfetch"]
            .median()
            .reset_index()
            .sort_values(["policy", "prefetch_limit"] if "policy" in df.columns else ["prefetch_limit"])
        )
    else:
        over = None

    limits = _df_labels(under)
    fig = go.Figure()
    fig.add_bar(
        x=limits, y=under["under"], name="Undercoverage (L3 + MISS)",
        marker_color="#d62728",
        hovertemplate="undercoverage: %{y:.0f}<extra></extra>",
    )
    if over is not None and not over.empty:
        over_limits = _df_labels(over)
        fig.add_bar(
            x=over_limits, y=over["overfetch"], name="Overfetch (TTG includes hidden roots)",
            marker_color="#ff7f0e",
            hovertemplate="overfetch: %{y:.0f}<extra></extra>",
        )
    fig.update_layout(
        barmode="group",
        title="Overfetch vs undercoverage (median over trials, per prefetch limit)",
        xaxis_title="prefetch_limit",
        yaxis_title="Nodes",
        template="plotly_white",
        margin=dict(l=60, r=20, t=60, b=60),
    )
    return fig


DB_OPS = [
    "node_pages", "hop_rows", "edge_endpoints", "existing_ids",
    "filter_ids", "batch_get", "get",
]
DB_OP_COLOR = {
    "node_pages": "#1f77b4",
    "hop_rows": "#ff7f0e",
    "edge_endpoints": "#2ca02c",
    "existing_ids": "#9467bd",
    "filter_ids": "#8c564b",
    "batch_get": "#e377c2",
    "get": "#7f7f7f",
}


def db_access_by_op(logs: list[TrialLog]) -> go.Figure:
    """Stacked bar per prefetch_limit: real DB read volume (docs/rows served
    from L3), split by storage operation, from the extended access log
    (op,tier,n_in,n_out,type).

    This is the true DB-pressure view — every request that reached the store,
    not just the get/batch_get object path.  Prefetch's effect shows up as a
    collapsing ``node_pages`` slice (the projection is pre-warmed) and a
    shrinking ``hop_rows`` slice (fewer adjacency misses hit the DB).
    Median over trials.  Empty for old-schema (id,tier,type) runs.
    """
    if not logs:
        return go.Figure()
    # (policy, limit) -> op -> list of per-trial db_docs
    by: dict[tuple[str, int], dict[str, list[int]]] = defaultdict(lambda: defaultdict(list))
    any_data = False
    for tl in logs:
        if not tl.db_ops:
            continue
        any_data = True
        for op, d in tl.db_ops.items():
            by[_log_key(tl)][op].append(d.get("db_docs", 0))
    if not any_data:
        return go.Figure()

    limits = _sort_log_keys(by.keys())
    x = [_log_label(l) for l in limits]
    # any op present in the data but not in our known list gets appended
    ops = DB_OPS + sorted(
        {op for lim in by.values() for op in lim} - set(DB_OPS)
    )
    fig = go.Figure()
    for op in ops:
        y = [
            int(np.median(by[l][op])) if by[l].get(op) else 0
            for l in limits
        ]
        if max(y) == 0:
            continue
        fig.add_bar(
            x=x, y=y, name=op,
            marker_color=DB_OP_COLOR.get(op, "#333333"),
            hovertemplate=f"{op}: %{{y}} docs<extra></extra>",
        )
    fig.update_layout(
        barmode="stack",
        title="DB read volume by operation (docs/rows from L3, median over trials)",
        xaxis_title="prefetch_limit",
        yaxis_title="Docs/rows read from DB",
        template="plotly_white",
        margin=dict(l=60, r=20, t=60, b=60),
    )
    return fig


def csv_raw(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    cols = ["policy", "prefetch_limit", "trial"] if "policy" in df.columns else ["prefetch_limit", "trial"]
    return df.sort_values(cols)
