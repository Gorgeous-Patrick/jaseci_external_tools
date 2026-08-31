"""Train and run a SeLeP-style SQL/block prewarm sidecar.

The sweep runner uses this script through the SeLeP Python environment
because the LSTM dependencies are not compatible with the free-threaded
Python used for Jac and Streamlit.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import signal
import shlex
import subprocess
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


STOP = False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    train = sub.add_parser("train", help="build a SeLeP model from a Jac SQL trace")
    train.add_argument("--trace", required=True)
    train.add_argument("--model-out", required=True)
    train.add_argument("--workload-out", required=True)
    train.add_argument("--selep-root", required=True)
    train.add_argument("--model-kind", choices=["frequency", "lstm"], default="lstm")
    train.add_argument("--look-back", type=int, default=4)
    train.add_argument("--top-k", type=int, default=42)
    train.add_argument("--test-fraction", type=float, default=0.20)
    train.add_argument("--lstm-epochs", type=int, default=5)
    train.add_argument("--lstm-batch-size", type=int, default=16)
    train.add_argument("--lstm-validation-fraction", type=float, default=0.10)
    train.add_argument("--lstm-seed", type=int, default=42)
    train.add_argument("--partition-size", type=int, default=8)
    train.add_argument("--partitions", type=int, default=64)
    train.add_argument("--block-source", choices=["pg-buffercache", "hash"], default="pg-buffercache")
    train.add_argument("--max-block-selects", type=int, default=256)
    train.add_argument("--sql-contains", default="")
    train.add_argument(
        "--relation-allowlist",
        default="anchors,graph_types",
        help="Comma-separated relation names to keep from pg_buffercache; empty keeps all.",
    )
    train.add_argument(
        "--relation-kinds",
        default="r",
        help="Comma-separated pg_class relkind values to keep; default r excludes indexes.",
    )
    add_db_args(train)

    serve = sub.add_parser("serve", help="tail a Jac SQL trace and issue pg_prewarm calls")
    serve.add_argument("--model", required=True)
    serve.add_argument("--trace", required=True)
    serve.add_argument("--postgres-uri", required=True)
    serve.add_argument("--stats", required=True)
    serve.add_argument("--ready-file", required=True)
    serve.add_argument("--selep-root", required=True)
    serve.add_argument("--top-k", type=int, default=0)
    serve.add_argument("--block-limit", type=int, default=0)
    serve.add_argument("--poll-sec", type=float, default=0.01)

    args = parser.parse_args()
    if args.command == "train":
        return train_command(args)
    if args.command == "serve":
        return serve_command(args)
    raise AssertionError(args.command)


def add_db_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--db-mode", choices=["local_docker", "remote_ssh"], default="local_docker")
    parser.add_argument("--ssh-target", default="")
    parser.add_argument("--ssh-option", action="append", default=[])
    parser.add_argument("--postgres-container", default="postgres")
    parser.add_argument("--postgres-user", default="jac")
    parser.add_argument("--postgres-db", default="jac_db")


def train_command(args: argparse.Namespace) -> int:
    model_path = Path(args.model_out).expanduser().resolve()
    workload_path = Path(args.workload_out).expanduser().resolve()
    model_path.parent.mkdir(parents=True, exist_ok=True)
    workload_path.parent.mkdir(parents=True, exist_ok=True)

    raw_records = load_trace(Path(args.trace))
    records = select_sql_records(raw_records, args.sql_contains, args.max_block_selects)
    if args.block_source == "pg-buffercache":
        records = collect_pg_buffercache_blocks(args, records)
    else:
        records = attach_hash_blocks(records, args.partitions)

    partition_events, partition_blocks, event_exact, event_shape = build_partition_workload(
        records,
        workload_path,
        args.partition_size,
    )
    frequency = train_frequency_model(
        partition_events,
        args.look_back,
        args.top_k,
        args.test_fraction,
    )
    if args.model_kind == "lstm":
        model = train_lstm_model(partition_events, args, model_path.parent)
    else:
        model = {
            "model_type": "selep_frequency",
            "look_back": args.look_back,
            "top_k": args.top_k,
            "vocab": sorted({part for event in partition_events for part in event}, key=partition_sort_key),
        }

    model.update(
        {
            "source": "JAC_SELEP_TRACE",
            "block_source": args.block_source,
            "raw_trace_events": len(raw_records),
            "training_events": len(records),
            "partition_size": args.partition_size,
            "sql_contains": args.sql_contains,
            "max_block_selects": args.max_block_selects,
            "relation_allowlist": sorted(parse_csv_set(args.relation_allowlist)),
            "relation_kinds": sorted(parse_csv_set(args.relation_kinds)),
            "partition_blocks": {
                part: sorted(blocks, key=block_sort_key)
                for part, blocks in partition_blocks.items()
            },
            "event_partitions_exact": {
                key: sorted(parts, key=partition_sort_key)
                for key, parts in event_exact.items()
            },
            "event_partitions_shape": {
                key: sorted(parts, key=partition_sort_key)
                for key, parts in event_shape.items()
            },
            "frequency_context_model": frequency["context_model"],
            "frequency_global_top": frequency["global_top"],
            "frequency_test_event_hit_rate": frequency["test_event_hit_rate"],
            "frequency_test_partition_coverage": frequency["test_partition_coverage"],
        }
    )
    model_path.write_text(json.dumps(model, indent=2, sort_keys=True))
    print(
        "trained SeLeP model: "
        f"kind={model['model_type']} trace_events={len(raw_records)} "
        f"training_events={len(records)} partitions={len(model['partition_blocks'])} "
        f"model={model_path}",
        flush=True,
    )
    return 0


def serve_command(args: argparse.Namespace) -> int:
    install_signal_handlers()
    stats_path = Path(args.stats).expanduser().resolve()
    ready_path = Path(args.ready_file).expanduser().resolve()
    trace_path = Path(args.trace).expanduser().resolve()
    stats_path.parent.mkdir(parents=True, exist_ok=True)
    ready_path.parent.mkdir(parents=True, exist_ok=True)
    trace_path.parent.mkdir(parents=True, exist_ok=True)

    stats: dict[str, Any] = {
        "events_seen": 0,
        "matched_events": 0,
        "predictions": 0,
        "predicted_partitions": 0,
        "prewarm_calls": 0,
        "blocks_requested": 0,
        "blocks_skipped": 0,
        "prewarm_ms": 0.0,
        "errors": [],
    }
    predictor = SelepPredictor(
        Path(args.model).expanduser().resolve(),
        Path(args.selep_root).expanduser().resolve(),
        top_k_override=args.top_k,
    )

    import psycopg

    conn = psycopg.connect(args.postgres_uri, autocommit=True)
    try:
        with conn.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS pg_prewarm")
        ready_path.write_text("ready\n")
        print(f"SeLeP sidecar ready: model={args.model} trace={trace_path}", flush=True)
        tail_trace(trace_path, predictor, conn, args, stats)
    finally:
        try:
            conn.close()
        finally:
            write_stats(stats_path, stats)
    return 0


class SelepPredictor:
    def __init__(self, model_path: Path, selep_root: Path, top_k_override: int = 0):
        self.model_path = model_path
        self.model = json.loads(model_path.read_text())
        self.look_back = int(self.model.get("look_back") or 4)
        self.top_k = int(top_k_override or self.model.get("top_k") or 42)
        self.vocab = [str(x) for x in self.model.get("vocab") or []]
        self.part_to_idx = {part: idx for idx, part in enumerate(self.vocab)}
        self.partition_blocks = {
            str(part): [str(block) for block in blocks]
            for part, blocks in (self.model.get("partition_blocks") or {}).items()
            if isinstance(blocks, list)
        }
        self.event_exact = {
            str(key): [str(part) for part in parts]
            for key, parts in (self.model.get("event_partitions_exact") or {}).items()
            if isinstance(parts, list)
        }
        self.event_shape = {
            str(key): [str(part) for part in parts]
            for key, parts in (self.model.get("event_partitions_shape") or {}).items()
            if isinstance(parts, list)
        }
        self.context_model = self.model.get("frequency_context_model") or {}
        self.global_top = self.model.get("frequency_global_top") or []
        self.history: list[list[str]] = []
        self.keras_model = None
        self.np = None
        if self.model.get("model_type") == "selep_binary_lstm":
            self._load_lstm(selep_root)

    def _load_lstm(self, selep_root: Path) -> None:
        os.environ.setdefault("CUDA_VISIBLE_DEVICES", "-1")
        os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")
        sys.path.insert(0, str(selep_root))
        import numpy as np
        from tensorflow import keras

        architecture = resolve_model_relative(self.model_path, self.model["keras_model_json"])
        weights = resolve_model_relative(self.model_path, self.model["keras_weights"])
        self.keras_model = keras.models.model_from_json(architecture.read_text())
        self.keras_model.load_weights(str(weights))
        self.np = np

    def observe(self, record: dict[str, Any]) -> tuple[list[str], list[str]]:
        parts = self._record_partitions(record)
        if not parts:
            return [], []
        self.history.append(parts)
        if len(self.history) < self.look_back:
            return parts, []
        context = self.history[-self.look_back :]
        if self.keras_model is not None:
            return parts, self._predict_lstm(context)
        return parts, self._predict_frequency(context)

    def _record_partitions(self, record: dict[str, Any]) -> list[str]:
        exact = event_key(record, include_params=True)
        if exact in self.event_exact:
            return self.event_exact[exact]
        shape = event_key(record, include_params=False)
        return self.event_shape.get(shape, [])

    def _predict_lstm(self, context: list[list[str]]) -> list[str]:
        assert self.keras_model is not None
        assert self.np is not None
        rows = int(self.model["rows"])
        cols = int(self.model["cols"])
        data_shape = rows * cols
        x = self.np.zeros((1, self.look_back, data_shape), dtype=self.np.float32)
        for pos, parts in enumerate(context):
            for part in parts:
                idx = self.part_to_idx.get(part)
                if idx is not None and idx < data_shape:
                    x[0, pos, idx] = 1.0
        pred = self.keras_model.predict(x, verbose=0)[0]
        k = max(1, min(self.top_k, len(self.vocab)))
        indices = self.np.argsort(pred)[-k:][::-1]
        return [self.vocab[int(idx)] for idx in indices]

    def _predict_frequency(self, context: list[list[str]]) -> list[str]:
        key = context_key(context)
        if key in self.context_model:
            entries = self.context_model[key]
        else:
            entries = self.global_top
        out = []
        for entry in entries:
            if isinstance(entry, dict):
                part = str(entry.get("partition") or "")
            else:
                part = str(entry)
            if part:
                out.append(part)
            if len(out) >= self.top_k:
                break
        return out

    def blocks_for(self, partitions: list[str], block_limit: int = 0) -> list[str]:
        out: list[str] = []
        seen: set[str] = set()
        for part in partitions:
            for block in self.partition_blocks.get(part, []):
                if block in seen:
                    continue
                seen.add(block)
                out.append(block)
                if block_limit > 0 and len(out) >= block_limit:
                    return out
        return out


def tail_trace(
    trace_path: Path,
    predictor: SelepPredictor,
    conn: Any,
    args: argparse.Namespace,
    stats: dict[str, Any],
) -> None:
    global STOP
    offset = 0
    while not trace_path.exists() and not STOP:
        time.sleep(args.poll_sec)
    while not STOP:
        try:
            with trace_path.open() as fh:
                fh.seek(offset)
                while not STOP:
                    line = fh.readline()
                    if not line:
                        offset = fh.tell()
                        time.sleep(args.poll_sec)
                        continue
                    offset = fh.tell()
                    handle_trace_line(line, predictor, conn, args, stats)
        except FileNotFoundError:
            time.sleep(args.poll_sec)


def handle_trace_line(
    line: str,
    predictor: SelepPredictor,
    conn: Any,
    args: argparse.Namespace,
    stats: dict[str, Any],
) -> None:
    try:
        record = json.loads(line)
    except json.JSONDecodeError:
        return
    if record.get("status") != "ok":
        return
    stats["events_seen"] += 1
    observed, predicted = predictor.observe(record)
    if not observed:
        return
    stats["matched_events"] += 1
    if not predicted:
        return
    stats["predictions"] += 1
    stats["predicted_partitions"] += len(predicted)
    blocks = predictor.blocks_for(predicted, args.block_limit)
    if not blocks:
        return
    stats["blocks_requested"] += len(blocks)
    started = time.perf_counter()
    try:
        calls, skipped = prewarm_blocks(conn, blocks)
        stats["prewarm_calls"] += calls
        stats["blocks_skipped"] += skipped
    except Exception as exc:  # keep the measured Jac request alive
        errors = stats.setdefault("errors", [])
        if len(errors) < 20:
            errors.append(repr(exc))
    finally:
        stats["prewarm_ms"] += (time.perf_counter() - started) * 1000.0


def prewarm_blocks(conn: Any, blocks: list[str]) -> tuple[int, int]:
    ranges = coalesce_blocks(blocks)
    if not ranges:
        return 0, 0
    limits = relation_block_limits(conn, [relation for relation, _start, _end in ranges])
    calls = 0
    skipped = 0
    with conn.cursor() as cur:
        for relation, start, end in ranges:
            max_block = limits.get(relation)
            if max_block is None or max_block < 0:
                skipped += end - start + 1
                continue
            clipped_end = min(end, max_block)
            if start > clipped_end:
                skipped += end - start + 1
                continue
            cur.execute(
                "SELECT pg_prewarm(%s::regclass, first_block => %s, last_block => %s)",
                (relation, start, clipped_end),
            )
            calls += 1
            skipped += max(0, end - clipped_end)
    return calls, skipped


def relation_block_limits(conn: Any, relations: list[str]) -> dict[str, int]:
    names = sorted({relation for relation in relations if relation})
    if not names:
        return {}
    out: dict[str, int] = {}
    with conn.cursor() as cur:
        for relation in names:
            try:
                cur.execute("SELECT pg_relation_size(%s::regclass)", (relation,))
                row = cur.fetchone()
            except Exception:
                out[relation] = -1
                continue
            size = int(row[0] or 0) if row else 0
            out[relation] = (size + 8191) // 8192 - 1
    return out


def coalesce_blocks(blocks: list[str]) -> list[tuple[str, int, int]]:
    by_rel: dict[str, set[int]] = defaultdict(set)
    for block in blocks:
        parsed = parse_block_id(block)
        if parsed is None:
            continue
        relation, num = parsed
        by_rel[relation].add(num)
    ranges: list[tuple[str, int, int]] = []
    for relation, nums in sorted(by_rel.items()):
        ordered = sorted(nums)
        start = prev = ordered[0]
        for num in ordered[1:]:
            if num == prev + 1:
                prev = num
                continue
            ranges.append((relation, start, prev))
            start = prev = num
        ranges.append((relation, start, prev))
    return ranges


def parse_block_id(block: str) -> tuple[str, int] | None:
    if "_" not in block:
        return None
    relation, raw = block.rsplit("_", 1)
    if not relation or not raw.isdigit():
        return None
    return relation, int(raw)


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
            sql = compact_sql(record.get("sql") or record.get("pos_sql") or "")
            if not sql:
                continue
            records.append(record)
    if not records:
        raise RuntimeError(f"trace has no successful SQL records: {trace_path}")
    return records


def select_sql_records(
    records: list[dict[str, Any]],
    sql_contains: str,
    max_block_selects: int,
) -> list[dict[str, Any]]:
    out = [record for record in records if is_select_record(record)]
    if sql_contains:
        needle = sql_contains.lower()
        out = [
            record
            for record in out
            if needle in compact_sql(record.get("sql") or record.get("pos_sql") or "").lower()
        ]
    if max_block_selects > 0:
        out = out[:max_block_selects]
    if not out:
        raise RuntimeError("no successful SELECT records available for SeLeP training")
    return out


def is_select_record(record: dict[str, Any]) -> bool:
    sql = compact_sql(record.get("sql") or record.get("pos_sql") or "")
    return sql.upper().startswith("SELECT ")


def collect_pg_buffercache_blocks(
    args: argparse.Namespace,
    records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    db_psql(args, "CREATE EXTENSION IF NOT EXISTS pg_buffercache;")
    relation_allowlist = parse_csv_set(args.relation_allowlist)
    relation_kinds = parse_csv_set(args.relation_kinds)
    enriched: list[dict[str, Any]] = []
    empty = 0
    for idx, record in enumerate(records, start=1):
        restart_postgres(args)
        sql = render_sql(record.get("sql") or "", record.get("params") or {})
        blocks = query_result_blocks(args, sql, relation_allowlist, relation_kinds)
        if not blocks:
            empty += 1
            continue
        item = dict(record)
        item["_result_blocks"] = blocks
        enriched.append(item)
        print(
            f"block replay {idx}/{len(records)}: blocks={len(blocks)} "
            f"sql={compact_sql(sql)[:120]}",
            flush=True,
        )
    if not enriched:
        raise RuntimeError(
            "pg_buffercache replay produced no block-bearing records; "
            "try lowering SELEP_SQL_CONTAINS or use SELEP_BLOCK_SOURCE=hash for a plumbing-only smoke"
        )
    print(
        "block replay summary: "
        f"selected={len(records)} block_bearing={len(enriched)} empty={empty}",
        flush=True,
    )
    return enriched


def attach_hash_blocks(records: list[dict[str, Any]], partition_count: int) -> list[dict[str, Any]]:
    out = []
    for record in records:
        relation = relation_name(record)
        digest = hashlib.sha256(
            json.dumps(record.get("params") or record.get("args") or {}, sort_keys=True).encode()
        ).digest()
        block = int.from_bytes(digest[:4], "big") % max(1, partition_count)
        item = dict(record)
        item["_result_blocks"] = [f"{relation}_{block}"]
        out.append(item)
    return out


def query_result_blocks(
    args: argparse.Namespace,
    sql: str,
    relation_allowlist: set[str],
    relation_kinds: set[str],
) -> list[str]:
    replay = sql.rstrip().rstrip(";")
    relation_filter = ""
    kind_filter = ""
    if relation_allowlist:
        relations = ", ".join(sql_quote(name) for name in sorted(relation_allowlist))
        relation_filter = f"  AND c.relname IN ({relations})\n"
    if relation_kinds:
        kinds = ", ".join(sql_quote(kind) for kind in sorted(relation_kinds))
        kind_filter = f"  AND c.relkind IN ({kinds})\n"
    block_sql = f"""
\\o /dev/null
{replay};
\\o
SELECT DISTINCT c.relname || '_' || b.relblocknumber
FROM pg_buffercache b
JOIN pg_database d ON b.reldatabase = d.oid
JOIN pg_class c ON b.relfilenode = pg_relation_filenode(c.oid)
WHERE d.datname = current_database()
  AND b.relblocknumber IS NOT NULL
{kind_filter}{relation_filter}
  AND c.relname NOT LIKE 'pg_%'
  AND c.relname NOT LIKE 'sql_%'
ORDER BY 1;
"""
    proc = db_psql(args, block_sql, capture=True)
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


def restart_postgres(args: argparse.Namespace) -> None:
    db_command(args, ["docker", "restart", args.postgres_container])
    deadline = time.time() + 60.0
    last = ""
    while time.time() < deadline:
        proc = db_command(
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
        last = (proc.stdout or "") + (proc.stderr or "")
        if proc.returncode == 0:
            return
        time.sleep(0.5)
    raise RuntimeError(f"Postgres did not become ready after restart: {last.strip()}")


def db_psql(args: argparse.Namespace, sql: str, capture: bool = False) -> subprocess.CompletedProcess[str]:
    return db_command(
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


def db_command(
    args: argparse.Namespace,
    command: list[str],
    *,
    input_text: str | None = None,
    capture: bool = False,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    if args.db_mode == "remote_ssh":
        if not args.ssh_target:
            raise RuntimeError("remote_ssh SeLeP training requires --ssh-target")
        cmd = ["ssh", *args.ssh_option, args.ssh_target, *command]
    else:
        cmd = list(command)
    proc = subprocess.run(
        cmd,
        input=input_text,
        text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
        check=False,
    )
    if check and proc.returncode != 0:
        rendered = " ".join(shlex.quote(part) for part in cmd)
        stderr = (proc.stderr or "").strip()
        stdout = (proc.stdout or "").strip()
        raise RuntimeError(f"command failed: {rendered}\n{stderr or stdout}")
    return proc


def build_partition_workload(
    records: list[dict[str, Any]],
    workload_path: Path,
    partition_size: int,
) -> tuple[list[list[str]], dict[str, set[str]], dict[str, set[str]], dict[str, set[str]]]:
    block_partitions = assign_block_partitions(records, partition_size)
    partition_blocks: dict[str, set[str]] = defaultdict(set)
    event_exact: dict[str, set[str]] = defaultdict(set)
    event_shape: dict[str, set[str]] = defaultdict(set)
    partition_events: list[list[str]] = []

    with workload_path.open("w", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=["theTime", "ClientIP", "row", "statement", "resultBlock", "resultPartitions"],
        )
        writer.writeheader()
        for record in records:
            blocks = [str(block) for block in record.get("_result_blocks") or []]
            if not blocks:
                continue
            parts = sorted({block_partitions[block] for block in blocks}, key=partition_sort_key)
            if not parts:
                continue
            for block in blocks:
                partition_blocks[block_partitions[block]].add(block)
            event_exact[event_key(record, include_params=True)].update(parts)
            event_shape[event_key(record, include_params=False)].update(parts)
            partition_events.append(parts)
            writer.writerow(
                {
                    "theTime": str(record.get("ts_ns") or ""),
                    "ClientIP": str(record.get("thread_id") or ""),
                    "row": str(record.get("row_count") or 0),
                    "statement": compact_sql(record.get("sql") or record.get("pos_sql") or ""),
                    "resultBlock": "[" + ", ".join(blocks) + "]",
                    "resultPartitions": "[" + ", ".join(parts) + "]",
                }
            )
    if not partition_events:
        raise RuntimeError("no partition events produced for SeLeP training")
    return partition_events, partition_blocks, event_exact, event_shape


def assign_block_partitions(records: list[dict[str, Any]], partition_size: int) -> dict[str, str]:
    if partition_size <= 0:
        raise ValueError(f"partition_size must be positive, got {partition_size}")
    mapping: dict[str, str] = {}
    for record in records:
        for block in record.get("_result_blocks") or []:
            block = str(block)
            if block not in mapping:
                mapping[block] = f"p{len(mapping) // partition_size}"
    return mapping


def train_frequency_model(
    partition_events: list[list[str]],
    look_back: int,
    top_k: int,
    test_fraction: float,
) -> dict[str, Any]:
    if len(partition_events) <= look_back:
        raise RuntimeError(f"need more than look_back={look_back} SQL events, got {len(partition_events)}")
    if not 0.0 <= test_fraction < 1.0:
        raise ValueError(f"test_fraction must be in [0, 1), got {test_fraction}")
    total_examples = len(partition_events) - look_back
    test_examples = int(round(total_examples * test_fraction))
    if total_examples > 1:
        test_examples = max(1, min(test_examples, total_examples - 1))
    else:
        test_examples = 0
    split_idx = len(partition_events) - test_examples

    counts: dict[str, Counter[str]] = defaultdict(Counter)
    global_counts: Counter[str] = Counter()
    for parts in partition_events[:split_idx]:
        global_counts.update(parts)

    for idx in range(look_back, split_idx):
        key = context_key(partition_events[idx - look_back : idx])
        counts[key].update(partition_events[idx])

    test_total = 0
    event_hits = 0
    covered_total = 0
    target_total = 0
    for idx in range(split_idx, len(partition_events)):
        key = context_key(partition_events[idx - look_back : idx])
        prediction = frequency_prediction(counts, global_counts, key, top_k)
        wanted = set(partition_events[idx])
        covered = wanted.intersection(prediction)
        event_hits += int(bool(covered))
        covered_total += len(covered)
        target_total += len(wanted)
        test_total += 1

    return {
        "context_model": {
            key: [{"partition": part, "count": count} for part, count in counter.most_common()]
            for key, counter in sorted(counts.items())
        },
        "global_top": [
            {"partition": part, "count": count}
            for part, count in global_counts.most_common(top_k)
        ],
        "test_event_hit_rate": event_hits / test_total if test_total else 0.0,
        "test_partition_coverage": covered_total / target_total if target_total else 0.0,
    }


def frequency_prediction(
    counts: dict[str, Counter[str]],
    global_counts: Counter[str],
    key: str,
    top_k: int,
) -> list[str]:
    if key in counts:
        return [part for part, _count in counts[key].most_common(top_k)]
    return [part for part, _count in global_counts.most_common(top_k)]


def train_lstm_model(
    partition_events: list[list[str]],
    args: argparse.Namespace,
    model_dir: Path,
) -> dict[str, Any]:
    if len(partition_events) <= args.look_back:
        raise RuntimeError(f"need more than look_back={args.look_back} SQL events, got {len(partition_events)}")

    os.environ.setdefault("CUDA_VISIBLE_DEVICES", "-1")
    os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "1")
    os.environ.setdefault("OMP_NUM_THREADS", "2")
    os.environ.setdefault("TF_NUM_INTRAOP_THREADS", "2")
    os.environ.setdefault("TF_NUM_INTEROP_THREADS", "1")

    selep_root = Path(args.selep_root).expanduser().resolve()
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

    x = np.asarray(
        [vectors[idx - args.look_back : idx] for idx in range(args.look_back, len(partition_events))],
        dtype=np.float32,
    )
    y = np.asarray(
        [outputs[idx] for idx in range(args.look_back, len(partition_events))],
        dtype=np.float32,
    )
    split_examples, test_examples = supervised_split(len(x), args.test_fraction)
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

    model = create_binary_lstm_model(len(vocab), args.look_back, rows, cols)
    model.compile(
        loss=keras.losses.BinaryCrossentropy(from_logits=False),
        optimizer=keras.optimizers.Adam(),
        metrics=[keras.metrics.MeanAbsoluteError(), "accuracy"],
    )
    callbacks = []
    if validation_data is not None:
        callbacks.append(keras.callbacks.EarlyStopping(monitor="val_loss", patience=3, restore_best_weights=True))

    started = time.perf_counter()
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
    train_ms = (time.perf_counter() - started) * 1000.0

    test_pred = model.predict(x_test, verbose=0) if len(x_test) else np.zeros((0, len(vocab)))
    test_eval = evaluate_lstm_predictions(test_pred, y_test, vocab, args.top_k)

    architecture = model_dir / "model_lstm_architecture.json"
    weights = model_dir / "model_lstm.weights.h5"
    architecture.write_text(model.to_json())
    model.save_weights(str(weights))
    return {
        "model_type": "selep_binary_lstm",
        "look_back": args.look_back,
        "top_k": args.top_k,
        "test_fraction": args.test_fraction,
        "events": len(partition_events),
        "examples": len(x),
        "train_examples": len(x_train),
        "test_examples": test_examples,
        "partitions": len(vocab),
        "rows": rows,
        "cols": cols,
        "lstm_epochs_requested": args.lstm_epochs,
        "lstm_epochs_ran": len(history.history.get("loss", [])),
        "lstm_batch_size": args.lstm_batch_size,
        "lstm_validation_examples": val_count,
        "lstm_train_ms": train_ms,
        "test_event_hit_rate": test_eval["event_hit_rate"],
        "test_partition_coverage": test_eval["partition_coverage"],
        "vocab": vocab,
        "history": {key: [float(value) for value in values] for key, values in history.history.items()},
        "keras_model_json": architecture.name,
        "keras_weights": weights.name,
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
        predicted = set(int(idx) for idx in np.argsort(pred)[-k:])
        wanted = {int(idx) for idx in np.flatnonzero(target > 0.0)}
        covered = predicted.intersection(wanted)
        event_hits += int(bool(covered))
        covered_total += len(covered)
        target_total += len(wanted)
    return {
        "event_hit_rate": event_hits / len(targets),
        "partition_coverage": covered_total / target_total if target_total else 0.0,
    }


def supervised_split(total_examples: int, test_fraction: float) -> tuple[int, int]:
    if total_examples <= 0:
        raise RuntimeError("need at least one supervised example")
    test_examples = int(round(total_examples * test_fraction))
    if total_examples > 1:
        test_examples = max(1, min(test_examples, total_examples - 1))
    else:
        test_examples = 0
    return total_examples - test_examples, test_examples


def matrix_dims(num_partitions: int) -> tuple[int, int]:
    rows = max(2, int(num_partitions ** 0.5))
    cols = max(2, (num_partitions + rows - 1) // rows)
    while rows * cols < num_partitions:
        cols += 1
    return rows, cols


def render_sql(sql: str, params: dict[str, Any]) -> str:
    out: list[str] = []
    i = 0
    in_squote = False
    in_dquote = False
    while i < len(sql):
        ch = sql[i]
        if in_squote:
            out.append(ch)
            if ch == "'":
                if i + 1 < len(sql) and sql[i + 1] == "'":
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
            if i + 1 < len(sql) and sql[i + 1] == ":":
                out.append("::")
                i += 2
                continue
            j = i + 1
            name = ""
            while j < len(sql) and (sql[j].isalnum() or sql[j] == "_"):
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
        return "'{" + ",".join(items) + "}'"
    return "'" + str(value).replace("'", "''") + "'"


def relation_name(record: dict[str, Any]) -> str:
    sql = compact_sql(record.get("sql") or record.get("pos_sql") or "").lower()
    for pattern in (
        r"\bfrom\s+([a-z_][a-z0-9_]*(?:\.[a-z_][a-z0-9_]*)?)",
        r"\bjoin\s+([a-z_][a-z0-9_]*(?:\.[a-z_][a-z0-9_]*)?)",
        r"\binto\s+([a-z_][a-z0-9_]*(?:\.[a-z_][a-z0-9_]*)?)",
        r"\bupdate\s+([a-z_][a-z0-9_]*(?:\.[a-z_][a-z0-9_]*)?)",
    ):
        match = re.search(pattern, sql)
        if match:
            raw = match.group(1)
            if raw not in {"unnest", "select"}:
                return raw.replace(".", "_")
    return "anchors"


def parse_csv_set(raw: str) -> set[str]:
    return {item.strip() for item in str(raw or "").split(",") if item.strip()}


def sql_quote(value: str) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def compact_sql(sql: str) -> str:
    return " ".join(str(sql).split())


def event_key(record: dict[str, Any], *, include_params: bool) -> str:
    sql = compact_sql(record.get("pos_sql") or record.get("sql") or "")
    if not include_params:
        raw = sql
    else:
        args = record.get("args")
        params = record.get("params")
        raw = sql + "\n" + json.dumps(args if args else params or {}, sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()


def context_key(events: list[list[str]]) -> str:
    return "|".join(";".join(parts) for parts in events)


def partition_sort_key(partition: str) -> tuple[int, str]:
    if partition.startswith("p") and partition[1:].isdigit():
        return (int(partition[1:]), partition)
    return (sys.maxsize, partition)


def block_sort_key(block: str) -> tuple[str, int, str]:
    parsed = parse_block_id(block)
    if parsed is None:
        return (block, sys.maxsize, block)
    relation, num = parsed
    return (relation, num, block)


def resolve_model_relative(model_path: Path, value: str) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else model_path.parent / path


def install_signal_handlers() -> None:
    def _stop(_signum, _frame) -> None:
        global STOP
        STOP = True

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)


def write_stats(stats_path: Path, stats: dict[str, Any]) -> None:
    stats = dict(stats)
    stats["prewarm_ms"] = round(float(stats.get("prewarm_ms") or 0.0), 3)
    stats_path.write_text(json.dumps(stats, indent=2, sort_keys=True))


if __name__ == "__main__":
    raise SystemExit(main())
