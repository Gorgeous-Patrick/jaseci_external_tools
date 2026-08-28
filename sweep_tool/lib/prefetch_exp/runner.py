"""Generic prefetch policy sweep runner."""

from __future__ import annotations

import json
import random
import re
from pathlib import Path

from lib.prefetch_exp import coaccess, markov, metrics, oracle, process
from lib.prefetch_exp.adapters import make_adapter
from lib.prefetch_exp.config_edit import RunConfigEditor
from lib.prefetch_exp.models import CaseState, RequestSpec, SweepOptions, TrialResult


SUPPORTED_POLICIES = {
    "none",
    "ttg",
    "oracle",
    "markov",
    "history",
    "manual",
    "markov1-pooled",
    "coaccess",
    "coaccess-pooled",
}
MARKOV_POOLED_PREFIX = "markov1-pooled"
COACCESS_POOLED_PREFIX = "coaccess-pooled"
ACCESS_LOG_RECORDS_ALL_TIERS = True


def run_sweep(options: SweepOptions) -> None:
    adapter = make_adapter(options)
    unknown = [p for p in options.policies if not _is_supported_policy(p)]
    if unknown:
        raise ValueError(f"unknown prefetch policy/policies: {', '.join(unknown)}")

    print(f"=== Python prefetch policy sweep: {adapter.name} ===")
    print(f"app_dir : {adapter.app_dir}")
    print(f"config  : {adapter.config_path}")
    print(f"policies: {' '.join(options.policies)}")
    print(f"limits  : {' '.join(str(x) for x in options.limits)}")
    print(f"trials  : {options.trials}")
    print(f"db      : {adapter.db_summary()}")
    print(f"oracle  : mode={options.oracle_mode} dir={options.oracle_dir}")
    print(f"markov  : mode={options.markov_mode} dir={options.markov_dir}")
    print(
        "coaccess: "
        f"mode={options.coaccess_mode} dir={options.coaccess_dir} "
        f"threshold={options.coaccess_cluster_threshold:g}"
    )
    print(
        "pooled  : "
        f"train_ns={' '.join(str(x) for x in options.markov_train_ns)} "
        f"trials={options.trials} seed={options.markov_pool_seed}"
    )
    print(
        "co-pool : "
        f"train_ns={' '.join(str(x) for x in options.coaccess_train_ns)} "
        f"trials={options.trials} seed={options.coaccess_pool_seed}"
    )
    print("")

    adapter.clean_outputs()
    adapter.prepare_sweep()
    print(f"auth    : {adapter.auth_summary()}")
    results_path = adapter.app_dir / options.manifest.results_csv
    metrics.write_header(results_path)

    editor = RunConfigEditor(adapter.config_path)
    try:
        for policy in options.policies:
            if _is_markov_pooled_policy(policy):
                for train_n in _pooled_train_ns(policy, options):
                    _run_markov_pooled(adapter, editor, policy, train_n, options, results_path)
                continue
            if _is_coaccess_pooled_policy(policy):
                for train_n in _coaccess_pooled_train_ns(policy, options):
                    _run_coaccess_pooled(adapter, editor, policy, train_n, options, results_path)
                continue
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
                    result = _run_trial(
                        adapter,
                        editor,
                        state,
                        policy,
                        limit,
                        trial,
                        options,
                        trial_count=options.trials,
                    )
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


def _run_markov_pooled(
    adapter,
    editor: RunConfigEditor,
    policy: str,
    train_n: int,
    options: SweepOptions,
    results_path: Path,
) -> None:
    if options.markov_mode != "auto":
        raise ValueError("markov1-pooled requires SWEEP_MARKOV_MODE=auto")
    if train_n <= 0:
        raise ValueError(f"pooled Markov train N must be positive, got {train_n}")
    if options.trials <= 0:
        raise ValueError(f"pooled Markov trial count must be positive, got {options.trials}")

    limits = _limits_for_policy("markov", options.limits)
    label = f"{MARKOV_POOLED_PREFIX}-N{train_n}"
    setup_limit = max(limits) if limits else 0

    print("")
    print("========================================")
    print(f"Case: policy={label} pooled_train={train_n} trials={options.trials}")
    print("========================================")

    editor.patch(_config_values("none", 0, access_log=""))
    state = adapter.prepare_case(label, setup_limit)
    if state.request is None:
        raise RuntimeError(f"{adapter.name} did not prepare a request")

    trial_spec = _require_request(state)
    trial_id = _request_id(trial_spec)
    pool = [
        spec
        for spec in _unique_spawn_pool(adapter.spawn_pool(state))
        if _request_id(spec) != trial_id
    ]
    required = train_n
    if len(pool) < required:
        raise RuntimeError(
            f"{adapter.name} exposes {len(pool)} pooled spawn request(s), "
            f"but markov1-pooled-N{train_n} needs N={required} training request(s) "
            f"after excluding measured request {trial_id}. "
            "Expose more seeded spawn targets for this adapter or lower "
            "SWEEP_MARKOV_TRAIN_NS."
        )

    rng = random.Random(options.markov_pool_seed)
    sample = list(pool)
    rng.shuffle(sample)
    train_specs = sample[:train_n]
    train_ids = [_request_id(spec) for spec in train_specs]
    metadata = {
        "policy": label,
        "runtime_policy": "markov",
        "app": adapter.name,
        "seed": options.markov_pool_seed,
        "train_n": train_n,
        "trial_count": options.trials,
        "trial_request_id": trial_id,
        "pool_size": len(pool),
        "limits": limits,
        "training_request_ids": train_ids,
        "trial_request_ids": [trial_id],
        "access_log_records_all_tiers": ACCESS_LOG_RECORDS_ALL_TIERS,
        "training_skips_cold_start_protocol": ACCESS_LOG_RECORDS_ALL_TIERS,
    }
    metadata_path = markov.pooled_metadata_path(
        options.markov_dir,
        adapter.name,
        state.request.walker,
        label,
        options.markov_pool_seed,
    )
    metadata_path = _app_path(adapter, metadata_path)
    markov.write_pooled_metadata(metadata_path, metadata)
    print(
        f"    pooled split: seed={options.markov_pool_seed} pool={len(pool)} "
        f"trial_request={trial_id} metadata={metadata_path}"
    )

    training_logs: list[Path] = []
    for idx, spec in enumerate(train_specs, start=1):
        access_log = _collect_markov_training_trace(adapter, editor, state, spec, label, idx)
        training_logs.append(access_log)
        print(
            f"    train {idx}/{train_n}: request={_request_id(spec)} "
            f"first_touch={len(markov.extract_first_touch_sequence(access_log))}"
        )

    for limit in limits:
        print("")
        print("----------------------------------------")
        print(f"Trial case: policy={label} prefetch_limit={limit}")
        print("----------------------------------------")
        model_path = markov.pooled_markov_model_path(
            options.markov_dir,
            adapter.name,
            state.request.walker,
            label,
            limit,
            options.markov_pool_seed,
        )
        model_path = _app_path(adapter, model_path)
        model = markov.write_pooled_markov_model_from_access_logs(
            training_logs,
            model_path,
            app_name=adapter.name,
            walker=state.request.walker,
            label=label,
            limit=limit,
            seed=options.markov_pool_seed,
            training_request_ids=train_ids,
            trial_request_ids=[trial_id],
            trial_count=options.trials,
            plan_start_ids=[trial_spec.target_id],
        )
        model_train_ids = set(_model_training_ids(model))
        leak = [rid for rid in [trial_id] if rid in model_train_ids]
        if leak:
            raise RuntimeError(
                "pooled Markov leakage guard failed; measured request ID(s) "
                f"present in model training metadata: {', '.join(leak)}"
            )
        print(
            f"    pooled model: distinct={len(model.get('fallback_order', []))} "
            f"plan={model.get('plan_len', 0)} file={model_path}"
        )

        results: list[TrialResult] = []
        for trial in range(1, options.trials + 1):
            result = _run_trial(
                adapter,
                editor,
                state,
                "markov",
                limit,
                trial,
                options,
                spec_override=trial_spec,
                result_policy=label,
                effective_policy_override="markov",
                model_file_override=model_path,
                request_id=trial_id,
                train_n=train_n,
                trial_count=options.trials,
                pool_seed=options.markov_pool_seed,
            )
            metrics.append_result(results_path, result.__dict__)
            results.append(result)
            print(
                f"  Trial {trial}: request={result.request_id} limit={limit} "
                f"{result.e2e_ms:.3f}ms coverage={result.coverage or '?'} "
                f"accuracy={result.accuracy or '?'} L1={result.l1 or '?'} L3={result.l3 or '?'}"
            )
        print(f"    coverage: {_rate_summary(results, 'coverage')}")
        print(f"    accuracy: {_rate_summary(results, 'accuracy')}")


def _run_coaccess_pooled(
    adapter,
    editor: RunConfigEditor,
    policy: str,
    train_n: int,
    options: SweepOptions,
    results_path: Path,
) -> None:
    if options.coaccess_mode != "auto":
        raise ValueError("coaccess-pooled requires SWEEP_COACCESS_MODE=auto")
    if train_n <= 0:
        raise ValueError(f"pooled co-access train N must be positive, got {train_n}")
    if options.trials <= 0:
        raise ValueError(f"pooled co-access trial count must be positive, got {options.trials}")

    limits = _limits_for_policy("coaccess", options.limits)
    label = f"{COACCESS_POOLED_PREFIX}-N{train_n}"
    setup_limit = max(limits) if limits else 0

    print("")
    print("========================================")
    print(f"Case: policy={label} pooled_train={train_n} trials={options.trials}")
    print("========================================")

    editor.patch(_config_values("none", 0, access_log=""))
    state = adapter.prepare_case(label, setup_limit)
    if state.request is None:
        raise RuntimeError(f"{adapter.name} did not prepare a request")

    trial_spec = _require_request(state)
    trial_id = _request_id(trial_spec)
    pool = [
        spec
        for spec in _unique_spawn_pool(adapter.spawn_pool(state))
        if _request_id(spec) != trial_id
    ]
    required = train_n
    if len(pool) < required:
        raise RuntimeError(
            f"{adapter.name} exposes {len(pool)} pooled spawn request(s), "
            f"but coaccess-pooled-N{train_n} needs N={required} training request(s) "
            f"after excluding measured request {trial_id}. "
            "Expose more seeded spawn targets for this adapter or lower "
            "SWEEP_COACCESS_TRAIN_NS."
        )

    rng = random.Random(options.coaccess_pool_seed)
    sample = list(pool)
    rng.shuffle(sample)
    train_specs = sample[:train_n]
    train_ids = [_request_id(spec) for spec in train_specs]
    metadata = {
        "policy": label,
        "runtime_policy": "coaccess",
        "app": adapter.name,
        "seed": options.coaccess_pool_seed,
        "train_n": train_n,
        "trial_count": options.trials,
        "trial_request_id": trial_id,
        "pool_size": len(pool),
        "limits": limits,
        "training_request_ids": train_ids,
        "trial_request_ids": [trial_id],
        "cluster_threshold": options.coaccess_cluster_threshold,
        "access_log_records_all_tiers": ACCESS_LOG_RECORDS_ALL_TIERS,
        "training_skips_cold_start_protocol": ACCESS_LOG_RECORDS_ALL_TIERS,
    }
    metadata_path = coaccess.pooled_metadata_path(
        options.coaccess_dir,
        adapter.name,
        state.request.walker,
        label,
        options.coaccess_pool_seed,
    )
    metadata_path = _app_path(adapter, metadata_path)
    coaccess.write_pooled_metadata(metadata_path, metadata)
    print(
        "    pooled split: "
        f"seed={options.coaccess_pool_seed} pool={len(pool)} "
        f"trial_request={trial_id} metadata={metadata_path}"
    )

    training_logs: list[Path] = []
    for idx, spec in enumerate(train_specs, start=1):
        access_log = _collect_coaccess_training_trace(adapter, editor, state, spec, label, idx)
        training_logs.append(access_log)
        print(
            f"    train {idx}/{train_n}: request={_request_id(spec)} "
            f"first_touch={len(coaccess.extract_first_touch_sequence(access_log))}"
        )

    for limit in limits:
        print("")
        print("----------------------------------------")
        print(f"Trial case: policy={label} prefetch_limit={limit}")
        print("----------------------------------------")
        model_path = coaccess.pooled_coaccess_model_path(
            options.coaccess_dir,
            adapter.name,
            state.request.walker,
            label,
            limit,
            options.coaccess_pool_seed,
        )
        model_path = _app_path(adapter, model_path)
        model = coaccess.write_pooled_coaccess_model_from_access_logs(
            training_logs,
            model_path,
            app_name=adapter.name,
            walker=state.request.walker,
            label=label,
            limit=limit,
            seed=options.coaccess_pool_seed,
            training_request_ids=train_ids,
            trial_request_ids=[trial_id],
            trial_count=options.trials,
            plan_start_ids=[trial_spec.target_id],
            cluster_threshold=options.coaccess_cluster_threshold,
        )
        model_train_ids = set(_model_training_ids(model))
        leak = [rid for rid in [trial_id] if rid in model_train_ids]
        if leak:
            raise RuntimeError(
                "pooled co-access leakage guard failed; measured request ID(s) "
                f"present in model training metadata: {', '.join(leak)}"
            )
        print(
            f"    pooled model: clusters={model.get('cluster_count', 0)} "
            f"distinct={len(model.get('fallback_order', []))} "
            f"plan={model.get('plan_len', 0)} file={model_path}"
        )

        results: list[TrialResult] = []
        for trial in range(1, options.trials + 1):
            result = _run_trial(
                adapter,
                editor,
                state,
                "coaccess",
                limit,
                trial,
                options,
                spec_override=trial_spec,
                result_policy=label,
                effective_policy_override="coaccess",
                model_file_override=model_path,
                request_id=trial_id,
                train_n=train_n,
                trial_count=options.trials,
                pool_seed=options.coaccess_pool_seed,
            )
            metrics.append_result(results_path, result.__dict__)
            results.append(result)
            print(
                f"  Trial {trial}: request={result.request_id} limit={limit} "
                f"{result.e2e_ms:.3f}ms coverage={result.coverage or '?'} "
                f"accuracy={result.accuracy or '?'} L1={result.l1 or '?'} L3={result.l3 or '?'}"
            )
        print(f"    coverage: {_rate_summary(results, 'coverage')}")
        print(f"    accuracy: {_rate_summary(results, 'accuracy')}")


def _collect_markov_training_trace(
    adapter,
    editor: RunConfigEditor,
    state: CaseState,
    spec: RequestSpec,
    label: str,
    train_idx: int,
) -> Path:
    logs_dir = adapter.app_dir / adapter.options.manifest.logs_dir
    safe_walker = _safe(spec.walker)
    safe_label = _safe(label)
    safe_request = _safe(_request_id(spec))[:80]
    record_log = logs_dir / f"markov_pooled_train_{safe_walker}_{safe_label}_{train_idx}_{safe_request}.log"
    record_access_log = logs_dir / f"markov_pooled_train_access_{safe_walker}_{safe_label}_{train_idx}_{safe_request}.csv"
    editor.patch(
        _config_values(
            "none",
            0,
            access_log=str(record_access_log),
            oracle_file="",
            markov_file="",
        )
    )
    proc = None
    try:
        proc = adapter.start_server(record_log)
        resp = adapter.post(spec.path, spec.body, token=spec.token or state.token)
        adapter.validate_response(spec, resp.json())
    finally:
        process.stop_process(proc)
        adapter.stop_stale_servers()
    return record_access_log


def _collect_coaccess_training_trace(
    adapter,
    editor: RunConfigEditor,
    state: CaseState,
    spec: RequestSpec,
    label: str,
    train_idx: int,
) -> Path:
    logs_dir = adapter.app_dir / adapter.options.manifest.logs_dir
    safe_walker = _safe(spec.walker)
    safe_label = _safe(label)
    safe_request = _safe(_request_id(spec))[:80]
    record_log = logs_dir / f"coaccess_pooled_train_{safe_walker}_{safe_label}_{train_idx}_{safe_request}.log"
    record_access_log = logs_dir / f"coaccess_pooled_train_access_{safe_walker}_{safe_label}_{train_idx}_{safe_request}.csv"
    editor.patch(
        _config_values(
            "none",
            0,
            access_log=str(record_access_log),
            oracle_file="",
            markov_file="",
            coaccess_file="",
        )
    )
    proc = None
    try:
        proc = adapter.start_server(record_log)
        resp = adapter.post(spec.path, spec.body, token=spec.token or state.token)
        adapter.validate_response(spec, resp.json())
    finally:
        process.stop_process(proc)
        adapter.stop_stale_servers()
    return record_access_log


def _run_trial(
    adapter,
    editor: RunConfigEditor,
    state: CaseState,
    policy: str,
    limit: int,
    trial: int,
    options: SweepOptions,
    *,
    spec_override: RequestSpec | None = None,
    result_policy: str = "",
    effective_policy_override: str = "",
    model_file_override: Path | None = None,
    request_id: str = "",
    train_n: int | None = None,
    trial_count: int | None = None,
    pool_seed: int | None = None,
) -> TrialResult:
    spec = spec_override or _require_request(state)
    oracle_file: Path | None = None
    model_file: Path | None = None
    if model_file_override is not None:
        model_file = model_file_override
        effective_policy = effective_policy_override or "markov"
    elif policy == "oracle":
        oracle_file = _oracle_for_trial(adapter, editor, state, spec, limit, trial, options)
        effective_policy = "oracle"
    elif policy == "markov":
        model_file = _markov_for_trial(adapter, editor, state, spec, limit, trial, options)
        effective_policy = "markov"
    elif policy == "coaccess":
        model_file = _coaccess_for_trial(adapter, editor, state, spec, limit, trial, options)
        effective_policy = "coaccess"
    else:
        effective_policy = policy

    output_policy = result_policy or policy
    log_path, access_log, profile_dir, profile_csv = _trial_paths(adapter, spec, output_policy, limit, trial)
    editor.patch(
        _config_values(
            effective_policy,
            limit,
            access_log=str(access_log),
            oracle_file=str(oracle_file) if oracle_file is not None else "",
            markov_file=str(model_file) if model_file is not None and effective_policy == "markov" else "",
            coaccess_file=str(model_file) if model_file is not None and effective_policy == "coaccess" else "",
        )
    )
    adapter.clear_runtime_cache()

    proc = None
    db_before = _db_query_count(adapter) if options.count_db else ""
    try:
        proc = adapter.start_server(log_path, profile_dir=profile_dir, profile_csv=profile_csv)
        resp = adapter.post(spec.path, spec.body, token=spec.token or state.token)
        payload = resp.json()
        adapter.validate_response(spec, payload)
    finally:
        process.stop_process(proc)
        adapter.stop_stale_servers()

    _assert_trial_profiles(profile_dir, profile_csv)
    db_after = _db_query_count(adapter) if options.count_db else ""
    counts = metrics.tier_counts(access_log)
    profile = metrics.profile_breakdown(profile_csv)
    if model_file and effective_policy == "coaccess":
        quality = coaccess.plan_quality(model_file, spec.target_id, access_log, limit)
    elif model_file:
        quality = markov.plan_quality(model_file, spec.target_id, access_log, limit)
    else:
        quality = {}
    db_q = ""
    if db_before != "" and db_after != "":
        try:
            db_q = str(int(db_after) - int(db_before))
        except ValueError:
            db_q = ""

    return TrialResult(
        policy=output_policy,
        walker=spec.walker,
        prefetch_limit=limit,
        trial=trial,
        e2e_ms=resp.elapsed_ms,
        request_id=request_id or _request_id(spec),
        train_n=str(train_n) if train_n is not None else "",
        trial_count=str(trial_count) if trial_count is not None else "",
        pool_seed=str(pool_seed) if pool_seed is not None else "",
        coverage=quality.get("coverage", ""),
        accuracy=quality.get("accuracy", ""),
        actual_ids=quality.get("actual_ids", ""),
        plan_ids=quality.get("plan_ids", ""),
        covered_ids=quality.get("covered_ids", ""),
        overfetch_ids=quality.get("overfetch_ids", ""),
        undercoverage_ids=quality.get("undercoverage_ids", ""),
        topo_idx_ms=profile.get("topo_idx_ms", ""),
        ttg_ms=profile.get("ttg_ms", ""),
        prefetch_ms=profile.get("prefetch_ms", ""),
        walker_ms=profile.get("walker_ms", ""),
        l1_hit_rate=counts.get("l1_hit_rate", ""),
        l1=counts.get("l1", ""),
        l2=counts.get("l2", ""),
        l3=counts.get("l3", ""),
        miss=counts.get("miss", ""),
        db_q=db_q,
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
    adapter.clear_runtime_cache()
    proc = None
    try:
        proc = adapter.start_server(record_log)
        resp = adapter.post(spec.path, spec.body, token=spec.token or state.token)
        adapter.validate_response(spec, resp.json())
    finally:
        process.stop_process(proc)
        adapter.stop_stale_servers()
    ids = oracle.write_oracle_from_access_log(record_access_log, output_path)
    print(f"    oracle record: wrote {len(ids)} UUID(s) to {output_path}")
    adapter.clear_runtime_cache()
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
    adapter.clear_runtime_cache()
    proc = None
    try:
        proc = adapter.start_server(record_log)
        resp = adapter.post(spec.path, spec.body, token=spec.token or state.token)
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
    adapter.clear_runtime_cache()
    return output_path


def _coaccess_for_trial(
    adapter,
    editor: RunConfigEditor,
    state: CaseState,
    spec: RequestSpec,
    limit: int,
    trial: int,
    options: SweepOptions,
) -> Path:
    explicit = options.env.get("SWEEP_COACCESS_FILE") or options.env.get("JAC_PREFETCH_COACCESS_FILE")
    if options.coaccess_mode == "file":
        path = Path(explicit) if explicit else coaccess.coaccess_model_path(
            options.coaccess_dir, adapter.name, spec.walker, spec.target_id, limit, trial
        )
        path = path if path.is_absolute() else adapter.app_dir / path
        if not path.exists():
            raise FileNotFoundError(f"co-access model file does not exist: {path}")
        return path
    if options.coaccess_mode != "auto":
        raise ValueError(f"unsupported SWEEP_COACCESS_MODE={options.coaccess_mode!r}")

    output_path = Path(explicit) if explicit else coaccess.coaccess_model_path(
        options.coaccess_dir, adapter.name, spec.walker, spec.target_id, limit, trial
    )
    output_path = output_path if output_path.is_absolute() else adapter.app_dir / output_path

    logs_dir = adapter.app_dir / adapter.options.manifest.logs_dir
    safe_walker = _safe(spec.walker)
    record_log = logs_dir / f"coaccess_train_{safe_walker}_limit{limit}_trial{trial}.log"
    record_access_log = logs_dir / f"coaccess_train_access_{safe_walker}_limit{limit}_trial{trial}.csv"
    editor.patch(
        _config_values(
            "none",
            0,
            access_log=str(record_access_log),
            oracle_file="",
            markov_file="",
            coaccess_file="",
        )
    )
    adapter.clear_runtime_cache()
    proc = None
    try:
        proc = adapter.start_server(record_log)
        resp = adapter.post(spec.path, spec.body, token=spec.token or state.token)
        adapter.validate_response(spec, resp.json())
    finally:
        process.stop_process(proc)
        adapter.stop_stale_servers()
    model = coaccess.write_coaccess_model_from_access_log(
        record_access_log,
        output_path,
        app_name=adapter.name,
        walker=spec.walker,
        target_id=spec.target_id,
        start_id=spec.target_id,
        limit=limit,
        cluster_threshold=options.coaccess_cluster_threshold,
    )
    print(
        "    coaccess train: wrote "
        f"{model.get('distinct_ids', 0)} distinct UUID(s), "
        f"clusters={len(model.get('clusters', []))} "
        f"plan={model.get('plan_len', 0)} "
        f"to {output_path}"
    )
    adapter.clear_runtime_cache()
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


def _assert_trial_profiles(profile_dir: Path, profile_csv: Path) -> None:
    missing = []
    raw_profile = profile_dir / "jac_server.prof"
    if not profile_csv.exists():
        missing.append(str(profile_csv))
    if not raw_profile.exists():
        missing.append(str(raw_profile))
    if missing:
        raise RuntimeError(
            "profiling output missing after measured trial. "
            "Ensure the active Jac config has [serve] profile = true. "
            f"Missing: {', '.join(missing)}"
        )


def _config_values(
    policy: str,
    limit: int,
    access_log: str,
    oracle_file: str = "",
    markov_file: str = "",
    coaccess_file: str = "",
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
    }


def _limits_for_policy(policy: str, limits: list[int]) -> list[int]:
    if policy == "none":
        return [0]
    positive = [x for x in limits if x > 0]
    return positive or [0]


def _app_path(adapter, path: Path) -> Path:
    return path if path.is_absolute() else adapter.app_dir / path


def _is_supported_policy(policy: str) -> bool:
    return (
        policy in SUPPORTED_POLICIES
        or _is_markov_pooled_policy(policy)
        or _is_coaccess_pooled_policy(policy)
    )


def _is_markov_pooled_policy(policy: str) -> bool:
    return policy == MARKOV_POOLED_PREFIX or re.fullmatch(
        rf"{MARKOV_POOLED_PREFIX}-n\d+", policy, flags=re.IGNORECASE
    ) is not None


def _is_coaccess_pooled_policy(policy: str) -> bool:
    return policy == COACCESS_POOLED_PREFIX or re.fullmatch(
        rf"{COACCESS_POOLED_PREFIX}-n\d+", policy, flags=re.IGNORECASE
    ) is not None


def _pooled_train_ns(policy: str, options: SweepOptions) -> list[int]:
    match = re.fullmatch(rf"{MARKOV_POOLED_PREFIX}-n(\d+)", policy, flags=re.IGNORECASE)
    if match:
        return [int(match.group(1))]
    return list(options.markov_train_ns)


def _coaccess_pooled_train_ns(policy: str, options: SweepOptions) -> list[int]:
    match = re.fullmatch(rf"{COACCESS_POOLED_PREFIX}-n(\d+)", policy, flags=re.IGNORECASE)
    if match:
        return [int(match.group(1))]
    return list(options.coaccess_train_ns)


def _unique_spawn_pool(pool: list[RequestSpec]) -> list[RequestSpec]:
    out: list[RequestSpec] = []
    seen: set[str] = set()
    for spec in pool:
        request_id = _request_id(spec)
        if request_id in seen:
            continue
        seen.add(request_id)
        out.append(spec)
    return out


def _request_id(spec: RequestSpec) -> str:
    if spec.request_id:
        return str(spec.request_id)
    if spec.target_id:
        return str(spec.target_id)
    return f"{spec.walker}:{spec.path}:{json.dumps(spec.body, sort_keys=True)}"


def _model_training_ids(model: dict[str, object]) -> list[str]:
    metadata = model.get("metadata")
    if not isinstance(metadata, dict):
        return []
    ids = metadata.get("training_request_ids", [])
    if not isinstance(ids, list):
        return []
    return [str(rid) for rid in ids]


def _rate_summary(results: list[TrialResult], attr: str) -> str:
    vals: list[float] = []
    for result in results:
        raw = getattr(result, attr, "")
        if raw == "":
            continue
        try:
            vals.append(float(raw))
        except ValueError:
            continue
    if not vals:
        return "n/a"
    mean = sum(vals) / len(vals)
    return f"mean={mean:.1f} range={min(vals):.1f}..{max(vals):.1f}"


def _db_query_count(adapter) -> str:
    return adapter.db_query_count()


def _require_request(state: CaseState) -> RequestSpec:
    if state.request is None:
        raise RuntimeError("case has no prepared request")
    return state.request


def _safe(raw: str) -> str:
    return "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in raw) or "default"
