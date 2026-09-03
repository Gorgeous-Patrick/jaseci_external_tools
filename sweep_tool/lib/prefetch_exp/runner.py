"""Generic prefetch policy sweep runner."""

from __future__ import annotations

import json
import random
import re
import time
from pathlib import Path

from lib.prefetch_exp import coaccess, markov, metrics, oracle, process, selep
from lib.prefetch_exp.adapters import make_adapter
from lib.prefetch_exp.config_edit import RunConfigEditor
from lib.prefetch_exp.models import CaseState, RequestSpec, SweepOptions, TrialResult


SUPPORTED_POLICIES = {
    "none",
    "ttg",
    "oracle",
    "capre",
    "markov",
    "history",
    "manual",
    "selep",
    "markov1-pooled",
    "coaccess",
    "coaccess-pooled",
    "random-paired",
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
    print(
        "random : "
        f"n={options.random_n} train_k={options.random_train_k} "
        f"seed={options.random_seed} "
        f"policies={' '.join(options.random_policies)}"
    )
    print(f"selep   : {selep.describe(options)}")
    print("")

    adapter.clean_outputs()
    adapter.prepare_sweep()
    print(f"auth    : {adapter.auth_summary()}")
    results_path = adapter.app_dir / options.manifest.results_csv
    metrics.write_header(results_path)

    editor = RunConfigEditor(adapter.config_path)
    try:
        for policy in options.policies:
            if policy == "random-paired":
                _run_random_paired(adapter, editor, options, results_path)
                continue
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
            if policy == "selep":
                _run_selep_policy(adapter, editor, options, results_path)
                continue
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
            model_topology_path = _trial_model_topology_file(model_path, trial_spec, trial)
            _record_model_topology(
                adapter,
                editor,
                state,
                trial_spec,
                "markov",
                limit,
                model_path,
                model_topology_path,
                trial,
                suffix=label,
            )
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
                model_topology_file_override=model_topology_path,
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
            model_topology_path = _trial_model_topology_file(model_path, trial_spec, trial)
            _record_model_topology(
                adapter,
                editor,
                state,
                trial_spec,
                "coaccess",
                limit,
                model_path,
                model_topology_path,
                trial,
                suffix=label,
            )
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
                model_topology_file_override=model_topology_path,
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


def _run_random_paired(
    adapter,
    editor: RunConfigEditor,
    options: SweepOptions,
    results_path: Path,
) -> None:
    if options.random_n <= 0:
        raise ValueError(f"SWEEP_RANDOM_N must be positive, got {options.random_n}")
    if options.random_train_k < 0:
        raise ValueError(
            f"SWEEP_RANDOM_TRAIN_K must be non-negative, got {options.random_train_k}"
        )
    unknown = [p for p in options.random_policies if not _is_random_runtime_policy(p)]
    if unknown:
        raise ValueError(
            "SWEEP_RANDOM_POLICIES supports stream-safe runtime policies only; "
            f"unknown/unsupported: {', '.join(unknown)}"
        )

    setup_policy = next((p for p in options.random_policies if p != "none"), "none")
    setup_limit = max(options.limits) if options.limits else 0
    print("")
    print("========================================")
    print(
        "Case: policy=random-paired "
        f"n={options.random_n} train_k={options.random_train_k} "
        f"seed={options.random_seed} "
        f"policies={' '.join(options.random_policies)}"
    )
    print("========================================")

    editor.patch(_config_values("none", 0, access_log=""))
    state = adapter.prepare_case(setup_policy, setup_limit)
    pool = _unique_spawn_pool(adapter.spawn_pool(state))
    min_pool = max(options.random_n, options.random_train_k)
    if len(pool) < min_pool:
        raise RuntimeError(
            f"{adapter.name} exposes {len(pool)} pooled spawn request(s), "
            f"but random-paired needs at least {min_pool} for "
            f"N={options.random_n}, K={options.random_train_k}. "
            "Expose more seeded spawn targets or lower SWEEP_RANDOM_N/"
            "SWEEP_RANDOM_TRAIN_K."
        )
    sample_indices = list(range(len(pool)))
    random.Random(options.random_seed).shuffle(sample_indices)
    if len(sample_indices) >= options.random_train_k + options.random_n:
        train_indices = sample_indices[: options.random_train_k]
        measured_indices = sample_indices[
            options.random_train_k : options.random_train_k + options.random_n
        ]
        split_mode = "disjoint"
    else:
        train_indices = sample_indices[: options.random_train_k]
        measured_indices = sample_indices[: options.random_n]
        split_mode = "overlap"
    train_specs = _select_specs_by_indices(pool, train_indices, "training")
    measured_specs = _select_specs_by_indices(pool, measured_indices, "measured")
    train_ids = [_request_id(spec) for spec in train_specs]
    measured_ids = [_request_id(spec) for spec in measured_specs]
    effective_trials = 1
    metadata = {
        "mode": "random-paired",
        "app": adapter.name,
        "seed": options.random_seed,
        "n": options.random_n,
        "train_k": options.random_train_k,
        "split_mode": split_mode,
        "requested_trials": options.trials,
        "effective_trials": effective_trials,
        "policies": list(options.random_policies),
        "limits": list(options.limits),
        "policy_limits": {
            policy: _random_limits_for_policy(policy, options.limits)
            for policy in options.random_policies
        },
        "pool_size": len(pool),
        "train_indices": train_indices,
        "measured_indices": measured_indices,
        "train_ids": train_ids,
        "measured_ids": measured_ids,
        "summaries": [],
    }
    metadata_path = (
        adapter.app_dir
        / options.manifest.logs_dir
        / (
            f"random_paired_seed{options.random_seed}_n{options.random_n}"
            f"_k{options.random_train_k}_metadata.json"
        )
    )
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n")
    print(
        f"    random split: seed={options.random_seed} pool={len(pool)} "
        f"train={len(train_specs)} measured={len(measured_specs)} "
        f"mode={split_mode} metadata={metadata_path}"
    )
    if options.trials != effective_trials:
        print(
            "    random-paired ignores Trials; each selected request runs "
            "once in a continuous stream per policy/limit."
        )

    for policy in options.random_policies:
        for limit in _random_limits_for_policy(policy, options.limits):
            print("")
            print("----------------------------------------")
            print(
                f"Stream: policy={policy} limit={limit} "
                f"measured={len(measured_specs)}"
            )
            print("----------------------------------------")
            cfg = None
            train_ms = ""
            if policy == "selep":
                if not train_indices:
                    raise RuntimeError("random-paired selep requires SWEEP_RANDOM_TRAIN_K > 0")
                editor.patch(_config_values("none", 0, access_log=""))
                train_state = adapter.prepare_case("selep", limit)
                train_pool = _unique_spawn_pool(adapter.spawn_pool(train_state))
                train_specs = _select_specs_by_indices(
                    train_pool, train_indices, "training"
                )
                cfg, train_ms = _collect_and_train_selep_stream(
                    adapter,
                    editor,
                    train_state,
                    train_specs,
                    limit,
                    options,
                )

            editor.patch(_config_values("none", 0, access_log=""))
            stream_state = adapter.prepare_case(policy, limit)
            stream_pool = _unique_spawn_pool(adapter.spawn_pool(stream_state))
            measured_specs = _select_specs_by_indices(
                stream_pool, measured_indices, "measured"
            )
            results, summary = _run_random_stream_trial(
                adapter,
                editor,
                stream_state,
                policy,
                limit,
                measured_specs,
                options,
                cfg=cfg,
                train_ms=train_ms,
            )
            for result in results:
                metrics.append_result(results_path, result.__dict__)
            summary["train_indices"] = train_indices
            summary["measured_indices"] = measured_indices
            summary["measured_ids"] = [_request_id(spec) for spec in measured_specs]
            metadata["summaries"].append(summary)
            metadata_path.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n")
            print(
                f"  Stream done: policy={policy} limit={limit} "
                f"sum_e2e={summary['sum_request_e2e_ms']:.3f}ms "
                f"wall={summary['stream_wall_ms']:.3f}ms"
            )


def _collect_and_train_selep_stream(
    adapter,
    editor: RunConfigEditor,
    state: CaseState,
    specs: list[RequestSpec],
    limit: int,
    options: SweepOptions,
) -> tuple[selep.SelepModelConfig, str]:
    first = specs[0]
    label_spec = RequestSpec(
        walker=first.walker,
        path=first.path,
        body=first.body,
        request_id=(
            f"random-paired-seed{options.random_seed}"
            f"-trainK{len(specs)}-limit{limit}"
        ),
    )
    cfg = selep.model_config(adapter, label_spec, limit, options)
    cfg.train_trace_path.unlink(missing_ok=True)
    cfg.train_access_log.unlink(missing_ok=True)
    editor.patch(
        _config_values(
            "none",
            0,
            access_log=str(cfg.train_access_log),
            oracle_file="",
            markov_file="",
            coaccess_file="",
        )
    )
    adapter.clear_runtime_cache()
    proc = None
    start = time.perf_counter()
    try:
        proc = adapter.start_server(
            cfg.train_log_path,
            extra_env={"JAC_SELEP_TRACE": str(cfg.train_trace_path)},
        )
        for spec in specs:
            resp = adapter.post(spec.path, spec.body, token=spec.token or state.token)
            payload = _response_payload_or_raise(resp, spec)
            adapter.validate_response(spec, payload)
    finally:
        process.stop_process(proc)
        adapter.stop_stale_servers()
    if not cfg.train_trace_path.exists() or cfg.train_trace_path.stat().st_size == 0:
        raise RuntimeError(f"SeLeP training produced no SQL trace: {cfg.train_trace_path}")
    selep.run_training_script(adapter, cfg, options)
    train_ms = (time.perf_counter() - start) * 1000
    print(
        "    selep stream train: "
        f"k={len(specs)} model={cfg.model_path} train_ms={train_ms:.3f}"
    )
    return cfg, f"{train_ms:.3f}"


def _run_random_stream_trial(
    adapter,
    editor: RunConfigEditor,
    state: CaseState,
    policy: str,
    limit: int,
    specs: list[RequestSpec],
    options: SweepOptions,
    *,
    cfg: selep.SelepModelConfig | None = None,
    train_ms: str = "",
) -> tuple[list[TrialResult], dict[str, object]]:
    if not specs:
        raise RuntimeError("random-paired stream has no measured requests")
    first = specs[0]
    stream_spec = RequestSpec(
        walker=first.walker,
        path=first.path,
        body=first.body,
        request_id=(
            f"random-paired-seed{options.random_seed}"
            f"-policy{policy}-limit{limit}-n{len(specs)}"
        ),
    )
    log_path, access_log, profile_dir, profile_csv = _trial_paths(
        adapter,
        stream_spec,
        policy,
        limit,
        1,
        suffix=f"stream_seed{options.random_seed}_n{len(specs)}",
    )
    if policy == "selep":
        if cfg is None:
            raise RuntimeError("random-paired selep stream requires a trained cfg")
        sidecar_paths = selep.trial_paths(
            adapter,
            stream_spec,
            limit,
            1,
            suffix=f"stream_seed{options.random_seed}_n{len(specs)}",
        )
        editor.patch(
            _config_values(
                "none",
                0,
                access_log=str(access_log),
                oracle_file="",
                markov_file="",
                coaccess_file="",
            )
        )
    else:
        sidecar_paths = None
        editor.patch(
            _config_values(
                policy,
                limit,
                access_log=str(access_log),
                oracle_file="",
                markov_file="",
                coaccess_file="",
            )
        )

    adapter.clear_runtime_cache()
    proc = None
    db_before = _db_query_count(adapter) if options.count_db else ""
    request_results: list[TrialResult] = []
    stream_start = time.perf_counter()
    try:
        if policy == "selep":
            assert cfg is not None and sidecar_paths is not None
            with selep.start_sidecar(adapter, cfg, sidecar_paths, options):
                proc = adapter.start_server(
                    log_path,
                    profile_dir=profile_dir,
                    profile_csv=profile_csv,
                    extra_env={"JAC_SELEP_TRACE": str(sidecar_paths.trace_path)},
                )
                request_results = _post_stream_requests(
                    adapter, state, policy, limit, specs, options, cfg
                )
        else:
            proc = adapter.start_server(
                log_path,
                profile_dir=profile_dir,
                profile_csv=profile_csv,
            )
            request_results = _post_stream_requests(
                adapter, state, policy, limit, specs, options, cfg
            )
    finally:
        process.stop_process(proc)
        adapter.stop_stale_servers()
    stream_wall_ms = (time.perf_counter() - stream_start) * 1000

    db_after = _db_query_count(adapter) if options.count_db else ""
    db_q = ""
    if db_before != "" and db_after != "":
        try:
            db_q = str(int(db_after) - int(db_before))
        except ValueError:
            db_q = ""
    counts = metrics.tier_counts(access_log)
    stats = selep.load_stats(sidecar_paths.sidecar_stats) if sidecar_paths else {}
    errors = stats.get("errors") or []
    error_text = str(len(errors)) if isinstance(errors, list) else ""
    if (
        policy == "selep"
        and isinstance(errors, list)
        and errors
        and not selep.env_bool(options, "SELEP_ALLOW_PREWARM_ERRORS")
    ):
        raise RuntimeError(
            "SeLeP sidecar reported pg_prewarm error(s); "
            f"see {sidecar_paths.sidecar_stats} and {sidecar_paths.sidecar_log}"
        )

    summary: dict[str, object] = {
        "policy": policy,
        "prefetch_limit": limit,
        "measured_n": len(specs),
        "train_k": options.random_train_k if policy == "selep" else 0,
        "measured_ids": [_request_id(spec) for spec in specs],
        "train_ms": train_ms,
        "sum_request_e2e_ms": sum(result.e2e_ms for result in request_results),
        "stream_wall_ms": stream_wall_ms,
        "db_q": db_q,
        "access_log": str(access_log),
        "server_log": str(log_path),
        "profile_csv": str(profile_csv),
        "l1_hit_rate": counts.get("l1_hit_rate", ""),
        "l1": counts.get("l1", ""),
        "l2": counts.get("l2", ""),
        "l3": counts.get("l3", ""),
        "miss": counts.get("miss", ""),
        "model_file": str(cfg.model_path) if cfg is not None else "",
        "selep_events": str(stats.get("events_seen", "")),
        "selep_matched_events": str(stats.get("matched_events", "")),
        "selep_predictions": str(stats.get("predictions", "")),
        "selep_blocks": str(stats.get("blocks_requested", "")),
        "selep_blocks_skipped": str(stats.get("blocks_skipped", "")),
        "selep_blocks_already_warmed": str(stats.get("blocks_already_warmed", "")),
        "selep_prewarm_calls": str(stats.get("prewarm_calls", "")),
        "selep_prewarm_ms": str(stats.get("prewarm_ms", "")),
        "selep_errors": error_text,
    }
    summary_path = (
        adapter.app_dir
        / options.manifest.logs_dir
        / (
            f"random_paired_stream_policy{_safe(policy)}_limit{limit}"
            f"_seed{options.random_seed}_n{len(specs)}_summary.json"
        )
    )
    summary["summary_path"] = str(summary_path)
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    return request_results, summary


def _post_stream_requests(
    adapter,
    state: CaseState,
    policy: str,
    limit: int,
    specs: list[RequestSpec],
    options: SweepOptions,
    cfg: selep.SelepModelConfig | None,
) -> list[TrialResult]:
    results: list[TrialResult] = []
    for request_order, spec in enumerate(specs, start=1):
        resp = adapter.post(spec.path, spec.body, token=spec.token or state.token)
        payload = _response_payload_or_raise(resp, spec)
        adapter.validate_response(spec, payload)
        results.append(
            TrialResult(
                policy=policy,
                walker=spec.walker,
                prefetch_limit=limit,
                trial=request_order,
                e2e_ms=resp.elapsed_ms,
                request_id=_request_id(spec),
                request_order=str(request_order),
                train_n=str(options.random_train_k if policy == "selep" else 0),
                trial_count=str(len(specs)),
                pool_seed=str(options.random_seed),
                model_file=str(cfg.model_path) if cfg is not None else "",
            )
        )
        print(
            f"  Request {request_order}/{len(specs)}: policy={policy} "
            f"limit={limit} {resp.elapsed_ms:.3f}ms"
        )
    return results


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
        payload = _response_payload_or_raise(resp, spec)
        adapter.validate_response(spec, payload)
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
        payload = _response_payload_or_raise(resp, spec)
        adapter.validate_response(spec, payload)
    finally:
        process.stop_process(proc)
        adapter.stop_stale_servers()
    return record_access_log


def _run_selep_policy(
    adapter,
    editor: RunConfigEditor,
    options: SweepOptions,
    results_path: Path,
) -> None:
    for limit in _limits_for_policy("selep", options.limits):
        print("")
        print("========================================")
        print(f"Case: policy=selep prefetch_limit={limit}")
        print("========================================")
        editor.patch(_config_values("none", 0, access_log=""))
        state = adapter.prepare_case("selep", limit)
        spec = _require_request(state)
        cfg = selep.collect_and_train(adapter, editor, state, spec, limit, options, _config_values)
        print(
            "    selep train: "
            f"model={cfg.model_path} workload={cfg.workload_path} "
            f"kind={cfg.model_kind} top_k={cfg.top_k} block_limit={cfg.block_limit}"
        )

        editor.patch(_config_values("none", 0, access_log=""))
        state = adapter.prepare_case("selep", limit)
        if state.request is None:
            raise RuntimeError(f"{adapter.name} did not prepare a request")

        for trial in range(1, options.trials + 1):
            result = _run_selep_trial(
                adapter,
                editor,
                state,
                cfg,
                limit,
                trial,
                options,
                trial_count=options.trials,
            )
            metrics.append_result(results_path, result.__dict__)
            print(
                f"  Trial {trial}: policy=selep limit={limit} "
                f"{result.e2e_ms:.3f}ms L1={result.l1 or '?'} "
                f"L3={result.l3 or '?'} prewarm={result.selep_prewarm_calls or '?'}"
            )


def _run_selep_trial(
    adapter,
    editor: RunConfigEditor,
    state: CaseState,
    cfg: selep.SelepModelConfig,
    limit: int,
    trial: int,
    options: SweepOptions,
    *,
    trial_count: int | None = None,
    spec_override: RequestSpec | None = None,
    request_id: str = "",
    request_order: int | None = None,
    path_suffix: str = "",
) -> TrialResult:
    spec = spec_override or _require_request(state)
    log_path, access_log, profile_dir, profile_csv = _trial_paths(
        adapter, spec, "selep", limit, trial, suffix=path_suffix
    )
    sidecar_paths = selep.trial_paths(adapter, spec, limit, trial, suffix=path_suffix)
    editor.patch(
        _config_values(
            "none",
            0,
            access_log=str(access_log),
            oracle_file="",
            markov_file="",
            coaccess_file="",
        )
    )
    adapter.clear_runtime_cache()

    proc = None
    db_before = _db_query_count(adapter) if options.count_db else ""
    try:
        with selep.start_sidecar(adapter, cfg, sidecar_paths, options):
            proc = adapter.start_server(
                log_path,
                profile_dir=profile_dir,
                profile_csv=profile_csv,
                extra_env={"JAC_SELEP_TRACE": str(sidecar_paths.trace_path)},
            )
            resp = adapter.post(spec.path, spec.body, token=spec.token or state.token)
            payload = _response_payload_or_raise(resp, spec)
            adapter.validate_response(spec, payload)
    finally:
        process.stop_process(proc)
        adapter.stop_stale_servers()

    _assert_trial_profiles(profile_dir, profile_csv)
    db_after = _db_query_count(adapter) if options.count_db else ""
    counts = metrics.tier_counts(access_log)
    profile = metrics.profile_breakdown(profile_csv)
    stats = selep.load_stats(sidecar_paths.sidecar_stats)
    db_q = ""
    if db_before != "" and db_after != "":
        try:
            db_q = str(int(db_after) - int(db_before))
        except ValueError:
            db_q = ""

    errors = stats.get("errors") or []
    if isinstance(errors, list):
        error_text = str(len(errors))
        if errors and not selep.env_bool(options, "SELEP_ALLOW_PREWARM_ERRORS"):
            raise RuntimeError(
                "SeLeP sidecar reported pg_prewarm error(s); "
                f"see {sidecar_paths.sidecar_stats} and {sidecar_paths.sidecar_log}"
            )
    else:
        error_text = ""
    return TrialResult(
        policy="selep",
        walker=spec.walker,
        prefetch_limit=limit,
        trial=trial,
        e2e_ms=resp.elapsed_ms,
        request_id=request_id or _request_id(spec),
        request_order=str(request_order) if request_order is not None else "",
        trial_count=str(trial_count) if trial_count is not None else "",
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
        model_file=str(cfg.model_path),
        selep_events=str(stats.get("events_seen", "")),
        selep_matched_events=str(stats.get("matched_events", "")),
        selep_predictions=str(stats.get("predictions", "")),
        selep_blocks=str(stats.get("blocks_requested", "")),
        selep_blocks_skipped=str(stats.get("blocks_skipped", "")),
        selep_blocks_already_warmed=str(stats.get("blocks_already_warmed", "")),
        selep_prewarm_calls=str(stats.get("prewarm_calls", "")),
        selep_prewarm_ms=str(stats.get("prewarm_ms", "")),
        selep_errors=error_text,
    )


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
    model_topology_file_override: Path | None = None,
    request_id: str = "",
    request_order: int | None = None,
    train_n: int | None = None,
    trial_count: int | None = None,
    pool_seed: int | None = None,
    path_suffix: str = "",
) -> TrialResult:
    spec = spec_override or _require_request(state)
    oracle_file: Path | None = None
    oracle_topology_file: Path | None = None
    model_file: Path | None = None
    model_topology_file: Path | None = None
    if model_file_override is not None:
        model_file = model_file_override
        effective_policy = effective_policy_override or "markov"
        model_topology_file = model_topology_file_override or _default_model_topology_file(
            effective_policy, model_file
        )
        if model_topology_file is not None and not model_topology_file.exists():
            raise FileNotFoundError(
                f"{effective_policy} topology snapshot does not exist: {model_topology_file}"
            )
    elif policy == "oracle":
        oracle_file, oracle_topology_file = _oracle_for_trial(
            adapter, editor, state, spec, limit, trial, options
        )
        effective_policy = "oracle"
    elif policy == "markov":
        model_file, model_topology_file = _markov_for_trial(
            adapter, editor, state, spec, limit, trial, options
        )
        effective_policy = "markov"
    elif policy == "coaccess":
        model_file, model_topology_file = _coaccess_for_trial(
            adapter, editor, state, spec, limit, trial, options
        )
        effective_policy = "coaccess"
    else:
        effective_policy = policy

    output_policy = result_policy or policy
    log_path, access_log, profile_dir, profile_csv = _trial_paths(
        adapter, spec, output_policy, limit, trial, suffix=path_suffix
    )
    call_spec = spec
    capre_response_file: Path | None = None
    if policy == "capre":
        call_spec, capre_response_file = _linked_list_capre_trial_spec(
            adapter, spec, access_log, profile_dir, profile_csv, limit, trial, options
        )
    editor.patch(
        _config_values(
            effective_policy,
            limit,
            access_log=str(access_log),
            oracle_file=str(oracle_file) if oracle_file is not None else "",
            oracle_topology_file=(
                str(oracle_topology_file) if oracle_topology_file is not None else ""
            ),
            markov_file=str(model_file) if model_file is not None and effective_policy == "markov" else "",
            markov_topology_file=(
                str(model_topology_file)
                if model_topology_file is not None and effective_policy == "markov"
                else ""
            ),
            coaccess_file=str(model_file) if model_file is not None and effective_policy == "coaccess" else "",
            coaccess_topology_file=(
                str(model_topology_file)
                if model_topology_file is not None and effective_policy == "coaccess"
                else ""
            ),
        )
    )
    adapter.clear_runtime_cache()

    proc = None
    db_before = _db_query_count(adapter) if options.count_db else ""
    try:
        proc = adapter.start_server(log_path, profile_dir=profile_dir, profile_csv=profile_csv)
        resp = adapter.post(
            call_spec.path,
            call_spec.body,
            token=call_spec.token or state.token,
        )
        payload = _response_payload_or_raise(resp, call_spec)
        if capre_response_file is not None:
            capre_response_file.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
        adapter.validate_response(call_spec, payload)
    finally:
        process.stop_process(proc)
        adapter.stop_stale_servers()

    _assert_trial_profiles(profile_dir, profile_csv)
    db_after = _db_query_count(adapter) if options.count_db else ""
    capre_metrics = _linked_list_capre_metrics(payload) if policy == "capre" else {}
    if capre_metrics:
        counts = _linked_list_capre_counts(capre_metrics)
        profile = metrics.profile_breakdown(profile_csv)
        quality = _linked_list_capre_quality(capre_metrics)
    else:
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
    if capre_metrics:
        db_q = str(capre_metrics.get("query_count", ""))

    return TrialResult(
        policy=output_policy,
        walker=spec.walker,
        prefetch_limit=limit,
        trial=trial,
        e2e_ms=resp.elapsed_ms,
        request_id=request_id or _request_id(spec),
        request_order=str(request_order) if request_order is not None else "",
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
        prefetch_ms=(
            str(capre_metrics.get("prefetch_ms", ""))
            if capre_metrics else profile.get("prefetch_ms", "")
        ),
        walker_ms=(
            str(capre_metrics.get("cpu_ms", ""))
            if capre_metrics else profile.get("walker_ms", "")
        ),
        l1_hit_rate=counts.get("l1_hit_rate", ""),
        l1=counts.get("l1", ""),
        l2=counts.get("l2", ""),
        l3=counts.get("l3", ""),
        miss=counts.get("miss", ""),
        db_q=db_q,
        oracle_file=str(oracle_file) if oracle_file is not None else "",
        oracle_topology_file=(
            str(oracle_topology_file) if oracle_topology_file is not None else ""
        ),
        model_file=str(model_file) if model_file is not None else "",
        model_topology_file=(
            str(model_topology_file) if model_topology_file is not None else ""
        ),
    )


def _linked_list_capre_trial_spec(
    adapter,
    spec: RequestSpec,
    access_log: Path,
    profile_dir: Path,
    profile_csv: Path,
    limit: int,
    trial: int,
    options: SweepOptions,
) -> tuple[RequestSpec, Path]:
    if adapter.name != "linked_list":
        raise ValueError("capre baseline is currently implemented only for linked_list")
    plans_dir = adapter.app_dir / "capre_plans"
    safe_walker = _safe(spec.walker)
    safe_request = _safe(_request_id(spec))[:80]
    actual_file = plans_dir / f"actual_{safe_walker}_{safe_request}_trial{trial}.uuids"
    prefetch_file = plans_dir / f"prefetch_{safe_walker}_{safe_request}_trial{trial}.uuids"
    response_file = (
        adapter.app_dir
        / adapter.options.manifest.logs_dir
        / f"http_response_{safe_walker}_policycapre_limit{limit}_trial{trial}.json"
    )
    return (
        RequestSpec(
            walker=spec.walker,
            path="/function/oop_traverse",
            body={
                "start_id": spec.target_id,
                "policy": "capre",
                "postgres_uri": adapter.postgres_uri,
                "access_log": str(access_log),
                "actual_file": str(actual_file),
                "prefetch_file": str(prefetch_file),
                "profile_dir": str(profile_dir),
                "profile_csv": str(profile_csv),
                "include_metrics": True,
            },
            target_id=spec.target_id,
            request_id=_request_id(spec),
            token=spec.token,
        ),
        response_file,
    )


def _linked_list_capre_metrics(payload: object) -> dict[str, object]:
    if not isinstance(payload, dict) or not payload.get("ok"):
        raise RuntimeError(f"capre returned failed payload: {payload!r}")
    data = payload.get("data")
    result = data.get("result") if isinstance(data, dict) else None
    capre_metrics = result.get("metrics") if isinstance(result, dict) else None
    reports = result.get("reports") if isinstance(result, dict) else None
    if not isinstance(capre_metrics, dict) or not isinstance(reports, list):
        raise RuntimeError(f"capre returned malformed payload: {payload!r}")
    if int(capre_metrics.get("visited", -1)) != len(reports):
        raise RuntimeError(
            "capre visited mismatch: "
            f"metrics={capre_metrics.get('visited')} reports={len(reports)}"
        )
    return capre_metrics


def _linked_list_capre_quality(capre_metrics: dict[str, object]) -> dict[str, str]:
    return {
        "coverage": str(capre_metrics.get("coverage", "")),
        "accuracy": str(capre_metrics.get("accuracy", "")),
        "actual_ids": str(capre_metrics.get("actual_ids", "")),
        "plan_ids": str(capre_metrics.get("prefetched_ids", "")),
        "covered_ids": str(capre_metrics.get("covered_ids", "")),
        "overfetch_ids": str(capre_metrics.get("overfetch_ids", "")),
        "undercoverage_ids": str(capre_metrics.get("undercoverage_ids", "")),
    }


def _linked_list_capre_counts(capre_metrics: dict[str, object]) -> dict[str, str]:
    l1 = str(capre_metrics.get("l1", ""))
    l2 = str(capre_metrics.get("l2", "0"))
    l3 = str(capre_metrics.get("l3", ""))
    miss = str(capre_metrics.get("miss", "0"))
    return {
        "l1_hit_rate": _hit_rate(l1, l3),
        "l1": l1,
        "l2": l2,
        "l3": l3,
        "miss": miss,
    }


def _hit_rate(l1: str, l3: str) -> str:
    try:
        l1_count = int(l1)
        l3_count = int(l3)
    except ValueError:
        return ""
    total = l1_count + l3_count
    return f"{(l1_count * 100.0 / total) if total else 0.0:.1f}"


def _oracle_for_trial(
    adapter,
    editor: RunConfigEditor,
    state: CaseState,
    spec: RequestSpec,
    limit: int,
    trial: int,
    options: SweepOptions,
) -> tuple[Path, Path]:
    explicit = options.env.get("SWEEP_ORACLE_FILE") or options.env.get("JAC_PREFETCH_ORACLE_FILE")
    explicit_topology = (
        options.env.get("SWEEP_ORACLE_TOPOLOGY_FILE")
        or options.env.get("JAC_PREFETCH_ORACLE_TOPOLOGY_FILE")
    )
    if options.oracle_mode == "file":
        path = Path(explicit) if explicit else oracle.oracle_file_path(
            options.oracle_dir, adapter.name, spec.walker, spec.target_id, limit, trial
        )
        path = path if path.is_absolute() else adapter.app_dir / path
        if not path.exists():
            raise FileNotFoundError(f"oracle file does not exist: {path}")
        topology_path = (
            Path(explicit_topology)
            if explicit_topology else oracle.oracle_topology_file_path(path)
        )
        topology_path = (
            topology_path if topology_path.is_absolute() else adapter.app_dir / topology_path
        )
        if not topology_path.exists():
            raise FileNotFoundError(f"oracle topology snapshot does not exist: {topology_path}")
        return path, topology_path
    if options.oracle_mode != "auto":
        raise ValueError(f"unsupported SWEEP_ORACLE_MODE={options.oracle_mode!r}")

    output_path = Path(explicit) if explicit else oracle.oracle_file_path(
        options.oracle_dir, adapter.name, spec.walker, spec.target_id, limit, trial
    )
    output_path = output_path if output_path.is_absolute() else adapter.app_dir / output_path
    topology_path = (
        Path(explicit_topology)
        if explicit_topology else oracle.oracle_topology_file_path(output_path)
    )
    topology_path = topology_path if topology_path.is_absolute() else adapter.app_dir / topology_path

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
            oracle_topology_file="",
            oracle_record_topology_file=str(topology_path),
            markov_file="",
            coaccess_file="",
        )
    )
    adapter.clear_runtime_cache()
    proc = None
    try:
        proc = adapter.start_server(record_log)
        resp = adapter.post(spec.path, spec.body, token=spec.token or state.token)
        payload = _response_payload_or_raise(resp, spec)
        adapter.validate_response(spec, payload)
    finally:
        process.stop_process(proc)
        adapter.stop_stale_servers()
    ids = oracle.write_oracle_from_access_log(record_access_log, output_path)
    print(f"    oracle record: wrote {len(ids)} UUID(s) to {output_path}")
    if not topology_path.exists():
        raise RuntimeError(f"oracle record did not produce topology snapshot: {topology_path}")
    print(f"    oracle record: wrote topology snapshot to {topology_path}")
    adapter.clear_runtime_cache()
    return output_path, topology_path


def _markov_for_trial(
    adapter,
    editor: RunConfigEditor,
    state: CaseState,
    spec: RequestSpec,
    limit: int,
    trial: int,
    options: SweepOptions,
) -> tuple[Path, Path]:
    explicit = options.env.get("SWEEP_MARKOV_FILE") or options.env.get("JAC_PREFETCH_MARKOV_FILE")
    explicit_topology = (
        options.env.get("SWEEP_MARKOV_TOPOLOGY_FILE")
        or options.env.get("JAC_PREFETCH_MARKOV_TOPOLOGY_FILE")
    )
    if options.markov_mode == "file":
        path = Path(explicit) if explicit else markov.markov_model_path(
            options.markov_dir, adapter.name, spec.walker, spec.target_id, limit, trial
        )
        path = path if path.is_absolute() else adapter.app_dir / path
        if not path.exists():
            raise FileNotFoundError(f"markov model file does not exist: {path}")
        topology_path = (
            Path(explicit_topology)
            if explicit_topology else markov.markov_topology_file_path(path)
        )
        topology_path = topology_path if topology_path.is_absolute() else adapter.app_dir / topology_path
        if not topology_path.exists():
            raise FileNotFoundError(
                f"markov topology snapshot does not exist: {topology_path}"
            )
        return path, topology_path
    if options.markov_mode != "auto":
        raise ValueError(f"unsupported SWEEP_MARKOV_MODE={options.markov_mode!r}")

    output_path = Path(explicit) if explicit else markov.markov_model_path(
        options.markov_dir, adapter.name, spec.walker, spec.target_id, limit, trial
    )
    output_path = output_path if output_path.is_absolute() else adapter.app_dir / output_path
    topology_path = (
        Path(explicit_topology)
        if explicit_topology else markov.markov_topology_file_path(output_path)
    )
    topology_path = topology_path if topology_path.is_absolute() else adapter.app_dir / topology_path

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
            markov_topology_file="",
            markov_record_topology_file="",
            coaccess_file="",
        )
    )
    adapter.clear_runtime_cache()
    proc = None
    try:
        proc = adapter.start_server(record_log)
        resp = adapter.post(spec.path, spec.body, token=spec.token or state.token)
        payload = _response_payload_or_raise(resp, spec)
        adapter.validate_response(spec, payload)
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
    _record_model_topology(
        adapter,
        editor,
        state,
        spec,
        "markov",
        limit,
        output_path,
        topology_path,
        trial,
        suffix="single",
    )
    adapter.clear_runtime_cache()
    return output_path, topology_path


def _coaccess_for_trial(
    adapter,
    editor: RunConfigEditor,
    state: CaseState,
    spec: RequestSpec,
    limit: int,
    trial: int,
    options: SweepOptions,
) -> tuple[Path, Path]:
    explicit = options.env.get("SWEEP_COACCESS_FILE") or options.env.get("JAC_PREFETCH_COACCESS_FILE")
    explicit_topology = (
        options.env.get("SWEEP_COACCESS_TOPOLOGY_FILE")
        or options.env.get("JAC_PREFETCH_COACCESS_TOPOLOGY_FILE")
    )
    if options.coaccess_mode == "file":
        path = Path(explicit) if explicit else coaccess.coaccess_model_path(
            options.coaccess_dir, adapter.name, spec.walker, spec.target_id, limit, trial
        )
        path = path if path.is_absolute() else adapter.app_dir / path
        if not path.exists():
            raise FileNotFoundError(f"co-access model file does not exist: {path}")
        topology_path = (
            Path(explicit_topology)
            if explicit_topology else coaccess.coaccess_topology_file_path(path)
        )
        topology_path = topology_path if topology_path.is_absolute() else adapter.app_dir / topology_path
        if not topology_path.exists():
            raise FileNotFoundError(
                f"co-access topology snapshot does not exist: {topology_path}"
            )
        return path, topology_path
    if options.coaccess_mode != "auto":
        raise ValueError(f"unsupported SWEEP_COACCESS_MODE={options.coaccess_mode!r}")

    output_path = Path(explicit) if explicit else coaccess.coaccess_model_path(
        options.coaccess_dir, adapter.name, spec.walker, spec.target_id, limit, trial
    )
    output_path = output_path if output_path.is_absolute() else adapter.app_dir / output_path
    topology_path = (
        Path(explicit_topology)
        if explicit_topology else coaccess.coaccess_topology_file_path(output_path)
    )
    topology_path = topology_path if topology_path.is_absolute() else adapter.app_dir / topology_path

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
            coaccess_topology_file="",
            coaccess_record_topology_file="",
        )
    )
    adapter.clear_runtime_cache()
    proc = None
    try:
        proc = adapter.start_server(record_log)
        resp = adapter.post(spec.path, spec.body, token=spec.token or state.token)
        payload = _response_payload_or_raise(resp, spec)
        adapter.validate_response(spec, payload)
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
    _record_model_topology(
        adapter,
        editor,
        state,
        spec,
        "coaccess",
        limit,
        output_path,
        topology_path,
        trial,
        suffix="single",
    )
    adapter.clear_runtime_cache()
    return output_path, topology_path


def _record_model_topology(
    adapter,
    editor: RunConfigEditor,
    state: CaseState,
    spec: RequestSpec,
    policy: str,
    limit: int,
    model_file: Path,
    topology_file: Path,
    trial: int,
    *,
    suffix: str = "",
) -> None:
    logs_dir = adapter.app_dir / adapter.options.manifest.logs_dir
    safe_walker = _safe(spec.walker)
    safe_policy = _safe(policy)
    safe_suffix = f"_{_safe(suffix)}" if suffix else ""
    record_log = (
        logs_dir
        / f"{safe_policy}_topology_record_{safe_walker}_limit{limit}_trial{trial}{safe_suffix}.log"
    )
    record_access_log = (
        logs_dir
        / f"{safe_policy}_topology_record_access_{safe_walker}_limit{limit}_trial{trial}{safe_suffix}.csv"
    )
    config_kwargs: dict[str, str] = {
        "access_log": str(record_access_log),
        "oracle_file": "",
        "oracle_topology_file": "",
        "oracle_record_topology_file": "",
        "markov_file": "",
        "markov_topology_file": "",
        "markov_record_topology_file": "",
        "coaccess_file": "",
        "coaccess_topology_file": "",
        "coaccess_record_topology_file": "",
    }
    if policy == "markov":
        config_kwargs["markov_file"] = str(model_file)
        config_kwargs["markov_record_topology_file"] = str(topology_file)
    elif policy == "coaccess":
        config_kwargs["coaccess_file"] = str(model_file)
        config_kwargs["coaccess_record_topology_file"] = str(topology_file)
    else:
        raise ValueError(f"unsupported model topology policy={policy!r}")

    editor.patch(_config_values(policy, limit, **config_kwargs))
    adapter.clear_runtime_cache()
    proc = None
    try:
        proc = adapter.start_server(record_log)
        resp = adapter.post(spec.path, spec.body, token=spec.token or state.token)
        payload = _response_payload_or_raise(resp, spec)
        adapter.validate_response(spec, payload)
    finally:
        process.stop_process(proc)
        adapter.stop_stale_servers()
    if not topology_file.exists():
        raise RuntimeError(
            f"{policy} topology record did not produce snapshot: {topology_file}"
        )
    print(f"    {policy} topology: wrote snapshot to {topology_file}")


def _default_model_topology_file(policy: str, model_file: Path) -> Path | None:
    if policy == "markov":
        return markov.markov_topology_file_path(model_file)
    if policy == "coaccess":
        return coaccess.coaccess_topology_file_path(model_file)
    return None


def _trial_model_topology_file(model_file: Path, spec: RequestSpec, trial: int) -> Path:
    safe_request = _safe(_request_id(spec))[:80]
    suffix = f"{safe_request}_trial{trial}.topology.json"
    return model_file.with_name(f"{model_file.name}.{suffix}")


def _trial_paths(
    adapter,
    spec: RequestSpec,
    policy: str,
    limit: int,
    trial: int,
    suffix: str = "",
):
    logs_dir = adapter.app_dir / adapter.options.manifest.logs_dir
    profiles_dir = adapter.app_dir / adapter.options.manifest.profiles_dir
    safe_walker = _safe(spec.walker)
    safe_policy = _safe(policy)
    safe_suffix = f"_{_safe(suffix)}" if suffix else ""
    log_path = logs_dir / f"jac_server_{safe_walker}_policy{safe_policy}_limit{limit}_trial{trial}{safe_suffix}.log"
    access_log = logs_dir / f"access_log_{safe_walker}_policy{safe_policy}_limit{limit}_trial{trial}{safe_suffix}.csv"
    profile_dir = (
        profiles_dir
        / f"policy_{safe_policy}"
        / f"limit_{limit}"
        / safe_walker
        / f"trial_{trial}{safe_suffix}"
    )
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
    oracle_topology_file: str = "",
    oracle_record_topology_file: str = "",
    markov_file: str = "",
    markov_topology_file: str = "",
    markov_record_topology_file: str = "",
    coaccess_file: str = "",
    coaccess_topology_file: str = "",
    coaccess_record_topology_file: str = "",
) -> dict[str, object]:
    effective = "none" if policy == "none" or (limit <= 0 and policy != "oracle") else policy
    return {
        "access_log": access_log,
        "topology_index": True,
        "prefetching": effective,
        "prefetch_limit": int(limit),
        "prefetch_oracle_file": oracle_file,
        "prefetch_oracle_topology_file": oracle_topology_file,
        "prefetch_oracle_record_topology_file": oracle_record_topology_file,
        "prefetch_markov_file": markov_file,
        "prefetch_markov_topology_file": markov_topology_file,
        "prefetch_markov_record_topology_file": markov_record_topology_file,
        "prefetch_coaccess_file": coaccess_file,
        "prefetch_coaccess_topology_file": coaccess_topology_file,
        "prefetch_coaccess_record_topology_file": coaccess_record_topology_file,
    }


def _limits_for_policy(policy: str, limits: list[int]) -> list[int]:
    if policy in {"none", "oracle", "capre"}:
        return [0]
    positive = [x for x in limits if x > 0]
    return positive or [0]


def _random_limits_for_policy(policy: str, limits: list[int]) -> list[int]:
    if policy in {"none", "selep"}:
        return [0]
    return _limits_for_policy(policy, limits)


def _app_path(adapter, path: Path) -> Path:
    return path if path.is_absolute() else adapter.app_dir / path


def _is_supported_policy(policy: str) -> bool:
    return (
        policy in SUPPORTED_POLICIES
        or _is_markov_pooled_policy(policy)
        or _is_coaccess_pooled_policy(policy)
    )


def _is_random_runtime_policy(policy: str) -> bool:
    return policy in {
        "none",
        "ttg",
        "history",
        "manual",
        "selep",
    }


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


def _select_specs_by_indices(
    pool: list[RequestSpec],
    indices: list[int],
    label: str,
) -> list[RequestSpec]:
    if not indices:
        return []
    max_index = max(indices)
    if max_index >= len(pool):
        raise RuntimeError(
            f"{label} split needs pool index {max_index}, "
            f"but this reset exposed only {len(pool)} request(s). "
            "The seeded spawn pool is not stable across resets."
        )
    return [pool[index] for index in indices]


def _response_payload_or_raise(resp, spec: RequestSpec) -> object:
    body = resp.body.decode("utf-8", errors="replace")[:500]
    request_id = _request_id(spec)
    context = f"{spec.walker} request {request_id}"
    if resp.status >= 400:
        raise RuntimeError(f"{context} failed: HTTP {resp.status} {body}")
    try:
        return resp.json()
    except Exception as exc:
        raise RuntimeError(
            f"{context} returned non-JSON HTTP {resp.status}: {body}"
        ) from exc


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
