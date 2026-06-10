#!/usr/bin/env python3
"""Analyze cache hit rate per type from access_log.csv.

Outputs a text table showing L1/L2/L3/MISS counts and hit rate for each
anchor type, with edge/node classification.

Usage:
    python analyze_hit_rate.py [access_log.csv]
"""

import csv
import sys
from collections import Counter, defaultdict

EDGE_TYPES = {"Follow", "Post", "Member", "ChannelPost", "GenericEdge"}
NODE_TYPES = {"Root", "Profile", "Tweet", "Channel"}


def main():
    csv_file = sys.argv[1] if len(sys.argv) > 1 else "access_log.csv"

    with open(csv_file) as f:
        rows = list(csv.DictReader(f))

    if not rows:
        print("No data found")
        return

    # Count by (type, tier)
    type_tier = defaultdict(Counter)
    for r in rows:
        type_tier[r["type"]][r["tier"]] += 1

    # Sort: nodes first, then edges, alphabetically within each group
    types = sorted(type_tier.keys(), key=lambda t: (
        0 if t in NODE_TYPES else (1 if t in EDGE_TYPES else 2), t
    ))

    # Print header
    print(f"{'Type':<16} {'Kind':<6} {'L1':>8} {'L2':>8} {'L3':>8} {'MISS':>8} {'Total':>8} {'L1 Hit%':>8}")
    print("-" * 82)

    total_counts = Counter()
    for tp in types:
        counts = type_tier[tp]
        l1 = counts.get("L1", 0)
        l2 = counts.get("L2", 0)
        l3 = counts.get("L3", 0)
        miss = counts.get("MISS", 0)
        total = l1 + l2 + l3 + miss
        hit_rate = l1 / total * 100 if total > 0 else 0

        if tp in EDGE_TYPES:
            kind = "edge"
        elif tp in NODE_TYPES:
            kind = "node"
        else:
            kind = "?"

        print(f"{tp:<16} {kind:<6} {l1:>8} {l2:>8} {l3:>8} {miss:>8} {total:>8} {hit_rate:>7.1f}%")

        total_counts["L1"] += l1
        total_counts["L2"] += l2
        total_counts["L3"] += l3
        total_counts["MISS"] += miss

    # Totals
    grand_total = sum(total_counts.values())
    print("-" * 82)
    print(f"{'TOTAL':<16} {'':>6} {total_counts['L1']:>8} {total_counts['L2']:>8} {total_counts['L3']:>8} {total_counts['MISS']:>8} {grand_total:>8} {total_counts['L1'] / grand_total * 100 if grand_total else 0:>7.1f}%")

    # Summary
    print()
    node_l1 = sum(type_tier[t].get("L1", 0) for t in types if t in NODE_TYPES)
    node_total = sum(sum(type_tier[t].values()) for t in types if t in NODE_TYPES)
    edge_l1 = sum(type_tier[t].get("L1", 0) for t in types if t in EDGE_TYPES)
    edge_total = sum(sum(type_tier[t].values()) for t in types if t in EDGE_TYPES)

    print(f"Node L1 hit rate: {node_l1 / node_total * 100 if node_total else 0:.1f}% ({node_l1}/{node_total})")
    print(f"Edge L1 hit rate: {edge_l1 / edge_total * 100 if edge_total else 0:.1f}% ({edge_l1}/{edge_total})")
    print(f"Overall L1 hit rate: {total_counts['L1'] / grand_total * 100 if grand_total else 0:.1f}% ({total_counts['L1']}/{grand_total})")


if __name__ == "__main__":
    main()
