"""Benchmark: batch-fetch X linked-list nodes from MongoDB and Redis.

Connects to the same MongoDB/Redis instance used by the Jaseci linked-list app.
Assumes data has already been populated (run bench_batch_fetch.sh first).

Usage:
    python bench_batch_fetch.py --step 100 --runs 10
"""

import argparse
import csv
import json
import statistics
import time

import matplotlib.pyplot as plt
from pymongo import MongoClient
import redis


def get_anchor_ids(col) -> tuple[list[str], list[str]]:
    """Return (node_ids, edge_ids) for Item nodes and Next/GenericEdge edges."""
    node_ids = [doc["_id"] for doc in col.find({"type": "NodeAnchor", "data.archetype.__type__": "Item"}, {"_id": 1})]
    edge_ids = [doc["_id"] for doc in col.find({"type": "EdgeAnchor"}, {"_id": 1})]
    return node_ids, edge_ids


def batch_get_mongo(col, ids: list[str]) -> list:
    return list(col.find({"_id": {"$in": ids}}))


def sequential_get_mongo(col, ids: list[str]) -> list:
    return [list(col.find({"_id": {"$in": [node_id]}})) for node_id in ids]


def batch_get_redis(r: redis.Redis, ids: list[str]) -> list:
    return r.mget(ids)


def sequential_get_redis(r: redis.Redis, ids: list[str]) -> list:
    return [r.mget([node_id]) for node_id in ids]


def time_once(func, *args) -> float:
    start = time.perf_counter()
    func(*args)
    return time.perf_counter() - start


def main():
    parser = argparse.ArgumentParser(
        description="Benchmark batch-fetch of linked-list nodes: MongoDB vs Redis"
    )
    parser.add_argument("--step", type=int, default=10, help="Step size for node counts")
    parser.add_argument("--runs", type=int, default=10, help="Repetitions per measurement")
    parser.add_argument("--output", "-o", default="bench_batch_fetch.csv", help="Output CSV path")
    parser.add_argument("--plot", default="bench_batch_fetch.png", help="Output plot path")
    parser.add_argument("--mongo-uri", default="mongodb://localhost:27017")
    parser.add_argument("--redis-host", default="localhost")
    parser.add_argument("--redis-port", type=int, default=6379)
    args = parser.parse_args()

    mongo_client = MongoClient(args.mongo_uri)
    col = mongo_client["jac_db"]["_anchors"]
    r = redis.Redis(host=args.redis_host, port=args.redis_port)

    all_node_ids, all_edge_ids = get_anchor_ids(col)
    if not all_node_ids:
        print("ERROR: No Item nodes found in jac_db._anchors.")
        print("Run bench_batch_fetch.sh first to populate the linked list.")
        return

    print(f"Found {len(all_node_ids)} Item nodes, {len(all_edge_ids)} edges in MongoDB")

    # Copy all anchors (nodes + edges) from MongoDB into Redis so the comparison is fair
    print("Loading all anchors into Redis...")
    pipe = r.pipeline()
    loaded = 0
    for doc in col.find():
        pipe.set(doc["_id"], json.dumps(doc["data"], default=str))
        loaded += 1
    pipe.execute()
    print(f"Loaded {loaded} anchors into Redis (nodes + edges)")

    node_counts = list(range(args.step, len(all_node_ids) + 1, args.step))
    if node_counts[-1] != len(all_node_ids):
        node_counts.append(len(all_node_ids))

    csv_file = open(args.output, "w", newline="")
    writer = csv.writer(csv_file)
    writer.writerow(["nodes", "run", "backend", "time_s"])

    print(f"{'Nodes':>8}  {'Mongo batch':>14}  {'Mongo seq':>14}  {'Redis mget':>14}  {'Redis seq':>14}")
    print("-" * 76)

    plot_nodes = []
    stats = {k: {"avg": [], "std": []} for k in ["mongo_batch", "mongo_seq", "redis_mget", "redis_seq"]}

    for n in node_counts:
        # For X nodes, take X-1 edges (linked list has N-1 edges for N nodes)
        n_ids = all_node_ids[:n]
        e_ids = all_edge_ids[:max(n - 1, 0)]
        ids = n_ids + e_ids

        times = {"mongo_batch": [], "mongo_seq": [], "redis_mget": [], "redis_seq": []}
        for run in range(1, args.runs + 1):
            times["mongo_batch"].append(time_once(batch_get_mongo, col, ids))
            times["mongo_seq"].append(time_once(sequential_get_mongo, col, ids))
            times["redis_mget"].append(time_once(batch_get_redis, r, ids))
            times["redis_seq"].append(time_once(sequential_get_redis, r, ids))
            for backend, t_list in times.items():
                writer.writerow([n, run, backend, f"{t_list[-1]:.6f}"])

        plot_nodes.append(n)
        for k in stats:
            stats[k]["avg"].append(statistics.mean(times[k]))
            stats[k]["std"].append(statistics.stdev(times[k]) if len(times[k]) > 1 else 0.0)

        print(f"{n:>8}  {stats['mongo_batch']['avg'][-1]:>12.4f} s"
              f"  {stats['mongo_seq']['avg'][-1]:>12.4f} s"
              f"  {stats['redis_mget']['avg'][-1]:>12.4f} s"
              f"  {stats['redis_seq']['avg'][-1]:>12.4f} s")

    csv_file.close()
    print(f"\nResults written to {args.output}")

    # Plot
    fig, ax = plt.subplots(figsize=(10, 6))

    colors = {
        "mongo_batch": "tab:blue",
        "mongo_seq": "tab:cyan",
        "redis_mget": "tab:red",
        "redis_seq": "tab:orange",
    }
    labels = {
        "mongo_batch": "MongoDB ($in)",
        "mongo_seq": "MongoDB (sequential)",
        "redis_mget": "Redis (mget)",
        "redis_seq": "Redis (sequential get)",
    }

    def linreg(xs, ys):
        n = len(xs)
        sx = sum(xs)
        sy = sum(ys)
        sxy = sum(x * y for x, y in zip(xs, ys))
        sx2 = sum(x * x for x in xs)
        a = (n * sxy - sx * sy) / (n * sx2 - sx * sx)
        b = (sy - a * sx) / n
        return a, b

    print(f"\nLinear fit (ms):")
    for k in stats:
        avg_ms = [v * 1000 for v in stats[k]["avg"]]
        std_ms = [v * 1000 for v in stats[k]["std"]]

        ax.plot(plot_nodes, avg_ms, label=labels[k], color=colors[k])
        ax.fill_between(
            plot_nodes,
            [a - s for a, s in zip(avg_ms, std_ms)],
            [a + s for a, s in zip(avg_ms, std_ms)],
            alpha=0.2, color=colors[k],
        )

        a, b = linreg(plot_nodes, avg_ms)
        ax.plot(plot_nodes, [a * x + b for x in plot_nodes], "--", color=colors[k], alpha=0.7,
                label=f"{labels[k]} fit: {a:.4f}x + {b:.4f}")
        print(f"  {labels[k]:.<30s} {a:.4f} * nodes + {b:.4f}")

    ax.set_xlabel("Number of nodes fetched")
    ax.set_ylabel("Time (ms)")
    ax.set_title("Batch Fetch: MongoDB vs Redis")
    ax.legend()
    ax.grid(True)

    fig.savefig(args.plot, dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"Plot saved to {args.plot}")

    mongo_client.close()
    r.close()


if __name__ == "__main__":
    main()
