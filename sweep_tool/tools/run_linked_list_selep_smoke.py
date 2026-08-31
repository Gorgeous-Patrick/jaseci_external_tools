"""Collect a LinkedList SQL trace and train a small SeLeP-shaped model.

This is a smoke-test pipeline for the SeLeP integration work.  The default
frequency model is intentionally lightweight.  The optional LSTM model reuses
SeLeP's TensorFlow/Keras LSTM implementation against the generated
partition-sequence workload.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import shlex
import shutil
import subprocess
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


SCRIPT = Path(__file__).resolve()
SWEEP_TOOL = SCRIPT.parents[1]
REPO_ROOT = SCRIPT.parents[2]
APP_DIR = REPO_ROOT / "linked_list"
MANIFEST = SWEEP_TOOL / "manifests" / "linked_list.yaml"
DEFAULT_JAC_BIN = Path("/home/patrickli/Space/jaseci/jac/zig-out/bin/jac")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jac-bin", default=str(DEFAULT_JAC_BIN))
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--out-dir", default=str(APP_DIR / "selep_smoke"))
    parser.add_argument("--list-size", type=int, default=24)
    parser.add_argument("--trials", type=int, default=1)
    parser.add_argument("--look-back", type=int, default=4)
    parser.add_argument("--top-k", type=int, default=4)
    parser.add_argument("--test-fraction", type=float, default=0.30)
    parser.add_argument("--model-kind", choices=["frequency", "lstm"], default="frequency")
    parser.add_argument("--selep-root", default="/home/patrickli/Space/jaseci_env/SeLeP")
    parser.add_argument("--lstm-epochs", type=int, default=8)
    parser.add_argument("--lstm-batch-size", type=int, default=8)
    parser.add_argument("--lstm-validation-fraction", type=float, default=0.10)
    parser.add_argument("--lstm-seed", type=int, default=42)
    parser.add_argument("--partitions", type=int, default=64)
    parser.add_argument("--block-source", choices=["hash", "pg-buffercache"], default="hash")
    parser.add_argument("--max-block-selects", type=int, default=16)
    parser.add_argument("--sql-contains", default="")
    parser.add_argument("--ssh-target", default="clarity2")
    parser.add_argument("--ssh-option", action="append", default=None)
    parser.add_argument("--postgres-container", default="postgres")
    parser.add_argument("--postgres-user", default="jac")
    parser.add_argument("--postgres-db", default="jac_db")
    parser.add_argument("--partition-size", type=int, default=8)
    parser.add_argument("--skip-collect", action="store_true")
    parser.add_argument("--skip-workload-rebuild", action="store_true")
    args = parser.parse_args()
    if args.ssh_option is None:
        args.ssh_option = ["-F", "/home/patrickli/.ssh/config"]
    return args


def reset_output_dir(out_dir: Path) -> None:
    protected = {REPO_ROOT.resolve(), APP_DIR.resolve(), SWEEP_TOOL.resolve()}
    resolved = out_dir.resolve()
    if resolved in protected or "selep" not in resolved.name:
        raise RuntimeError(f"refusing to clear suspicious output directory: {resolved}")
    if resolved.exists():
        shutil.rmtree(resolved)
    resolved.mkdir(parents=True, exist_ok=True)


def run_collect(args: argparse.Namespace, out_dir: Path) -> None:
    trace_path = out_dir / "trace.jsonl"
    log_path = out_dir / "collect.log"
    app_copy = out_dir / "app_copy"
    manifest_copy = out_dir / "linked_list_smoke.yaml"
    trace_path.unlink(missing_ok=True)
    prepare_app_copy(app_copy, manifest_copy)
    env = os.environ.copy()
    env.update(
        {
            "JAC_SELEP_TRACE": str(trace_path),
            "JAC_LIST_SIZE": str(args.list_size),
            "JAC_TRIALS": str(args.trials),
            "SWEEP_POLICIES": "none",
            "SWEEP_PREFETCH_LIMITS": "0",
            "JAC_COUNT_DB": "0",
            "JAC_QUERY_CACHE": "1",
            "PYTHONUNBUFFERED": "1",
            "SWEEP_DB_HOST": args.ssh_target,
            "SWEEP_DB_SSH_OPTIONS": " ".join(shlex.quote(part) for part in args.ssh_option),
        }
    )
    cmd = [
        args.python,
        "-m",
        "lib.prefetch_exp.cli",
        "--manifest",
        str(manifest_copy),
        "--jac-bin",
        args.jac_bin,
    ]
    with log_path.open("w", buffering=1) as log:
        log.write(f"started={time.strftime('%Y-%m-%dT%H:%M:%S%z')}\n")
        log.write(f"cmd={' '.join(cmd)}\n")
        log.write(f"trace={trace_path}\n")
        proc = subprocess.run(
            cmd,
            cwd=str(SWEEP_TOOL),
            env=env,
            text=True,
            stdout=log,
            stderr=subprocess.STDOUT,
            check=False,
        )
        log.write(f"returncode={proc.returncode}\n")
    if proc.returncode != 0:
        raise RuntimeError(f"LinkedList trace collection failed; see {log_path}")
    if not trace_path.exists() or trace_path.stat().st_size == 0:
        raise RuntimeError(f"LinkedList trace collection produced no trace: {trace_path}")


def prepare_app_copy(app_copy: Path, manifest_copy: Path) -> None:
    shutil.rmtree(app_copy, ignore_errors=True)
    app_copy.mkdir(parents=True, exist_ok=True)
    for name in ("jac.toml", "main.jac", "docker-compose.yaml"):
        shutil.copy2(APP_DIR / name, app_copy / name)
    manifest_text = MANIFEST.read_text()
    lines = []
    for line in manifest_text.splitlines():
        if line.startswith("app_dir:"):
            lines.append(f"app_dir: {app_copy}")
        else:
            lines.append(line)
    manifest_copy.write_text("\n".join(lines) + "\n")


def load_trace(trace_path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with trace_path.open() as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            if record.get("status") != "ok":
                continue
            sql = str(record.get("sql") or "").strip()
            if not sql:
                continue
            records.append(record)
    if not records:
        raise RuntimeError(f"trace has no successful SQL records: {trace_path}")
    return records


def collect_pg_buffercache_blocks(args: argparse.Namespace, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    selects = [record for record in records if is_select_record(record)]
    if args.sql_contains:
        needle = args.sql_contains.lower()
        selects = [
            record
            for record in selects
            if needle in compact_sql(record.get("sql") or "").lower()
        ]
    if args.max_block_selects > 0:
        selects = selects[: args.max_block_selects]
    if not selects:
        raise RuntimeError("no successful SELECT records available for pg-buffercache collection")
    remote_psql(args, "CREATE EXTENSION IF NOT EXISTS pg_buffercache;")
    enriched: list[dict[str, Any]] = []
    empty = 0
    for idx, record in enumerate(selects, start=1):
        restart_remote_postgres(args)
        sql = render_sql(record.get("sql") or "", record.get("params") or {})
        blocks = psql_query_blocks(args, sql)
        if not blocks:
            empty += 1
            continue
        item = dict(record)
        item["_result_blocks"] = blocks
        enriched.append(item)
        print(f"block replay {idx}/{len(selects)}: blocks={len(blocks)} sql={compact_sql(sql)[:90]}")
    if not enriched:
        raise RuntimeError("pg-buffercache replay produced no block-bearing records")
    print(
        "block replay summary: "
        f"selected={len(selects)} block_bearing={len(enriched)} empty={empty}"
        f" filter={args.sql_contains or '<none>'}"
    )
    return enriched


def is_select_record(record: dict[str, Any]) -> bool:
    if record.get("status") != "ok":
        return False
    sql = compact_sql(record.get("sql") or "")
    return sql.upper().startswith("SELECT ")


def compact_sql(sql: str) -> str:
    return " ".join(str(sql).split())


def restart_remote_postgres(args: argparse.Namespace) -> None:
    remote(args, ["docker", "restart", args.postgres_container])
    deadline = time.time() + 30.0
    while time.time() < deadline:
        proc = remote(
            args,
            [
                "docker",
                "exec",
                args.postgres_container,
                "pg_isready",
                "-U",
                args.postgres_user,
                "-d",
                args.postgres_db,
            ],
            check=False,
            capture=True,
        )
        if proc.returncode == 0:
            return
        time.sleep(0.5)
    raise RuntimeError(f"remote Postgres did not become ready after restart: {args.postgres_container}")


def psql_query_blocks(args: argparse.Namespace, sql: str) -> list[str]:
    block_sql = """
\\o /dev/null
{query};
\\o
SELECT DISTINCT c.relname || '_' || b.relblocknumber
FROM pg_buffercache b
JOIN pg_database d ON b.reldatabase = d.oid
JOIN pg_class c ON b.relfilenode = pg_relation_filenode(c.oid)
WHERE d.datname = current_database()
  AND b.relblocknumber IS NOT NULL
  AND c.relkind IN ('r', 'i', 't')
  AND c.relname NOT LIKE 'pg_%'
  AND c.relname NOT LIKE 'sql_%'
ORDER BY 1;
""".format(query=sql.rstrip().rstrip(";"))
    proc = remote_psql(args, block_sql, capture=True)
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


def remote_psql(args: argparse.Namespace, sql: str, capture: bool = False) -> subprocess.CompletedProcess[str]:
    return remote(
        args,
        [
            "docker",
            "exec",
            "-i",
            args.postgres_container,
            "psql",
            "-qAtX",
            "-v",
            "ON_ERROR_STOP=1",
            "-U",
            args.postgres_user,
            "-d",
            args.postgres_db,
        ],
        input_text=sql,
        capture=capture,
    )


def remote(
    args: argparse.Namespace,
    command: list[str],
    *,
    input_text: str | None = None,
    capture: bool = False,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    ssh_cmd = ["ssh", *args.ssh_option, args.ssh_target, *command]
    proc = subprocess.run(
        ssh_cmd,
        input=input_text,
        text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
        check=False,
    )
    if check and proc.returncode != 0:
        rendered = " ".join(shlex.quote(part) for part in ssh_cmd)
        stderr = (proc.stderr or "").strip()
        raise RuntimeError(f"remote command failed: {rendered}\n{stderr}")
    return proc


def render_sql(sql: str, params: dict[str, Any]) -> str:
    out: list[str] = []
    i = 0
    n = len(sql)
    in_squote = False
    in_dquote = False
    while i < n:
        ch = sql[i]
        if in_squote:
            out.append(ch)
            if ch == "'":
                if i + 1 < n and sql[i + 1] == "'":
                    out.append("'")
                    i += 1
                else:
                    in_squote = False
            i += 1
            continue
        if in_dquote:
            out.append(ch)
            if ch == '"':
                in_dquote = False
            i += 1
            continue
        if ch == "'":
            in_squote = True
            out.append(ch)
            i += 1
            continue
        if ch == '"':
            in_dquote = True
            out.append(ch)
            i += 1
            continue
        if ch == ":":
            if i + 1 < n and sql[i + 1] == ":":
                out.append("::")
                i += 2
                continue
            j = i + 1
            name = ""
            while j < n and (sql[j].isalnum() or sql[j] == "_"):
                name += sql[j]
                j += 1
            if name and name in params:
                out.append(sql_literal(params[name]))
                i = j
                continue
        out.append(ch)
        i += 1
    return "".join(out)


def sql_literal(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list):
        items = []
        for item in value:
            escaped = str(item).replace("\\", "\\\\").replace('"', '\\"')
            items.append(f'"{escaped}"')
        return "'" + "{" + ",".join(items) + "}" + "'"
    text = str(value).replace("'", "''")
    return f"'{text}'"


def stable_partition(record: dict[str, Any], partition_count: int) -> str:
    sql = " ".join(str(record.get("sql") or "").split())
    params = json.dumps(record.get("params") or {}, sort_keys=True)
    digest = hashlib.sha256(f"{sql}\n{params}".encode()).digest()
    value = int.from_bytes(digest[:8], "big")
    return f"p{value % partition_count}"


def block_id(record: dict[str, Any], partition: str) -> str:
    sql = " ".join(str(record.get("sql") or "").split())
    relation = "unknown"
    lowered = sql.lower()
    if " from " in lowered:
        relation = lowered.split(" from ", 1)[1].split()[0].strip('"')
    elif " into " in lowered:
        relation = lowered.split(" into ", 1)[1].split()[0].strip('"')
    digest = hashlib.sha256(json.dumps(record.get("params") or {}, sort_keys=True).encode()).hexdigest()
    return f"{relation}_{partition}_{digest[:8]}"


def assign_block_partitions(records: list[dict[str, Any]], partition_size: int) -> dict[str, str]:
    if partition_size <= 0:
        raise ValueError(f"partition_size must be positive, got {partition_size}")
    mapping: dict[str, str] = {}
    for record in records:
        for block in record.get("_result_blocks") or []:
            if block not in mapping:
                mapping[block] = f"p{len(mapping) // partition_size}"
    return mapping


def write_workload(
    records: list[dict[str, Any]],
    workload_path: Path,
    partition_count: int,
    partition_size: int,
) -> list[list[str]]:
    partition_events: list[list[str]] = []
    block_partitions = assign_block_partitions(records, partition_size)
    with workload_path.open("w", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=[
                "theTime",
                "ClientIP",
                "row",
                "statement",
                "resultBlock",
                "resultPartitions",
            ],
        )
        writer.writeheader()
        for idx, record in enumerate(records):
            result_blocks = record.get("_result_blocks") or []
            if result_blocks:
                event_partitions = sorted({block_partitions[block] for block in result_blocks})
                result_block_text = "[" + ", ".join(result_blocks) + "]"
            else:
                partition = stable_partition(record, partition_count)
                event_partitions = [partition]
                result_block_text = f"[{block_id(record, partition)}]"
            partition_events.append(event_partitions)
            writer.writerow(
                {
                    "theTime": str(record.get("ts_ns") or ""),
                    "ClientIP": str(record.get("thread_id") or "linked_list"),
                    "row": str(record.get("row_count") or 0),
                    "statement": record.get("sql") or "",
                    "resultBlock": result_block_text,
                    "resultPartitions": "[" + ", ".join(event_partitions) + "]",
                }
            )
    return partition_events


def read_workload_partitions(workload_path: Path) -> list[list[str]]:
    if not workload_path.exists():
        raise RuntimeError(f"workload does not exist: {workload_path}")
    partition_events: list[list[str]] = []
    with workload_path.open(newline="") as fh:
        reader = csv.DictReader(fh)
        if "resultPartitions" not in (reader.fieldnames or []):
            raise RuntimeError(f"workload is missing resultPartitions column: {workload_path}")
        for row in reader:
            parts = [
                part.strip()
                for part in str(row.get("resultPartitions") or "").strip("[]").split(",")
                if part.strip()
            ]
            if parts:
                partition_events.append(parts)
    if not partition_events:
        raise RuntimeError(f"workload has no partition events: {workload_path}")
    return partition_events


def context_key(partition_events: list[list[str]], start: int, look_back: int) -> str:
    return "|".join(
        ";".join(parts) for parts in partition_events[start : start + look_back]
    )


def top_predictions(
    counts: dict[str, Counter[str]],
    key: str,
    global_counts: Counter[str],
    top_k: int,
) -> list[str]:
    if key in counts:
        return [part for part, _count in counts[key].most_common(top_k)]
    return [part for part, _count in global_counts.most_common(top_k)]


def train_frequency_model(
    partition_events: list[list[str]],
    look_back: int,
    top_k: int,
    test_fraction: float,
) -> dict[str, Any]:
    if len(partition_events) <= look_back:
        raise RuntimeError(
            f"need more than look_back={look_back} SQL events, got {len(partition_events)}"
        )
    counts: dict[str, Counter[str]] = defaultdict(Counter)
    total_examples = len(partition_events) - look_back
    if not 0.0 <= test_fraction < 1.0:
        raise ValueError(f"test_fraction must be in [0, 1), got {test_fraction}")
    test_examples = int(round(total_examples * test_fraction))
    if total_examples > 1:
        test_examples = max(1, min(test_examples, total_examples - 1))
    split_idx = len(partition_events) - test_examples

    global_counts: Counter[str] = Counter()
    for parts in partition_events[:split_idx]:
        global_counts.update(parts)

    train_total = 0
    train_hits = 0
    for idx in range(look_back, split_idx):
        key = context_key(partition_events, idx - look_back, look_back)
        targets = partition_events[idx]
        prediction = top_predictions(counts, key, global_counts, top_k)
        if any(target in prediction for target in targets):
            train_hits += 1
        for target in targets:
            counts[key][target] += 1
        train_total += 1

    test_total = 0
    test_event_hits = 0
    test_partition_covered = 0
    test_partition_total = 0
    for idx in range(split_idx, len(partition_events)):
        key = context_key(partition_events, idx - look_back, look_back)
        targets = partition_events[idx]
        prediction = top_predictions(counts, key, global_counts, top_k)
        target_set = set(targets)
        covered = target_set.intersection(prediction)
        if covered:
            test_event_hits += 1
        test_partition_covered += len(covered)
        test_partition_total += len(target_set)
        test_total += 1

    model_contexts = {
        key: [{"partition": part, "count": count} for part, count in counter.most_common()]
        for key, counter in sorted(counts.items())
    }
    all_counts: Counter[str] = Counter()
    for parts in partition_events:
        all_counts.update(parts)
    return {
        "model_type": "next_partition_frequency_smoke",
        "source": "linked_list JAC_SELEP_TRACE",
        "look_back": look_back,
        "top_k": top_k,
        "test_fraction": test_fraction,
        "split_idx": split_idx,
        "events": len(partition_events),
        "examples": total_examples,
        "train_examples": train_total,
        "test_examples": test_total,
        "contexts": len(model_contexts),
        "online_train_hit_rate": train_hits / train_total if train_total else 0.0,
        "test_event_hit_rate": test_event_hits / test_total if test_total else 0.0,
        "test_partition_coverage": (
            test_partition_covered / test_partition_total
            if test_partition_total
            else 0.0
        ),
        "global_top": [
            {"partition": part, "count": count}
            for part, count in all_counts.most_common(top_k)
        ],
        "context_model": model_contexts,
    }


def partition_sort_key(partition: str) -> tuple[int, str]:
    if partition.startswith("p") and partition[1:].isdigit():
        return (int(partition[1:]), partition)
    return (sys.maxsize, partition)


def matrix_dims(num_partitions: int) -> tuple[int, int]:
    if num_partitions <= 0:
        raise ValueError(f"num_partitions must be positive, got {num_partitions}")
    rows = max(2, int(num_partitions ** 0.5))
    cols = max(2, (num_partitions + rows - 1) // rows)
    while rows * cols < num_partitions:
        cols += 1
    return rows, cols


def supervised_split(total_examples: int, test_fraction: float) -> tuple[int, int]:
    if total_examples <= 0:
        raise RuntimeError("need at least one supervised example")
    if not 0.0 <= test_fraction < 1.0:
        raise ValueError(f"test_fraction must be in [0, 1), got {test_fraction}")
    test_examples = int(round(total_examples * test_fraction))
    if total_examples > 1:
        test_examples = max(1, min(test_examples, total_examples - 1))
    else:
        test_examples = 0
    split_idx = total_examples - test_examples
    return split_idx, test_examples


def train_lstm_model(
    partition_events: list[list[str]],
    look_back: int,
    top_k: int,
    test_fraction: float,
    args: argparse.Namespace,
    out_dir: Path,
) -> dict[str, Any]:
    if len(partition_events) <= look_back:
        raise RuntimeError(
            f"need more than look_back={look_back} SQL events, got {len(partition_events)}"
        )

    os.environ.setdefault("CUDA_VISIBLE_DEVICES", "-1")
    os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "1")
    os.environ.setdefault("OMP_NUM_THREADS", "2")
    os.environ.setdefault("TF_NUM_INTRAOP_THREADS", "2")
    os.environ.setdefault("TF_NUM_INTEROP_THREADS", "1")

    selep_root = Path(args.selep_root).expanduser().resolve()
    if not (selep_root / "Backend" / "Models" / "LSTM.py").exists():
        raise RuntimeError(f"SeLeP LSTM.py not found under {selep_root}")
    sys.path.insert(0, str(selep_root))

    import numpy as np
    import tensorflow as tf
    from tensorflow import keras
    from Backend.Models.LSTM import create_binary_lstm_model

    tf.random.set_seed(args.lstm_seed)
    np.random.seed(args.lstm_seed)

    vocab = sorted({part for event in partition_events for part in event}, key=partition_sort_key)
    part_to_idx = {part: idx for idx, part in enumerate(vocab)}
    rows, cols = matrix_dims(len(vocab))
    data_shape = rows * cols

    vectors = np.zeros((len(partition_events), data_shape), dtype=np.float32)
    outputs = np.zeros((len(partition_events), len(vocab)), dtype=np.float32)
    for event_idx, parts in enumerate(partition_events):
        for part in parts:
            idx = part_to_idx[part]
            vectors[event_idx, idx] = 1.0
            outputs[event_idx, idx] = 1.0

    data_x: list[Any] = []
    data_y: list[Any] = []
    for idx in range(look_back, len(partition_events)):
        data_x.append(vectors[idx - look_back : idx])
        data_y.append(outputs[idx])
    x = np.asarray(data_x, dtype=np.float32)
    y = np.asarray(data_y, dtype=np.float32)

    split_examples, test_examples = supervised_split(len(x), test_fraction)
    x_train, y_train = x[:split_examples], y[:split_examples]
    x_test, y_test = x[split_examples:], y[split_examples:]

    val_count = int(round(len(x_train) * args.lstm_validation_fraction))
    if len(x_train) > 1:
        val_count = max(1, min(val_count, len(x_train) - 1))
    else:
        val_count = 0
    if val_count:
        train_inputs = x_train[:-val_count]
        train_targets = y_train[:-val_count]
        validation_data = (x_train[-val_count:], y_train[-val_count:])
    else:
        train_inputs = x_train
        train_targets = y_train
        validation_data = None

    model = create_binary_lstm_model(len(vocab), look_back, rows, cols)
    model.compile(
        loss=keras.losses.BinaryCrossentropy(from_logits=False),
        optimizer=keras.optimizers.Adam(),
        metrics=[keras.metrics.MeanAbsoluteError(), "accuracy"],
    )
    callbacks = []
    if validation_data is not None:
        callbacks.append(keras.callbacks.EarlyStopping(monitor="val_loss", patience=3, restore_best_weights=True))

    started = time.time()
    history = model.fit(
        train_inputs,
        train_targets,
        epochs=args.lstm_epochs,
        batch_size=args.lstm_batch_size,
        validation_data=validation_data,
        callbacks=callbacks,
        verbose=1,
        shuffle=False,
    )
    train_seconds = time.time() - started

    train_pred = model.predict(x_train, verbose=0)
    test_pred = model.predict(x_test, verbose=0) if len(x_test) else np.zeros((0, len(vocab)))

    train_eval = evaluate_lstm_predictions(train_pred, y_train, vocab, top_k)
    test_eval = evaluate_lstm_predictions(test_pred, y_test, vocab, top_k)

    keras_json_path = out_dir / "model_lstm_architecture.json"
    weights_path = out_dir / "model_lstm.weights.h5"
    keras_json_path.write_text(model.to_json())
    model.save_weights(str(weights_path))

    return {
        "model_type": "selep_binary_lstm",
        "source": "linked_list JAC_SELEP_TRACE",
        "selep_root": str(selep_root),
        "look_back": look_back,
        "top_k": top_k,
        "test_fraction": test_fraction,
        "events": len(partition_events),
        "examples": len(x),
        "train_examples": len(x_train),
        "test_examples": test_examples,
        "contexts": 0,
        "partitions": len(vocab),
        "rows": rows,
        "cols": cols,
        "lstm_epochs_requested": args.lstm_epochs,
        "lstm_epochs_ran": len(history.history.get("loss", [])),
        "lstm_batch_size": args.lstm_batch_size,
        "lstm_validation_examples": val_count,
        "lstm_train_seconds": train_seconds,
        "online_train_hit_rate": train_eval["event_hit_rate"],
        "test_event_hit_rate": test_eval["event_hit_rate"],
        "test_partition_coverage": test_eval["partition_coverage"],
        "train_partition_coverage": train_eval["partition_coverage"],
        "vocab": vocab,
        "history": {key: [float(value) for value in values] for key, values in history.history.items()},
        "keras_model_json": str(keras_json_path),
        "keras_weights": str(weights_path),
    }


def evaluate_lstm_predictions(predictions: Any, targets: Any, vocab: list[str], top_k: int) -> dict[str, float]:
    if len(targets) == 0:
        return {"event_hit_rate": 0.0, "partition_coverage": 0.0}
    import numpy as np

    event_hits = 0
    covered_total = 0
    target_total = 0
    k = max(1, min(top_k, len(vocab)))
    for pred, target in zip(predictions, targets, strict=True):
        top_indices = np.argsort(pred)[-k:]
        predicted = set(int(idx) for idx in top_indices)
        wanted = {int(idx) for idx in np.flatnonzero(target > 0.0)}
        covered = predicted.intersection(wanted)
        if covered:
            event_hits += 1
        covered_total += len(covered)
        target_total += len(wanted)
    return {
        "event_hit_rate": event_hits / len(targets),
        "partition_coverage": covered_total / target_total if target_total else 0.0,
    }


def write_summary(out_dir: Path, trace_path: Path, workload_path: Path, model_path: Path, model: dict[str, Any]) -> None:
    summary = {
        "trace": str(trace_path),
        "workload": str(workload_path),
        "model": str(model_path),
        "raw_trace_events": model.get("raw_trace_events", model["events"]),
        "training_events": model["events"],
        "events": model["events"],
        "examples": model["examples"],
        "train_examples": model["train_examples"],
        "test_examples": model["test_examples"],
        "contexts": model["contexts"],
        "online_train_hit_rate": model["online_train_hit_rate"],
        "test_event_hit_rate": model["test_event_hit_rate"],
        "test_partition_coverage": model["test_partition_coverage"],
        "model_type": model["model_type"],
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True))


def main() -> int:
    args = parse_args()
    out_dir = Path(args.out_dir).expanduser().resolve()
    if args.skip_collect:
        out_dir.mkdir(parents=True, exist_ok=True)
    else:
        reset_output_dir(out_dir)
    trace_path = out_dir / "trace.jsonl"
    workload_path = out_dir / "workload.csv"
    model_path = out_dir / "model.json"

    if args.skip_workload_rebuild and not args.skip_collect:
        raise RuntimeError("--skip-workload-rebuild requires --skip-collect")

    if not args.skip_collect:
        run_collect(args, out_dir)
    if args.skip_workload_rebuild:
        raw_records = load_trace(trace_path) if trace_path.exists() else []
        records = []
        partition_events = read_workload_partitions(workload_path)
    else:
        raw_records = load_trace(trace_path)
        records = raw_records
        if args.block_source == "pg-buffercache":
            records = collect_pg_buffercache_blocks(args, records)
        partition_events = write_workload(records, workload_path, args.partitions, args.partition_size)
    if args.model_kind == "lstm":
        model = train_lstm_model(
            partition_events,
            args.look_back,
            args.top_k,
            args.test_fraction,
            args,
            out_dir,
        )
    else:
        model = train_frequency_model(
            partition_events,
            args.look_back,
            args.top_k,
            args.test_fraction,
        )
    model["raw_trace_events"] = len(raw_records)
    model["training_events"] = len(records) if records else len(partition_events)
    model["block_source"] = args.block_source
    model["sql_contains"] = args.sql_contains
    model["partition_size"] = args.partition_size
    model["max_block_selects"] = args.max_block_selects
    model_path.write_text(json.dumps(model, indent=2, sort_keys=True))
    write_summary(out_dir, trace_path, workload_path, model_path, model)

    print("=== LinkedList SeLeP smoke complete ===")
    print(f"trace    : {trace_path} ({len(raw_records)} successful SQL records)")
    print(f"workload : {workload_path} ({len(records) if records else len(partition_events)} training records)")
    print(f"model    : {model_path}")
    print(
        "train    : "
        f"examples={model['train_examples']} contexts={model['contexts']} "
        f"online_hit={model['online_train_hit_rate']:.3f}"
    )
    print(
        "test     : "
        f"examples={model['test_examples']} "
        f"event_hit={model['test_event_hit_rate']:.3f} "
        f"partition_coverage={model['test_partition_coverage']:.3f}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
