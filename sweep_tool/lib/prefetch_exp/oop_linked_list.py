"""Shared schema helpers for LinkedList's Jac-native OOP/DBridge-like endpoint."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any


RESULT_COLUMNS = [
    "policy",
    "prefetch_limit",
    "trial",
    "start_id",
    "visited",
    "checksum",
    "first_value",
    "last_value",
    "e2e_ms",
    "db_ms",
    "cpu_ms",
    "prefetch_ms",
    "materialize_ms",
    "prefetch_wait_ms",
    "query_count",
    "l1",
    "l2",
    "l3",
    "miss",
    "actual_ids",
    "prefetched_ids",
    "covered_ids",
    "overfetch_ids",
    "undercoverage_ids",
    "coverage",
    "accuracy",
    "serialized_bytes",
    "access_log",
    "actual_file",
    "prefetch_file",
    "error",
]

SUPPORTED_POLICIES = {
    "dbridge_like": "dbridge_like",
}


def canonical_policy(policy: str) -> str:
    try:
        return SUPPORTED_POLICIES[policy.strip().lower()]
    except KeyError as exc:
        raise ValueError(f"unsupported LinkedList OOP policy: {policy}") from exc


def write_results_header(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=RESULT_COLUMNS)
        writer.writeheader()


def append_row(path: Path, row: dict[str, Any]) -> None:
    with path.open("a", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=RESULT_COLUMNS)
        writer.writerow(row)


__all__ = [
    "RESULT_COLUMNS",
    "SUPPORTED_POLICIES",
    "canonical_policy",
    "write_results_header",
    "append_row",
]
