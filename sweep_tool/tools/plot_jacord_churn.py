#!/usr/bin/env python3
"""Plot Jacord churn coverage and hit rate from churn_results.csv."""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd


WORKSPACE_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CSV = WORKSPACE_ROOT / "jacord" / "churn_results.csv"
POLICY_ORDER = ["oracle", "ttg", "history", "markov", "coaccess", "none"]
POLICY_STYLE = {
    "oracle": {"color": "#2ca02c", "marker": "o"},
    "ttg": {"color": "#1f77b4", "marker": "s"},
    "history": {"color": "#ff7f0e", "marker": "^"},
    "markov": {"color": "#9467bd", "marker": "D"},
    "coaccess": {"color": "#e377c2", "marker": "v"},
    "none": {"color": "#7f7f7f", "marker": "x"},
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Backward-compatible alias for --coverage-out.",
    )
    parser.add_argument("--coverage-out", type=Path, default=None)
    parser.add_argument("--hit-rate-out", type=Path, default=None)
    args = parser.parse_args()

    csv_path = args.csv.expanduser().resolve()
    coverage_out = (
        args.coverage_out.expanduser().resolve()
        if args.coverage_out
        else args.out.expanduser().resolve()
        if args.out
        else csv_path.parent / "churn_coverage.pdf"
    )
    hit_rate_out = (
        args.hit_rate_out.expanduser().resolve()
        if args.hit_rate_out
        else csv_path.parent / "churn_hit_rate.pdf"
    )
    df = pd.read_csv(csv_path)
    required = {"churn_rate", "policy", "coverage", "l1_hit_rate"}
    missing = required - set(df.columns)
    if missing:
        raise SystemExit(f"{csv_path} is missing column(s): {', '.join(sorted(missing))}")

    for col in ("churn_rate", "coverage", "l1_hit_rate", "analytic_stale_coverage"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    df["policy"] = df["policy"].astype(str).str.lower()
    _plot_metric(
        df,
        metric="coverage",
        ylabel="Coverage (%)",
        title="Jacord churn coverage",
        out=coverage_out,
        include_stale_ceiling=True,
    )
    _plot_metric(
        df,
        metric="l1_hit_rate",
        ylabel="L1 hit rate (%)",
        title="Jacord churn hit rate",
        out=hit_rate_out,
        include_stale_ceiling=False,
    )
    print(coverage_out)
    print(hit_rate_out)
    return 0


def _plot_metric(
    df: pd.DataFrame,
    *,
    metric: str,
    ylabel: str,
    title: str,
    out: Path,
    include_stale_ceiling: bool,
) -> None:
    work = df.dropna(subset=["churn_rate", metric])
    if work.empty:
        raise SystemExit(f"{out.name}: no rows with {metric}")

    fig, ax = plt.subplots(figsize=(6.2, 3.4))
    grouped = (
        work.groupby(["policy", "churn_rate"])[metric]
        .median()
        .reset_index()
    )
    policies = [p for p in POLICY_ORDER if p in set(grouped["policy"])]
    policies += sorted(set(grouped["policy"]) - set(policies))
    for policy in policies:
        s = grouped[grouped["policy"] == policy].sort_values("churn_rate")
        style = POLICY_STYLE.get(policy, {})
        ax.plot(
            s["churn_rate"],
            s[metric],
            label=policy,
            linewidth=2.0,
            markersize=5.0,
            **style,
        )

    if include_stale_ceiling and "analytic_stale_coverage" in work.columns:
        ceiling = (
            work.dropna(subset=["analytic_stale_coverage"])
            .groupby("churn_rate")["analytic_stale_coverage"]
            .median()
            .reset_index()
            .sort_values("churn_rate")
        )
        if not ceiling.empty:
            ax.plot(
                ceiling["churn_rate"],
                ceiling["analytic_stale_coverage"],
                label="analytic stale ceiling",
                color="#111111",
                linestyle="--",
                linewidth=1.6,
            )

    ax.set_title(title)
    ax.set_xlabel("Churn rate (%)")
    ax.set_ylabel(ylabel)
    ax.set_ylim(0, 105)
    ax.grid(axis="y", color="#dddddd", linewidth=0.7)
    ax.legend(frameon=False, ncol=2, fontsize=8)
    fig.tight_layout()
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out)
    plt.close(fig)


if __name__ == "__main__":
    raise SystemExit(main())
