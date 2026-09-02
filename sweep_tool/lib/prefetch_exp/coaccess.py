"""Offline co-access clustering model generation for prefetch sweeps.

This intentionally mirrors the Markov experiment shape: runtime consumes a
precomputed UUID plan and does not inspect graph structure.  The training side
clusters request transactions by UUID co-access, then ranks UUIDs within each
cluster by support and first-touch order.
"""

from __future__ import annotations

import csv
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID


DEFAULT_CLUSTER_THRESHOLD = 0.05


@dataclass
class _Cluster:
    trace_indexes: list[int]
    items: set[str]


def coaccess_model_path(
    coaccess_dir: Path,
    app_name: str,
    walker: str,
    target_id: str,
    limit: int,
    trial: int,
) -> Path:
    safe_target = _safe_name(target_id or "default")
    return (
        coaccess_dir
        / _safe_name(app_name)
        / _safe_name(walker)
        / f"{safe_target}_limit{limit}_trial{trial}.json"
    )


def coaccess_topology_file_path(model_file: Path) -> Path:
    return model_file.with_name(model_file.name + ".topology.json")


def pooled_coaccess_model_path(
    coaccess_dir: Path,
    app_name: str,
    walker: str,
    label: str,
    limit: int,
    seed: int,
) -> Path:
    return (
        coaccess_dir
        / _safe_name(app_name)
        / _safe_name(walker)
        / f"{_safe_name(label)}_seed{seed}_limit{limit}.json"
    )


def pooled_metadata_path(
    coaccess_dir: Path,
    app_name: str,
    walker: str,
    label: str,
    seed: int,
) -> Path:
    return (
        coaccess_dir
        / _safe_name(app_name)
        / _safe_name(walker)
        / f"{_safe_name(label)}_seed{seed}_metadata.json"
    )


def write_coaccess_model_from_access_log(
    access_log: Path,
    output_path: Path,
    *,
    app_name: str,
    walker: str,
    target_id: str,
    start_id: str,
    limit: int,
    cluster_threshold: float = DEFAULT_CLUSTER_THRESHOLD,
) -> dict[str, object]:
    trace = extract_first_touch_sequence(access_log)
    model = build_coaccess_model(
        trace,
        app_name=app_name,
        walker=walker,
        target_id=target_id,
        start_id=start_id,
        limit=limit,
        source=str(access_log),
        cluster_threshold=cluster_threshold,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(model, indent=2, sort_keys=True) + "\n")
    return model


def write_pooled_metadata(path: Path, metadata: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n")


def write_pooled_coaccess_model_from_access_logs(
    access_logs: list[Path],
    output_path: Path,
    *,
    app_name: str,
    walker: str,
    label: str,
    limit: int,
    seed: int,
    training_request_ids: list[str],
    trial_request_ids: list[str],
    trial_count: int,
    plan_start_ids: list[str],
    cluster_threshold: float = DEFAULT_CLUSTER_THRESHOLD,
) -> dict[str, object]:
    traces = [extract_first_touch_sequence(path) for path in access_logs]
    model = build_pooled_coaccess_model(
        traces,
        app_name=app_name,
        walker=walker,
        label=label,
        limit=limit,
        seed=seed,
        training_request_ids=training_request_ids,
        trial_request_ids=trial_request_ids,
        trial_count=trial_count,
        plan_start_ids=plan_start_ids,
        sources=[str(path) for path in access_logs],
        cluster_threshold=cluster_threshold,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(model, indent=2, sort_keys=True) + "\n")
    return model


def extract_uuid_sequence(access_log: Path) -> list[str]:
    sequence: list[str] = []
    if not access_log.exists():
        return sequence
    with open(access_log, newline="") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames is None or "id" not in reader.fieldnames:
            return sequence
        for row in reader:
            if row.get("tier") == "MISS":
                continue
            raw = (row.get("id") or "").strip()
            if not raw:
                continue
            try:
                sequence.append(str(UUID(raw)))
            except ValueError:
                continue
    return sequence


def extract_first_touch_sequence(access_log: Path) -> list[str]:
    return dedupe_first_touch(extract_uuid_sequence(access_log))


def dedupe_first_touch(sequence: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in sequence:
        uid = _uuid_or_raw(raw)
        if not uid or uid in seen:
            continue
        seen.add(uid)
        out.append(uid)
    return out


def build_coaccess_model(
    sequence: list[str],
    *,
    app_name: str,
    walker: str,
    target_id: str,
    start_id: str,
    limit: int,
    source: str = "",
    cluster_threshold: float = DEFAULT_CLUSTER_THRESHOLD,
) -> dict[str, object]:
    trace = dedupe_first_touch(sequence)
    start_key = _uuid_or_raw(start_id or target_id or "*")
    plan = _prepend_start(start_key, _rank_cluster_items([0], [trace]), limit)
    fallback = _rank_cluster_items([0], [trace])[:limit] if limit > 0 else []
    return {
        "version": 1,
        "policy": "coaccess",
        "algorithm": "greedy-transaction-clustering",
        "app": app_name,
        "walker": walker,
        "target_id": target_id,
        "start_id": start_key,
        "limit": limit,
        "source": source,
        "cluster_threshold": cluster_threshold,
        "sequence_len": len(sequence),
        "distinct_ids": len(trace),
        "clusters": [
            {
                "id": 0,
                "trace_count": 1,
                "distinct_ids": len(trace),
                "top_ids": fallback[: min(20, len(fallback))],
            }
        ],
        "fallback_order": fallback,
        "plan_len": max(len(plan), len(fallback)),
        "plans": {
            start_key: {
                "plan": plan,
                "training_trace_count": 1,
                "distinct_ids": len(trace),
                "cluster_id": 0,
            },
            "*": {
                "plan": fallback,
                "training_trace_count": 1,
                "distinct_ids": len(trace),
                "cluster_id": 0,
            },
        },
    }


def build_pooled_coaccess_model(
    traces: list[list[str]],
    *,
    app_name: str,
    walker: str,
    label: str,
    limit: int,
    seed: int,
    training_request_ids: list[str],
    trial_request_ids: list[str],
    trial_count: int,
    plan_start_ids: list[str],
    sources: list[str] | None = None,
    cluster_threshold: float = DEFAULT_CLUSTER_THRESHOLD,
) -> dict[str, object]:
    normalized = [dedupe_first_touch(trace) for trace in traces]
    clusters = cluster_transactions(normalized, cluster_threshold)
    fallback = _rank_cluster_items(list(range(len(normalized))), normalized)
    starts = list(dict.fromkeys(_uuid_or_raw(raw) for raw in plan_start_ids if raw))
    if "*" not in starts:
        starts.append("*")

    plans: dict[str, dict[str, object]] = {}
    longest_plan = 0
    for start in starts:
        cluster_idx = -1 if start == "*" else _cluster_for_start(start, clusters)
        if cluster_idx >= 0:
            ranked = _rank_cluster_items(clusters[cluster_idx].trace_indexes, normalized)
            plan = _prepend_start(start, ranked, limit)
            trace_count = len(clusters[cluster_idx].trace_indexes)
            distinct_ids = len(clusters[cluster_idx].items)
        else:
            base = fallback[:limit] if limit > 0 else []
            plan = base if start == "*" else _prepend_start(start, fallback, limit)
            trace_count = len(normalized)
            distinct_ids = len(set(fallback))
        longest_plan = max(longest_plan, len(plan))
        plans[start] = {
            "plan": plan,
            "training_trace_count": trace_count,
            "distinct_ids": distinct_ids,
            "cluster_id": cluster_idx if cluster_idx >= 0 else "*",
        }

    metadata = {
        "pooled": True,
        "seed": seed,
        "train_n": len(training_request_ids),
        "trial_count": trial_count,
        "training_request_ids": list(training_request_ids),
        "trial_request_ids": list(trial_request_ids),
        "source_logs": sources or [],
        "trace_lengths": [len(trace) for trace in normalized],
        "trace_distinct_ids": [len(trace) for trace in normalized],
        "cluster_threshold": cluster_threshold,
    }
    return {
        "version": 1,
        "policy": label,
        "runtime_policy": "coaccess",
        "algorithm": "greedy-transaction-clustering",
        "app": app_name,
        "walker": walker,
        "limit": limit,
        "metadata": metadata,
        "cluster_threshold": cluster_threshold,
        "cluster_count": len(clusters),
        "clusters": _cluster_summaries(clusters, normalized),
        "fallback_order": fallback,
        "plan_len": longest_plan,
        "plans": plans,
    }


def cluster_transactions(
    traces: list[list[str]],
    threshold: float = DEFAULT_CLUSTER_THRESHOLD,
) -> list[_Cluster]:
    clusters: list[_Cluster] = []
    trace_sets = [set(trace) for trace in traces]
    for idx, items in enumerate(trace_sets):
        if not items:
            continue
        best_idx = -1
        best_score = 0.0
        for cluster_idx, cluster in enumerate(clusters):
            score = _jaccard(items, cluster.items)
            if score > best_score:
                best_score = score
                best_idx = cluster_idx
        if best_idx >= 0 and best_score >= threshold:
            clusters[best_idx].trace_indexes.append(idx)
            clusters[best_idx].items.update(items)
        else:
            clusters.append(_Cluster(trace_indexes=[idx], items=set(items)))
    return clusters


def plan_quality(model_path: Path, start_id: str, access_log: Path, limit: int) -> dict[str, str]:
    if not model_path.exists():
        return {}
    try:
        model = json.loads(model_path.read_text())
    except Exception:
        return {}
    plan = [] if limit <= 0 else _select_plan(model, start_id)[:limit]
    plan = dedupe_first_touch(plan)
    actual = extract_first_touch_sequence(access_log)
    actual_set = set(actual)
    plan_set = set(plan)
    covered = actual_set & plan_set
    overfetch = plan_set - actual_set
    undercoverage = actual_set - plan_set
    coverage = (len(covered) * 100.0 / len(actual_set)) if actual_set else 0.0
    accuracy = (len(covered) * 100.0 / len(plan_set)) if plan_set else 0.0
    return {
        "coverage": f"{coverage:.1f}",
        "accuracy": f"{accuracy:.1f}",
        "actual_ids": str(len(actual_set)),
        "plan_ids": str(len(plan_set)),
        "covered_ids": str(len(covered)),
        "overfetch_ids": str(len(overfetch)),
        "undercoverage_ids": str(len(undercoverage)),
    }


def _rank_cluster_items(trace_indexes: list[int], traces: list[list[str]]) -> list[str]:
    support: Counter[str] = Counter()
    position_sum: Counter[str] = Counter()
    first_global_order: dict[str, int] = {}
    for trace_idx in trace_indexes:
        if trace_idx < 0 or trace_idx >= len(traces):
            continue
        for position, uid in enumerate(traces[trace_idx]):
            if uid not in first_global_order:
                first_global_order[uid] = len(first_global_order)
            support[uid] += 1
            position_sum[uid] += position
    return sorted(
        support,
        key=lambda uid: (
            -support[uid],
            position_sum[uid] / support[uid],
            first_global_order[uid],
            uid,
        ),
    )


def _prepend_start(start: str, ranked: list[str], limit: int) -> list[str]:
    if limit <= 0:
        return []
    out: list[str] = []
    seen: set[str] = set()
    if start and start != "*" and _is_uuid(start):
        out.append(start)
        seen.add(start)
    for uid in ranked:
        if uid in seen:
            continue
        out.append(uid)
        seen.add(uid)
        if len(out) >= limit:
            break
    return out


def _cluster_for_start(start: str, clusters: list[_Cluster]) -> int:
    if not start:
        return -1
    for idx, cluster in enumerate(clusters):
        if start in cluster.items:
            return idx
    return -1


def _cluster_summaries(clusters: list[_Cluster], traces: list[list[str]]) -> list[dict[str, object]]:
    summaries: list[dict[str, object]] = []
    for idx, cluster in enumerate(clusters):
        ranked = _rank_cluster_items(cluster.trace_indexes, traces)
        summaries.append(
            {
                "id": idx,
                "trace_count": len(cluster.trace_indexes),
                "distinct_ids": len(cluster.items),
                "top_ids": ranked[: min(20, len(ranked))],
            }
        )
    return summaries


def _select_plan(model: dict[str, Any], start_id: str) -> list[str]:
    plans = model.get("plans")
    if not isinstance(plans, dict):
        return []
    keys = [_uuid_or_raw(start_id), str(start_id), "*"]
    for key in keys:
        entry = plans.get(key)
        if isinstance(entry, dict):
            raw_plan = entry.get("plan", [])
        else:
            raw_plan = entry
        if isinstance(raw_plan, list):
            return [_uuid_or_raw(uid) for uid in raw_plan if uid]
    return []


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left and not right:
        return 1.0
    union = len(left | right)
    return (len(left & right) / union) if union else 0.0


def _uuid_or_raw(value: Any) -> str:
    try:
        return str(UUID(str(value)))
    except Exception:
        return str(value or "")


def _is_uuid(value: str) -> bool:
    try:
        UUID(str(value))
        return True
    except Exception:
        return False


def _safe_name(raw: str) -> str:
    safe = "".join(ch if ch.isalnum() or ch in ("-", "_", ".") else "_" for ch in str(raw))
    return safe or "default"
