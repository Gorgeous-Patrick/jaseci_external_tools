import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.ticker import PercentFormatter


def load_cache_stats(path: str | Path) -> pd.DataFrame:
    """Load cache stats JSON and append hit_rate column."""

    path = Path(path)
    with path.open("r") as f:
        data = json.load(f)

    df = pd.DataFrame(data)
    # Keep only the last occurrence for duplicate configurations
    df = df.drop_duplicates(
        subset=["JAC_NODE_NUM", "JAC_EDGE_NUM", "JAC_TWEET_NUM", "jac_prefetch", "cache_size"],
        keep="last"
    )
    df["hit_rate"] = df["hit"] / df["total_acc"]
    return df


def aggregate_hit_rates(df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate hit rates per edge count for each cache/prefetch setting."""

    grouped = (
        df.groupby(["cache_size", "jac_prefetch", "JAC_EDGE_NUM"], as_index=False)
        .agg(hit=("hit", "sum"), total_acc=("total_acc", "sum"))
        .sort_values("JAC_EDGE_NUM")
    )

    grouped["hit_rate"] = grouped["hit"] / grouped["total_acc"].replace({0: pd.NA})
    grouped["hit_rate"] = grouped["hit_rate"].fillna(0)
    return grouped


def plot_hit_rate_curves(
    aggregated_df: pd.DataFrame,
    figsize=(10, 6),
    save_path: str | None = "cache_hit_rate.png",
):
    """Plot hit rate vs edge count for each (cache_size, jac_prefetch) tuple."""

    plt.figure(figsize=figsize)
    
    # Get unique cache sizes and assign colors
    cache_sizes = sorted(aggregated_df["cache_size"].unique())
    colors = plt.cm.tab10(range(len(cache_sizes)))
    color_map = {size: colors[i] for i, size in enumerate(cache_sizes)}
    
    for (cache_size, jac_prefetch), subset in aggregated_df.groupby(["cache_size", "jac_prefetch"]):
        ordered = subset.sort_values("JAC_EDGE_NUM")
        marker = "^" if jac_prefetch != 0 else "o"
        prefetch_status = "enabled" if jac_prefetch != 0 else "disabled"
        label = f"cache={cache_size}, prefetch {prefetch_status}"
        plt.plot(
            ordered["JAC_EDGE_NUM"],
            ordered["hit_rate"],
            marker=marker,
            color=color_map[cache_size],
            label=label,
        )

    plt.xlabel("Edge Count (JAC_EDGE_NUM)")
    plt.ylabel("Hit Rate")
    plt.title("Cache Hit Rate vs Edge Count")
    ax = plt.gca()
    ax.yaxis.set_major_formatter(PercentFormatter(1.0))
    ax.set_ylim(bottom=0)
    plt.grid(True)
    plt.legend(title="cache_size / jac_prefetch", bbox_to_anchor=(1.05, 1), loc='upper left')

    if save_path:
        plt.savefig(save_path, dpi=300, bbox_inches='tight')
        plt.close()
        print(f"Saved plot to {save_path}")
    else:
        plt.show()


def main() -> None:
    parser = argparse.ArgumentParser(description="Plot cache hit rates from JSON data")
    parser.add_argument(
        "cache_stats_path",
        nargs="?",
        default="cache_stats.json",
        help="Path to cache_stats.json file (default: cache_stats.json)"
    )
    parser.add_argument(
        "-o", "--output",
        default="cache_hit_rate.png",
        help="Output path for the plot (default: cache_hit_rate.png)"
    )
    args = parser.parse_args()
    
    dataset_path = Path(args.cache_stats_path)
    if not dataset_path.exists():
        raise FileNotFoundError(f"Could not find {dataset_path}")

    aggregated_df = aggregate_hit_rates(load_cache_stats(dataset_path))
    plot_hit_rate_curves(aggregated_df, save_path=args.output)


if __name__ == "__main__":
    main()
