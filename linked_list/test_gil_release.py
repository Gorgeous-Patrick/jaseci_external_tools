#!/usr/bin/env python3
"""Test whether pymongo and redis-py actually release the GIL during I/O."""

import threading
import time

from pymongo import MongoClient
import redis


def time_mongo_read(col, ids, label="mongo"):
    start = time.perf_counter()
    list(col.find({"_id": {"$in": ids}}))
    elapsed = (time.perf_counter() - start) * 1000
    print(f"  {label}: {elapsed:.1f}ms")
    return elapsed


def time_redis_read(r, ids, label="redis"):
    start = time.perf_counter()
    r.mget(ids)
    elapsed = (time.perf_counter() - start) * 1000
    print(f"  {label}: {elapsed:.1f}ms")
    return elapsed


def cpu_burn(duration_ms, label="cpu"):
    """Pure CPU work (no GIL release)."""
    start = time.perf_counter()
    target = start + duration_ms / 1000
    x = 0
    while time.perf_counter() < target:
        x += 1
    elapsed = (time.perf_counter() - start) * 1000
    print(f"  {label}: {elapsed:.1f}ms (iterations={x})")
    return elapsed


def main():
    col = MongoClient("mongodb://localhost:27017")["jac_db"]["_anchors"]
    r = redis.Redis(host="localhost", port=6379)

    all_ids = [doc["_id"] for doc in col.find({}, {"_id": 1}).limit(2000)]
    print(f"Loaded {len(all_ids)} IDs\n")

    # Test 1: Sequential I/O
    print("=== Test 1: Sequential (mongo then redis) ===")
    start = time.perf_counter()
    time_mongo_read(col, all_ids, "mongo")
    time_redis_read(r, all_ids, "redis")
    seq_total = (time.perf_counter() - start) * 1000
    print(f"  Sequential total: {seq_total:.1f}ms\n")

    # Test 2: Parallel I/O (threads)
    print("=== Test 2: Parallel (mongo + redis in threads) ===")
    start = time.perf_counter()
    t1 = threading.Thread(target=time_mongo_read, args=(col, all_ids, "mongo"))
    t2 = threading.Thread(target=time_redis_read, args=(r, all_ids, "redis"))
    t1.start()
    t2.start()
    t1.join()
    t2.join()
    par_total = (time.perf_counter() - start) * 1000
    print(f"  Parallel total: {par_total:.1f}ms")
    print(f"  Speedup: {seq_total / par_total:.2f}x (1.0 = no GIL release, ~2.0 = full release)\n")

    # Test 3: I/O + CPU (does I/O release GIL for CPU thread?)
    print("=== Test 3: MongoDB I/O + CPU burn in parallel ===")
    start = time.perf_counter()
    time_mongo_read(col, all_ids, "mongo alone")
    mongo_alone = (time.perf_counter() - start) * 1000

    start = time.perf_counter()
    cpu_burn(100, "cpu alone")
    cpu_alone = (time.perf_counter() - start) * 1000

    print(f"  Sequential would be: {mongo_alone + cpu_alone:.1f}ms")

    start = time.perf_counter()
    t1 = threading.Thread(target=time_mongo_read, args=(col, all_ids, "mongo"))
    t2 = threading.Thread(target=cpu_burn, args=(100, "cpu"))
    t1.start()
    t2.start()
    t1.join()
    t2.join()
    par_total = (time.perf_counter() - start) * 1000
    print(f"  Parallel total: {par_total:.1f}ms")
    print(f"  Speedup: {(mongo_alone + cpu_alone) / par_total:.2f}x\n")

    # Test 4: Redis I/O + CPU
    print("=== Test 4: Redis I/O + CPU burn in parallel ===")
    start = time.perf_counter()
    time_redis_read(r, all_ids, "redis alone")
    redis_alone = (time.perf_counter() - start) * 1000

    print(f"  Sequential would be: {redis_alone + cpu_alone:.1f}ms")

    start = time.perf_counter()
    t1 = threading.Thread(target=time_redis_read, args=(r, all_ids, "redis"))
    t2 = threading.Thread(target=cpu_burn, args=(100, "cpu"))
    t1.start()
    t2.start()
    t1.join()
    t2.join()
    par_total = (time.perf_counter() - start) * 1000
    print(f"  Parallel total: {par_total:.1f}ms")
    print(f"  Speedup: {(redis_alone + cpu_alone) / par_total:.2f}x\n")


if __name__ == "__main__":
    main()
