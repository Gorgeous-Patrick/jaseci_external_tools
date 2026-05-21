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


def get_item_ids(col, limit: int = 0) -> list[str]:
    """Return _ids of Item nodes from the _anchors collection."""
    query = {"data.archetype.__type__": "Item"}
    cursor = col.find(query, {"_id": 1})
    if limit > 0:
        cursor = cursor.limit(limit)
    return [doc["_id"] for doc in cursor]


def batch_get_mongo(col, ids: list[str]) -> list:
    return list(col.find({"_id": {"$in": ids}}))


def batch_get_redis(r: redis.Redis, ids: list[str]) -> list:
    pipe = r.pipeline()
    for node_id in ids:
        pipe.get(node_id)
    return pipe.execute()


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

    all_ids = get_item_ids(col)
    if not all_ids:
        print("ERROR: No Item nodes found in jac_db._anchors.")
        print("Run bench_batch_fetch.sh first to populate the linked list.")
        return

    print(f"Found {len(all_ids)} Item nodes in MongoDB")

    # Copy all Item docs from MongoDB into Redis so the comparison is fair
    print("Loading Item nodes into Redis...")
    pipe = r.pipeline()
    for doc in col.find({"data.archetype.__type__": "Item"}):
        pipe.set(doc["_id"], json.dumps(doc["data"], default=str))
    pipe.execute()
    print(f"Loaded {len(all_ids)} nodes into Redis")

    node_counts = list(range(args.step, len(all_ids) + 1, args.step))
    if node_counts[-1] != len(all_ids):
        node_counts.append(len(all_ids))

    csv_file = open(args.output, "w", newline="")
    writer = csv.writer(csv_file)
    writer.writerow(["nodes", "run", "backend", "time_s"])

    print(f"{'Nodes':>8}  {'MongoDB avg':>14}  {'Redis avg':>14}  {'Speedup':>8}")
    print("-" * 56)

    plot_nodes = []
    plot_mongo_avg = []
    plot_mongo_std = []
    plot_redis_avg = []
    plot_redis_std = []

    for n in node_counts:
        ids = all_ids[:n]

        mongo_times = []
        redis_times = []
        for run in range(1, args.runs + 1):
            mt = time_once(batch_get_mongo, col, ids)
            rt = time_once(batch_get_redis, r, ids)
            mongo_times.append(mt)
            redis_times.append(rt)
            writer.writerow([n, run, "mongodb", f"{mt:.6f}"])
            writer.writerow([n, run, "redis", f"{rt:.6f}"])

        m_avg = statistics.mean(mongo_times)
        r_avg = statistics.mean(redis_times)
        m_std = statistics.stdev(mongo_times) if len(mongo_times) > 1 else 0.0
        r_std = statistics.stdev(redis_times) if len(redis_times) > 1 else 0.0

        plot_nodes.append(n)
        plot_mongo_avg.append(m_avg)
        plot_mongo_std.append(m_std)
        plot_redis_avg.append(r_avg)
        plot_redis_std.append(r_std)

        speedup = m_avg / r_avg if r_avg > 0 else float("inf")
        print(f"{n:>8}  {m_avg:>12.4f} s  {r_avg:>12.4f} s  {speedup:>7.2f}x")

    csv_file.close()
    print(f"\nResults written to {args.output}")

    # Plot
    fig, ax = plt.subplots(figsize=(10, 6))

    m_avg_arr = [v * 1000 for v in plot_mongo_avg]
    m_std_arr = [v * 1000 for v in plot_mongo_std]
    r_avg_arr = [v * 1000 for v in plot_redis_avg]
    r_std_arr = [v * 1000 for v in plot_redis_std]

    ax.plot(plot_nodes, m_avg_arr, label="MongoDB", color="tab:blue")
    ax.fill_between(
        plot_nodes,
        [a - s for a, s in zip(m_avg_arr, m_std_arr)],
        [a + s for a, s in zip(m_avg_arr, m_std_arr)],
        alpha=0.2, color="tab:blue",
    )

    ax.plot(plot_nodes, r_avg_arr, label="Redis", color="tab:red")
    ax.fill_between(
        plot_nodes,
        [a - s for a, s in zip(r_avg_arr, r_std_arr)],
        [a + s for a, s in zip(r_avg_arr, r_std_arr)],
        alpha=0.2, color="tab:red",
    )

    # Linear regression (least squares) for both backends
    def linreg(xs, ys):
        n = len(xs)
        sx = sum(xs)
        sy = sum(ys)
        sxy = sum(x * y for x, y in zip(xs, ys))
        sx2 = sum(x * x for x in xs)
        a = (n * sxy - sx * sy) / (n * sx2 - sx * sx)
        b = (sy - a * sx) / n
        return a, b

    ma, mb = linreg(plot_nodes, m_avg_arr)
    ra, rb = linreg(plot_nodes, r_avg_arr)
    fit_line = [ma * x + mb for x in plot_nodes]
    fit_line_r = [ra * x + rb for x in plot_nodes]

    ax.plot(plot_nodes, fit_line, "--", color="tab:blue", alpha=0.7,
            label=f"MongoDB fit: {ma:.4f}x + {mb:.4f}")
    ax.plot(plot_nodes, fit_line_r, "--", color="tab:red", alpha=0.7,
            label=f"Redis fit: {ra:.4f}x + {rb:.4f}")

    print(f"\nLinear fit (ms):")
    print(f"  MongoDB: {ma:.4f} * nodes + {mb:.4f}")
    print(f"  Redis:   {ra:.4f} * nodes + {rb:.4f}")

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
