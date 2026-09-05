"""CSV/log parsing used by the Python prefetch sweep runner."""

from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path


RESULT_COLUMNS = [
    "policy",
    "walker",
    "prefetch_limit",
    "trial",
    "e2e_ms",
    "request_id",
    "request_order",
    "train_n",
    "trial_count",
    "pool_seed",
    "coverage",
    "accuracy",
    "actual_ids",
    "plan_ids",
    "covered_ids",
    "overfetch_ids",
    "undercoverage_ids",
    "topo_idx_ms",
    "ttg_ms",
    "prefetch_ms",
    "materialize_ms",
    "prefetch_wait_ms",
    "walker_ms",
    "l1_hit_rate",
    "l1",
    "l2",
    "l3",
    "miss",
    "db_q",
    "oracle_file",
    "oracle_topology_file",
    "model_file",
    "model_topology_file",
    "selep_events",
    "selep_matched_events",
    "selep_predictions",
    "selep_blocks",
    "selep_blocks_skipped",
    "selep_blocks_already_warmed",
    "selep_prewarm_calls",
    "selep_prewarm_ms",
    "selep_errors",
    "selep_score_file",
    "selep_score_workload",
    "selep_block_cache_size",
    "selep_score_events",
    "selep_block_accesses",
    "selep_general_block_hit_ratio",
    "selep_combined_block_hit_ratio",
    "selep_miss_coverage",
    "selep_block_hits",
    "selep_block_misses",
    "selep_general_block_hits",
    "selep_general_block_misses",
    "capre_prefetch_l3_requests",
    "capre_prefetch_l3_objects",
    "capre_demand_l3_requests",
    "capre_demand_l3_objects",
    "capre_total_l3_requests",
    "capre_useful_prefetches",
    "capre_late_prefetches",
    "capre_unused_prefetches",
    "capre_duplicate_prefetches_suppressed",
    "capre_peak_inflight",
    "capre_avg_inflight",
    "capre_app_db_round_trips",
    "capre_limit_dropped",
    "capre_depth_dropped",
    "capre_drain_ms",
    "capre_trace_file",
    "capre_metrics_file",
]


def profile_breakdown(profile_csv: Path) -> dict[str, str]:
    if not profile_csv.exists():
        return {}
    try:
        with open(profile_csv, newline="") as fh:
            rows = list(csv.DictReader(fh))
    except Exception:
        return {}
    if not rows:
        return {}
    row = rows[-1]
    return {
        "topo_idx_ms": row.get("topo_idx_ms", ""),
        "ttg_ms": row.get("ttg_ms", ""),
        "prefetch_ms": row.get("prefetch_ms", ""),
        "materialize_ms": row.get("materialize_ms", ""),
        "prefetch_wait_ms": row.get("prefetch_wait_ms", ""),
        "walker_ms": row.get("walker_ms", ""),
        "capre_prefetch_l3_requests": row.get("capre_prefetch_l3_requests", ""),
        "capre_prefetch_l3_objects": row.get("capre_prefetch_l3_objects", ""),
        "capre_demand_l3_requests": row.get("capre_demand_l3_requests", ""),
        "capre_demand_l3_objects": row.get("capre_demand_l3_objects", ""),
        "capre_total_l3_requests": row.get("capre_total_l3_requests", ""),
        "capre_useful_prefetches": row.get("capre_useful_prefetches", ""),
        "capre_late_prefetches": row.get("capre_late_prefetches", ""),
        "capre_unused_prefetches": row.get("capre_unused_prefetches", ""),
        "capre_duplicate_prefetches_suppressed": row.get(
            "capre_duplicate_prefetches_suppressed", ""
        ),
        "capre_peak_inflight": row.get("capre_peak_inflight", ""),
        "capre_avg_inflight": row.get("capre_avg_inflight", ""),
        "capre_app_db_round_trips": row.get("capre_app_db_round_trips", ""),
        "capre_limit_dropped": row.get("capre_limit_dropped", ""),
        "capre_depth_dropped": row.get("capre_depth_dropped", ""),
        "capre_drain_ms": row.get("capre_drain_ms", ""),
        "capre_trace_file": row.get("capre_trace_file", ""),
        "capre_metrics_file": row.get("capre_metrics_file", ""),
    }


def tier_counts(access_log: Path) -> dict[str, str]:
    counts = Counter({"L1": 0, "L2": 0, "L3": 0, "MISS": 0})
    if not access_log.exists():
        return {}
    try:
        with open(access_log, newline="") as fh:
            for row in csv.DictReader(fh):
                tier = row.get("tier", "")
                if tier in counts:
                    counts[tier] += 1
    except Exception:
        return {}
    total = sum(counts.values())
    return {
        "l1_hit_rate": f"{(counts['L1'] * 100.0 / total) if total else 0.0:.1f}",
        "l1": str(counts["L1"]),
        "l2": str(counts["L2"]),
        "l3": str(counts["L3"]),
        "miss": str(counts["MISS"]),
    }


def write_header(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as fh:
        csv.DictWriter(fh, fieldnames=RESULT_COLUMNS).writeheader()


def append_result(path: Path, row: dict[str, object]) -> None:
    with open(path, "a", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=RESULT_COLUMNS, extrasaction="ignore")
        writer.writerow({key: row.get(key, "") for key in RESULT_COLUMNS})
