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
    hit_df: pd.DataFrame,
    figsize=(10, 6),
    save_path: str | None = "cache_hit_rate.png",
):
    """Plot hit rate vs edge count."""

    plt.figure(figsize=figsize)
    plt.plot(
        hit_df["JAC_EDGE_NUM"],
        hit_df["avg_hit_rate"],
        label="Cache Hit Rate",
        marker="o",
    )

    plt.xlabel("Number of Edges")
    plt.ylabel("Hit Rate")
    plt.title("Cache Hit Rate vs Edge Count")
    plt.gca().yaxis.set_major_formatter(PercentFormatter(1.0))
    plt.grid(True)
    plt.legend()

    if save_path:
        plt.savefig(save_path, dpi=300)
        plt.close()
        print(f"Saved plot to {save_path}")
    else:
        plt.show()


if __name__ == "__main__":
    stats_path = Path("cache_stats.json")

    if not stats_path.exists():
        raise FileNotFoundError("Expected cache_stats.json in the current directory.")

    cache_df = load_cache_stats(stats_path)
    cache_df = compute_hit_rate_by_edge(cache_df)

    plot_hit_rates(cache_df)
