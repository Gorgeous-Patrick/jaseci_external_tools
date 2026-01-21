import json
import pandas as pd

def load_timer_json(path: str) -> pd.DataFrame:
    # Load the JSON list
    with open(path, "r") as f:
        data = json.load(f)

    # Convert to DataFrame
    df = pd.DataFrame(data)

    # Add useful computed columns
    df["ttg_time"] = df["ttg_end_time"] - df["ttg_start_time"]
    df["traversal_time"] = df["traversal_end_time"] - df["traversal_start_time"]
    df["total_time"] = df["traversal_end_time"] - df["ttg_start_time"]

    return df

def compute_avg_times(df: pd.DataFrame) -> pd.DataFrame:
    """
    Given the updated timer dataframe, compute:
      - average ttg_time
      - average traversal_time
      - average ttg_visited_num
      - average traversal_visited_num
    grouped by JAC_EDGE_NUM.

    Returns
    -------
    grouped_df : pd.DataFrame
        Columns:
        ["JAC_EDGE_NUM",
         "avg_ttg_time", "avg_traversal_time",
         "avg_ttg_visited", "avg_traversal_visited"]
    """

    grouped_df = (
        df.groupby("JAC_EDGE_NUM")
        .agg(
            avg_ttg_time=("ttg_time", "mean"),
            avg_traversal_time=("traversal_time", "mean"),
            avg_ttg_visited=("ttg_visited_num", "mean"),
            avg_traversal_visited=("traversal_visited_num", "mean"),
        )
        .reset_index()
        .sort_values("JAC_EDGE_NUM")
    )

    return grouped_df

import matplotlib.pyplot as plt

def plot_avg_times(avg_df: pd.DataFrame, avg_df_old: pd.DataFrame, figsize=(10, 6), save_path=None):
    """
    Plot average TTG time and traversal time vs edge count.

    Parameters
    ----------
    avg_df : pd.DataFrame
        Must contain: ["JAC_EDGE_NUM", "avg_ttg_time", "avg_traversal_time"]

    figsize : tuple
        Figure size.

    save_path : str or None
        If provided, save the figure to this path instead of showing it.
    """

    plt.figure(figsize=figsize)

    # Plot the two lines
    plt.plot(
        avg_df["JAC_EDGE_NUM"],
        avg_df["avg_ttg_time"],
        label="Average TTG Time (After)",
        marker="o",
    )

    plt.plot(
        avg_df_old["JAC_EDGE_NUM"],
        avg_df_old["avg_ttg_time"],
        label="Average TTG Time (Before)",
        marker="o",
    )

    plt.plot(
        avg_df["JAC_EDGE_NUM"],
        avg_df["avg_traversal_time"],
        label="Average Walker Traversal Time",
        marker="o",
    )

    # Labels and formatting
    plt.xlabel("Number of Edges")
    plt.ylabel("Time (seconds)")
    plt.title("TTG Generation Time vs Traversal Time by Graph Density")
    plt.legend()
    plt.grid(True)

    if save_path:
        plt.savefig(save_path, dpi=300)
        plt.close()
        print(f"Saved plot to {save_path}")
    else:
        plt.show()


def plot_avg_visited(avg_df: pd.DataFrame, figsize=(10, 6), save_path=None):
    """
    Plot average TTG visited count and traversal visited count vs edge count.

    Parameters
    ----------
    avg_df : pd.DataFrame
        Must contain: ["JAC_EDGE_NUM",
                        "avg_ttg_visited",
                        "avg_traversal_visited"]

    figsize : tuple
        Figure size.

    save_path : str or None
        If provided, save the figure to this path instead of showing it.
    """

    plt.figure(figsize=figsize)

    # Plot TTG visited count
    plt.plot(
        avg_df["JAC_EDGE_NUM"],
        avg_df["avg_ttg_visited"],
        label="Average TTG Visited Nodes",
        marker="o",
    )

    # Plot traversal visited count
    plt.plot(
        avg_df["JAC_EDGE_NUM"],
        avg_df["avg_traversal_visited"],
        label="Average Traversal Visited Nodes",
        marker="o",
    )

    # Labels and formatting
    plt.xlabel("Number of Edges")
    plt.ylabel("Visited Node Count")
    plt.title("TTG vs Traversal: Average Nodes Visited by Graph Density")
    plt.legend()
    plt.grid(True)

    if save_path:
        plt.savefig(save_path, dpi=300)
        plt.close()
        print(f"Saved plot to {save_path}")
    else:
        plt.show()
df_old = load_timer_json("old/timer.json")
df_old = compute_avg_times(df_old)
df_new = load_timer_json("new/timer.json")
df_new = compute_avg_times(df_new)
plot_avg_times(df_new, df_old, save_path="timer_plot.png")
plot_avg_visited(df_new, save_path="visited_plot.png")
