"""Plotly chart builders (interactive versions of the matplotlib plots
in each app's own plot_* scripts)."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
import pstats

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
    "selep": "#636efa",
}
POLICY_ORDER = {
    "none": 0,
    "ttg": 1,
    "oracle": 2,
    "selep": 3,
    "markov": 4,
    "markov1-pooled": 5,
    "coaccess": 6,
    "coaccess-pooled": 7,
    "history": 8,
    "manual": 9,
}

JACORD_TTG_HIDDEN_ROOT_PREFETCH = 200

MEMORY_SOCKET_FUNC_MARKERS = ("recv", "recv_into", "send", "sendall")
MEMORY_SOCKET_CALLER_MARKERS = (
    "/site-packages/psycopg/",
    "/site-packages/psycopg2/",
    "/jaclang/data/pg",
    "/jaclang/data/impl/pg",
    "/site-packages/redis/",
    "/site-packages/pymongo/",
)


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


def db_request_count(df: pd.DataFrame, logs: list[TrialLog]) -> go.Figure:
    """Median number of requests that reached the backing store.

    Prefer the extended access log's operation-level call counts. Older runs
    only have tier rows, so fall back to L3+MISS counts from the sweep CSV.
    """
    fig = _db_request_count_from_logs(logs)
    if fig.data:
        return fig
    return _db_request_count_from_csv(df)


def _db_request_count_from_logs(logs: list[TrialLog]) -> go.Figure:
    by: dict[tuple[str, int], dict[str, list[int]]] = defaultdict(lambda: defaultdict(list))
    any_data = False
    for tl in logs:
        if not tl.db_ops:
            continue
        any_data = True
        for op, d in tl.db_ops.items():
            by[_log_key(tl)][op].append(d.get("db_calls", 0))
    if not any_data:
        return go.Figure()

    limits = _sort_log_keys(by.keys())
    x = [_log_label(limit) for limit in limits]
    ops = DB_OPS + sorted({op for lim in by.values() for op in lim} - set(DB_OPS))
    fig = go.Figure()
    for op in ops:
        y = [int(np.median(by[limit][op])) if by[limit].get(op) else 0 for limit in limits]
        if max(y) == 0:
            continue
        fig.add_bar(
            x=x,
            y=y,
            name=op,
            marker_color=DB_OP_COLOR.get(op, "#333333"),
            hovertemplate=f"{op}: %{{y}} DB requests<extra></extra>",
        )
    fig.update_layout(
        barmode="stack",
        title="DB request count by operation (L3/DB calls, median over trials)",
        xaxis_title="policy / prefetch_limit",
        yaxis_title="DB requests",
        template="plotly_white",
        margin=dict(l=60, r=20, t=60, b=60),
    )
    return fig


def _db_request_count_from_csv(df: pd.DataFrame) -> go.Figure:
    required = {"prefetch_limit", "l3", "miss"}
    if df.empty or not required.issubset(df.columns):
        return go.Figure()

    work = df.copy()
    if "policy" not in work.columns:
        work["policy"] = "default"
    work["policy"] = work["policy"].fillna("default").astype(str).str.lower()
    for col in required:
        work[col] = pd.to_numeric(work[col], errors="coerce")
    work = work.dropna(subset=["prefetch_limit"])
    if work.empty:
        return go.Figure()
    work["db_requests"] = work["l3"].fillna(0) + work["miss"].fillna(0)
    work = _hide_repeated_none_baseline(work)
    if work.empty:
        return go.Figure()

    med = (
        work.groupby(["policy", "prefetch_limit"])
        .agg(
            db_requests=("db_requests", "median"),
            l3=("l3", "median"),
            miss=("miss", "median"),
            trials=("trial", "count") if "trial" in work.columns else ("db_requests", "count"),
        )
        .reset_index()
    )
    if med.empty:
        return go.Figure()

    med, limits, bar_width = _positioned_policy_limit_bars(med)
    fig = go.Figure()
    for policy in sorted(med["policy"].unique(), key=_policy_sort_key):
        s = med[med["policy"] == policy].sort_values("prefetch_limit")
        custom = np.stack(
            [s["prefetch_limit"], s["l3"], s["miss"], s["trials"]],
            axis=-1,
        )
        fig.add_bar(
            x=s["_x"],
            y=s["db_requests"],
            width=[bar_width * 0.86] * len(s),
            name=policy,
            marker_color=_policy_color(policy),
            customdata=custom,
            hovertemplate=(
                "policy=" + policy + "<br>"
                "prefetch_limit=%{customdata[0]:.0f}<br>"
                "DB requests=%{y:.0f}<br>"
                "L3=%{customdata[1]:.0f}<br>"
                "MISS=%{customdata[2]:.0f}<br>"
                "trials=%{customdata[3]:.0f}"
                "<extra></extra>"
            ),
        )
    fig.update_layout(
        title="DB request count (L3 + MISS tier touches, median over trials)",
        xaxis=dict(
            title="prefetch_limit",
            tickmode="array",
            tickvals=list(range(len(limits))),
            ticktext=[_format_limit(limit) for limit in limits],
        ),
        yaxis_title="DB requests",
        legend_title="policy",
        template="plotly_white",
        margin=dict(l=60, r=20, t=60, b=60),
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
    background prefetch elapsed time."""
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
    # Background prefetch (right bar). Distinct offsetgroup to sit alongside.
    fig.add_bar(
        x=limits, y=prefetch, name="Background prefetch",
        marker_color="orange", offsetgroup="prefetch",
        hovertemplate="background prefetch: %{y:.0f} ms<extra></extra>",
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
        title="E2E vs Prefetch Limit - left bar = e2e stack, right bar = background prefetch (median over trials)",
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


def memory_time_reduction(df: pd.DataFrame, profiles_dir: Path) -> go.Figure:
    """Median socket I/O self-time spent below the storage client.

    This intentionally uses caller-attributed cProfile self time for socket
    send/recv calls, not cumulative time. It excludes serializer, cache
    bookkeeping, and most client-library CPU, keeping this chart focused on
    blocking storage I/O rather than surrounding walker CPU.
    """
    profile_rows = _load_memory_profile_rows(profiles_dir)
    if profile_rows.empty:
        return go.Figure()
    work = _join_profiles_to_sweep_rows(df, profile_rows)
    if work.empty:
        return go.Figure()

    stats = (
        work.groupby(["policy", "prefetch_limit"])
        .agg(
            memory_median=("memory_ms", "median"),
            memory_p25=("memory_ms", lambda s: s.quantile(0.25)),
            memory_p75=("memory_ms", lambda s: s.quantile(0.75)),
            prefetch_median=("prefetch_ms", "median"),
            prefetch_p25=("prefetch_ms", lambda s: s.quantile(0.25)),
            prefetch_p75=("prefetch_ms", lambda s: s.quantile(0.75)),
            trials=("memory_ms", "count"),
        )
        .reset_index()
    )
    stats = _hide_repeated_none_baseline(stats)
    if stats.empty:
        return go.Figure()

    baseline = stats[
        (stats["policy"].astype(str) == "none")
        & (pd.to_numeric(stats["prefetch_limit"], errors="coerce").fillna(-1) == 0)
    ]["memory_median"]
    baseline_ms = float(baseline.iloc[0]) if not baseline.empty and baseline.iloc[0] > 0 else None
    if baseline_ms:
        stats["reduction_pct"] = 100.0 * (baseline_ms - stats["memory_median"]) / baseline_ms
    else:
        stats["reduction_pct"] = np.nan

    stats, limits, bar_width = _positioned_policy_limit_bars(stats)
    stacked_width = bar_width * 0.86
    fig = go.Figure()
    for policy in sorted(stats["policy"].unique(), key=_policy_sort_key):
        s = stats[stats["policy"] == policy].sort_values("prefetch_limit")
        color = _policy_color(policy)

        memory_upper = np.maximum(s["memory_p75"] - s["memory_median"], 0)
        memory_lower = np.maximum(s["memory_median"] - s["memory_p25"], 0)
        memory_custom = np.stack(
            [
                s["prefetch_limit"],
                s["memory_p25"],
                s["memory_p75"],
                s["trials"],
                s["reduction_pct"],
            ],
            axis=-1,
        )
        fig.add_bar(
            x=s["_x"],
            y=s["memory_median"],
            width=[stacked_width] * len(s),
            name=f"{policy} storage I/O",
            legendgroup=policy,
            marker_color=color,
            error_y=dict(
                type="data",
                array=memory_upper,
                arrayminus=memory_lower,
                visible=bool((memory_upper > 0).any() or (memory_lower > 0).any()),
                thickness=1.2,
                width=3,
            ),
            customdata=memory_custom,
            hovertemplate=(
                "policy=" + policy + "<br>"
                "component=blocking storage I/O<br>"
                "prefetch_limit=%{customdata[0]:.0f}<br>"
                "median storage I/O=%{y:.1f} ms<br>"
                "IQR=%{customdata[1]:.1f}-"
                "%{customdata[2]:.1f} ms<br>"
                "reduction vs none:0=%{customdata[4]:.1f}%<br>"
                "trials=%{customdata[3]:.0f}"
                "<extra></extra>"
            ),
        )

        prefetch = s.dropna(subset=["prefetch_median"])
        if not prefetch.empty and (prefetch["prefetch_median"].fillna(0) > 0).any():
            prefetch_upper = np.maximum(prefetch["prefetch_p75"] - prefetch["prefetch_median"], 0)
            prefetch_lower = np.maximum(prefetch["prefetch_median"] - prefetch["prefetch_p25"], 0)
            prefetch_custom = np.stack(
                [
                    prefetch["prefetch_limit"],
                    prefetch["prefetch_p25"],
                    prefetch["prefetch_p75"],
                    prefetch["trials"],
                ],
                axis=-1,
            )
            fig.add_bar(
                x=prefetch["_x"],
                y=prefetch["prefetch_median"],
                width=[stacked_width] * len(prefetch),
                name=f"{policy} prefetcher",
                legendgroup=policy,
                marker=dict(
                    color=color,
                    opacity=0.72,
                    pattern=dict(shape="/", solidity=0.28, fgcolor=color),
                ),
                error_y=dict(
                    type="data",
                    array=prefetch_upper,
                    arrayminus=prefetch_lower,
                    visible=bool((prefetch_upper > 0).any() or (prefetch_lower > 0).any()),
                    thickness=1.2,
                    width=3,
                ),
                customdata=prefetch_custom,
                hovertemplate=(
                    "policy=" + policy + "<br>"
                    "component=background prefetch<br>"
                    "prefetch_limit=%{customdata[0]:.0f}<br>"
                    "median background prefetch=%{y:.1f} ms<br>"
                    "IQR=%{customdata[1]:.1f}-"
                    "%{customdata[2]:.1f} ms<br>"
                    "trials=%{customdata[3]:.0f}"
                    "<extra></extra>"
                ),
            )

    if baseline_ms:
        fig.add_hline(
            y=baseline_ms,
            line_dash="dot",
            line_color="#7f7f7f",
            annotation_text=f"none:0 median {baseline_ms:.0f} ms",
            annotation_position="top left",
        )

    fig.update_layout(
        title="Blocking storage I/O time with background prefetch time stacked",
        barmode="stack",
        xaxis=dict(
            title="prefetch_limit",
            tickmode="array",
            tickvals=list(range(len(limits))),
            ticktext=[_format_limit(limit) for limit in limits],
        ),
        yaxis=dict(title="Time (ms)"),
        template="plotly_white",
        legend_title="policy / component",
        margin=dict(l=60, r=20, t=70, b=60),
    )
    return fig


def _load_memory_profile_rows(profiles_dir: Path) -> pd.DataFrame:
    if not profiles_dir.exists():
        return pd.DataFrame()
    rows: list[dict[str, object]] = []
    for profile_path in sorted(profiles_dir.glob("policy_*/limit_*/*/trial_*/jac_server.prof")):
        ident = _profile_path_identity(profiles_dir, profile_path)
        if not ident:
            continue
        memory_ms = _profile_memory_self_ms(profile_path)
        if memory_ms is None:
            continue
        ident["memory_ms"] = memory_ms
        rows.append(ident)
    return pd.DataFrame(rows)


def _profile_path_identity(profiles_dir: Path, profile_path: Path) -> dict[str, object] | None:
    try:
        parts = profile_path.relative_to(profiles_dir).parts
    except ValueError:
        return None
    if len(parts) < 5:
        return None
    policy_part, limit_part, walker, trial_part = parts[:4]
    if not policy_part.startswith("policy_") or not limit_part.startswith("limit_"):
        return None
    if not trial_part.startswith("trial_"):
        return None
    try:
        limit = int(limit_part.removeprefix("limit_"))
        trial = int(trial_part.removeprefix("trial_"))
    except ValueError:
        return None
    return {
        "policy": policy_part.removeprefix("policy_"),
        "prefetch_limit": limit,
        "walker": walker,
        "trial": trial,
        "profile_path": str(profile_path),
    }


def _profile_memory_self_ms(profile_path: Path) -> float | None:
    try:
        stats = pstats.Stats(str(profile_path))
    except Exception:
        return None

    total_sec = 0.0
    for func, values in stats.stats.items():
        callers = values[4]
        total_sec += _memory_socket_self_sec(func, callers, float(values[2]))
    return total_sec * 1000.0


def _memory_socket_self_sec(func, callers: dict, self_sec: float) -> float:
    filename, _line, func_name = func
    path = str(filename).replace("\\", "/")
    if path != "~" or not any(marker in str(func_name) for marker in MEMORY_SOCKET_FUNC_MARKERS):
        return 0.0
    caller_self = 0.0
    for caller, caller_values in callers.items():
        caller_path = str(caller[0]).replace("\\", "/")
        if any(marker in caller_path for marker in MEMORY_SOCKET_CALLER_MARKERS):
            caller_self += float(caller_values[2])
    return min(caller_self, self_sec)


def _join_profiles_to_sweep_rows(df: pd.DataFrame, profile_rows: pd.DataFrame) -> pd.DataFrame:
    if profile_rows.empty:
        return profile_rows
    if df.empty:
        return profile_rows

    work = df.copy()
    if "policy" not in work.columns:
        work["policy"] = np.where(
            pd.to_numeric(work.get("prefetch_limit", 0), errors="coerce").fillna(0) > 0,
            "ttg",
            "none",
        )
    if "walker" not in work.columns:
        work["walker"] = profile_rows["walker"].iloc[0]

    for col in ("prefetch_limit", "trial"):
        work[col] = pd.to_numeric(work[col], errors="coerce").astype("Int64")
    work["policy"] = work["policy"].astype(str)
    work["walker"] = work["walker"].astype(str)

    keys = ["policy", "prefetch_limit", "walker", "trial"]
    keep = keys + [col for col in ("prefetch_ms",) if col in work.columns]
    valid = work[keep].dropna(subset=keys).drop_duplicates(subset=keys)
    out = profile_rows.merge(valid, on=keys, how="inner")
    if "prefetch_ms" not in out.columns:
        out["prefetch_ms"] = np.nan
    return out if not out.empty else profile_rows


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
        title="Per-worker background prefetch time (max of the box ~= prefetch_ms CSV column)",
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


def churn_coverage(df: pd.DataFrame) -> go.Figure:
    """Line chart for Jacord churn coverage."""
    required = {"churn_rate", "policy", "coverage"}
    if df.empty or not required.issubset(df.columns):
        return go.Figure()
    work = df.copy()
    for col in ("churn_rate", "coverage", "analytic_stale_coverage"):
        if col in work.columns:
            work[col] = pd.to_numeric(work[col], errors="coerce")
    work["policy"] = work["policy"].fillna("").astype(str).str.lower()
    work = work.dropna(subset=["churn_rate", "coverage"])
    if work.empty:
        return go.Figure()

    stats = (
        work.groupby(["policy", "churn_rate"])["coverage"]
        .agg(
            median="median",
            p25=lambda s: s.quantile(0.25),
            p75=lambda s: s.quantile(0.75),
            trials="count",
        )
        .reset_index()
    )
    fig = go.Figure()
    for policy in sorted(stats["policy"].unique(), key=_policy_sort_key):
        s = stats[stats["policy"] == policy].sort_values("churn_rate")
        upper = np.maximum(s["p75"] - s["median"], 0)
        lower = np.maximum(s["median"] - s["p25"], 0)
        fig.add_scatter(
            x=s["churn_rate"],
            y=s["median"],
            mode="lines+markers",
            name=policy,
            line=dict(color=_policy_color(policy)),
            error_y=dict(
                type="data",
                array=upper,
                arrayminus=lower,
                visible=bool((upper > 0).any() or (lower > 0).any()),
                thickness=1.2,
                width=3,
            ),
            customdata=np.stack([s["p25"], s["p75"], s["trials"]], axis=-1),
            hovertemplate=(
                "policy=%{fullData.name}<br>"
                "churn=%{x:.0f}%<br>"
                "median coverage=%{y:.1f}%<br>"
                "IQR=%{customdata[0]:.1f}%-"
                "%{customdata[1]:.1f}%<br>"
                "trials=%{customdata[2]:.0f}"
                "<extra></extra>"
            ),
        )

    if "analytic_stale_coverage" in work.columns:
        ceiling = (
            work.dropna(subset=["analytic_stale_coverage"])
            .groupby("churn_rate")["analytic_stale_coverage"]
            .median()
            .reset_index()
            .sort_values("churn_rate")
        )
        if not ceiling.empty:
            fig.add_scatter(
                x=ceiling["churn_rate"],
                y=ceiling["analytic_stale_coverage"],
                mode="lines",
                name="analytic stale ceiling",
                line=dict(color="#111111", dash="dash"),
                hovertemplate="churn=%{x:.0f}%<br>ceiling=%{y:.1f}%<extra></extra>",
            )

    fig.update_layout(
        title="Jacord churn coverage",
        xaxis_title="churn rate (%)",
        yaxis=dict(title="Coverage (%)", range=[0, 105], ticksuffix="%"),
        template="plotly_white",
        margin=dict(l=60, r=20, t=60, b=60),
    )
    return fig


def churn_hit_rate(df: pd.DataFrame) -> go.Figure:
    """Line chart for Jacord churn L1 hit rate."""
    required = {"churn_rate", "policy", "l1_hit_rate"}
    if df.empty or not required.issubset(df.columns):
        return go.Figure()
    work = df.copy()
    for col in ("churn_rate", "l1_hit_rate"):
        work[col] = pd.to_numeric(work[col], errors="coerce")
    work["policy"] = work["policy"].fillna("").astype(str).str.lower()
    work = work.dropna(subset=["churn_rate", "l1_hit_rate"])
    if work.empty:
        return go.Figure()

    stats = (
        work.groupby(["policy", "churn_rate"])["l1_hit_rate"]
        .agg(
            median="median",
            p25=lambda s: s.quantile(0.25),
            p75=lambda s: s.quantile(0.75),
            trials="count",
        )
        .reset_index()
    )
    fig = go.Figure()
    for policy in sorted(stats["policy"].unique(), key=_policy_sort_key):
        s = stats[stats["policy"] == policy].sort_values("churn_rate")
        upper = np.maximum(s["p75"] - s["median"], 0)
        lower = np.maximum(s["median"] - s["p25"], 0)
        fig.add_scatter(
            x=s["churn_rate"],
            y=s["median"],
            mode="lines+markers",
            name=policy,
            line=dict(color=_policy_color(policy)),
            error_y=dict(
                type="data",
                array=upper,
                arrayminus=lower,
                visible=bool((upper > 0).any() or (lower > 0).any()),
                thickness=1.2,
                width=3,
            ),
            customdata=np.stack([s["p25"], s["p75"], s["trials"]], axis=-1),
            hovertemplate=(
                "policy=%{fullData.name}<br>"
                "churn=%{x:.0f}%<br>"
                "median L1 hit=%{y:.1f}%<br>"
                "IQR=%{customdata[0]:.1f}%-"
                "%{customdata[1]:.1f}%<br>"
                "trials=%{customdata[2]:.0f}"
                "<extra></extra>"
            ),
        )

    fig.update_layout(
        title="Jacord churn hit rate",
        xaxis_title="churn rate (%)",
        yaxis=dict(title="L1 hit rate (%)", range=[0, 105], ticksuffix="%"),
        template="plotly_white",
        margin=dict(l=60, r=20, t=60, b=60),
    )
    return fig


def churn_e2e(df: pd.DataFrame) -> go.Figure:
    """Line chart for Jacord churn e2e latency."""
    required = {"churn_rate", "policy", "e2e_ms"}
    if df.empty or not required.issubset(df.columns):
        return go.Figure()
    work = df.copy()
    for col in ("churn_rate", "e2e_ms"):
        work[col] = pd.to_numeric(work[col], errors="coerce")
    work["policy"] = work["policy"].fillna("").astype(str).str.lower()
    work = work.dropna(subset=["churn_rate", "e2e_ms"])
    if work.empty:
        return go.Figure()

    stats = (
        work.groupby(["policy", "churn_rate"])["e2e_ms"]
        .agg(
            median="median",
            p25=lambda s: s.quantile(0.25),
            p75=lambda s: s.quantile(0.75),
            trials="count",
        )
        .reset_index()
    )
    fig = go.Figure()
    for policy in sorted(stats["policy"].unique(), key=_policy_sort_key):
        s = stats[stats["policy"] == policy].sort_values("churn_rate")
        upper = np.maximum(s["p75"] - s["median"], 0)
        lower = np.maximum(s["median"] - s["p25"], 0)
        fig.add_scatter(
            x=s["churn_rate"],
            y=s["median"],
            mode="lines+markers",
            name=policy,
            line=dict(color=_policy_color(policy)),
            error_y=dict(
                type="data",
                array=upper,
                arrayminus=lower,
                visible=bool((upper > 0).any() or (lower > 0).any()),
                thickness=1.2,
                width=3,
            ),
            hovertemplate=(
                "policy=%{fullData.name}<br>"
                "churn=%{x:.0f}%<br>"
                "median e2e=%{y:.1f} ms<extra></extra>"
            ),
        )

    fig.update_layout(
        title="Jacord churn e2e latency",
        xaxis_title="churn rate (%)",
        yaxis_title="E2E latency (ms)",
        template="plotly_white",
        margin=dict(l=60, r=20, t=60, b=60),
    )
    return fig


def csv_raw(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    if "churn_rate" in df.columns:
        cols = ["churn_rate", "policy", "prefetch_limit", "trial"]
    elif "policy" in df.columns:
        cols = ["policy", "prefetch_limit", "trial"]
    else:
        cols = ["prefetch_limit", "trial"]
    return df.sort_values(cols)
