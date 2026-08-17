"""Offline Markov model generation for prefetch policy sweeps."""

from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
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


def predict_plan(
    transitions: dict[str, Counter[str]],
    fallback_order: list[str],
    limit: int,
) -> list[str]:
    if limit <= 0:
        return []
    plan: list[str] = []
    seen: set[str] = set()
    current = START_STATE
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


def _safe_name(raw: str) -> str:
    keep = []
    for ch in str(raw):
        if ch.isalnum() or ch in ("-", "_", "."):
            keep.append(ch)
        else:
            keep.append("_")
    return "".join(keep)[:160] or "default"
