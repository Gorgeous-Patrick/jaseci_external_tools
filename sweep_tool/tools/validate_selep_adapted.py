"""Offline validation gates for the SeLeP-adapted baseline.

Run this with a Python environment that can import TensorFlow and the local
SeLeP checkout, for example from the SeLeP repo:

    source ./activate_venv.sh
    PYTHONPATH=/path/to/jaseci_external_tools/sweep_tool:/path/to/SeLeP \
        python /path/to/sweep_tool/tools/validate_selep_adapted.py
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import UUID

from lib.prefetch_exp import coaccess, selep_adapted


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate SeLeP-adapted offline gates")
    parser.add_argument("--output-dir", default="", help="Keep artifacts under this directory")
    parser.add_argument("--epochs", type=int, default=3, help="LSTM epochs for gate data")
    parser.add_argument("--seed", type=int, default=7, help="Deterministic training seed")
    parser.add_argument("--look-back", type=int, default=4, help="SeLeP look_back")
    args = parser.parse_args()

    if args.output_dir:
        base = Path(args.output_dir).resolve()
        base.mkdir(parents=True, exist_ok=True)
        report = run_gates(base, epochs=args.epochs, seed=args.seed, look_back=args.look_back)
    else:
        with TemporaryDirectory(dir="/tmp") as tmp:
            report = run_gates(Path(tmp), epochs=args.epochs, seed=args.seed, look_back=args.look_back)

    print(json.dumps(report, indent=2, sort_keys=True))
    failed = [name for name, gate in report["gates"].items() if not gate["passed"]]
    if failed:
        raise SystemExit(f"failed gate(s): {', '.join(failed)}")


def run_gates(base: Path, *, epochs: int, seed: int, look_back: int) -> dict[str, object]:
    planted = _planted_groups(group_count=10, group_size=5)
    recovery_logs = _write_group_logs(base / "recovery", planted, list(range(10)) * 3)
    recovery_model = selep_adapted.write_pooled_selep_models_from_access_logs(
        recovery_logs,
        {10: base / "recovery" / "selep_model_limit10.json"},
        app_name="synthetic",
        walker="SyntheticWalker",
        label="selep-adapted-validation-recovery",
        seed=seed,
        training_request_ids=[f"recovery-train-{i}" for i in range(len(recovery_logs))],
        trial_request_ids=["recovery-trial"],
        trial_count=1,
        plan_start_ids=["*"],
        look_back=look_back,
        epochs=epochs,
        batch_size=8,
    )[10]
    recovery = _group_recovery(recovery_model, planted)

    repeat_dir = base / "repeat"
    repeat_group = sorted(planted[0])
    repeat_logs = _write_repeat_logs(repeat_dir, repeat_group, count=12, prefix="train")
    actual_log = _write_trace(repeat_dir / "actual.csv", repeat_group, "RepeatNode")
    repeat_model_path = repeat_dir / "selep_model_limit5.json"
    repeat_model = selep_adapted.write_pooled_selep_models_from_access_logs(
        repeat_logs,
        {5: repeat_model_path},
        app_name="synthetic",
        walker="RepeatWalker",
        label="selep-adapted-validation-repeat",
        seed=seed,
        training_request_ids=[f"repeat-train-{i}" for i in range(len(repeat_logs))],
        trial_request_ids=["repeat-trial"],
        trial_count=1,
        plan_start_ids=["*"],
        look_back=look_back,
        epochs=epochs,
        batch_size=4,
    )[5]
    quality = selep_adapted.plan_quality(repeat_model_path, "*", actual_log, limit=5)
    repeat_coverage = float(quality.get("coverage", "0") or "0")

    cold_model = selep_adapted.write_pooled_selep_models_from_access_logs(
        repeat_logs[:look_back],
        {5: base / "cold" / "selep_model_limit5.json"},
        app_name="synthetic",
        walker="ColdWalker",
        label="selep-adapted-validation-cold",
        seed=seed,
        training_request_ids=[f"cold-train-{i}" for i in range(look_back)],
        trial_request_ids=["cold-trial"],
        trial_count=1,
        plan_start_ids=["*"],
        look_back=look_back,
        epochs=epochs,
        batch_size=4,
    )[5]

    det_a = selep_adapted.write_pooled_selep_models_from_access_logs(
        repeat_logs,
        {5: base / "determinism_a" / "selep_model_limit5.json"},
        app_name="synthetic",
        walker="RepeatWalker",
        label="selep-adapted-validation-determinism",
        seed=seed,
        training_request_ids=[f"det-train-{i}" for i in range(len(repeat_logs))],
        trial_request_ids=["det-trial"],
        trial_count=1,
        plan_start_ids=["*"],
        look_back=look_back,
        epochs=epochs,
        batch_size=4,
    )[5]
    det_b = selep_adapted.write_pooled_selep_models_from_access_logs(
        repeat_logs,
        {5: base / "determinism_b" / "selep_model_limit5.json"},
        app_name="synthetic",
        walker="RepeatWalker",
        label="selep-adapted-validation-determinism",
        seed=seed,
        training_request_ids=[f"det-train-{i}" for i in range(len(repeat_logs))],
        trial_request_ids=["det-trial"],
        trial_count=1,
        plan_start_ids=["*"],
        look_back=look_back,
        epochs=epochs,
        batch_size=4,
    )[5]
    det_plan_a = det_a["plans"]["*"]["plan"]
    det_plan_b = det_b["plans"]["*"]["plan"]

    return {
        "metric": {
            "partition_recovery": "for each planted group, max(|group intersect partition| / |group|)",
            "repeat_coverage": "covered distinct UUIDs / actual distinct UUIDs",
        },
        "gates": {
            "partition_recovery": {
                "passed": recovery["mean"] >= 0.9 and recovery["minimum"] >= 0.8,
                **recovery,
            },
            "repeat_regime": {
                "passed": repeat_coverage >= 90.0,
                "coverage": repeat_coverage,
                "quality": quality,
                "trained": repeat_model["metadata"]["trained"],
                "train_samples": repeat_model["metadata"]["train_samples"],
            },
            "cold_start": {
                "passed": cold_model["plans"]["*"]["plan"] == [],
                "plan_len": len(cold_model["plans"]["*"]["plan"]),
                "cold_start": cold_model["metadata"]["cold_start"],
                "failure_reason": cold_model["metadata"]["failure_reason"],
            },
            "determinism": {
                "passed": det_plan_a == det_plan_b,
                "plan_a": det_plan_a,
                "plan_b": det_plan_b,
            },
        },
        "artifacts": {
            "base_dir": str(base),
            "recovery_model": str(base / "recovery" / "selep_model_limit10.json"),
            "repeat_model": str(repeat_model_path),
        },
    }


def _planted_groups(group_count: int, group_size: int) -> list[set[str]]:
    return [
        {str(UUID(int=gid * 1000 + idx + 1)) for idx in range(group_size)}
        for gid in range(group_count)
    ]


def _write_group_logs(base: Path, groups: list[set[str]], order: list[int]) -> list[Path]:
    logs: list[Path] = []
    for req_idx, gid in enumerate(order):
        logs.append(_write_trace(base / f"trace_{req_idx:03d}.csv", sorted(groups[gid]), f"NodeG{gid}"))
    return logs


def _write_repeat_logs(base: Path, group: list[str], *, count: int, prefix: str) -> list[Path]:
    return [
        _write_trace(base / f"{prefix}_{idx:03d}.csv", group, "RepeatNode")
        for idx in range(count)
    ]


def _write_trace(path: Path, ids: list[str], node_type: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["id", "tier", "type"])
        writer.writeheader()
        for uid in ids:
            writer.writerow({"id": uid, "tier": "L2", "type": node_type})
    return path


def _group_recovery(model: dict[str, object], groups: list[set[str]]) -> dict[str, object]:
    partitions = [
        set(part.get("top_ids", []))
        for part in model.get("partitions", [])
        if isinstance(part, dict)
    ]
    overlaps = [
        max((len(group & partition) / len(group) for partition in partitions), default=0.0)
        for group in groups
    ]
    return {
        "mean": round(sum(overlaps) / len(overlaps), 3),
        "minimum": round(min(overlaps), 3),
        "overlaps": [round(value, 3) for value in overlaps],
        "cluster_count": int(model.get("cluster_count", 0)),
    }


if __name__ == "__main__":
    main()
