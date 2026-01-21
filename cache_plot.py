import json
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.ticker import PercentFormatter
import pandas as pd


def load_cache_stats(path: str | Path) -> pd.DataFrame:
    """Load cache stats JSON and append hit_rate column."""

    path = Path(path)
    with path.open("r") as f:
        data = json.load(f)

    df = pd.DataFrame(data)
    df["hit_rate"] = df["hit"] / df["total_acc"]
    return df


def compute_hit_rate_by_edge(df: pd.DataFrame) -> pd.DataFrame:
    """Group cache stats by edge count to obtain average hit rates."""

    grouped = (
        df.groupby("JAC_EDGE_NUM")
        .agg(
            avg_hit_rate=("hit_rate", "mean"),
            total_hits=("hit", "sum"),
            total_attempts=("total_acc", "sum"),
        )
        .reset_index()
        .sort_values("JAC_EDGE_NUM")
    )

    return grouped


def plot_hit_rates(
    enabled_df: pd.DataFrame,
    disabled_df: pd.DataFrame | None = None,
    figsize=(10, 6),
    save_path: str | None = "cache_hit_rate.png",
):
    """Plot hit rate vs edge count for both cache modes."""

    plt.figure(figsize=figsize)
    plt.plot(
        enabled_df["JAC_EDGE_NUM"],
        enabled_df["avg_hit_rate"],
        label="TTG-prefetch enabled",
        marker="o",
    )

    if disabled_df is not None:
        plt.plot(
            disabled_df["JAC_EDGE_NUM"],
            disabled_df["avg_hit_rate"],
            label="prefetch disabled",
            marker="o",
        )

    plt.xlabel("Number of Following")
    plt.ylabel("Hit Rate")
    plt.title("Cache Hit Rate vs Edge Count")
    ax = plt.gca()
    ax.yaxis.set_major_formatter(PercentFormatter(1.0))
    ax.set_ylim(bottom=0)
    plt.grid(True)
    plt.legend()

    if save_path:
        plt.savefig(save_path, dpi=300)
        plt.close()
        print(f"Saved plot to {save_path}")
    else:
        plt.show()


def resolve_dataset(label: str, candidates: list[Path], required: bool) -> Path | None:
    """Return the first existing candidate path for a dataset."""

    for path in candidates:
        if path.exists():
            return path

    if required:
        cand_str = ", ".join(str(p) for p in candidates)
        raise FileNotFoundError(f"Could not find {label}. Checked: {cand_str}")

    return None


if __name__ == "__main__":
    enabled_candidates = [
        Path("cache_stats_TTG-prefetch_enabled.json"),
        Path("cache_stats_prefetch_enabled.json"),
        Path("cache_stats.json"),
        Path("new/cache_stats.json"),
    ]

    disabled_candidates = [
        Path("cache_stats_prefetch_disabled.json"),
        Path("cache_stats_prefetch_disabled_old.json"),
        Path("old/cache_stats.json"),
    ]

    enabled_path = resolve_dataset("TTG-prefetch enabled metrics", enabled_candidates, required=True)
    disabled_path = resolve_dataset("prefetch disabled metrics", disabled_candidates, required=False)

    enabled_df = compute_hit_rate_by_edge(load_cache_stats(enabled_path))
    disabled_df = None
    if disabled_path is not None:
        disabled_df = compute_hit_rate_by_edge(load_cache_stats(disabled_path))

    plot_hit_rates(enabled_df, disabled_df)
