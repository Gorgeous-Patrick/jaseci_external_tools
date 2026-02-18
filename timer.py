import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.patches import Patch


def load_timer_stats(path: str | Path, use_avg: bool = False) -> pd.DataFrame:
    """Load timer stats JSON and keep only last occurrence for each configuration, or average if use_avg=True."""

    path = Path(path)
    with path.open("r") as f:
        data = json.load(f)

    df = pd.DataFrame(data)
    
    if use_avg:
        # Take average for each configuration
        df = df.groupby(
            ["JAC_NODE_NUM", "JAC_EDGE_NUM", "JAC_TWEET_NUM", "jac_prefetch"],
            as_index=False
        ).agg({
            "simulated": "first",
            "hit": "mean",
            "total_acc": "mean",
            "cache_size": "first",
            "ttg_generation_time": "mean",
            "prefetch_time": "mean",
            "traversal_time": "mean",
            "memory_get_time": "mean",
            "memory_get_count": "mean",
        })
    else:
        # Keep only the last occurrence for duplicate configurations
        df = df.drop_duplicates(
            subset=["JAC_NODE_NUM", "JAC_EDGE_NUM", "JAC_TWEET_NUM", "jac_prefetch"],
            keep="last"
        )
    return df


def plot_time_bars(
    df: pd.DataFrame,
    figsize=(14, 6),
    save_path: str | None = "timer_plot_bar.png",
    hide_prefetch: bool = False,
    hide_ttg: bool = False,
    only_memory: bool = False,
):
    """Plot timing metrics vs edge count as grouped bars for each prefetch configuration."""

    plt.figure(figsize=figsize)
    
    # Get unique values
    edge_nums = sorted(df["JAC_EDGE_NUM"].unique())
    prefetch_vals = sorted(df["jac_prefetch"].unique())
    
    # Assign colors based on prefetch status
    colors = plt.cm.tab10(range(len(prefetch_vals)))
    color_map = {val: colors[i] for i, val in enumerate(prefetch_vals)}
    
    # Calculate bar positions
    n_groups = len(prefetch_vals)
    bar_width = 0.8 / n_groups
    x = range(len(edge_nums))
    
    # Plot bars for each configuration
    for idx, jac_prefetch in enumerate(prefetch_vals):
        subset = df[df["jac_prefetch"] == jac_prefetch]
        ordered = subset.sort_values("JAC_EDGE_NUM")
        
        prefetch_status = "enabled" if jac_prefetch != 0 else "disabled"
        label = f"prefetch {prefetch_status}"
        
        positions = [i + idx * bar_width - 0.4 + bar_width/2 for i in x]
        
        if only_memory:
            # Only plot memory_get_time
            plt.bar(
                positions,
                ordered["memory_get_time"],
                width=bar_width,
                color=color_map[jac_prefetch],
                label=label,
                edgecolor='black',
                linewidth=0.5,
            )
        else:
            # Plot traversal time (bottom layer)
            plt.bar(
                positions,
                ordered["traversal_time"],
                width=bar_width,
                color=color_map[jac_prefetch],
                label=label,
                edgecolor='black',
                linewidth=0.5,
            )
            
            # Plot prefetch time (middle layer) - in orange
            if not hide_prefetch:
                plt.bar(
                    positions,
                    ordered["prefetch_time"],
                    width=bar_width,
                    bottom=ordered["traversal_time"],
                    color='orange',
                    edgecolor='black',
                    linewidth=0.5,
                )
            
            # Plot ttg generation time (top layer) - in green
            if not hide_ttg:
                bottom_value = ordered["traversal_time"] + (ordered["prefetch_time"] if not hide_prefetch else 0)
                plt.bar(
                    positions,
                    ordered["ttg_generation_time"],
                    width=bar_width,
                    bottom=bottom_value,
                    color='green',
                    edgecolor='black',
                    linewidth=0.5,
                )
    
    plt.xlabel("Edge Count (JAC_EDGE_NUM)")
    
    if only_memory:
        y_label = "Memory Get Time (seconds)"
        title = "Memory Get Time vs Edge Count"
    else:
        y_label = "Walker Execution Time (seconds)"
        title = "Walker Execution Time vs Edge Count"
    
    plt.ylabel(y_label)
    plt.title(title)
    plt.xticks(x, edge_nums)
    ax = plt.gca()
    ax.set_ylim(bottom=0)
    plt.grid(True, axis='y', alpha=0.3)
    
    handles, labels = ax.get_legend_handles_labels()
    
    if only_memory:
        time_handles = []
    else:
        time_handles = []
        
        if not hide_ttg:
            time_handles.append(Patch(facecolor='green', edgecolor='black', label='TTG Generation Time'))
        
        if not hide_prefetch:
            time_handles.append(Patch(facecolor='orange', edgecolor='black', label='Prefetch Time'))
    
    all_handles = handles + time_handles
    plt.legend(
        handles=all_handles,
        title="Prefetch / Time Components",
        bbox_to_anchor=(1.05, 1),
        loc='upper left'
    )

    if save_path:
        plt.savefig(save_path, dpi=300, bbox_inches='tight')
        plt.close()
        print(f"Saved plot to {save_path}")
    else:
        plt.show()


def main() -> None:
    parser = argparse.ArgumentParser(description="Plot timing metrics as grouped bars from JSON data")
    parser.add_argument(
        "cache_stats_path",
        nargs="?",
        default="cache_stats.json",
        help="Path to cache_stats.json file (default: cache_stats.json)"
    )
    parser.add_argument(
        "-o", "--output",
        default="timer_plot_bar.png",
        help="Output path for the plot (default: timer_plot_bar.png)"
    )
    parser.add_argument(
        "--hide-prefetch",
        action="store_true",
        help="Hide prefetch time from the plot"
    )
    parser.add_argument(
        "--hide-ttg",
        action="store_true",
        help="Hide TTG generation time from the plot"
    )
    parser.add_argument(
        "--only-memory",
        action="store_true",
        help="Only plot memory_get_time (ignores other hide flags)"
    )
    parser.add_argument(
        "--avg",
        action="store_true",
        help="Take average for each test case instead of using last data point"
    )
    args = parser.parse_args()
    
    dataset_path = Path(args.cache_stats_path)
    if not dataset_path.exists():
        raise FileNotFoundError(f"Could not find {dataset_path}")

    df = load_timer_stats(dataset_path, use_avg=args.avg)
    plot_time_bars(df, save_path=args.output, hide_prefetch=args.hide_prefetch, hide_ttg=args.hide_ttg, only_memory=args.only_memory)


if __name__ == "__main__":
    main()
