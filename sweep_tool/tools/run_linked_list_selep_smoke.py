"""Collect a LinkedList SQL trace and train a small SeLeP-shaped model.

This is a smoke-test pipeline for the SeLeP integration work.  It does not
train the original SeLeP ED-LSTM; that still needs the SeLeP TensorFlow
environment.  The goal here is to prove that Jac can emit replayable SQL
events and that those events can be converted into a partition-sequence
training artifact.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
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
    parser.add_argument("--partitions", type=int, default=64)
    parser.add_argument("--skip-collect", action="store_true")
    return parser.parse_args()


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
            "SWEEP_DB_SSH_OPTIONS": env.get("SWEEP_DB_SSH_OPTIONS", "-F /home/patrickli/.ssh/config"),
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


def write_workload(records: list[dict[str, Any]], workload_path: Path, partition_count: int) -> list[str]:
    partitions: list[str] = []
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
            partition = stable_partition(record, partition_count)
            partitions.append(partition)
            writer.writerow(
                {
                    "theTime": str(record.get("ts_ns") or ""),
                    "ClientIP": str(record.get("thread_id") or "linked_list"),
                    "row": str(record.get("row_count") or 0),
                    "statement": record.get("sql") or "",
                    "resultBlock": f"[{block_id(record, partition)}]",
                    "resultPartitions": f"[{partition}]",
                }
            )
    return partitions


def train_frequency_model(partitions: list[str], look_back: int, top_k: int) -> dict[str, Any]:
    if len(partitions) <= look_back:
        raise RuntimeError(
            f"need more than look_back={look_back} SQL events, got {len(partitions)}"
        )
    counts: dict[str, Counter[str]] = defaultdict(Counter)
    total = 0
    hits = 0
    for idx in range(look_back, len(partitions)):
        context = tuple(partitions[idx - look_back : idx])
        target = partitions[idx]
        key = "|".join(context)
        prediction = [part for part, _count in counts[key].most_common(top_k)]
        if target in prediction:
            hits += 1
        counts[key][target] += 1
        total += 1

    model_contexts = {
        key: [{"partition": part, "count": count} for part, count in counter.most_common()]
        for key, counter in sorted(counts.items())
    }
    global_counts = Counter(partitions)
    return {
        "model_type": "next_partition_frequency_smoke",
        "source": "linked_list JAC_SELEP_TRACE",
        "look_back": look_back,
        "top_k": top_k,
        "events": len(partitions),
        "examples": total,
        "contexts": len(model_contexts),
        "online_train_hit_rate": hits / total if total else 0.0,
        "global_top": [
            {"partition": part, "count": count}
            for part, count in global_counts.most_common(top_k)
        ],
        "context_model": model_contexts,
    }


def write_summary(out_dir: Path, trace_path: Path, workload_path: Path, model_path: Path, model: dict[str, Any]) -> None:
    summary = {
        "trace": str(trace_path),
        "workload": str(workload_path),
        "model": str(model_path),
        "events": model["events"],
        "examples": model["examples"],
        "contexts": model["contexts"],
        "online_train_hit_rate": model["online_train_hit_rate"],
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

    if not args.skip_collect:
        run_collect(args, out_dir)
    records = load_trace(trace_path)
    partitions = write_workload(records, workload_path, args.partitions)
    model = train_frequency_model(partitions, args.look_back, args.top_k)
    model_path.write_text(json.dumps(model, indent=2, sort_keys=True))
    write_summary(out_dir, trace_path, workload_path, model_path, model)

    print("=== LinkedList SeLeP smoke complete ===")
    print(f"trace    : {trace_path} ({len(records)} SQL records)")
    print(f"workload : {workload_path}")
    print(f"model    : {model_path}")
    print(
        "train    : "
        f"examples={model['examples']} contexts={model['contexts']} "
        f"online_hit={model['online_train_hit_rate']:.3f}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
