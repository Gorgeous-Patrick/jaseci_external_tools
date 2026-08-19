"""Offline Markov model generation for prefetch policy sweeps."""

from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any
from uuid import UUID


START_STATE = "__start__"


def markov_model_path(
    markov_dir: Path,
    app_name: str,
    walker: str,
    target_id: str,
    limit: int,
    trial: int,
) -> Path:
    safe_target = _safe_name(target_id or "default")
    return (
        markov_dir
        / _safe_name(app_name)
        / _safe_name(walker)
        / f"{safe_target}_limit{limit}_trial{trial}.json"
    )


def pooled_markov_model_path(
    markov_dir: Path,
    app_name: str,
    walker: str,
    label: str,
    limit: int,
    seed: int,
) -> Path:
    return (
        markov_dir
        / _safe_name(app_name)
        / _safe_name(walker)
        / f"{_safe_name(label)}_seed{seed}_limit{limit}.json"
    )


def pooled_metadata_path(
    markov_dir: Path,
    app_name: str,
    walker: str,
    label: str,
    seed: int,
) -> Path:
    return (
        markov_dir
        / _safe_name(app_name)
        / _safe_name(walker)
        / f"{_safe_name(label)}_seed{seed}_metadata.json"
    )


def write_markov_model_from_access_log(
    access_log: Path,
    output_path: Path,
    *,
    app_name: str,
    walker: str,
    target_id: str,
    start_id: str,
    limit: int,
) -> dict[str, object]:
    sequence = extract_uuid_sequence(access_log)
    model = build_markov_model(
        sequence,
        app_name=app_name,
        walker=walker,
        target_id=target_id,
        start_id=start_id,
        limit=limit,
        source=str(access_log),
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(model, indent=2, sort_keys=True) + "\n")
    return model


def write_pooled_metadata(path: Path, metadata: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n")


def write_pooled_markov_model_from_access_logs(
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
) -> dict[str, object]:
    traces = [extract_first_touch_sequence(path) for path in access_logs]
    model = build_pooled_markov_model(
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
    for uid in sequence:
        if uid in seen:
            continue
        seen.add(uid)
        out.append(uid)
    return out


def build_markov_model(
    sequence: list[str],
    *,
    app_name: str,
    walker: str,
    target_id: str,
    start_id: str,
    limit: int,
    source: str = "",
) -> dict[str, object]:
    transitions: dict[str, Counter[str]] = defaultdict(Counter)
    first_seen: list[str] = []
    seen: set[str] = set()
    prev = START_STATE
    for uid in sequence:
        transitions[prev][uid] += 1
        prev = uid
        if uid not in seen:
            seen.add(uid)
            first_seen.append(uid)

    plan = predict_plan(transitions, first_seen, limit)
    start_key = _uuid_or_raw(start_id or target_id or "*")
    return {
        "version": 1,
        "policy": "markov",
        "order": 1,
        "app": app_name,
        "walker": walker,
        "target_id": target_id,
        "start_id": start_key,
        "limit": limit,
        "source": source,
        "sequence_len": len(sequence),
        "distinct_ids": len(first_seen),
        "plans": {
            start_key: {
                "plan": plan,
                "sequence_len": len(sequence),
                "distinct_ids": len(first_seen),
            },
            "*": {
                "plan": plan,
                "sequence_len": len(sequence),
                "distinct_ids": len(first_seen),
            },
        },
    }


def build_pooled_markov_model(
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
) -> dict[str, object]:
    transitions, fallback_order = build_transition_table(traces)
    starts = list(dict.fromkeys(_uuid_or_raw(raw) for raw in plan_start_ids if raw))
    if "*" not in starts:
        starts.append("*")
    plans = {}
    longest_plan = 0
    for start in starts:
        plan = predict_plan(
            transitions,
            fallback_order,
            limit,
            start_state="" if start == "*" else start,
        )
        longest_plan = max(longest_plan, len(plan))
        plans[start] = {
            "plan": plan,
            "training_trace_count": len(traces),
            "distinct_ids": len(fallback_order),
        }
    metadata = {
        "pooled": True,
        "seed": seed,
        "train_n": len(training_request_ids),
        "trial_count": trial_count,
        "training_request_ids": list(training_request_ids),
        "trial_request_ids": list(trial_request_ids),
        "source_logs": sources or [],
        "trace_lengths": [len(trace) for trace in traces],
        "trace_distinct_ids": [len(dedupe_first_touch(trace)) for trace in traces],
    }
    return {
        "version": 1,
        "policy": label,
        "runtime_policy": "markov",
        "order": 1,
        "app": app_name,
        "walker": walker,
        "limit": limit,
        "metadata": metadata,
        "transitions": _serializable_transitions(transitions),
        "fallback_order": list(fallback_order),
        "plan_len": longest_plan,
        "plans": plans,
    }


def build_transition_table(
    traces: list[list[str]],
) -> tuple[dict[str, Counter[str]], list[str]]:
    transitions: dict[str, Counter[str]] = defaultdict(Counter)
    fallback_order: list[str] = []
    globally_seen: set[str] = set()
    for raw_trace in traces:
        sequence = dedupe_first_touch(raw_trace)
        prev = START_STATE
        for uid in sequence:
            transitions[prev][uid] += 1
            prev = uid
            if uid not in globally_seen:
                globally_seen.add(uid)
                fallback_order.append(uid)
    return transitions, fallback_order


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


def predict_plan(
    transitions: dict[str, Counter[str]],
    fallback_order: list[str],
    limit: int,
    *,
    start_state: str = "",
) -> list[str]:
    if limit <= 0:
        return []
    plan: list[str] = []
    seen: set[str] = set()
    current = START_STATE
    if start_state:
        current = _uuid_or_raw(start_state)
        if _is_uuid(current):
            plan.append(current)
            seen.add(current)
    while len(plan) < limit:
        nxt = _best_unseen(transitions.get(current, Counter()), seen)
        if nxt is None:
            nxt = _first_unseen(fallback_order, seen)
        if nxt is None:
            break
        plan.append(nxt)
        seen.add(nxt)
        current = nxt
    return plan


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


def _serializable_transitions(transitions: dict[str, Counter[str]]) -> dict[str, dict[str, int]]:
    return {
        state: {uid: int(count) for uid, count in sorted(counter.items())}
        for state, counter in sorted(transitions.items())
    }


def _best_unseen(counter: Counter[str], seen: set[str]) -> str | None:
    for uid, _count in sorted(counter.items(), key=lambda item: (-item[1], item[0])):
        if uid not in seen:
            return uid
    return None


def _first_unseen(ids: list[str], seen: set[str]) -> str | None:
    for uid in ids:
        if uid not in seen:
            return uid
    return None


def _uuid_or_raw(raw: str) -> str:
    try:
        return str(UUID(str(raw)))
    except ValueError:
        return str(raw)


def _is_uuid(raw: str) -> bool:
    try:
        UUID(str(raw))
        return True
    except ValueError:
        return False


def _safe_name(raw: str) -> str:
    keep = []
    for ch in str(raw):
        if ch.isalnum() or ch in ("-", "_", "."):
            keep.append(ch)
        else:
            keep.append("_")
    return "".join(keep)[:160] or "default"
