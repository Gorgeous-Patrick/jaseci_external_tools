"""Generic prefetch policy sweep runner."""

from __future__ import annotations

import subprocess
from pathlib import Path

from lib.prefetch_exp import markov, metrics, oracle, process
from lib.prefetch_exp.adapters import make_adapter
from lib.prefetch_exp.config_edit import RunConfigEditor
from lib.prefetch_exp.models import CaseState, RequestSpec, SweepOptions, TrialResult


SUPPORTED_POLICIES = {"none", "ttg", "oracle", "markov", "history", "manual"}


def run_sweep(options: SweepOptions) -> None:
    adapter = make_adapter(options)
    unknown = [p for p in options.policies if p not in SUPPORTED_POLICIES]
    if unknown:
        raise ValueError(f"unknown prefetch policy/policies: {', '.join(unknown)}")

    print(f"=== Python prefetch policy sweep: {adapter.name} ===")
    print(f"app_dir : {adapter.app_dir}")
    print(f"config  : {adapter.config_path}")
    print(f"policies: {' '.join(options.policies)}")
    print(f"limits  : {' '.join(str(x) for x in options.limits)}")
    print(f"trials  : {options.trials}")
    print(f"oracle  : mode={options.oracle_mode} dir={options.oracle_dir}")
    print(f"markov  : mode={options.markov_mode} dir={options.markov_dir}")
    print("")

    adapter.clean_outputs()
    adapter.prepare_sweep()
    print(f"auth    : {adapter.auth_summary()}")
    results_path = adapter.app_dir / options.manifest.results_csv
    metrics.write_header(results_path)

    editor = RunConfigEditor(adapter.config_path)
    try:
        for policy in options.policies:
            if policy == "history":
                print(
                    "warning: history policy is in-process; this cold-restart "
                    "runner records the structural baseline but does not warm "
                    "history across server restarts."
                )
            for limit in _limits_for_policy(policy, options.limits):
                print("")
                print("========================================")
                print(f"Case: policy={policy} prefetch_limit={limit}")
                print("========================================")
                editor.patch(_config_values("none", 0, access_log=""))
                state = adapter.prepare_case(policy, limit)
                if state.request is None:
                    raise RuntimeError(f"{adapter.name} did not prepare a request")
                for trial in range(1, options.trials + 1):
                    result = _run_trial(adapter, editor, state, policy, limit, trial, options)
                    metrics.append_result(results_path, result.__dict__)
                    print(
                        f"  Trial {trial}: policy={policy} limit={limit} "
                        f"{result.e2e_ms:.3f}ms L1={result.l1 or '?'} "
                        f"L2={result.l2 or '?'} L3={result.l3 or '?'}"
                    )
    finally:
        editor.restore()
        adapter.stop_stale_servers()

    print("")
    print("========================================")
    print("Sweep complete")
    print(f"Results saved to: {results_path}")
    print("========================================")
    print(results_path.read_text())


def _run_trial(
    adapter,
    editor: RunConfigEditor,
    state: CaseState,
    policy: str,
    limit: int,
    trial: int,
    options: SweepOptions,
) -> TrialResult:
    spec = _require_request(state)
    oracle_file: Path | None = None
    model_file: Path | None = None
    if policy == "oracle":
        oracle_file = _oracle_for_trial(adapter, editor, state, spec, limit, trial, options)
        effective_policy = "oracle"
    elif policy == "markov":
        model_file = _markov_for_trial(adapter, editor, state, spec, limit, trial, options)
        effective_policy = "markov"
    else:
        effective_policy = policy

    log_path, access_log, profile_dir, profile_csv = _trial_paths(adapter, spec, effective_policy, limit, trial)
    editor.patch(
        _config_values(
            effective_policy,
            limit,
            access_log=str(access_log),
            oracle_file=str(oracle_file) if oracle_file is not None else "",
            markov_file=str(model_file) if model_file is not None else "",
        )
    )
    adapter.flush_redis()

    proc = None
    mongo_before = _mongo_query_count(adapter) if options.count_mongo else ""
    try:
        proc = adapter.start_server(log_path, profile_dir=profile_dir, profile_csv=profile_csv)
        resp = adapter.post(spec.path, spec.body, token=state.token)
        payload = resp.json()
        adapter.validate_response(spec, payload)
    finally:
        process.stop_process(proc)
        adapter.stop_stale_servers()

    mongo_after = _mongo_query_count(adapter) if options.count_mongo else ""
    counts = metrics.tier_counts(access_log)
    profile = metrics.profile_breakdown(profile_csv)
    mongo_q = ""
    if mongo_before != "" and mongo_after != "":
        try:
            mongo_q = str(int(mongo_after) - int(mongo_before))
        except ValueError:
            mongo_q = ""

    return TrialResult(
        policy=policy,
        walker=spec.walker,
        prefetch_limit=limit,
        trial=trial,
        e2e_ms=resp.elapsed_ms,
        topo_idx_ms=profile.get("topo_idx_ms", ""),
        ttg_ms=profile.get("ttg_ms", ""),
        prefetch_ms=profile.get("prefetch_ms", ""),
        walker_ms=profile.get("walker_ms", ""),
        l1_hit_rate=counts.get("l1_hit_rate", ""),
        l1=counts.get("l1", ""),
        l2=counts.get("l2", ""),
        l3=counts.get("l3", ""),
        miss=counts.get("miss", ""),
        mongo_q=mongo_q,
        oracle_file=str(oracle_file) if oracle_file is not None else "",
        model_file=str(model_file) if model_file is not None else "",
    )


def _oracle_for_trial(
    adapter,
    editor: RunConfigEditor,
    state: CaseState,
    spec: RequestSpec,
    limit: int,
    trial: int,
    options: SweepOptions,
) -> Path:
    explicit = options.env.get("SWEEP_ORACLE_FILE") or options.env.get("JAC_PREFETCH_ORACLE_FILE")
    if options.oracle_mode == "file":
        path = Path(explicit) if explicit else oracle.oracle_file_path(
            options.oracle_dir, adapter.name, spec.walker, spec.target_id, limit, trial
        )
        path = path if path.is_absolute() else adapter.app_dir / path
        if not path.exists():
            raise FileNotFoundError(f"oracle file does not exist: {path}")
        return path
    if options.oracle_mode != "auto":
        raise ValueError(f"unsupported SWEEP_ORACLE_MODE={options.oracle_mode!r}")

    output_path = Path(explicit) if explicit else oracle.oracle_file_path(
        options.oracle_dir, adapter.name, spec.walker, spec.target_id, limit, trial
    )
    output_path = output_path if output_path.is_absolute() else adapter.app_dir / output_path

    logs_dir = adapter.app_dir / adapter.options.manifest.logs_dir
    safe_walker = _safe(spec.walker)
    record_log = logs_dir / f"oracle_record_{safe_walker}_limit{limit}_trial{trial}.log"
    record_access_log = logs_dir / f"oracle_record_access_{safe_walker}_limit{limit}_trial{trial}.csv"
    editor.patch(
        _config_values(
            "none",
            0,
            access_log=str(record_access_log),
            oracle_file="",
            markov_file="",
        )
    )
    adapter.flush_redis()
    proc = None
    try:
        proc = adapter.start_server(record_log)
        resp = adapter.post(spec.path, spec.body, token=state.token)
        adapter.validate_response(spec, resp.json())
    finally:
        process.stop_process(proc)
        adapter.stop_stale_servers()
    ids = oracle.write_oracle_from_access_log(record_access_log, output_path)
    print(f"    oracle record: wrote {len(ids)} UUID(s) to {output_path}")
    adapter.flush_redis()
    return output_path


def _markov_for_trial(
    adapter,
    editor: RunConfigEditor,
    state: CaseState,
    spec: RequestSpec,
    limit: int,
    trial: int,
    options: SweepOptions,
) -> Path:
    explicit = options.env.get("SWEEP_MARKOV_FILE") or options.env.get("JAC_PREFETCH_MARKOV_FILE")
    if options.markov_mode == "file":
        path = Path(explicit) if explicit else markov.markov_model_path(
            options.markov_dir, adapter.name, spec.walker, spec.target_id, limit, trial
        )
        path = path if path.is_absolute() else adapter.app_dir / path
        if not path.exists():
            raise FileNotFoundError(f"markov model file does not exist: {path}")
        return path
    if options.markov_mode != "auto":
        raise ValueError(f"unsupported SWEEP_MARKOV_MODE={options.markov_mode!r}")

    output_path = Path(explicit) if explicit else markov.markov_model_path(
        options.markov_dir, adapter.name, spec.walker, spec.target_id, limit, trial
    )
    output_path = output_path if output_path.is_absolute() else adapter.app_dir / output_path

    logs_dir = adapter.app_dir / adapter.options.manifest.logs_dir
    safe_walker = _safe(spec.walker)
    record_log = logs_dir / f"markov_train_{safe_walker}_limit{limit}_trial{trial}.log"
    record_access_log = logs_dir / f"markov_train_access_{safe_walker}_limit{limit}_trial{trial}.csv"
    editor.patch(
        _config_values(
            "none",
            0,
            access_log=str(record_access_log),
            oracle_file="",
            markov_file="",
        )
    )
    adapter.flush_redis()
    proc = None
    try:
        proc = adapter.start_server(record_log)
        resp = adapter.post(spec.path, spec.body, token=state.token)
        adapter.validate_response(spec, resp.json())
    finally:
        process.stop_process(proc)
        adapter.stop_stale_servers()
    model = markov.write_markov_model_from_access_log(
        record_access_log,
        output_path,
        app_name=adapter.name,
        walker=spec.walker,
        target_id=spec.target_id,
        start_id=spec.target_id,
        limit=limit,
    )
    print(
        "    markov train: wrote "
        f"{model.get('distinct_ids', 0)} distinct UUID(s), "
        f"plan={len(model.get('plans', {}).get(model.get('start_id', ''), {}).get('plan', []))} "
        f"to {output_path}"
    )
    adapter.flush_redis()
    return output_path


def _trial_paths(adapter, spec: RequestSpec, policy: str, limit: int, trial: int):
    logs_dir = adapter.app_dir / adapter.options.manifest.logs_dir
    profiles_dir = adapter.app_dir / adapter.options.manifest.profiles_dir
    safe_walker = _safe(spec.walker)
    safe_policy = _safe(policy)
    log_path = logs_dir / f"jac_server_{safe_walker}_policy{safe_policy}_limit{limit}_trial{trial}.log"
    access_log = logs_dir / f"access_log_{safe_walker}_policy{safe_policy}_limit{limit}_trial{trial}.csv"
    profile_dir = profiles_dir / f"policy_{safe_policy}" / f"limit_{limit}" / safe_walker / f"trial_{trial}"
    profile_csv = profile_dir / "profile.csv"
    return log_path, access_log, profile_dir, profile_csv


def _config_values(
    policy: str,
    limit: int,
    access_log: str,
    oracle_file: str = "",
    markov_file: str = "",
) -> dict[str, object]:
    effective = "none" if policy == "none" or limit <= 0 else policy
    return {
        "access_log": access_log,
        "topology_index": True,
        "prefetching": effective,
        "prefetch_limit": int(limit),
        "prefetch_oracle_file": oracle_file,
        "prefetch_markov_file": markov_file,
    }


def _limits_for_policy(policy: str, limits: list[int]) -> list[int]:
    if policy == "none":
        return [0]
    positive = [x for x in limits if x > 0]
    return positive or [0]


def _mongo_query_count(adapter) -> str:
    try:
        proc = subprocess.run(
            [
                "docker",
                "exec",
                adapter.mongo_container,
                "mongosh",
                "jac_db",
                "--quiet",
                "--eval",
                "print(Number(db.serverStatus().opcounters.query))",
            ],
            cwd=str(adapter.app_dir),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        return proc.stdout.strip().splitlines()[-1]
    except Exception:
        return ""


def _require_request(state: CaseState) -> RequestSpec:
    if state.request is None:
        raise RuntimeError("case has no prepared request")
    return state.request


def _safe(raw: str) -> str:
    return "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in raw) or "default"
