#!/usr/bin/env python3
"""Regenerate bench_batch_fetch.png from existing CSV data."""

import csv
import statistics

import matplotlib.pyplot as plt


def linreg(xs, ys):
    n = len(xs)
    sx, sy = sum(xs), sum(ys)
    sxy = sum(x * y for x, y in zip(xs, ys))
    sx2 = sum(x * x for x in xs)
    a = (n * sxy - sx * sy) / (n * sx2 - sx * sx)
    b = (sy - a * sx) / n
    return a, b


def main():
    data = {}
    with open("bench_batch_fetch.csv") as f:
        for row in csv.DictReader(f):
            key = (int(row["nodes"]), row["backend"])
            data.setdefault(key, []).append(float(row["time_s"]))

    all_backends = sorted(set(b for _, b in data.keys()))
    all_nodes = sorted(set(n for n, _ in data.keys()))

    # 1 node = 2 objects (1 node anchor + 1 edge anchor)
    plot_objects = [n * 2 for n in all_nodes]

    colors = {
        "mongo_batch": "tab:blue",
        "mongo_seq": "tab:cyan",
        "redis_mget": "tab:red",
        "redis_seq": "tab:orange",
        "redis_mset": "tab:green",
        "redis_seq_set": "tab:olive",
    }
    labels = {
        "mongo_batch": "MongoDB ($in)",
        "mongo_seq": "MongoDB (sequential)",
        "redis_mget": "Redis (mget)",
        "redis_seq": "Redis (sequential get)",
        "redis_mset": "Redis (mset)",
        "redis_seq_set": "Redis (sequential set)",
    }

    # Only plot backends present in the CSV
    backends = [b for b in labels if b in all_backends]

    stats = {k: {"avg": [], "std": []} for k in backends}
    for n in all_nodes:
        for k in backends:
            vals = data[(n, k)]
            stats[k]["avg"].append(statistics.mean(vals) * 1000)
            stats[k]["std"].append(
                statistics.stdev(vals) * 1000 if len(vals) > 1 else 0.0
            )

    fig, ax = plt.subplots(figsize=(10, 6))

    print("Linear fit (ms):")
    for k in backends:
        avg = stats[k]["avg"]
        std = stats[k]["std"]

        ax.plot(plot_objects, avg, label=labels[k], color=colors[k])
        ax.fill_between(
            plot_objects,
            [a - s for a, s in zip(avg, std)],
            [a + s for a, s in zip(avg, std)],
            alpha=0.2,
            color=colors[k],
        )

        a, b = linreg(plot_objects, avg)
        ax.plot(
            plot_objects,
            [a * x + b for x in plot_objects],
            "--",
            color=colors[k],
            alpha=0.7,
            label=f"{labels[k]} fit: {a:.4f}x + {b:.4f}",
        )
        print(f"  {labels[k]:.<30s} {a:.4f} * objects + {b:.4f}")

    ax.set_xlabel("Number of objects fetched")
    ax.set_ylabel("Time (ms)")
    ax.set_title("Batch Fetch: MongoDB vs Redis")
    ax.legend()
    ax.grid(True)

    fig.savefig("bench_batch_fetch.png", dpi=300, bbox_inches="tight")
    plt.close(fig)
    print("Plot saved to bench_batch_fetch.png")


if __name__ == "__main__":
    main()
