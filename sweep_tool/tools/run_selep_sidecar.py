"""Train and run SeLeP SQL/block prewarm sidecars.

The sweep runner uses this script through the SeLeP Python environment
because the LSTM dependencies are not compatible with the free-threaded
Python used for Jac and Streamlit.
"""

from __future__ import annotations

import argparse
import csv
import io
import hashlib
import json
import math
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
    train.add_argument("--model-kind", choices=["frequency", "lstm", "original", "faithful"], default="faithful")
    train.add_argument("--look-back", type=int, default=4)
    train.add_argument("--top-k", type=int, default=42)
    train.add_argument("--test-fraction", type=float, default=0.10)
    train.add_argument("--lstm-epochs", type=int, default=75)
    train.add_argument("--lstm-batch-size", type=int, default=32)
    train.add_argument("--lstm-validation-fraction", type=float, default=0.10)
    train.add_argument("--lstm-seed", type=int, default=42)
    train.add_argument("--encoding-length", type=int, default=32)
    train.add_argument("--encoding-epochs", type=int, default=100)
    train.add_argument("--table-encoding-method", default="AutoEncoder_1")
    train.add_argument("--semantic-rows-per-block", type=int, default=64)
    train.add_argument("--partition-size", type=int, default=128)
    train.add_argument("--partitions", type=int, default=64)
    train.add_argument("--block-source", choices=["jac-ctid", "pg-buffercache", "hash"], default="jac-ctid")
    train.add_argument("--max-block-selects", type=int, default=0)
    train.add_argument("--clay-repartition-threshold", type=int, default=2500)
    train.add_argument("--clay-initial-fill", type=float, default=0.90)
    train.add_argument("--clay-empty-fraction", type=float, default=0.10)
    train.add_argument("--clay-max-load", type=float, default=1.0)
    train.add_argument("--clay-weight-reset", type=float, default=0.10)
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
    elif args.block_source == "jac-ctid":
        records = collect_jac_ctid_blocks(args, records)
    else:
        records = attach_hash_blocks(records, args.partitions)

    event_vectors_exact: dict[str, list[list[float]]] = {}
    event_vectors_shape: dict[str, list[list[float]]] = {}
    if args.model_kind in {"original", "faithful"}:
        (
            model,
            partition_events,
            partition_blocks,
            event_exact,
            event_shape,
            event_vectors_exact,
            event_vectors_shape,
        ) = train_original_selep_model(records, workload_path, args, model_path.parent)
    else:
        partition_events, partition_blocks, event_exact, event_shape = build_partition_workload(
            records,
            workload_path,
            args.partition_size,
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

    frequency = train_frequency_model(
        partition_events,
        args.look_back,
        args.top_k,
        args.test_fraction,
    )

    model.update(
        {
            "source": "JAC_SELEP_TRACE",
            "block_source": args.block_source,
            "raw_trace_events": len(raw_records),
            "training_events": len(records),
            "partition_size": args.partition_size,
            "sql_contains": args.sql_contains,
            "max_block_selects": args.max_block_selects,
            "training_sql_event_cap": args.max_block_selects,
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
            "event_vectors_exact": event_vectors_exact,
            "event_vectors_shape": event_vectors_shape,
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
        "blocks_already_warmed": 0,
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
        self.model_type = str(self.model.get("model_type") or "")
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
        self.event_vectors_exact = {
            str(key): vector
            for key, vector in (self.model.get("event_vectors_exact") or {}).items()
            if isinstance(vector, list)
        }
        self.event_vectors_shape = {
            str(key): vector
            for key, vector in (self.model.get("event_vectors_shape") or {}).items()
            if isinstance(vector, list)
        }
        self.context_model = self.model.get("frequency_context_model") or {}
        self.global_top = self.model.get("frequency_global_top") or []
        self.history: list[list[str]] = []
        self.encoded_history: list[list[list[float]]] = []
        self.keras_model = None
        self.np = None
        if self.model_type in {"selep_binary_lstm", "selep_original_lstm"}:
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
        parts, vector = self._record_observation(record)
        if not parts:
            return [], []
        self.history.append(parts)
        if self.model_type == "selep_original_lstm":
            if vector is None:
                return parts, []
            self.encoded_history.append(vector)
            if len(self.encoded_history) < self.look_back:
                return parts, []
            assert self.keras_model is not None
            return parts, self._predict_original_lstm(self.encoded_history[-self.look_back :])
        if len(self.history) < self.look_back:
            return parts, []
        context = self.history[-self.look_back :]
        if self.keras_model is not None:
            return parts, self._predict_lstm(context)
        return parts, self._predict_frequency(context)

    def _record_observation(self, record: dict[str, Any]) -> tuple[list[str], list[list[float]] | None]:
        exact = event_key(record, include_params=True)
        if exact in self.event_exact:
            return self.event_exact[exact], self.event_vectors_exact.get(exact)
        shape = event_key(record, include_params=False)
        return self.event_shape.get(shape, []), self.event_vectors_shape.get(shape)

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

    def _predict_original_lstm(self, context: list[list[list[float]]]) -> list[str]:
        assert self.keras_model is not None
        assert self.np is not None
        rows = int(self.model["rows"])
        cols = int(self.model["cols"])
        data_shape = rows * cols
        x = self.np.zeros((1, self.look_back, data_shape), dtype=self.np.float32)
        for pos, matrix in enumerate(context):
            arr = self.np.asarray(matrix, dtype=self.np.float32).reshape(-1)
            usable = min(data_shape, arr.shape[0])
            x[0, pos, :usable] = arr[:usable]
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
    relation_size_cache: dict[str, int] = {}
    warmed_blocks: set[str] = set()
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
                    handle_trace_line(
                        line,
                        predictor,
                        conn,
                        args,
                        stats,
                        relation_size_cache,
                        warmed_blocks,
                    )
        except FileNotFoundError:
            time.sleep(args.poll_sec)


def handle_trace_line(
    line: str,
    predictor: SelepPredictor,
    conn: Any,
    args: argparse.Namespace,
    stats: dict[str, Any],
    relation_size_cache: dict[str, int],
    warmed_blocks: set[str],
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
    fresh_blocks = [block for block in blocks if block not in warmed_blocks]
    already_warmed = len(blocks) - len(fresh_blocks)
    if already_warmed:
        stats["blocks_already_warmed"] += already_warmed
    if not fresh_blocks:
        return
    stats["blocks_requested"] += len(fresh_blocks)
    started = time.perf_counter()
    try:
        calls, skipped = prewarm_blocks(conn, fresh_blocks, relation_size_cache)
        stats["prewarm_calls"] += calls
        stats["blocks_skipped"] += skipped
        warmed_blocks.update(fresh_blocks)
    except Exception as exc:  # keep the measured Jac request alive
        errors = stats.setdefault("errors", [])
        if len(errors) < 20:
            errors.append(repr(exc))
    finally:
        stats["prewarm_ms"] += (time.perf_counter() - started) * 1000.0


def prewarm_blocks(
    conn: Any,
    blocks: list[str],
    relation_size_cache: dict[str, int],
) -> tuple[int, int]:
    ranges = coalesce_blocks(blocks)
    if not ranges:
        return 0, 0
    limits = relation_block_limits(
        conn,
        [relation for relation, _start, _end in ranges],
        relation_size_cache,
    )
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


def relation_block_limits(
    conn: Any,
    relations: list[str],
    cache: dict[str, int],
) -> dict[str, int]:
    names = sorted({relation for relation in relations if relation})
    if not names:
        return {}
    out: dict[str, int] = {}
    with conn.cursor() as cur:
        for relation in names:
            if relation in cache:
                out[relation] = cache[relation]
                continue
            try:
                cur.execute("SELECT pg_relation_size(%s::regclass)", (relation,))
                row = cur.fetchone()
            except Exception:
                cache[relation] = -1
                out[relation] = cache[relation]
                continue
            size = int(row[0] or 0) if row else 0
            cache[relation] = (size + 8191) // 8192 - 1
            out[relation] = cache[relation]
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


def collect_jac_ctid_blocks(
    args: argparse.Namespace,
    records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    relation_allowlist = parse_csv_set(args.relation_allowlist)
    relation_kinds = parse_csv_set(args.relation_kinds)
    if relation_allowlist and "anchors" not in relation_allowlist:
        raise RuntimeError("SELEP_BLOCK_SOURCE=jac-ctid requires anchors in SELEP_RELATION_ALLOWLIST")
    if relation_kinds and "r" not in relation_kinds:
        raise RuntimeError("SELEP_BLOCK_SOURCE=jac-ctid requires relkind r in SELEP_RELATION_KINDS")

    classified: list[tuple[int, dict[str, Any], str]] = []
    for idx, record in enumerate(records, start=1):
        try:
            kind = jac_ctid_sql_kind(record)
        except RuntimeError as exc:
            raise RuntimeError(f"{exc} (record {idx}/{len(records)})") from exc
        classified.append((idx, record, kind))

    wait_postgres_ready(args)
    enriched: list[dict[str, Any]] = []
    materialize_blocks = prefetch_jac_materialize_blocks(args, classified)
    label_cache: dict[str, list[str]] = {}
    skipped: Counter[str] = Counter()
    empty = 0
    cache_hits = 0
    cache_misses = 0
    for idx, record, kind in classified:
        if kind == "skip":
            skipped["runtime_noise"] += 1
            continue

        key = event_key(record, include_params=True)
        if key in label_cache:
            blocks = label_cache[key]
            cache_hits += 1
        else:
            blocks = query_jac_ctid_blocks(args, record, kind, materialize_blocks)
            label_cache[key] = blocks
            cache_misses += 1

        if not blocks:
            empty += 1
            continue
        item = dict(record)
        item["_result_blocks"] = blocks
        enriched.append(item)
        if idx == 1 or idx % 1000 == 0 or idx == len(records):
            print(
                f"jac-ctid label {idx}/{len(records)}: "
                f"kind={kind} blocks={len(blocks)} "
                f"block_bearing={len(enriched)} cache_hits={cache_hits}",
                flush=True,
            )

    if not enriched:
        raise RuntimeError(
            "jac-ctid labeling produced no block-bearing records; "
            "extend the Jac SQL classifier or use SELEP_BLOCK_SOURCE=pg-buffercache for validation"
        )
    print(
        "jac-ctid label summary: "
        f"selected={len(records)} block_bearing={len(enriched)} "
        f"empty={empty} skipped={dict(skipped)} "
        f"unique_queries={cache_misses} cache_hits={cache_hits}",
        flush=True,
    )
    return enriched


def jac_ctid_sql_kind(record: dict[str, Any]) -> str:
    sql = compact_sql(record.get("sql") or record.get("pos_sql") or "")
    lowered = sql.lower()
    params = record.get("params") or record.get("args") or {}
    if is_jac_ctid_ignored_select(lowered):
        return "skip"
    if is_jac_materialize_sql(sql, params):
        return "materialize"
    if is_jac_resolve_sql(sql):
        return "resolve"
    raise RuntimeError(
        "unsupported SELECT for SELEP_BLOCK_SOURCE=jac-ctid: "
        f"{sql[:300]}"
    )


def is_jac_ctid_ignored_select(lowered_sql: str) -> bool:
    sql = f" {lowered_sql} "
    return (
        lowered_sql.startswith("select 1")
        or " from identity_" in sql
        or " join identity_" in sql
        or " from kv_state" in sql
        or re.search(r"^select\s+(distinct\s+)?type_name\s+from\s+graph_types\b", lowered_sql) is not None
        or " from pg_" in sql
        or " information_schema." in sql
        or "current_setting(" in lowered_sql
        or "version()" in lowered_sql
    )


def is_jac_materialize_sql(sql: str, params: dict[str, Any]) -> bool:
    lowered = sql.lower()
    return (
        "ids" in params
        and re.search(r"\bfrom\s+anchors\s+a\b", sql, re.IGNORECASE) is not None
        and re.search(r"\bselect\s+a\.id\b", lowered) is not None
    )


def is_jac_resolve_sql(sql: str) -> bool:
    return (
        re.search(r"^select\s+n\d+\.id\s*,\s*e\d+\.id\s+from\b", sql, re.IGNORECASE) is not None
        and re.search(r"\bjoin\s+anchors\s+e\d+\b", sql, re.IGNORECASE) is not None
        and "edgeanchor" in sql.lower()
    )


def prefetch_jac_materialize_blocks(
    args: argparse.Namespace,
    records: list[tuple[int, dict[str, Any], str]],
) -> dict[str, str]:
    ids: set[str] = set()
    for _idx, record, kind in records:
        if kind != "materialize":
            continue
        params = record.get("params") or record.get("args") or {}
        ids.update(str(value) for value in flatten_sql_values(params.get("ids")) if value)
    if not ids:
        return {}

    out: dict[str, str] = {}
    ordered = sorted(ids)
    for chunk in chunked(ordered, 2000):
        values = ", ".join(sql_quote(value) for value in chunk)
        sql = f"""
WITH wanted(id) AS (
  SELECT unnest(ARRAY[{values}]::uuid[])
)
SELECT w.id::text, 'anchors_' || ((a.ctid::text::point)[0]::bigint)::text
FROM wanted w
JOIN anchors a ON a.id = w.id
ORDER BY 1;
"""
        proc = db_psql_when_ready(args, sql, capture=True)
        for line in proc.stdout.splitlines():
            raw_id, sep, block = line.strip().partition("|")
            if sep and raw_id and block:
                out[raw_id] = block
    print(
        "jac-ctid materialize preload: "
        f"ids={len(ordered)} mapped={len(out)} chunks={math.ceil(len(ordered) / 2000)}",
        flush=True,
    )
    return out


def query_jac_ctid_blocks(
    args: argparse.Namespace,
    record: dict[str, Any],
    kind: str,
    materialize_blocks: dict[str, str],
) -> list[str]:
    if kind == "materialize":
        return query_jac_materialize_blocks(record, materialize_blocks)
    if kind == "resolve":
        return query_jac_resolve_blocks(args, record)
    raise AssertionError(kind)


def query_jac_materialize_blocks(record: dict[str, Any], materialize_blocks: dict[str, str]) -> list[str]:
    params = record.get("params") or record.get("args") or {}
    ids = flatten_sql_values(params.get("ids"))
    return sorted({materialize_blocks[str(value)] for value in ids if str(value) in materialize_blocks})


def query_jac_resolve_blocks(args: argparse.Namespace, record: dict[str, Any]) -> list[str]:
    sql = record.get("sql") or record.get("pos_sql") or ""
    params = record.get("params") or record.get("args") or {}
    replay = render_sql(sql, params).rstrip().rstrip(";")
    block_sql = f"""
WITH q(node_id, edge_id) AS (
  {replay}
),
wanted(id) AS (
  SELECT node_id FROM q WHERE node_id IS NOT NULL
  UNION
  SELECT edge_id FROM q WHERE edge_id IS NOT NULL
)
SELECT DISTINCT 'anchors_' || ((a.ctid::text::point)[0]::bigint)::text
FROM anchors a
JOIN wanted w ON w.id = a.id
ORDER BY 1;
"""
    return psql_lines(args, block_sql)


def psql_lines(args: argparse.Namespace, sql: str) -> list[str]:
    proc = db_psql_when_ready(args, sql, capture=True)
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


def flatten_sql_values(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        out: list[Any] = []
        for item in value:
            out.extend(flatten_sql_values(item))
        return out
    return [value]


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
    wait_postgres_ready(args)


def wait_postgres_ready(args: argparse.Namespace, timeout: float = 60.0) -> None:
    deadline = time.time() + timeout
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
    raise RuntimeError(f"Postgres did not become ready: {last.strip()}")


def db_psql_when_ready(
    args: argparse.Namespace,
    sql: str,
    capture: bool = False,
    attempts: int = 3,
) -> subprocess.CompletedProcess[str]:
    last_exc: RuntimeError | None = None
    for attempt in range(max(1, attempts)):
        wait_postgres_ready(args, timeout=30.0)
        try:
            return db_psql(args, sql, capture=capture)
        except RuntimeError as exc:
            last_exc = exc
            if not is_transient_postgres_startup_error(str(exc)):
                raise
            if attempt + 1 < attempts:
                time.sleep(1.0)
    assert last_exc is not None
    raise last_exc


def is_transient_postgres_startup_error(message: str) -> bool:
    lowered = message.lower()
    return (
        "no such file or directory" in lowered
        or "the database system is starting up" in lowered
        or "could not connect to server" in lowered
        or "connection refused" in lowered
    )


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


def train_original_selep_model(
    records: list[dict[str, Any]],
    workload_path: Path,
    args: argparse.Namespace,
    model_dir: Path,
) -> tuple[
    dict[str, Any],
    list[list[str]],
    dict[str, set[str]],
    dict[str, set[str]],
    dict[str, set[str]],
    dict[str, list[list[float]]],
    dict[str, list[list[float]]],
]:
    table_list = original_table_list(records)
    with Pushd(Path(args.selep_root).expanduser().resolve()):
        configure_original_selep(args, table_list)
        table_manager = build_original_table_manager(records, args, table_list)
        partition_manager, block_partitions, partition_blocks, partition_stats = build_original_partition_manager(
            records,
            table_manager,
            args,
        )
        (
            partition_events,
            event_vectors,
            event_exact,
            event_shape,
            event_vectors_exact,
            event_vectors_shape,
        ) = build_original_workload(records, workload_path, partition_manager, block_partitions, args)
        vocab = sorted(partition_manager.partitions.keys(), key=partition_sort_key)
        model = train_original_lstm_model(
            event_vectors,
            partition_events,
            vocab,
            args,
            model_dir,
            rows=len(table_list),
            cols=args.encoding_length,
        )
    model.update(
        {
            "model_type": "selep_original_lstm",
            "selep_mode": "faithful_policy",
            "model_kind_requested": args.model_kind,
            "selep_root": str(Path(args.selep_root).expanduser().resolve()),
            "selep_repo_commit": selep_repo_commit(Path(args.selep_root).expanduser().resolve()),
            "table_list": table_list,
            "encoding_length": args.encoding_length,
            "encoding_epochs": args.encoding_epochs,
            "table_encoding_method": args.table_encoding_method,
            "semantic_rows_per_block": args.semantic_rows_per_block,
            "partitioning_method": "selep_clay_affinity_repartition",
            "partitioning_stats": partition_stats,
            "clay_repartition_threshold": args.clay_repartition_threshold,
            "clay_initial_fill": args.clay_initial_fill,
            "clay_empty_fraction": args.clay_empty_fraction,
            "clay_max_load": args.clay_max_load,
            "clay_weight_reset": args.clay_weight_reset,
            "implementation_fidelity": "faithful SeLeP policy reimplementation with Jac storage-interface adapters",
            "original_components": [
                "semantic_block_autoencoder",
                "affinity_matrix",
                "clay_style_repartitioning",
                "partition_encoding",
                "encoder_decoder_lstm",
            ],
        }
    )
    return (
        model,
        partition_events,
        partition_blocks,
        event_exact,
        event_shape,
        event_vectors_exact,
        event_vectors_shape,
    )


def configure_original_selep(args: argparse.Namespace, table_list: list[str]) -> None:
    os.environ.setdefault("CUDA_VISIBLE_DEVICES", "-1")
    os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "1")
    os.environ.setdefault("OMP_NUM_THREADS", "2")
    os.environ.setdefault("TF_NUM_INTRAOP_THREADS", "2")
    os.environ.setdefault("TF_NUM_INTEROP_THREADS", "1")
    selep_root = Path(args.selep_root).expanduser().resolve()
    sys.path.insert(0, str(selep_root))
    from Configuration.config import Config

    Config.table_list = list(table_list)
    lookup: dict[Any, Any] = {}
    for idx, table in enumerate(table_list, start=1):
        lookup[table] = idx
        lookup[idx] = table
    Config.table_lookup = lookup
    Config.encoding_length = int(args.encoding_length)
    Config.encoding_epoch_no = int(args.encoding_epochs)
    Config.max_partition_size = int(args.partition_size)
    Config.look_back = int(args.look_back)
    Config.prefetching_k = int(args.top_k)
    Config.tb_encoding_method = str(args.table_encoding_method)


class Pushd:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.previous: Path | None = None

    def __enter__(self) -> None:
        self.previous = Path.cwd()
        os.chdir(self.path)

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        if self.previous is not None:
            os.chdir(self.previous)


def original_table_list(records: list[dict[str, Any]]) -> list[str]:
    tables: set[str] = set()
    for record in records:
        for block in record.get("_result_blocks") or []:
            parsed = parse_block_id(str(block))
            if parsed is not None:
                tables.add(parsed[0])
    if not tables:
        raise RuntimeError("original SeLeP mode found no relation-qualified blocks")
    return sorted(tables)


def build_original_table_manager(records: list[dict[str, Any]], args: argparse.Namespace, table_list: list[str]) -> Any:
    from Backend.Util.Block import Block
    from Backend.Util.Table import Table
    from Backend.Util.TableManager import TableManager
    import numpy as np
    from Utils.AutoEncoder import encode_table

    blocks_by_table: dict[str, set[int]] = defaultdict(set)
    for record in records:
        for block in record.get("_result_blocks") or []:
            parsed = parse_block_id(str(block))
            if parsed is None:
                continue
            blocks_by_table[parsed[0]].add(parsed[1])

    manager = TableManager()
    for table_name in table_list:
        matrices = fetch_table_block_feature_matrices(
            args,
            table_name,
            sorted(blocks_by_table.get(table_name, set())),
            args.encoding_length,
            args.semantic_rows_per_block,
        )
        table = Table(table_name)
        for block_id, matrix in sorted(matrices.items(), key=lambda item: block_sort_key(item[0])):
            table.add_block(Block(block_id, np.asarray(matrix, dtype=float)))
        if not table.blocks:
            continue
        train_mats = [np.asarray(block.pca_df, dtype=float) for block in table.blocks.values()]
        eval_count = max(1, int(round(len(train_mats) * 0.10)))
        eval_mats = train_mats[:eval_count]
        method = str(args.table_encoding_method)
        if method.startswith("AutoEncoder_"):
            option = int(method.rsplit("_", 1)[1])
            autoencoder = encode_table_with_compatibility(
                encode_table,
                train_mats,
                eval_mats,
                args.encoding_length,
                args.encoding_epochs,
                option,
            )
            for block in table.blocks.values():
                encoded = autoencoder.encoder(np.asarray([block.pca_df], dtype=float)).numpy()[0]
                block.set_encoding(encoded)
        elif method == "PCAOnly":
            for block in table.blocks.values():
                encoded = np.mean(np.asarray(block.pca_df, dtype=float), axis=0)
                block.set_encoding(encoded)
        else:
            raise RuntimeError(f"unsupported original SeLeP table encoding method: {method}")
        manager.add_table(table)
    if not manager.tables:
        raise RuntimeError("original SeLeP mode could not build any table encodings")
    return manager


def encode_table_with_compatibility(
    encode_table: Any,
    train_mats: list[Any],
    eval_mats: list[Any],
    latent_dim: int,
    epoch_no: int,
    encoder_option: int,
) -> Any:
    try:
        return encode_table(train_mats, eval_mats, latent_dim, epoch_no, encoder_option)
    except (TypeError, ValueError) as exc:
        if encoder_option != 1 or "float" not in str(exc).lower():
            raise
    import tensorflow as tf
    from tensorflow import keras
    from keras import layers, losses
    from keras.models import Model
    import numpy as np

    class CompatMLPAutoencoder(Model):
        def __init__(self, latent_dim: int, row_num: int, col_num: int):
            super().__init__()
            self.encoder = keras.Sequential(
                [
                    layers.Flatten(),
                    layers.Dense(latent_dim * 2, activation="relu"),
                    layers.Dense(latent_dim, activation="sigmoid"),
                ]
            )
            self.decoder = keras.Sequential(
                [
                    layers.Dense(int(row_num * col_num / 2), activation="relu"),
                    layers.Dense(row_num * col_num, activation="sigmoid"),
                    layers.Reshape((row_num, col_num)),
                ]
            )

        def call(self, x, **kwargs):
            encoded = self.encoder(x)
            return self.decoder(encoded)

    train_arr = np.asarray(train_mats, dtype=float)
    eval_arr = np.asarray(eval_mats, dtype=float)
    autoencoder = CompatMLPAutoencoder(latent_dim, train_arr.shape[1], train_arr.shape[2])
    autoencoder.compile(optimizer="adam", loss=losses.MeanSquaredError(), metrics=["accuracy", "mse"])
    callbacks = [keras.callbacks.EarlyStopping(monitor="val_loss", patience=25, mode="min")]
    autoencoder.fit(
        train_arr,
        train_arr,
        validation_data=(eval_arr, eval_arr),
        epochs=epoch_no,
        callbacks=callbacks,
        verbose=1,
    )
    return autoencoder


def fetch_table_block_feature_matrices(
    args: argparse.Namespace,
    relation: str,
    block_numbers: list[int],
    width: int,
    rows_per_block: int,
) -> dict[str, Any]:
    import numpy as np

    rows_by_block: dict[str, list[list[float]]] = {f"{relation}_{num}": [] for num in block_numbers}
    if not block_numbers:
        return rows_by_block
    if args.block_source == "hash":
        return {
            block_id: np.asarray([fallback_feature_vector(block_id, width)], dtype=float)
            for block_id in rows_by_block
        }
    for chunk in chunked(block_numbers, 200):
        numbers = ", ".join(str(int(num)) for num in chunk)
        sql = f"""
COPY (
  WITH sampled AS (
    SELECT
      (ctid::text::point)[0]::bigint AS _selep_block,
      to_jsonb(t)::text AS _selep_row,
      row_number() OVER (
        PARTITION BY (ctid::text::point)[0]::bigint
        ORDER BY ctid
      ) AS _selep_rn
    FROM {sql_ident(relation)} AS t
    WHERE (ctid::text::point)[0]::bigint IN ({numbers})
  )
  SELECT _selep_block, _selep_row
  FROM sampled
  WHERE _selep_rn <= {max(1, int(rows_per_block))}
  ORDER BY _selep_block, _selep_rn
) TO STDOUT WITH CSV HEADER;
"""
        proc = db_psql(args, sql, capture=True)
        reader = csv.DictReader(io.StringIO(proc.stdout))
        for row in reader:
            block_id = f"{relation}_{int(row['_selep_block'])}"
            try:
                payload = json.loads(row["_selep_row"])
            except Exception:
                payload = row.get("_selep_row") or ""
            rows_by_block.setdefault(block_id, []).append(row_feature_vector(payload, width))
    max_rows = max([1, *[len(rows) for rows in rows_by_block.values()]])
    max_rows = min(max_rows, max(1, int(rows_per_block)))
    matrices: dict[str, Any] = {}
    for block_id, rows in rows_by_block.items():
        usable = rows[:max_rows]
        if not usable:
            usable = [fallback_feature_vector(block_id, width)]
        while len(usable) < max_rows:
            usable.append(list(np.mean(np.asarray(usable, dtype=float), axis=0)))
        matrices[block_id] = np.asarray(usable, dtype=float)
    return matrices


def row_feature_vector(payload: Any, width: int) -> list[float]:
    vec = [0.0 for _ in range(width)]
    count = 0
    for key, value in flatten_json(payload):
        count += 1
        add_hashed_feature(vec, key, value)
        if count >= 256:
            break
    if count == 0:
        add_hashed_feature(vec, "empty", "empty")
    norm = math.sqrt(sum(value * value for value in vec))
    if norm > 0:
        vec = [value / norm for value in vec]
    return [max(0.0, min(1.0, (value + 1.0) / 2.0)) for value in vec]


def flatten_json(value: Any, prefix: str = ""):
    if isinstance(value, dict):
        for key in sorted(value):
            next_prefix = f"{prefix}.{key}" if prefix else str(key)
            yield from flatten_json(value[key], next_prefix)
    elif isinstance(value, list):
        for idx, item in enumerate(value[:32]):
            yield from flatten_json(item, f"{prefix}[{idx}]")
    else:
        yield prefix, value


def add_hashed_feature(vec: list[float], key: str, value: Any) -> None:
    width = len(vec)
    digest = hashlib.sha256(f"{key}:{type(value).__name__}".encode()).digest()
    idx = int.from_bytes(digest[:4], "big") % width
    if isinstance(value, bool):
        numeric = 1.0 if value else -1.0
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        try:
            numeric = math.tanh(float(value) / 1000000.0)
        except Exception:
            numeric = 0.0
    elif value is None:
        numeric = 0.0
    else:
        raw = str(value)
        vdigest = hashlib.sha256(raw.encode(errors="replace")).digest()
        numeric = (int.from_bytes(vdigest[:8], "big") / float(2**63)) - 1.0
        vec[(idx + 7) % width] += min(len(raw), 256) / 256.0
    vec[idx] += numeric


def fallback_feature_vector(block_id: str, width: int) -> list[float]:
    return row_feature_vector({"block_id": block_id}, width)


def build_original_partition_manager(
    records: list[dict[str, Any]],
    table_manager: Any,
    args: argparse.Namespace,
) -> tuple[Any, dict[str, str], dict[str, set[str]], dict[str, Any]]:
    from Backend.Util.PartitionManager import Partition, PartitionManager

    block_ids = sorted(
        {
            str(block)
            for record in records
            for block in (record.get("_result_blocks") or [])
            if parse_block_id(str(block)) is not None
        },
        key=block_sort_key,
    )
    if not block_ids:
        raise RuntimeError("original SeLeP mode found no blocks to partition")

    partitioner = SelepClayPartitioner(
        block_ids,
        table_manager,
        Partition,
        PartitionManager,
        max_partition_size=max(1, int(args.partition_size)),
        initial_fill_portion=float(args.clay_initial_fill),
        initial_empty_fraction=float(args.clay_empty_fraction),
        repartition_threshold=max(1, int(args.clay_repartition_threshold)),
        max_partition_load=float(args.clay_max_load),
        weight_reset_threshold=float(args.clay_weight_reset),
    )
    stats = partitioner.train(records)
    partition_manager = partitioner.partition_manager
    partition_manager.calculate_partition_encodings(table_manager)
    return (
        partition_manager,
        partitioner.block_partitions(),
        partitioner.partition_blocks(),
        stats,
    )


class SelepClayPartitioner:
    """Clay-style affinity partitioner matching SeLeP's storage-policy layer.

    The original Python entrypoint in the SeLeP artifact is not directly usable
    in this harness, but the algorithm is explicit in the artifact's Java server:
    initialize mostly-full physical-block partitions, maintain a block affinity
    matrix from training-query result blocks, and periodically relocate a
    co-accessed clump out of overloaded partitions.
    """

    def __init__(
        self,
        block_ids: list[str],
        table_manager: Any,
        partition_cls: Any,
        partition_manager_cls: Any,
        *,
        max_partition_size: int,
        initial_fill_portion: float,
        initial_empty_fraction: float,
        repartition_threshold: int,
        max_partition_load: float,
        weight_reset_threshold: float,
    ) -> None:
        self.block_ids = block_ids
        self.table_manager = table_manager
        self.partition_cls = partition_cls
        self.partition_manager = partition_manager_cls()
        self.max_partition_size = max_partition_size
        self.initial_fill_portion = min(1.0, max(0.01, initial_fill_portion))
        self.initial_empty_fraction = max(0.0, initial_empty_fraction)
        self.repartition_threshold = repartition_threshold
        self.max_partition_load = max_partition_load
        self.weight_reset_threshold = weight_reset_threshold
        self.k = 1
        self.res_size_limit = 1000
        self.affinity: dict[str, Counter[str]] = defaultdict(Counter)
        self.access_counts: Counter[str] = Counter()
        self.block_to_partition: dict[str, str] = {}
        self.window_size = 0
        self.total_partition_access = 0
        self.total_received_queries = 0
        self.repartition_attempts = 0
        self.repartition_moves = 0
        self._initialize_partitions()

    def _initialize_partitions(self) -> None:
        initial_cap = max(1, int(math.ceil(self.max_partition_size * self.initial_fill_portion)))
        blocks_by_table: dict[str, list[str]] = defaultdict(list)
        for block in self.block_ids:
            parsed = parse_block_id(block)
            if parsed is not None:
                blocks_by_table[parsed[0]].append(block)
        pid_num = 1
        for table in sorted(blocks_by_table):
            current: list[str] = []
            for block in sorted(blocks_by_table[table], key=block_sort_key):
                current.append(block)
                if len(current) >= initial_cap:
                    self._add_partition(f"p{pid_num}", current)
                    pid_num += 1
                    current = []
            if current:
                self._add_partition(f"p{pid_num}", current)
                pid_num += 1
        extra = int(math.ceil(self.initial_empty_fraction * max(1, len(self.partition_manager.partitions))))
        for _ in range(extra):
            self._add_partition(f"p{pid_num}", [])
            pid_num += 1
        self.partition_manager.increasing_index = pid_num - 1

    def _add_partition(self, pid: str, blocks: list[str]) -> None:
        partition = self.partition_cls(pid, list(blocks))
        self.partition_manager.add_partition_with_load(partition, 0.0)
        for block in partition.blocks:
            self.block_to_partition[block] = pid
            self._set_block_partition(block, pid)

    def train(self, records: list[dict[str, Any]]) -> dict[str, Any]:
        for record in records:
            blocks = self._event_blocks(record)
            if not blocks:
                continue
            self._update_affinities(blocks)
            requested = sorted({self.block_to_partition[block] for block in blocks}, key=partition_sort_key)
            self.total_partition_access += len(requested)
            self.total_received_queries += 1
            self._update_loads(requested)
            self.window_size += 1
            if self.window_size >= self.repartition_threshold:
                self._process_repartition_window()
        return {
            "initial_blocks": len(self.block_ids),
            "partition_count": len(self.partition_manager.partitions),
            "non_empty_partition_count": sum(
                1 for part in self.partition_manager.partitions.values() if part.get_size() > 0
            ),
            "training_events_seen_by_partitioner": self.total_received_queries,
            "repartition_threshold": self.repartition_threshold,
            "repartition_attempts": self.repartition_attempts,
            "repartition_moves": self.repartition_moves,
            "avg_partitions_per_event": (
                self.total_partition_access / self.total_received_queries
                if self.total_received_queries
                else 0.0
            ),
            "max_partition_load_observed": max(self.partition_manager.loads.values(), default=0.0),
        }

    def _event_blocks(self, record: dict[str, Any]) -> list[str]:
        return sorted(
            {str(block) for block in record.get("_result_blocks") or [] if str(block) in self.block_to_partition},
            key=block_sort_key,
        )

    def _update_affinities(self, blocks: list[str]) -> None:
        total = max(1, len(blocks))
        for block in blocks:
            self.access_counts[block] += 1
            block_pid = self.block_to_partition.get(block, "")
            for other in blocks:
                if other == block:
                    continue
                if total > self.res_size_limit and self.block_to_partition.get(other, "") != block_pid:
                    continue
                self.affinity[block][other] += 1.0 / total

    def _process_repartition_window(self) -> None:
        overloads = [
            pid
            for pid, load in self.partition_manager.loads.items()
            if load > self.max_partition_load
        ]
        if not overloads:
            self._decay_affinities()
            self.window_size = 0
            return
        overloads.sort(key=lambda pid: self.partition_manager.loads.get(pid, 0.0), reverse=True)
        for pid in overloads:
            if self._partition_load(pid) < self.max_partition_load:
                continue
            self.repartition_attempts += 1
            before = self.repartition_moves
            self._update_partition(pid)
            if self.partition_manager.loads.get(pid, 0.0) > self.max_partition_load:
                self.max_partition_load = 1.05 * self.partition_manager.loads[pid]
            if self.repartition_moves > before:
                self._update_loads(list(self.partition_manager.partitions.keys()))
        self._decay_affinities()
        self.window_size = 0

    def _update_partition(self, pid: str) -> None:
        max_clump_size = self._max_clump_size()
        original_load = self._partition_load(pid)
        clump: list[str] = []
        candidate = ""
        best_clump: list[str] = []
        best_candidate = ""
        affected: set[str] = set()
        lookahead = 5
        while self._partition_load(pid) > self.max_partition_load:
            neighbor = self._find_clump_neighbor(clump, candidate)
            if not clump:
                hottest = self._hottest_block(pid)
                if not hottest:
                    break
                clump.append(hottest)
                affected.add(pid)
                candidate = self._initial_candidate_partition(hottest)
                if not candidate:
                    if original_load > self.max_partition_load:
                        self.max_partition_load = 1.05 * original_load
                    break
            elif neighbor:
                clump.append(neighbor)
                affected.add(self.block_to_partition.get(neighbor, ""))
                candidate = self._update_candidate_partition(clump, candidate, pid)
                if len(clump) >= max_clump_size:
                    self._done_repartition_with_new_partition(clump, affected, original_load)
                    break
            else:
                if best_clump and best_candidate:
                    self._move_clump(best_clump, best_candidate)
                    affected.add(best_candidate)
                    self._update_loads(list(affected))
                    break
                if len(clump) >= max_clump_size:
                    self._done_repartition_with_new_partition(clump, affected, original_load)
                    break
                if original_load > self.max_partition_load:
                    self.max_partition_load = 1.05 * original_load
                break

            if candidate and self._feasible(clump, candidate):
                best_clump = list(clump)
                best_candidate = candidate
            elif best_clump:
                lookahead -= 1
            if lookahead == 0:
                self._move_clump(best_clump, best_candidate)
                affected.add(best_candidate)
                self._update_loads(list(affected))
                break

    def _done_repartition_with_new_partition(
        self,
        clump: list[str],
        affected: set[str],
        max_load: float,
    ) -> None:
        dest = self._least_filled_partition()
        if not dest or self._partition_size(dest) + len(clump) > self.max_partition_size:
            if max_load > self.max_partition_load:
                self.max_partition_load = 1.05 * max_load
            return
        total_sender_delta = sum(self._sender_delta(clump, pid) for pid in affected if pid)
        receiver_delta = self._receiver_delta(clump, dest)
        if total_sender_delta + receiver_delta >= 0:
            if max_load > self.max_partition_load:
                self.max_partition_load = 1.05 * max_load
            return
        if (
            len([pid for pid in affected if pid]) == 1
            and self._partition_size(dest) == 0
            and len(clump) == self._partition_size(next(pid for pid in affected if pid))
        ):
            if max_load > self.max_partition_load:
                self.max_partition_load = 1.05 * max_load
            return
        self._move_clump(clump, dest)
        affected.add(dest)
        self._update_loads(list(affected))

    def _move_clump(self, clump: list[str], dest: str) -> None:
        if not dest:
            return
        dest_partition = self.partition_manager.partitions[dest]
        for block in clump:
            prev = self.block_to_partition.get(block)
            if not prev or prev == dest:
                continue
            prev_partition = self.partition_manager.partitions[prev]
            prev_partition.blocks = [item for item in prev_partition.blocks if item != block]
            if block not in dest_partition.blocks:
                dest_partition.add_block(block)
            self.block_to_partition[block] = dest
            self._set_block_partition(block, dest)
            self.repartition_moves += 1

    def _feasible(self, clump: list[str], dest: str) -> bool:
        if not dest or dest not in self.partition_manager.partitions:
            return False
        moving = [block for block in clump if self.block_to_partition.get(block) != dest]
        if self._partition_size(dest) + len(moving) > self.max_partition_size:
            return False
        delta = self._receiver_delta(clump, dest)
        return self._partition_load(dest) + delta < self.max_partition_load or delta <= 0

    def _receiver_delta(self, clump: list[str], dest: str) -> float:
        dest_blocks = set(self.partition_manager.partitions.get(dest).blocks if dest in self.partition_manager.partitions else [])
        clump_set = set(clump)
        cost = 0.0
        for block in clump:
            if block in dest_blocks:
                continue
            for other, freq in self.affinity.get(block, {}).items():
                if other in dest_blocks:
                    cost -= self.k * freq
                elif other not in clump_set:
                    cost += self.k * freq
        return cost

    def _sender_delta(self, clump: list[str], pid: str) -> float:
        if pid not in self.partition_manager.partitions:
            return 0.0
        source_blocks = set(self.partition_manager.partitions[pid].blocks)
        clump_set = set(clump)
        cost = 0.0
        for block in clump:
            if block not in source_blocks:
                continue
            for other, freq in self.affinity.get(block, {}).items():
                if other not in source_blocks:
                    cost -= self.k * freq
                elif other not in clump_set:
                    cost += self.k * freq
        return cost

    def _update_candidate_partition(self, clump: list[str], dest: str, source: str) -> str:
        if dest and self._feasible(clump, dest):
            return dest
        most = self._most_coaccessed_partition(clump, dest)
        if most and most != dest and most != source and self._feasible(clump, most):
            return most
        least = self._least_filled_partition()
        if least and least != dest and least != source and self._feasible(clump, least):
            if not most or self._receiver_delta(clump, most) < self._receiver_delta(clump, least):
                return least
        return dest

    def _most_coaccessed_partition(self, clump: list[str], dest: str) -> str:
        scores: Counter[str] = Counter()
        for block in clump:
            for other, freq in self.affinity.get(block, {}).items():
                pid = self.block_to_partition.get(other, "")
                if pid and pid != dest:
                    scores[pid] += freq
        if not scores:
            return ""
        return max(scores, key=lambda pid: (scores[pid], -self._partition_size(pid), pid))

    def _find_clump_neighbor(self, clump: list[str], dest: str) -> str:
        best = ""
        best_score = 0.0
        clump_set = set(clump)
        for block in clump:
            for other, freq in self.affinity.get(block, {}).most_common():
                if other in clump_set or self.block_to_partition.get(other, "") == dest:
                    continue
                score = freq * self.access_counts[block]
                if score > best_score:
                    best = other
                    best_score = score
                break
        return best

    def _initial_candidate_partition(self, block: str) -> str:
        source = self.block_to_partition.get(block, "")
        scores: Counter[str] = Counter()
        for other, freq in self.affinity.get(block, {}).items():
            pid = self.block_to_partition.get(other, "")
            if pid and pid != source:
                scores[pid] += freq
        if not scores:
            return ""
        return max(scores, key=lambda pid: (scores[pid], -self._partition_size(pid), pid))

    def _hottest_block(self, pid: str) -> str:
        partition = self.partition_manager.partitions.get(pid)
        if partition is None:
            return ""
        best = ""
        best_exit_freq = 0.0
        members = set(partition.blocks)
        for block in partition.blocks:
            exit_freq = sum(freq for other, freq in self.affinity.get(block, {}).items() if other not in members)
            if exit_freq > best_exit_freq:
                best = block
                best_exit_freq = exit_freq
        return best

    def _partition_load(self, pid: str) -> float:
        partition = self.partition_manager.partitions.get(pid)
        if partition is None:
            return 0.0
        members = set(partition.blocks)
        load = 0.0
        for block in partition.blocks:
            load += sum(self.k * freq for other, freq in self.affinity.get(block, {}).items() if other not in members)
        self.partition_manager.loads[pid] = load
        return load

    def _update_loads(self, pids: list[str]) -> None:
        for pid in pids:
            self._partition_load(pid)

    def _decay_affinities(self) -> None:
        for block, freqs in list(self.affinity.items()):
            for other in list(freqs):
                freqs[other] *= self.weight_reset_threshold
                if freqs[other] <= 1e-12:
                    del freqs[other]

    def _max_clump_size(self) -> int:
        least = self._least_filled_partition()
        if not least:
            return self.max_partition_size
        return max(1, self.max_partition_size - self._partition_size(least))

    def _least_filled_partition(self) -> str:
        if not self.partition_manager.partitions:
            return ""
        return min(
            self.partition_manager.partitions,
            key=lambda pid: (self._partition_size(pid), partition_sort_key(pid)),
        )

    def _partition_size(self, pid: str) -> int:
        partition = self.partition_manager.partitions.get(pid)
        return partition.get_size() if partition is not None else 0

    def _set_block_partition(self, block: str, pid: str) -> None:
        parsed = parse_block_id(block)
        if parsed is None:
            return
        table = parsed[0]
        table_obj = self.table_manager.tables.get(table) if table in self.table_manager.tables else None
        block_obj = table_obj.blocks.get(block) if table_obj is not None else None
        if block_obj is not None:
            block_obj.set_partitionid(pid)

    def block_partitions(self) -> dict[str, str]:
        return dict(self.block_to_partition)

    def partition_blocks(self) -> dict[str, set[str]]:
        return {
            pid: set(partition.blocks)
            for pid, partition in self.partition_manager.partitions.items()
        }


def build_original_workload(
    records: list[dict[str, Any]],
    workload_path: Path,
    partition_manager: Any,
    block_partitions: dict[str, str],
    args: argparse.Namespace,
) -> tuple[
    list[list[str]],
    list[list[list[float]]],
    dict[str, set[str]],
    dict[str, set[str]],
    dict[str, list[list[float]]],
    dict[str, list[list[float]]],
]:
    from Backend.Util.BackendUtilFunctions import get_encoded_block_aggregation
    import numpy as np

    event_exact: dict[str, set[str]] = defaultdict(set)
    event_shape: dict[str, set[str]] = defaultdict(set)
    vector_exact: dict[str, list[Any]] = defaultdict(list)
    vector_shape: dict[str, list[Any]] = defaultdict(list)
    partition_events: list[list[str]] = []
    event_vectors: list[list[list[float]]] = []
    with workload_path.open("w", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=["theTime", "ClientIP", "row", "statement", "resultBlock", "resultPartitions"],
        )
        writer.writeheader()
        for record in records:
            blocks = [str(block) for block in record.get("_result_blocks") or []]
            parts = sorted({block_partitions[block] for block in blocks if block in block_partitions}, key=partition_sort_key)
            if not parts:
                continue
            encodings = [partition_manager.get_partition_encoding(part) for part in parts]
            encodings = [enc for enc in encodings if enc is not None]
            if not encodings:
                continue
            matrix = np.asarray(get_encoded_block_aggregation(encodings, b_level=False), dtype=float)
            partition_events.append(parts)
            event_vectors.append(matrix.tolist())
            exact = event_key(record, include_params=True)
            shape = event_key(record, include_params=False)
            event_exact[exact].update(parts)
            event_shape[shape].update(parts)
            vector_exact[exact].append(matrix)
            vector_shape[shape].append(matrix)
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
        raise RuntimeError("no original SeLeP partition events produced")
    return (
        partition_events,
        event_vectors,
        event_exact,
        event_shape,
        {key: mean_matrix(mats) for key, mats in vector_exact.items()},
        {key: mean_matrix(mats) for key, mats in vector_shape.items()},
    )


def train_original_lstm_model(
    event_vectors: list[list[list[float]]],
    partition_events: list[list[str]],
    vocab: list[str],
    args: argparse.Namespace,
    model_dir: Path,
    *,
    rows: int,
    cols: int,
) -> dict[str, Any]:
    if len(event_vectors) <= args.look_back:
        raise RuntimeError(f"need more than look_back={args.look_back} SQL events, got {len(event_vectors)}")
    import numpy as np
    import tensorflow as tf
    from tensorflow import keras
    from Backend.Models.LSTM import create_binary_lstm_model

    tf.random.set_seed(args.lstm_seed)
    np.random.seed(args.lstm_seed)
    model_rows = max(2, int(rows))
    model_cols = int(cols)
    prepared_event_vectors = [
        pad_event_matrix(matrix, model_rows, model_cols) for matrix in event_vectors
    ]
    part_to_idx = {part: idx for idx, part in enumerate(vocab)}
    binary_outputs = []
    for parts in partition_events:
        target = np.zeros(len(vocab), dtype=np.float32)
        for part in parts:
            idx = part_to_idx.get(part)
            if idx is not None:
                target[idx] = 1.0
        binary_outputs.append(target)

    supervised_builder = "compatible_local"
    try:
        from selep_main import convert_to_supervised as selep_convert_to_supervised

        x, y_raw = selep_convert_to_supervised(
            [[np.asarray(matrix, dtype=np.float32) for matrix in prepared_event_vectors]],
            [binary_outputs],
            args.look_back,
        )
        y = np.asarray(y_raw, dtype=np.float32)
        supervised_builder = "selep_main.convert_to_supervised"
    except Exception as exc:
        print(f"warning: using local SeLeP supervised conversion fallback: {exc}", flush=True)
        x_events = np.asarray(
            [np.asarray(matrix, dtype=np.float32).reshape(model_rows * model_cols) for matrix in prepared_event_vectors]
        )
        x = np.asarray(
            [x_events[idx - args.look_back : idx] for idx in range(args.look_back, len(event_vectors))],
            dtype=np.float32,
        )
        y = np.asarray(
            [binary_outputs[idx] for idx in range(args.look_back, len(partition_events))],
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
    model = create_binary_lstm_model(len(vocab), args.look_back, model_rows, model_cols)
    model.compile(
        loss=keras.losses.BinaryCrossentropy(from_logits=False),
        optimizer=keras.optimizers.Adam(),
        metrics=[keras.metrics.MeanAbsoluteError(), "accuracy"],
    )
    callbacks = []
    if validation_data is not None:
        callbacks.append(keras.callbacks.EarlyStopping(monitor="val_loss", patience=5, restore_best_weights=True))
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
        "look_back": args.look_back,
        "top_k": args.top_k,
        "test_fraction": args.test_fraction,
        "events": len(partition_events),
        "examples": len(x),
        "train_examples": len(x_train),
        "test_examples": test_examples,
        "partitions": len(vocab),
        "rows": model_rows,
        "cols": model_cols,
        "source_rows": rows,
        "supervised_builder": supervised_builder,
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


def pad_event_matrix(matrix: Any, rows: int, cols: int) -> Any:
    import numpy as np

    arr = np.asarray(matrix, dtype=np.float32)
    if arr.ndim == 1:
        arr = arr.reshape(1, -1)
    elif arr.ndim > 2:
        arr = arr.reshape(arr.shape[0], -1)
    out = np.zeros((rows, cols), dtype=np.float32)
    usable_rows = min(rows, arr.shape[0])
    usable_cols = min(cols, arr.shape[1])
    out[:usable_rows, :usable_cols] = arr[:usable_rows, :usable_cols]
    return out


def mean_matrix(matrices: list[Any]) -> list[list[float]]:
    import numpy as np

    return np.mean(np.asarray(matrices, dtype=float), axis=0).tolist()


def chunked(values: list[Any], size: int):
    for idx in range(0, len(values), size):
        yield values[idx : idx + size]


def sql_ident(value: str) -> str:
    return ".".join('"' + part.replace('"', '""') + '"' for part in value.split("."))


def selep_repo_commit(selep_root: Path) -> str:
    proc = subprocess.run(
        ["git", "-C", str(selep_root), "rev-parse", "HEAD"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return proc.stdout.strip() if proc.returncode == 0 else ""


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
        callbacks.append(keras.callbacks.EarlyStopping(monitor="val_loss", patience=5, restore_best_weights=True))

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
