#!/usr/bin/env python3
"""Run the Jacord same-spawn churn experiment.

The experiment trains stale history-style predictors on one channel before
churn, generates deterministic churned Mongo dumps by mutating through Jac
walkers, restarts the whole storage stack after mutation, then measures cold
post-churn runs from those dumps.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import random
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID


SWEEP_TOOL_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SWEEP_TOOL_ROOT))

from lib import manifest as mf  # noqa: E402
from lib.prefetch_exp import coaccess, markov, metrics, oracle, process, selep_adapted  # noqa: E402
from lib.prefetch_exp.adapters import make_adapter  # noqa: E402
from lib.prefetch_exp.config_edit import RunConfigEditor  # noqa: E402
from lib.prefetch_exp.models import RequestSpec, SweepOptions  # noqa: E402


DEFAULT_POLICIES = ["oracle", "ttg", "history", "markov", "coaccess", "none"]
SUPPORTED_POLICIES = DEFAULT_POLICIES + ["selep", "selep-adapted"]
DEFAULT_CHURN_RATES = [0, 5, 10, 25, 50]
CHURN_COLUMNS = [
    "churn_rate",
    "churn_seed",
    "policy",
    "runtime_policy",
    "walker",
    "prefetch_limit",
    "trial",
    "e2e_ms",
    "request_id",
    "base_message_count",
    "added_messages",
    "post_message_count",
    "analytic_stale_coverage",
    "empirical_stale_coverage",
    "coverage",
    "accuracy",
    "actual_ids",
    "plan_ids",
    "covered_ids",
    "overfetch_ids",
    "undercoverage_ids",
    "topo_idx_ms",
    "ttg_ms",
    "prefetch_ms",
    "walker_ms",
    "l1_hit_rate",
    "l1",
    "l2",
    "l3",
    "miss",
    "mongo_q",
    "base_dump",
    "churn_dump",
    "oracle_file",
    "model_file",
    "ttg_plan_file",
]


@dataclass
class ChurnPaths:
    logs_dir: Path
    profiles_dir: Path
    models_dir: Path
    dumps_dir: Path
    results_csv: Path
    metadata_json: Path


@dataclass
class ChurnDump:
    rate: int
    dump_name: str
    added_messages: int
    post_message_count: int
    working_set_path: Path
    actual_ids: list[str]


@dataclass
class StalePlans:
    access_log: Path
    oracle_file: Path
    markov_file: Path
    coaccess_file: Path
    selep_file: Path | None
    selep_training_logs: list[Path]
    actual_ids: list[str]
    message_ids: list[str]
    message_count: int


def main() -> int:
    args = _parse_args()
    manifest = mf.load(args.manifest)
    if manifest.name != "jacord":
        raise ValueError(f"Jacord churn requires the jacord manifest, got {manifest.name!r}")

    options = SweepOptions.from_env(manifest, jac_bin=args.jac_bin)
    options.limits = [args.limit]
    options.trials = args.trials
    options.policies = list(args.policies)
    options.env["JACORD_DUMP"] = args.base_dump
    if args.channel_id:
        options.env["JACORD_CHANNEL_ID"] = args.channel_id
    options.env.pop("JAC_PREFETCH_DUMP", None)

    adapter = make_adapter(options)
    paths = _paths(adapter.app_dir, args)
    _prepare_output_dirs(adapter, paths, clean=not args.keep_outputs)
    _write_header(paths.results_csv)

    editor = RunConfigEditor(adapter.config_path)
    try:
        print("=== Jacord churn experiment ===")
        print(f"app_dir     : {adapter.app_dir}")
        print(f"base_dump   : {args.base_dump} -> {adapter.dump_description(args.base_dump)}")
        print(f"policies    : {' '.join(args.policies)}")
        print(f"churn_rates : {' '.join(str(x) for x in args.churn_rates)}")
        print(f"limit       : {args.limit}")
        print(f"trials      : {args.trials}")
        print(f"seed        : {args.seed}")
        print(f"reply_frac  : {args.reply_fraction:g}")
        print(f"restore     : {args.restore_scope}")
        print(f"db          : {adapter.db_summary()}")
        print("")

        print("=== Restoring base dump and selecting channel ===")
        _restore_named_dump(adapter, args.base_dump)
        spec, base_count = _select_request(adapter, editor, paths, args.channel_id)
        print(f"channel     : {spec.target_id}")
        print(f"base messages reported by load_channel: {base_count}")

        print("")
        print("=== Recording pre-churn same-spawn training trace ===")
        stale = _build_stale_plans(adapter, editor, spec, paths, args)
        if stale.message_count != base_count:
            raise RuntimeError(
                "base channel count changed while recording stale trace: "
                f"selected={base_count} trace={stale.message_count}"
            )
        print(
            f"stale trace : messages={stale.message_count} "
            f"actual_ids={len(stale.actual_ids)}"
        )
        print(f"history file: {stale.oracle_file}")
        print(f"markov file : {stale.markov_file}")
        print(f"coaccess    : {stale.coaccess_file}")
        if stale.selep_file is not None:
            print(f"selep       : {stale.selep_file}")

        print("")
        print("=== Generating/reusing deterministic churn dumps ===")
        dumps: list[ChurnDump] = []
        for rate in args.churn_rates:
            dump = _ensure_churn_dump(
                adapter,
                editor,
                spec,
                paths,
                args,
                rate,
                stale.message_ids,
                base_count,
            )
            dumps.append(dump)
            print(
                f"p={rate:>2}% dump={dump.dump_name} "
                f"added={dump.added_messages} post_messages={dump.post_message_count} "
                f"actual_ids={len(dump.actual_ids)}"
            )

        largest = max(dumps, key=lambda d: d.rate)
        if len(largest.actual_ids) > args.limit and not args.allow_limit_under_working_set:
            raise RuntimeError(
                f"prefetch limit {args.limit} is smaller than p={largest.rate} "
                f"working set ({len(largest.actual_ids)} distinct IDs). Increase "
                "JACORD_CHURN_LIMIT or pass --allow-limit-under-working-set."
            )

        p0 = next((d for d in dumps if d.rate == 0), None)
        if p0 is not None and set(p0.actual_ids) != set(stale.actual_ids):
            raise RuntimeError(
                "p=0 churn dump does not reproduce the pre-churn access set; "
                "stop and debug before using churn results."
            )

        metadata = {
            "app": "jacord",
            "base_dump": args.base_dump,
            "channel_id": spec.target_id,
            "walker": spec.walker,
            "limit": args.limit,
            "trials": args.trials,
            "seed": args.seed,
            "reply_fraction": args.reply_fraction,
            "restore_scope": args.restore_scope,
            "policies": args.policies,
            "base_message_count": stale.message_count,
            "base_actual_ids": len(stale.actual_ids),
            "churn_rates": args.churn_rates,
            "selep_file": str(stale.selep_file) if stale.selep_file is not None else "",
            "selep_training_logs": [str(path) for path in stale.selep_training_logs],
            "dumps": [
                {
                    "rate": d.rate,
                    "dump_name": d.dump_name,
                    "dump_description": adapter.dump_description(d.dump_name),
                    "added_messages": d.added_messages,
                    "post_message_count": d.post_message_count,
                    "actual_ids": len(d.actual_ids),
                }
                for d in dumps
            ],
        }
        paths.metadata_json.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n")
        print(f"metadata    : {paths.metadata_json}")

        print("")
        print("=== Measuring post-churn cold runs ===")
        rows_by_rate: dict[int, list[dict[str, Any]]] = {}
        for dump in dumps:
            rows_by_rate[dump.rate] = []
            if args.restore_scope == "case":
                _restore_named_dump(adapter, dump.dump_name)
            for policy in args.policies:
                if args.restore_scope == "case":
                    _restore_named_dump(adapter, dump.dump_name)
                for trial in range(1, args.trials + 1):
                    if args.restore_scope == "trial":
                        _restore_named_dump(adapter, dump.dump_name)
                    row = _measure_policy_trial(
                        adapter,
                        editor,
                        spec,
                        paths,
                        args,
                        dump,
                        stale,
                        policy,
                        trial,
                    )
                    _append_row(paths.results_csv, row)
                    rows_by_rate[dump.rate].append(row)
                    print(
                        f"  p={dump.rate:>2}% policy={policy:<8} trial={trial} "
                        f"e2e={float(row['e2e_ms']):.1f}ms "
                        f"coverage={row['coverage']} hit={row['l1_hit_rate']}"
                    )

            if dump.rate == 0:
                _assert_p0_sanity(
                    rows_by_rate[dump.rate],
                    args.sanity_min_coverage,
                    requested_policies=set(args.policies),
                )

    finally:
        editor.restore()
        adapter.stop_stale_servers()
        options.env.pop("JAC_PREFETCH_DUMP", None)

    print("")
    print("========================================")
    print("Jacord churn experiment complete")
    print(f"Results saved to: {paths.results_csv}")
    print("========================================")
    return 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=SWEEP_TOOL_ROOT / "manifests" / "jacord.yaml",
        help="Path to sweep_tool/manifests/jacord.yaml.",
    )
    parser.add_argument("--jac-bin", default=os.environ.get("JAC_BIN", ""))
    parser.add_argument(
        "--base-dump",
        default=os.environ.get("JACORD_CHURN_BASE_DUMP")
        or os.environ.get("JACORD_DUMP")
        or "jac_db.dump",
    )
    parser.add_argument(
        "--channel-id",
        default=os.environ.get("JACORD_CHURN_CHANNEL_ID")
        or os.environ.get("JACORD_CHANNEL_ID", ""),
    )
    parser.add_argument(
        "--churn-rates",
        type=_parse_ints,
        default=_parse_ints(os.environ.get("JACORD_CHURN_RATES", "")) or DEFAULT_CHURN_RATES,
        help="Space- or comma-separated churn rates in percent.",
    )
    parser.add_argument(
        "--policies",
        type=_parse_words,
        default=_parse_words(os.environ.get("JACORD_CHURN_POLICIES", "")) or DEFAULT_POLICIES,
        help="Policies to measure: none oracle ttg history markov coaccess selep-adapted.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=int(os.environ.get("JACORD_CHURN_LIMIT", "12000")),
    )
    parser.add_argument(
        "--trials",
        type=int,
        default=int(os.environ.get("JACORD_CHURN_TRIALS", "5")),
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=int(os.environ.get("JACORD_CHURN_SEED", "42")),
    )
    parser.add_argument(
        "--reply-fraction",
        type=float,
        default=float(os.environ.get("JACORD_CHURN_REPLY_FRACTION", "0.0")),
        help="Fraction of added message anchors posted as replies. Default 0 keeps pure top-level addition.",
    )
    parser.add_argument(
        "--restore-scope",
        choices=["trial", "case"],
        default=os.environ.get("JACORD_CHURN_RESTORE_SCOPE", "trial"),
        help="trial restores the churn dump before every measured trial; case restores before each policy case.",
    )
    parser.add_argument(
        "--stack-wait-sec",
        type=float,
        default=float(os.environ.get("JACORD_CHURN_STACK_WAIT_SEC", "5")),
    )
    parser.add_argument(
        "--force-dumps",
        action="store_true",
        default=_truthy(os.environ.get("JACORD_CHURN_FORCE_DUMPS", "")),
        help="Regenerate churn dumps even when the target dump file already exists.",
    )
    parser.add_argument(
        "--keep-outputs",
        action="store_true",
        default=_truthy(os.environ.get("JACORD_CHURN_KEEP_OUTPUTS", "")),
        help="Do not delete churn_logs/churn_profiles/churn_models before running.",
    )
    parser.add_argument(
        "--allow-limit-under-working-set",
        action="store_true",
        default=_truthy(os.environ.get("JACORD_CHURN_ALLOW_SMALL_LIMIT", "")),
    )
    parser.add_argument(
        "--sanity-min-coverage",
        type=float,
        default=float(os.environ.get("JACORD_CHURN_SANITY_MIN_COVERAGE", "99.0")),
        help="Minimum p=0 coverage required for oracle/history/markov/coaccess/selep-adapted.",
    )
    parser.add_argument(
        "--selep-train-repeats",
        type=int,
        default=int(os.environ.get("JACORD_CHURN_SELEP_TRAIN_REPEATS", "0") or "0"),
        help=(
            "Pre-churn no-prefetch repeats used to train SeLeP-adapted. "
            "Default is max(12, SWEEP_SELEP_LOOK_BACK + 8) when SeLeP is requested."
        ),
    )
    args = parser.parse_args()
    unknown = sorted(set(args.policies) - set(SUPPORTED_POLICIES))
    if unknown:
        raise ValueError(f"unsupported churn policy/policies: {', '.join(unknown)}")
    if args.limit <= 0:
        raise ValueError("--limit must be positive")
    if args.trials <= 0:
        raise ValueError("--trials must be positive")
    if any(rate < 0 for rate in args.churn_rates):
        raise ValueError("--churn-rates must be non-negative")
    if args.reply_fraction < 0 or args.reply_fraction > 1:
        raise ValueError("--reply-fraction must be between 0 and 1")
    return args


def _paths(app_dir: Path, args: argparse.Namespace) -> ChurnPaths:
    return ChurnPaths(
        logs_dir=app_dir / "churn_logs",
        profiles_dir=app_dir / "churn_profiles",
        models_dir=app_dir / "churn_models",
        dumps_dir=app_dir / "churn_dumps",
        results_csv=app_dir / "churn_results.csv",
        metadata_json=app_dir / "churn_metadata.json",
    )


def _prepare_output_dirs(adapter, paths: ChurnPaths, *, clean: bool) -> None:
    if clean:
        for path in (paths.logs_dir, paths.profiles_dir, paths.models_dir):
            if path.exists():
                import shutil

                shutil.rmtree(path)
    for path in (paths.logs_dir, paths.profiles_dir, paths.models_dir, paths.dumps_dir):
        path.mkdir(parents=True, exist_ok=True)
    adapter.db_manager.ensure_app_dir("churn_dumps")


def _select_request(
    adapter,
    editor: RunConfigEditor,
    paths: ChurnPaths,
    channel_id: str,
) -> tuple[RequestSpec, int]:
    walker = adapter.options.env.get("WALKER") or "load_channel"
    editor.patch(
        _config_values(
            "none",
            0,
            access_log=str(paths.logs_dir / "select_channel_access.csv"),
        )
    )
    adapter.flush_redis()
    proc = None
    try:
        proc = adapter.start_server(paths.logs_dir / "select_channel.log")
        token = adapter.login()
        if channel_id:
            message_count = _load_channel_count(adapter, walker, channel_id, token)
            adapter._validate_channel_size(channel_id, message_count)
        else:
            channel_id = adapter._select_channel(token)
            message_count = adapter._selected_channel_messages
    finally:
        process.stop_process(proc)
        adapter.stop_stale_servers()
    return (
        RequestSpec(
            walker=walker,
            path=f"/walker/{walker}/{channel_id}",
            body={},
            target_id=channel_id,
            request_id=channel_id,
        ),
        int(message_count),
    )


def _build_stale_plans(
    adapter,
    editor: RunConfigEditor,
    spec: RequestSpec,
    paths: ChurnPaths,
    args: argparse.Namespace,
) -> StalePlans:
    limit = args.limit
    record = _record_access_trace(
        adapter,
        editor,
        spec,
        log_path=paths.logs_dir / "pre_churn_train.log",
        access_log=paths.logs_dir / "pre_churn_train_access.csv",
    )
    stale_oracle = paths.models_dir / "history_pre_churn.uuids"
    stale_markov = paths.models_dir / "markov_pre_churn.json"
    stale_coaccess = paths.models_dir / "coaccess_pre_churn.json"
    stale_selep: Path | None = None
    selep_training_logs: list[Path] = []
    ids = oracle.write_oracle_from_access_log(record["access_log"], stale_oracle)
    markov.write_markov_model_from_access_log(
        record["access_log"],
        stale_markov,
        app_name=adapter.name,
        walker=spec.walker,
        target_id=spec.target_id,
        start_id=spec.target_id,
        limit=limit,
    )
    coaccess.write_coaccess_model_from_access_log(
        record["access_log"],
        stale_coaccess,
        app_name=adapter.name,
        walker=spec.walker,
        target_id=spec.target_id,
        start_id=spec.target_id,
        limit=limit,
        cluster_threshold=adapter.options.coaccess_cluster_threshold,
    )
    if _requests_selep_policy(args.policies):
        stale_selep = paths.models_dir / "selep_pre_churn.json"
        selep_training_logs = _record_selep_repeat_traces(
            adapter,
            editor,
            spec,
            paths,
            base_record=record,
            repeats=args.selep_train_repeats,
        )
        train_ids = [
            f"{spec.request_id}:pre_churn_repeat_{idx}"
            for idx in range(1, len(selep_training_logs) + 1)
        ]
        try:
            selep_adapted.write_pooled_selep_models_from_access_logs(
                selep_training_logs,
                {limit: stale_selep},
                app_name=adapter.name,
                walker=spec.walker,
                label="selep-adapted-churn-repeat",
                seed=adapter.options.selep_pool_seed,
                training_request_ids=train_ids,
                trial_request_ids=[spec.request_id],
                trial_count=args.trials,
                plan_start_ids=[spec.target_id],
                cluster_threshold=adapter.options.coaccess_cluster_threshold,
                look_back=adapter.options.selep_look_back,
                epochs=adapter.options.selep_epochs,
                batch_size=adapter.options.selep_batch_size,
                selep_repo=adapter.options.selep_repo,
                source_commit=adapter.options.selep_source_commit,
            )
        except Exception as exc:
            print(f"SeLeP-adapted churn training failed; measuring empty plan: {exc}")
            selep_adapted.write_empty_selep_model(
                stale_selep,
                app_name=adapter.name,
                walker=spec.walker,
                label="selep-adapted-churn-repeat",
                limit=limit,
                seed=adapter.options.selep_pool_seed,
                training_request_ids=train_ids,
                trial_request_ids=[spec.request_id],
                trial_count=args.trials,
                plan_start_ids=[spec.target_id],
                reason=f"pipeline_failure:{type(exc).__name__}:{exc}",
                cluster_threshold=adapter.options.coaccess_cluster_threshold,
                look_back=adapter.options.selep_look_back,
                epochs=adapter.options.selep_epochs,
                batch_size=adapter.options.selep_batch_size,
                source_commit=adapter.options.selep_source_commit,
            )
    return StalePlans(
        access_log=record["access_log"],
        oracle_file=stale_oracle,
        markov_file=stale_markov,
        coaccess_file=stale_coaccess,
        selep_file=stale_selep,
        selep_training_logs=selep_training_logs,
        actual_ids=ids,
        message_ids=record["message_ids"],
        message_count=record["message_count"],
    )


def _record_selep_repeat_traces(
    adapter,
    editor: RunConfigEditor,
    spec: RequestSpec,
    paths: ChurnPaths,
    *,
    base_record: dict[str, Any],
    repeats: int,
) -> list[Path]:
    needed = repeats if repeats > 0 else max(12, adapter.options.selep_look_back + 8)
    if needed <= adapter.options.selep_look_back:
        raise RuntimeError(
            "SeLeP-adapted churn training needs more repeats than look_back; "
            f"got repeats={needed}, look_back={adapter.options.selep_look_back}"
        )
    logs = [base_record["access_log"]]
    base_ids = set(base_record["actual_ids"])
    for idx in range(2, needed + 1):
        record = _record_access_trace(
            adapter,
            editor,
            spec,
            log_path=paths.logs_dir / f"pre_churn_selep_train_{idx:03d}.log",
            access_log=paths.logs_dir / f"pre_churn_selep_train_{idx:03d}_access.csv",
        )
        if record["message_count"] != base_record["message_count"]:
            raise RuntimeError(
                "SeLeP-adapted pre-churn repeat changed message count: "
                f"base={base_record['message_count']} repeat={record['message_count']}"
            )
        if set(record["actual_ids"]) != base_ids:
            raise RuntimeError(
                "SeLeP-adapted pre-churn repeat did not reproduce the base access set"
            )
        logs.append(record["access_log"])
    return logs


def _ensure_churn_dump(
    adapter,
    editor: RunConfigEditor,
    spec: RequestSpec,
    paths: ChurnPaths,
    args: argparse.Namespace,
    rate: int,
    base_message_ids: list[str],
    base_message_count: int,
) -> ChurnDump:
    dump_name = f"churn_dumps/jacord_churn_p{rate:02d}_seed{args.seed}.dump"
    added_messages = int(round(base_message_count * (rate / 100.0)))
    if args.force_dumps or not adapter.dump_exists(dump_name):
        print(f"  generating p={rate}% dump via Jac walkers")
        _restore_named_dump(adapter, args.base_dump)
        if added_messages > 0:
            _mutate_channel(
                adapter,
                editor,
                spec,
                paths,
                rate,
                seed=args.seed,
                total_additions=added_messages,
                reply_fraction=args.reply_fraction,
                base_message_ids=base_message_ids,
            )
        _restart_storage_stack(adapter, wait_sec=args.stack_wait_sec)
        post_count = _verify_channel_after_restart(adapter, editor, spec, paths, rate)
        if post_count < base_message_count + added_messages:
            raise RuntimeError(
                f"p={rate} verification saw only {post_count} messages; expected at least "
                f"{base_message_count + added_messages}"
            )
        adapter.mongodump_to_app(dump_name)
        print(f"    wrote {adapter.dump_description(dump_name)}")
    else:
        print(f"  reusing p={rate}% dump: {adapter.dump_description(dump_name)}")

    _restore_named_dump(adapter, dump_name)
    working = _record_access_trace(
        adapter,
        editor,
        spec,
        log_path=paths.logs_dir / f"working_set_p{rate:02d}.log",
        access_log=paths.logs_dir / f"working_set_p{rate:02d}_access.csv",
    )
    if working["message_count"] < base_message_count + added_messages:
        raise RuntimeError(
            f"p={rate} working-set run saw {working['message_count']} messages; "
            f"expected at least {base_message_count + added_messages}"
        )
    return ChurnDump(
        rate=rate,
        dump_name=dump_name,
        added_messages=added_messages,
        post_message_count=working["message_count"],
        working_set_path=working["access_log"],
        actual_ids=working["actual_ids"],
    )


def _mutate_channel(
    adapter,
    editor: RunConfigEditor,
    spec: RequestSpec,
    paths: ChurnPaths,
    rate: int,
    *,
    seed: int,
    total_additions: int,
    reply_fraction: float,
    base_message_ids: list[str],
) -> None:
    rng = random.Random((seed * 1009) + rate)
    reply_count = int(round(total_additions * reply_fraction))
    top_level_count = total_additions - reply_count
    editor.patch(
        _config_values(
            "none",
            0,
            access_log=str(paths.logs_dir / f"mutate_p{rate:02d}_access.csv"),
        )
    )
    adapter.flush_redis()
    proc = None
    new_message_ids: list[str] = []
    try:
        proc = adapter.start_server(paths.logs_dir / f"mutate_p{rate:02d}.log")
        token = adapter.login()
        for idx in range(top_level_count):
            content = f"churn seed={seed} rate={rate} top={idx}"
            resp = adapter.post(
                "/walker/PostMessage",
                {"channel_id": spec.target_id, "content": content},
                token=token,
            )
            msg_id = _first_report(resp, f"PostMessage p={rate} idx={idx}")
            new_message_ids.append(msg_id)
            _progress("post", idx + 1, top_level_count)

        parents = list(base_message_ids) + list(new_message_ids)
        if reply_count and not parents:
            raise RuntimeError("cannot post churn replies because no parent message IDs were available")
        for idx in range(reply_count):
            parent_id = rng.choice(parents)
            content = f"churn seed={seed} rate={rate} reply={idx}"
            resp = adapter.post(
                "/walker/PostReply",
                {"parent_message_id": parent_id, "content": content},
                token=token,
            )
            msg_id = _first_report(resp, f"PostReply p={rate} idx={idx}")
            new_message_ids.append(msg_id)
            parents.append(msg_id)
            _progress("reply", idx + 1, reply_count)
    finally:
        process.stop_process(proc)
        adapter.stop_stale_servers()
    print(f"    mutations: top_level={top_level_count} replies={reply_count}")


def _restart_storage_stack(adapter, *, wait_sec: float) -> None:
    print("    restarting full Mongo/Redis stack after mutation")
    adapter.compose_down()
    adapter.compose_up()
    time.sleep(wait_sec)
    adapter.flush_redis()


def _verify_channel_after_restart(
    adapter,
    editor: RunConfigEditor,
    spec: RequestSpec,
    paths: ChurnPaths,
    rate: int,
) -> int:
    editor.patch(
        _config_values(
            "none",
            0,
            access_log=str(paths.logs_dir / f"verify_p{rate:02d}_access.csv"),
        )
    )
    adapter.flush_redis()
    proc = None
    try:
        proc = adapter.start_server(paths.logs_dir / f"verify_p{rate:02d}.log")
        token = adapter.login()
        return _load_channel_count(adapter, spec.walker, spec.target_id, token)
    finally:
        process.stop_process(proc)
        adapter.stop_stale_servers()


def _measure_policy_trial(
    adapter,
    editor: RunConfigEditor,
    spec: RequestSpec,
    paths: ChurnPaths,
    args: argparse.Namespace,
    dump: ChurnDump,
    stale: StalePlans,
    policy: str,
    trial: int,
) -> dict[str, Any]:
    oracle_file: Path | None = None
    model_file: Path | None = None
    ttg_plan_file: Path | None = None
    runtime_policy = policy
    plan_ids: list[str] = []

    if policy == "oracle":
        oracle_file = paths.models_dir / "oracle" / f"p{dump.rate:02d}_trial{trial}.uuids"
        record = _record_access_trace(
            adapter,
            editor,
            spec,
            log_path=paths.logs_dir / f"oracle_record_p{dump.rate:02d}_trial{trial}.log",
            access_log=paths.logs_dir / f"oracle_record_p{dump.rate:02d}_trial{trial}_access.csv",
        )
        plan_ids = oracle.write_oracle_from_access_log(record["access_log"], oracle_file)
        _restore_named_dump(adapter, dump.dump_name)
    elif policy == "history":
        runtime_policy = "oracle"
        oracle_file = stale.oracle_file
        plan_ids = _read_uuid_lines(stale.oracle_file)
    elif policy == "markov":
        model_file = stale.markov_file
        plan_ids = _model_plan_ids(model_file, spec.target_id, args.limit)
    elif policy == "coaccess":
        model_file = stale.coaccess_file
        plan_ids = _model_plan_ids(model_file, spec.target_id, args.limit)
    elif policy in ("selep", "selep-adapted"):
        runtime_policy = "selep-adapted"
        model_file = stale.selep_file
        plan_ids = _model_plan_ids(model_file, spec.target_id, args.limit) if model_file is not None else []
    elif policy == "ttg":
        ttg_plan_file = paths.logs_dir / f"ttg_plan_p{dump.rate:02d}_trial{trial}.csv"
        ttg_plan_file.unlink(missing_ok=True)
    elif policy == "none":
        runtime_policy = "none"

    log_path = paths.logs_dir / (
        f"jac_server_load_channel_churn{dump.rate:02d}_policy{policy}_"
        f"limit{args.limit}_trial{trial}.log"
    )
    access_log = paths.logs_dir / (
        f"access_log_load_channel_churn{dump.rate:02d}_policy{policy}_"
        f"limit{args.limit}_trial{trial}.csv"
    )
    profile_dir = (
        paths.profiles_dir
        / f"churn_{dump.rate:02d}"
        / f"policy_{policy}"
        / f"limit_{args.limit}"
        / spec.walker
        / f"trial_{trial}"
    )
    profile_csv = profile_dir / "profile.csv"

    editor.patch(
        _config_values(
            runtime_policy,
            args.limit,
            access_log=str(access_log),
            oracle_file=str(oracle_file) if oracle_file is not None else "",
            markov_file=str(model_file) if model_file is not None and runtime_policy == "markov" else "",
            coaccess_file=str(model_file) if model_file is not None and runtime_policy == "coaccess" else "",
            selep_file=str(model_file) if model_file is not None and runtime_policy == "selep-adapted" else "",
        )
    )
    adapter.flush_redis()
    old_ttg_dump = adapter.options.env.get("JAC_PREFETCH_DUMP")
    if ttg_plan_file is not None:
        adapter.options.env["JAC_PREFETCH_DUMP"] = str(ttg_plan_file)
    else:
        adapter.options.env.pop("JAC_PREFETCH_DUMP", None)

    proc = None
    mongo_before = adapter.mongo_query_count() if adapter.options.count_mongo else ""
    try:
        proc = adapter.start_server(log_path, profile_dir=profile_dir, profile_csv=profile_csv)
        token = adapter.login()
        resp = adapter.post(spec.path, spec.body, token=token)
        payload = resp.json()
        adapter.validate_response(spec, payload)
    finally:
        process.stop_process(proc)
        adapter.stop_stale_servers()
        if old_ttg_dump is None:
            adapter.options.env.pop("JAC_PREFETCH_DUMP", None)
        else:
            adapter.options.env["JAC_PREFETCH_DUMP"] = old_ttg_dump

    _assert_profiles(profile_dir, profile_csv)
    mongo_after = adapter.mongo_query_count() if adapter.options.count_mongo else ""
    if policy == "ttg" and ttg_plan_file is not None:
        plan_ids = _read_ttg_plan_dump(ttg_plan_file)
    actual_ids = oracle.extract_uuid_order(access_log)
    quality = _quality(actual_ids, plan_ids)
    tiers = metrics.tier_counts(access_log)
    profile = metrics.profile_breakdown(profile_csv)
    mongo_q = ""
    if mongo_before and mongo_after:
        try:
            mongo_q = str(int(mongo_after) - int(mongo_before))
        except ValueError:
            mongo_q = ""

    empirical_ceiling = _pct(len(set(stale.actual_ids) & set(dump.actual_ids)), len(set(dump.actual_ids)))
    analytic_ceiling = 100.0 / (1.0 + (dump.rate / 100.0))
    return {
        "churn_rate": dump.rate,
        "churn_seed": args.seed,
        "policy": policy,
        "runtime_policy": runtime_policy,
        "walker": spec.walker,
        "prefetch_limit": args.limit,
        "trial": trial,
        "e2e_ms": f"{resp.elapsed_ms:.3f}",
        "request_id": spec.request_id,
        "base_message_count": stale.message_count,
        "added_messages": dump.added_messages,
        "post_message_count": dump.post_message_count,
        "analytic_stale_coverage": f"{analytic_ceiling:.1f}",
        "empirical_stale_coverage": f"{empirical_ceiling:.1f}",
        **quality,
        "topo_idx_ms": profile.get("topo_idx_ms", ""),
        "ttg_ms": profile.get("ttg_ms", ""),
        "prefetch_ms": profile.get("prefetch_ms", ""),
        "walker_ms": profile.get("walker_ms", ""),
        "l1_hit_rate": tiers.get("l1_hit_rate", ""),
        "l1": tiers.get("l1", ""),
        "l2": tiers.get("l2", ""),
        "l3": tiers.get("l3", ""),
        "miss": tiers.get("miss", ""),
        "mongo_q": mongo_q,
        "base_dump": args.base_dump,
        "churn_dump": dump.dump_name,
        "oracle_file": str(oracle_file) if oracle_file is not None else "",
        "model_file": str(model_file) if model_file is not None else "",
        "ttg_plan_file": str(ttg_plan_file) if ttg_plan_file is not None else "",
    }


def _record_access_trace(
    adapter,
    editor: RunConfigEditor,
    spec: RequestSpec,
    *,
    log_path: Path,
    access_log: Path,
) -> dict[str, Any]:
    editor.patch(_config_values("none", 0, access_log=str(access_log)))
    adapter.flush_redis()
    proc = None
    try:
        proc = adapter.start_server(log_path)
        token = adapter.login()
        resp = adapter.post(spec.path, spec.body, token=token)
        payload = resp.json()
        adapter.validate_response(spec, payload)
        reports = _reports(payload)
    finally:
        process.stop_process(proc)
        adapter.stop_stale_servers()
    actual_ids = oracle.extract_uuid_order(access_log)
    return {
        "access_log": access_log,
        "actual_ids": actual_ids,
        "message_ids": _message_ids(reports),
        "message_count": len(reports),
    }


def _restore_named_dump(adapter, dump_name: str) -> None:
    adapter.options.env["JACORD_DUMP"] = dump_name
    adapter.reset_storage()


def _load_channel_count(adapter, walker: str, channel_id: str, token: str) -> int:
    resp = adapter.post(f"/walker/{walker}/{channel_id}", {}, token=token)
    payload = resp.json()
    if resp.status >= 400 or payload.get("error"):
        body = resp.body.decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"{walker}({channel_id}) failed: HTTP {resp.status} {body}")
    return len(_reports(payload))


def _first_report(resp, context: str) -> str:
    payload = resp.json()
    if resp.status >= 400 or payload.get("error"):
        body = resp.body.decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"{context} failed: HTTP {resp.status} {body}")
    reports = _reports(payload)
    first = reports[0] if reports else ""
    try:
        return str(UUID(str(first)))
    except ValueError as exc:
        raise RuntimeError(f"{context} did not report a UUID: {first!r}") from exc


def _reports(payload: dict[str, Any]) -> list[Any]:
    data = payload.get("data")
    if not isinstance(data, dict):
        return []
    reports = data.get("reports")
    return reports if isinstance(reports, list) else []


def _message_ids(reports: list[Any]) -> list[str]:
    out: list[str] = []
    for report in reports:
        if not isinstance(report, dict):
            continue
        raw = report.get("id")
        if not raw:
            continue
        try:
            out.append(str(UUID(str(raw))))
        except ValueError:
            continue
    return list(dict.fromkeys(out))


def _config_values(
    policy: str,
    limit: int,
    access_log: str,
    oracle_file: str = "",
    markov_file: str = "",
    coaccess_file: str = "",
    selep_file: str = "",
) -> dict[str, object]:
    effective = "none" if policy == "none" or limit <= 0 else policy
    return {
        "access_log": access_log,
        "topology_index": True,
        "prefetching": effective,
        "prefetch_limit": int(limit),
        "prefetch_oracle_file": oracle_file,
        "prefetch_markov_file": markov_file,
        "prefetch_coaccess_file": coaccess_file,
        "prefetch_selep_file": selep_file,
    }


def _model_plan_ids(path: Path, start_id: str, limit: int) -> list[str]:
    if not path.exists() or limit <= 0:
        return []
    try:
        model = json.loads(path.read_text())
    except Exception:
        return []
    plans = model.get("plans")
    if not isinstance(plans, dict):
        return []
    keys = [_uuid_or_raw(start_id), str(start_id), "*"]
    for key in keys:
        entry = plans.get(key)
        raw_plan = entry.get("plan", []) if isinstance(entry, dict) else entry
        if isinstance(raw_plan, list):
            return _dedupe_uuid_list(raw_plan[:limit])
    return []


def _read_uuid_lines(path: Path) -> list[str]:
    if not path.exists():
        return []
    return _dedupe_uuid_list(path.read_text().splitlines())


def _read_ttg_plan_dump(path: Path) -> list[str]:
    if not path.exists():
        return []
    ids: list[str] = []
    with path.open(newline="") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames is None or "id" not in reader.fieldnames:
            return []
        for row in reader:
            ids.append(row.get("id", ""))
    return _dedupe_uuid_list(ids)


def _dedupe_uuid_list(values: list[Any]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in values:
        try:
            uid = str(UUID(str(raw).strip()))
        except ValueError:
            continue
        if uid in seen:
            continue
        seen.add(uid)
        out.append(uid)
    return out


def _quality(actual_ids: list[str], plan_ids: list[str]) -> dict[str, str]:
    actual = set(_dedupe_uuid_list(actual_ids))
    plan = set(_dedupe_uuid_list(plan_ids))
    covered = actual & plan
    overfetch = plan - actual
    undercoverage = actual - plan
    return {
        "coverage": f"{_pct(len(covered), len(actual)):.1f}",
        "accuracy": f"{_pct(len(covered), len(plan)):.1f}",
        "actual_ids": str(len(actual)),
        "plan_ids": str(len(plan)),
        "covered_ids": str(len(covered)),
        "overfetch_ids": str(len(overfetch)),
        "undercoverage_ids": str(len(undercoverage)),
    }


def _pct(num: int, den: int) -> float:
    return (num * 100.0 / den) if den else 0.0


def _assert_profiles(profile_dir: Path, profile_csv: Path) -> None:
    raw_profile = profile_dir / "jac_server.prof"
    missing = [str(p) for p in (profile_csv, raw_profile) if not p.exists()]
    if missing:
        raise RuntimeError(
            "profiling output missing after measured trial. Ensure [serve] "
            f"profile = true in jac.toml. Missing: {', '.join(missing)}"
        )


def _assert_p0_sanity(
    rows: list[dict[str, Any]],
    min_coverage: float,
    *,
    requested_policies: set[str],
) -> None:
    required = {"oracle", "history", "markov", "coaccess", "selep", "selep-adapted"} & requested_policies
    if not required:
        return
    by_policy = {str(row["policy"]): row for row in rows if int(row["trial"]) == 1}
    missing = sorted(required - set(by_policy))
    if missing:
        raise RuntimeError(f"p=0 sanity missing policy rows: {', '.join(missing)}")
    failures = []
    for policy in sorted(required):
        coverage = float(by_policy[policy]["coverage"])
        if coverage < min_coverage:
            failures.append(f"{policy}={coverage:.1f}%")
    if failures:
        raise RuntimeError(
            "p=0 same-spawn sanity failed; expected oracle-level coverage, got "
            + ", ".join(failures)
        )


def _requests_selep_policy(policies: list[str]) -> bool:
    return any(policy in ("selep", "selep-adapted") for policy in policies)


def _write_header(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as fh:
        csv.DictWriter(fh, fieldnames=CHURN_COLUMNS).writeheader()


def _append_row(path: Path, row: dict[str, Any]) -> None:
    with path.open("a", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=CHURN_COLUMNS, extrasaction="ignore")
        writer.writerow({col: row.get(col, "") for col in CHURN_COLUMNS})


def _parse_ints(raw: str | list[int] | None) -> list[int]:
    if isinstance(raw, list):
        return [int(x) for x in raw]
    if not raw:
        return []
    return [int(part) for part in str(raw).replace(",", " ").split() if part.strip()]


def _parse_words(raw: str | list[str] | None) -> list[str]:
    if isinstance(raw, list):
        return [str(x).strip().lower() for x in raw if str(x).strip()]
    if not raw:
        return []
    return [part.strip().lower() for part in str(raw).replace(",", " ").split() if part.strip()]


def _truthy(raw: str | None) -> bool:
    return str(raw or "").strip().lower() in {"1", "true", "yes", "on"}


def _uuid_or_raw(value: Any) -> str:
    try:
        return str(UUID(str(value)))
    except Exception:
        return str(value or "")


def _progress(label: str, done: int, total: int) -> None:
    if total <= 0:
        return
    interval = max(1, total // 10)
    if done == total or done % interval == 0:
        print(f"    {label}: {done}/{total}")


if __name__ == "__main__":
    raise SystemExit(main())
