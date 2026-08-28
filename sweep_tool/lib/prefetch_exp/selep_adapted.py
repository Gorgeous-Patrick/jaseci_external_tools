"""SeLeP-adapted model generation for Jac prefetch sweeps.

This keeps the measured Jac runtime file-based: the LSTM and co-access
partitioning run offline, then runtime consumes precomputed UUID plans.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import platform
import subprocess
import sys
import sysconfig
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

from lib.prefetch_exp import coaccess


DEFAULT_LOOK_BACK = 4
DEFAULT_EPOCHS = 25
DEFAULT_BATCH_SIZE = 16
DEFAULT_SELEP_SOURCE_COMMIT = "0b896c4ff6bb3ec04b8a9a1d4454061cfbfb062d"
POLICY_NAME = "selep-adapted"
RUNTIME_POLICY = "selep-adapted"


@dataclass(frozen=True)
class NodeAccess:
    uuid: str
    node_type: str

    @property
    def block_id(self) -> str:
        return f"{self.node_type}:{self.uuid}"


def selep_model_path(
    selep_dir: Path,
    app_name: str,
    walker: str,
    target_id: str,
    limit: int,
    trial: int,
) -> Path:
    safe_target = _safe_name(target_id or "default")
    return (
        selep_dir
        / _safe_name(app_name)
        / _safe_name(walker)
        / f"{safe_target}_limit{limit}_trial{trial}.json"
    )


def pooled_selep_model_path(
    selep_dir: Path,
    app_name: str,
    walker: str,
    label: str,
    limit: int,
    seed: int,
) -> Path:
    return (
        selep_dir
        / _safe_name(app_name)
        / _safe_name(walker)
        / f"{_safe_name(label)}_seed{seed}_limit{limit}.json"
    )


def pooled_metadata_path(
    selep_dir: Path,
    app_name: str,
    walker: str,
    label: str,
    seed: int,
) -> Path:
    return (
        selep_dir
        / _safe_name(app_name)
        / _safe_name(walker)
        / f"{_safe_name(label)}_seed{seed}_metadata.json"
    )


def write_pooled_metadata(path: Path, metadata: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n")


def write_empty_selep_model(
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
    reason: str,
    cluster_threshold: float = coaccess.DEFAULT_CLUSTER_THRESHOLD,
    look_back: int = DEFAULT_LOOK_BACK,
    epochs: int = 0,
    batch_size: int = DEFAULT_BATCH_SIZE,
    source_commit: str = DEFAULT_SELEP_SOURCE_COMMIT,
) -> dict[str, object]:
    starts = list(dict.fromkeys(_uuid_or_raw(raw) for raw in plan_start_ids if raw))
    if "*" not in starts:
        starts.append("*")
    plans = {
        start: {
            "plan": [],
            "predicted_partitions": [],
            "partition_scores": {},
            "history_request_count": 0,
            "training_trace_count": 0,
            "distinct_ids": 0,
            "cold_start": True,
            "failure_reason": reason,
        }
        for start in starts
    }
    model = _runtime_model(
        app_name=app_name,
        walker=walker,
        label=label,
        limit=limit,
        seed=seed,
        training_request_ids=training_request_ids,
        trial_request_ids=trial_request_ids,
        trial_count=trial_count,
        sources=[],
        normalized=[],
        node_types={},
        clusters=[],
        partition_members=[],
        fallback_order=[],
        partition_scores=[],
        predicted_partition_order=[],
        plans=plans,
        cluster_threshold=cluster_threshold,
        look_back=look_back,
        epochs=epochs,
        batch_size=batch_size,
        trained=False,
        train_samples=0,
        lstm_model_json="",
        lstm_weights="",
        selep_repo="",
        observed_source_commit="",
        train_history={},
        source_commit=source_commit,
        plan_len=0,
        cold_start=True,
        failure_reason=reason,
        self_labeled=False,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(model, indent=2, sort_keys=True) + "\n")
    return model


def write_selep_model_from_access_log(
    access_log: Path,
    output_path: Path,
    *,
    app_name: str,
    walker: str,
    target_id: str,
    start_id: str,
    limit: int,
    cluster_threshold: float = coaccess.DEFAULT_CLUSTER_THRESHOLD,
    request_id: str = "",
    source_commit: str = DEFAULT_SELEP_SOURCE_COMMIT,
    self_labeled: bool = False,
) -> dict[str, object]:
    trace = coaccess.extract_first_touch_sequence(access_log)
    node_types = extract_first_touch_types(access_log)
    clusters = coaccess.cluster_transactions([trace], cluster_threshold)
    fallback = coaccess._rank_cluster_items([0], [trace])
    start_key = _uuid_or_raw(start_id or target_id or "*")
    plan = _expand_partition_order(
        list(range(len(clusters))),
        _partition_members(clusters, [trace]),
        fallback,
        start_key,
        limit,
    )
    model = _runtime_model(
        app_name=app_name,
        walker=walker,
        label=POLICY_NAME,
        limit=limit,
        seed=0,
        training_request_ids=[request_id or target_id] if (request_id or target_id) else [],
        trial_request_ids=[request_id or target_id] if (request_id or target_id) else [],
        trial_count=1,
        sources=[str(access_log)],
        normalized=[trace],
        node_types=node_types,
        clusters=clusters,
        partition_members=_partition_members(clusters, [trace]),
        fallback_order=fallback,
        partition_scores=[1.0 for _ in clusters],
        predicted_partition_order=list(range(len(clusters))),
        plans={
            start_key: {
                "plan": plan,
                "predicted_partitions": [f"p{idx}" for idx in range(len(clusters))],
            },
            "*": {
                "plan": _expand_partition_order(
                    list(range(len(clusters))),
                    _partition_members(clusters, [trace]),
                    fallback,
                    "*",
                    limit,
                ),
                "predicted_partitions": [f"p{idx}" for idx in range(len(clusters))],
            },
        },
        cluster_threshold=cluster_threshold,
        look_back=DEFAULT_LOOK_BACK,
        epochs=0,
        batch_size=DEFAULT_BATCH_SIZE,
        trained=False,
        train_samples=0,
        lstm_model_json="",
        lstm_weights="",
        selep_repo="",
        observed_source_commit="",
        train_history={},
        source_commit=source_commit,
        self_labeled=self_labeled,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(model, indent=2, sort_keys=True) + "\n")
    return model


def write_pooled_selep_models_from_access_logs(
    access_logs: list[Path],
    output_paths: dict[int, Path],
    *,
    app_name: str,
    walker: str,
    label: str,
    seed: int,
    training_request_ids: list[str],
    trial_request_ids: list[str],
    trial_count: int,
    plan_start_ids: list[str],
    cluster_threshold: float = coaccess.DEFAULT_CLUSTER_THRESHOLD,
    look_back: int = DEFAULT_LOOK_BACK,
    epochs: int = DEFAULT_EPOCHS,
    batch_size: int = DEFAULT_BATCH_SIZE,
    selep_repo: Path | None = None,
    source_commit: str = DEFAULT_SELEP_SOURCE_COMMIT,
) -> dict[int, dict[str, object]]:
    if look_back <= 0:
        raise ValueError(f"SeLeP look_back must be positive, got {look_back}")
    if batch_size <= 0:
        raise ValueError(f"SeLeP batch_size must be positive, got {batch_size}")
    traces = [coaccess.extract_first_touch_sequence(path) for path in access_logs]
    normalized = [coaccess.dedupe_first_touch(trace) for trace in traces]
    node_types = _merge_type_maps([extract_first_touch_types(path) for path in access_logs])
    clusters = coaccess.cluster_transactions(normalized, cluster_threshold)
    fallback = coaccess._rank_cluster_items(list(range(len(normalized))), normalized)
    partition_members = _partition_members(clusters, normalized)
    request_vectors = _partition_access_vectors(normalized, clusters)

    artifact_dir = _common_artifact_dir(output_paths)
    training = _train_or_score_partitions(
        request_vectors,
        clusters=clusters,
        look_back=look_back,
        epochs=epochs,
        batch_size=batch_size,
        seed=seed,
        artifact_dir=artifact_dir,
        label=label,
        selep_repo=selep_repo,
        source_commit=source_commit,
    )

    starts = list(dict.fromkeys(_uuid_or_raw(raw) for raw in plan_start_ids if raw))
    if "*" not in starts:
        starts.append("*")

    models: dict[int, dict[str, object]] = {}
    for limit, output_path in sorted(output_paths.items()):
        plans: dict[str, dict[str, object]] = {}
        longest_plan = 0
        for start in starts:
            plan = [] if training["cold_start"] else _expand_partition_order(
                training["predicted_partition_order"],
                partition_members,
                fallback,
                start,
                limit,
            )
            longest_plan = max(longest_plan, len(plan))
            plans[start] = {
                "plan": plan,
                "predicted_partitions": [
                    f"p{idx}" for idx in training["predicted_partition_order"]
                ],
                "partition_scores": {
                    f"p{idx}": float(training["partition_scores"][idx])
                    for idx in range(len(training["partition_scores"]))
                },
                "history_request_count": min(len(request_vectors), max(look_back, 0)),
                "training_trace_count": len(normalized),
                "distinct_ids": len(set(fallback)),
                "cold_start": bool(training["cold_start"]),
                "failure_reason": str(training["failure_reason"]),
            }
        model = _runtime_model(
            app_name=app_name,
            walker=walker,
            label=label,
            limit=limit,
            seed=seed,
            training_request_ids=training_request_ids,
            trial_request_ids=trial_request_ids,
            trial_count=trial_count,
            sources=[str(path) for path in access_logs],
            normalized=normalized,
            node_types=node_types,
            clusters=clusters,
            partition_members=partition_members,
            fallback_order=fallback,
            partition_scores=training["partition_scores"],
            predicted_partition_order=training["predicted_partition_order"],
            plans=plans,
            cluster_threshold=cluster_threshold,
            look_back=look_back,
            epochs=epochs,
            batch_size=batch_size,
            trained=bool(training["trained"]),
            train_samples=int(training["train_samples"]),
            lstm_model_json=str(training["lstm_model_json"]),
            lstm_weights=str(training["lstm_weights"]),
            selep_repo=str(training["selep_repo"]),
            observed_source_commit=str(training["observed_source_commit"]),
            train_history=training["train_history"],
            source_commit=source_commit,
            plan_len=longest_plan,
            cold_start=bool(training["cold_start"]),
            failure_reason=str(training["failure_reason"]),
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(model, indent=2, sort_keys=True) + "\n")
        models[limit] = model
    return models


def plan_quality(model_path: Path, start_id: str, access_log: Path, limit: int) -> dict[str, str]:
    if not model_path.exists():
        return {}
    try:
        model = json.loads(model_path.read_text())
    except Exception:
        return {}
    plan = [] if limit <= 0 else _select_plan(model, start_id)[:limit]
    plan = coaccess.dedupe_first_touch(plan)
    actual = coaccess.extract_first_touch_sequence(access_log)
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


def extract_node_access_sequence(access_log: Path) -> list[NodeAccess]:
    sequence: list[NodeAccess] = []
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
                uid = str(UUID(raw))
            except ValueError:
                continue
            node_type = (row.get("type") or "Node").strip() or "Node"
            sequence.append(NodeAccess(uuid=uid, node_type=node_type))
    return sequence


def extract_first_touch_types(access_log: Path) -> dict[str, str]:
    types: dict[str, str] = {}
    for access in extract_node_access_sequence(access_log):
        types.setdefault(access.uuid, access.node_type)
    return types


def _train_or_score_partitions(
    request_vectors: list[list[float]],
    *,
    clusters: list[Any],
    look_back: int,
    epochs: int,
    batch_size: int,
    seed: int,
    artifact_dir: Path,
    label: str,
    selep_repo: Path | None,
    source_commit: str,
) -> dict[str, Any]:
    num_partitions = len(clusters)
    support_scores = _support_scores(request_vectors, num_partitions)
    if num_partitions == 0 or len(request_vectors) <= look_back or epochs <= 0:
        return _score_result(
            [0.0 for _ in range(num_partitions)],
            trained=False,
            train_samples=0,
            lstm_model_json="",
            lstm_weights="",
            train_history={},
            cold_start=True,
            failure_reason=(
                "insufficient_partition_history"
                if len(request_vectors) <= look_back
                else "training_disabled"
            ),
        )

    np, keras, create_binary_lstm_model, repo = _load_training_deps(selep_repo)
    observed_commit = _observed_selep_commit(repo)
    if observed_commit and source_commit and observed_commit != source_commit:
        raise RuntimeError(
            "SeLeP source commit mismatch: "
            f"expected {source_commit}, observed {observed_commit} at {repo}"
        )
    np.random.seed(seed)
    try:
        import tensorflow as tf

        keras.backend.clear_session()
        tf.random.set_seed(seed)
        if hasattr(tf.config.experimental, "enable_op_determinism"):
            tf.config.experimental.enable_op_determinism()
    except Exception:
        pass

    rows = 2
    cols = max(num_partitions, 2)
    vectors = np.asarray(
        [_encode_partition_access_vector(vector, rows, cols) for vector in request_vectors],
        dtype=np.float32,
    )
    data_x = []
    data_y = []
    for idx in range(len(vectors) - look_back):
        data_x.append(vectors[idx : idx + look_back])
        data_y.append(request_vectors[idx + look_back])
    x = np.asarray(data_x, dtype=np.float32).reshape(
        len(data_x), look_back, rows * cols
    )
    y = np.asarray(data_y, dtype=np.float32)

    model = create_binary_lstm_model(
        num_partitions=num_partitions,
        look_back=look_back,
        rows=rows,
        cols=cols,
    )
    model.compile(
        loss=keras.losses.BinaryCrossentropy(from_logits=False),
        optimizer=keras.optimizers.Adam(),
        metrics=[keras.metrics.MeanAbsoluteError(name="mae"), "accuracy"],
    )
    history = model.fit(
        x,
        y,
        epochs=epochs,
        batch_size=batch_size,
        verbose=0,
        shuffle=False,
    )
    history_window = _history_window(vectors, look_back, rows * cols)
    partition_scores = model.predict(history_window, verbose=0)[0].astype(float).tolist()

    artifact_dir.mkdir(parents=True, exist_ok=True)
    safe_label = _safe_name(label)
    model_json_path = artifact_dir / f"{safe_label}_seed{seed}_lookback{look_back}_lstm.json"
    weights_path = artifact_dir / f"{safe_label}_seed{seed}_lookback{look_back}_lstm.weights.h5"
    model_json_path.write_text(model.to_json())
    model.save_weights(weights_path)

    return _score_result(
        _blend_missing_scores(partition_scores, support_scores),
        trained=True,
        train_samples=len(data_x),
        lstm_model_json=str(model_json_path),
        lstm_weights=str(weights_path),
        train_history={key: [float(v) for v in vals] for key, vals in history.history.items()},
        selep_repo=str(repo),
        observed_source_commit=observed_commit,
    )


def _score_result(
    partition_scores: list[float],
    *,
    trained: bool,
    train_samples: int,
    lstm_model_json: str,
    lstm_weights: str,
    train_history: dict[str, list[float]],
    selep_repo: str = "",
    observed_source_commit: str = "",
    cold_start: bool = False,
    failure_reason: str = "",
) -> dict[str, Any]:
    order = [] if cold_start else sorted(
        range(len(partition_scores)),
        key=lambda idx: (-float(partition_scores[idx]), idx),
    )
    return {
        "partition_scores": [float(score) for score in partition_scores],
        "predicted_partition_order": order,
        "trained": trained,
        "train_samples": train_samples,
        "lstm_model_json": lstm_model_json,
        "lstm_weights": lstm_weights,
        "train_history": train_history,
        "selep_repo": selep_repo,
        "observed_source_commit": observed_source_commit,
        "cold_start": cold_start,
        "failure_reason": failure_reason,
    }


def _load_training_deps(selep_repo: Path | None):
    repo = selep_repo or _default_selep_repo()
    if not repo.exists():
        raise FileNotFoundError(
            f"SeLeP repo not found at {repo}; set SWEEP_SELEP_REPO"
        )
    os.environ.setdefault("TF_DETERMINISTIC_OPS", "1")
    os.environ.setdefault("TF_ENABLE_ONEDNN_OPTS", "0")
    repo_str = str(repo)
    if repo_str not in sys.path:
        sys.path.insert(0, repo_str)
    try:
        import numpy as np
        import tensorflow.keras as keras
        from Backend.Models.LSTM import create_binary_lstm_model
    except Exception as exc:
        raise RuntimeError(
            "SeLeP-adapted training requires TensorFlow plus the local SeLeP "
            f"repo on sys.path. Tried repo={repo}."
        ) from exc
    return np, keras, create_binary_lstm_model, repo


def _observed_selep_commit(repo: Path) -> str:
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "HEAD"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except Exception:
        return ""
    if proc.returncode != 0:
        return ""
    return proc.stdout.strip()


def _canonical_metadata() -> dict[str, Any]:
    external_tools = Path(__file__).resolve().parents[3]
    jaseci = external_tools.parent / "jaseci"
    py_gil_disabled = sysconfig.get_config_var("Py_GIL_DISABLED")
    gil_enabled: bool | None = None
    if hasattr(sys, "_is_gil_enabled"):
        try:
            gil_enabled = bool(sys._is_gil_enabled())
        except Exception:
            gil_enabled = None
    free_threaded_runtime = py_gil_disabled == 1
    gil_assert_passed = (
        gil_enabled is False if free_threaded_runtime and gil_enabled is not None else None
    )
    return {
        "python_executable": sys.executable,
        "python_version": sys.version,
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "py_gil_disabled": py_gil_disabled,
        "free_threaded_runtime": free_threaded_runtime,
        "gil_enabled": gil_enabled,
        "gil_assert_passed": gil_assert_passed,
        "tensorflow_imported_in_process": "tensorflow" in sys.modules,
        "git_commits": {
            "jaseci_external_tools": _git_commit(external_tools),
            "jaseci": _git_commit(jaseci),
        },
    }


def _git_commit(repo: Path) -> str:
    if not repo.exists():
        return ""
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "HEAD"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except Exception:
        return ""
    return proc.stdout.strip() if proc.returncode == 0 else ""


def _sha256_file(path: Path) -> str:
    try:
        hasher = hashlib.sha256()
        with path.open("rb") as fh:
            for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                hasher.update(chunk)
        return hasher.hexdigest()
    except Exception:
        return ""


def _stable_hash_json(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _default_selep_repo() -> Path:
    raw = os.environ.get("SWEEP_SELEP_REPO") or os.environ.get("SELEP_REPO")
    if raw:
        return Path(raw).expanduser().resolve()
    return Path(__file__).resolve().parents[4] / "SeLeP"


def _history_window(vectors: Any, look_back: int, feature_len: int):
    np = __import__("numpy")
    window = vectors[-look_back:]
    if len(window) < look_back:
        pad = np.zeros((look_back - len(window), feature_len), dtype=np.float32)
        window = np.vstack([pad, window])
    return np.asarray(window, dtype=np.float32).reshape(1, look_back, feature_len)


def _encode_partition_access_vector(
    vector: list[float],
    rows: int,
    cols: int,
) -> list[float]:
    encoded = [0.0 for _ in range(rows * cols)]
    for idx, val in enumerate(vector):
        if idx >= cols:
            break
        encoded[idx] = float(val)
    return encoded


def _support_scores(request_vectors: list[list[float]], num_partitions: int) -> list[float]:
    if num_partitions <= 0:
        return []
    counts = [0.0 for _ in range(num_partitions)]
    for vector in request_vectors:
        for idx, val in enumerate(vector):
            if val > 0:
                counts[idx] += 1.0
    denom = float(len(request_vectors) or 1)
    return [count / denom for count in counts]


def _blend_missing_scores(predicted: list[float], fallback: list[float]) -> list[float]:
    out: list[float] = []
    for idx, fallback_score in enumerate(fallback):
        if idx < len(predicted):
            out.append(float(predicted[idx]))
        else:
            out.append(float(fallback_score))
    return out


def _partition_access_vectors(
    traces: list[list[str]],
    clusters: list[Any],
) -> list[list[float]]:
    vectors: list[list[float]] = []
    for trace in traces:
        items = set(trace)
        vector = [0.0 for _ in clusters]
        for idx, cluster in enumerate(clusters):
            if items & cluster.items:
                vector[idx] = 1.0
        vectors.append(vector)
    return vectors


def _partition_members(clusters: list[Any], traces: list[list[str]]) -> list[list[str]]:
    return [
        coaccess._rank_cluster_items(cluster.trace_indexes, traces)
        for cluster in clusters
    ]


def _expand_partition_order(
    partition_order: list[int],
    partition_members: list[list[str]],
    fallback_order: list[str],
    start: str,
    limit: int,
) -> list[str]:
    if limit <= 0:
        return []
    out: list[str] = []
    seen: set[str] = set()
    if start and start != "*" and _is_uuid(start):
        out.append(start)
        seen.add(start)
    for partition_idx in partition_order:
        if partition_idx < 0 or partition_idx >= len(partition_members):
            continue
        for uid in partition_members[partition_idx]:
            if uid in seen:
                continue
            out.append(uid)
            seen.add(uid)
            if len(out) >= limit:
                return out
    for uid in fallback_order:
        if uid in seen:
            continue
        out.append(uid)
        seen.add(uid)
        if len(out) >= limit:
            break
    return out


def _runtime_model(
    *,
    app_name: str,
    walker: str,
    label: str,
    limit: int,
    seed: int,
    training_request_ids: list[str],
    trial_request_ids: list[str],
    trial_count: int,
    sources: list[str],
    normalized: list[list[str]],
    node_types: dict[str, str],
    clusters: list[Any],
    partition_members: list[list[str]],
    fallback_order: list[str],
    partition_scores: list[float],
    predicted_partition_order: list[int],
    plans: dict[str, dict[str, object]],
    cluster_threshold: float,
    look_back: int,
    epochs: int,
    batch_size: int,
    trained: bool,
    train_samples: int,
    lstm_model_json: str,
    lstm_weights: str,
    selep_repo: str,
    observed_source_commit: str,
    train_history: dict[str, list[float]],
    source_commit: str = DEFAULT_SELEP_SOURCE_COMMIT,
    plan_len: int | None = None,
    cold_start: bool = False,
    failure_reason: str = "",
    self_labeled: bool = False,
) -> dict[str, object]:
    partition_payload = [
        {
            "id": f"p{idx}",
            "members": members,
            "trace_indexes": list(clusters[idx].trace_indexes),
        }
        for idx, members in enumerate(partition_members)
    ]
    plan_payload = {
        key: entry.get("plan", []) if isinstance(entry, dict) else entry
        for key, entry in plans.items()
    }
    canonical = _canonical_metadata()
    metadata = {
        "pooled": len(sources) > 1,
        "seed": seed,
        "train_n": len(training_request_ids),
        "trial_count": trial_count,
        "training_request_ids": list(training_request_ids),
        "trial_request_ids": list(trial_request_ids),
        "source_logs": sources,
        "trace_lengths": [len(trace) for trace in normalized],
        "trace_distinct_ids": [len(set(trace)) for trace in normalized],
        "cluster_threshold": cluster_threshold,
        "look_back": look_back,
        "epochs": epochs,
        "batch_size": batch_size,
        "trained": trained,
        "train_samples": train_samples,
        "cold_start": cold_start,
        "failure_reason": failure_reason,
        "self_labeled": self_labeled,
        "lstm_model_json": lstm_model_json,
        "lstm_weights": lstm_weights,
        "selep_repo": selep_repo,
        "selep_source_commit": source_commit,
        "observed_selep_source_commit": observed_source_commit,
        "source_log_sha256": {
            path: _sha256_file(Path(path)) for path in sources
        },
        "partition_map_sha256": _stable_hash_json(partition_payload),
        "plan_sha256": _stable_hash_json(plan_payload),
        "canonical": canonical,
        "partition_stage": "lib.prefetch_exp.coaccess.cluster_transactions",
        "partition_stage_hyperparameters": {
            "cluster_threshold": cluster_threshold,
        },
        "block_unit": "Jac node anchor",
        "block_identity": "node_class + UUID",
        "partition_clustering_key": (
            "UUID string, matching the standalone coaccess baseline; "
            "node_class is retained in block_ids for partition-stage visibility"
        ),
        "block_encoding_substitution": (
            "No Jac analog for SeLeP data-value block encodings; the LSTM "
            "input is a binary partition-access vector per request."
        ),
        "input_shape": {
            "look_back": look_back,
            "rows": 2,
            "cols": max(len(clusters), 2) if clusters else 0,
        },
        "history_source": "last look_back training requests for static file plans",
        "train_test_hygiene": {
            "training_trace_collection": (
                "same_request_self_label_escape_hatch"
                if self_labeled
                else "strictly_before_measured_request"
            ),
            "self_labeled": self_labeled,
            "self_label_requires_escape_hatch": True,
            "cold_start_uses_empty_plan": cold_start,
        },
        "train_history": train_history,
    }
    partitions = []
    for idx, members in enumerate(partition_members):
        partitions.append(
            {
                "id": f"p{idx}",
                "cluster_id": idx,
                "trace_count": len(clusters[idx].trace_indexes),
                "distinct_ids": len(clusters[idx].items),
                "score": float(partition_scores[idx]) if idx < len(partition_scores) else 0.0,
                "top_ids": members[: min(20, len(members))],
                "top_blocks": [
                    _block_record(uid, node_types) for uid in members[: min(20, len(members))]
                ],
            }
        )
    return {
        "version": 1,
        "policy": label,
        "runtime_policy": RUNTIME_POLICY,
        "algorithm": "selep-adapted-coaccess-partitions-author-lstm",
        "app": app_name,
        "walker": walker,
        "limit": limit,
        "metadata": metadata,
        "cluster_threshold": cluster_threshold,
        "cluster_count": len(clusters),
        "num_partitions": len(clusters),
        "partitions": partitions,
        "partition_members": {
            f"p{idx}": members for idx, members in enumerate(partition_members)
        },
        "block_types": dict(sorted(node_types.items())),
        "fallback_order": fallback_order,
        "partition_scores": {
            f"p{idx}": float(score) for idx, score in enumerate(partition_scores)
        },
        "predicted_partition_order": [f"p{idx}" for idx in predicted_partition_order],
        "plan_len": plan_len if plan_len is not None else max(
            (len(entry.get("plan", [])) for entry in plans.values()),
            default=0,
        ),
        "plans": plans,
    }


def _block_record(uid: str, node_types: dict[str, str]) -> dict[str, str]:
    node_type = node_types.get(uid, "Node")
    return {
        "uuid": uid,
        "node_type": node_type,
        "block_id": f"{node_type}:{uid}",
    }


def _merge_type_maps(maps: list[dict[str, str]]) -> dict[str, str]:
    out: dict[str, str] = {}
    for mapping in maps:
        for uid, node_type in mapping.items():
            out.setdefault(uid, node_type)
    return out


def _common_artifact_dir(output_paths: dict[int, Path]) -> Path:
    for path in output_paths.values():
        return path.parent
    return Path(".")


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
    return safe[:160] or "default"
