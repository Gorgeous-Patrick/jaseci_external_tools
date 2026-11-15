import logging;
import os;
import sys as _sys;
import threading;
import time as _time;
import from uuid { UUID }

import from jaclang.runtime.archetype { NodeAnchor }

glob logger = logging.getLogger(__name__),
     _prefetch_metrics_lock: threading.Lock = threading.Lock(),
     _prefetch_worker_times: list[float] = [],
     _prefetch_observation_count: int = 0;

def prefetch_worker_times_append(elapsed_ms: float) {
    with _prefetch_metrics_lock {
        _prefetch_worker_times.append(elapsed_ms);
    }
}

def prefetch_worker_times_snapshot -> list[float] {
    with _prefetch_metrics_lock {
        return list(_prefetch_worker_times);
    }
}

def prefetch_worker_times_reset {
    with _prefetch_metrics_lock {
        _prefetch_worker_times.clear();
    }
}

def prefetch_observation_begin {
    with _prefetch_metrics_lock {
        _prefetch_observation_count += 1;
    }
}

def prefetch_observation_end {
    with _prefetch_metrics_lock {
        _prefetch_observation_count = max(_prefetch_observation_count - 1, 0);
    }
}

def observe_anchor_access(id: UUID) -> None {
    with _prefetch_metrics_lock {
        active = _prefetch_observation_count > 0;
    }
    if not active {
        return;
    }
    try {
        import from jaclang.runtime.runtime { JacRuntimeInterface }
        ctx = JacRuntimeInterface.get_context();
        obs = ctx?._prefetch_observed_ids;
        if isinstance(obs, list) {
            obs.append(id);
        }
    } except Exception {
        ;
    }
}

def _chunk_evenly(items: list, n: int) -> list {
    if n <= 1 or len(items) <= 1 {
        return [items];
    }
    out: list = [];
    for k in range(n) {
        shard = items[k::n];
        if shard {
            out.append(shard);
        }
    }
    return out;
}

def _signal_done_after_all(threads: list, done: any) {
    for t in threads {
        t.join();
    }
    done.set();
}

def _prefetch_worker(mem: any, ids: list, observer: any = None) {
    started = _time.perf_counter();
    failure: str | None = None;
    try {
        mem.prefetch(ids);
    } except Exception as e {
        failure = str(e);
        logger.debug(f"prefetch worker failed: {e}");
    } finally {
        if observer is not None {
            try {
                observer(ids, (_time.perf_counter() - started) * 1000, failure);
            } except Exception as error {
                logger.debug(f"prefetch observer failed: {error}");
            }
        }
    }
}

def dispatch_prefetch(
    ctx: any,
    prefetch_ids: list,
    mode: str,
    workers: int = 1,
    append: bool = False,
    observer: any = None
) -> None {
    if append and not prefetch_ids {
        return;
    }
    previous_threads: list = list(getattr(ctx.mem, '_prefetch_threads', []))
        if append
        else [];
    previous_ids: set = set(getattr(ctx.mem, '_prefetch_ids', set()))
        if append
        else set();
    ctx.mem._prefetch_ids = previous_ids | set(prefetch_ids);
    ctx.mem._prefetch_done = threading.Event();
    if not prefetch_ids {
        ctx.mem._prefetch_done.set();
        return;
    }
    if mode == "process" {
        import from jaclang.runtime.ttg_process_reader {
            ProcessReader,
            process_prefetch_worker
        }
        ctx.mem.read_barrier();
        readers = getattr(ctx.mem, '_prefetch_process_readers', None);
        if readers is None or not readers {
            readers = [ProcessReader(ctx.mem.store) for i in range(max(1, workers))];
            setattr(ctx.mem, '_prefetch_process_readers', readers);
        }
        threads: list = list(previous_threads);
        for (index, shard) in enumerate(_chunk_evenly(prefetch_ids, workers)) {
            thread = threading.Thread(
                target=process_prefetch_worker,
                args=(ctx.mem, shard, readers[index % len(readers)], observer),
                daemon=True
            );
            thread.start();
            threads.append(thread);
        }
        ctx.mem._prefetch_threads = threads;
        ctx.mem._prefetch_thread = threads[0] if threads else None;
        ctx.mem._prefetch_process_pids = [reader.process.pid for reader in readers];
        ctx.mem._prefetch_process_startup_ms = [
            reader.startup_ms for reader in readers
        ];
        threading.Thread(
            target=_signal_done_after_all,
            args=(threads, ctx.mem._prefetch_done),
            daemon=True
        ).start();
        return;
    }
    if mode == "thread" {
        shards = _chunk_evenly(prefetch_ids, workers);
        threads: list = list(previous_threads);
        for shard in shards {
            t = threading.Thread(
                target=_prefetch_worker, args=(ctx.mem, shard, observer), daemon=True,
            );
            t.start();
            threads.append(t);
        }
        ctx.mem._prefetch_thread = threads[0] if threads else None;
        ctx.mem._prefetch_threads = threads;
        if threads {
            mon = threading.Thread(
                target=_signal_done_after_all,
                args=(threads, ctx.mem._prefetch_done),
                daemon=True,
            );
            mon.start();
        } else {
            ctx.mem._prefetch_done.set();
        }
        return;
    }
    for thread in previous_threads {
        thread.join();
    }
    if workers <= 1 {
        _prefetch_worker(ctx.mem, prefetch_ids, observer);
        ctx.mem._prefetch_done.set();
        return;
    }
    shards = _chunk_evenly(prefetch_ids, workers);
    threads: list = [];
    for shard in shards {
        t = threading.Thread(target=_prefetch_worker, args=(ctx.mem, shard, observer));
        t.start();
        threads.append(t);
    }
    for t in threads {
        t.join();
    }
    ctx.mem._prefetch_done.set();
}

def run_prefetch_policy(ctx: any, cfg: any, warch: any, nd: NodeAnchor) -> tuple {
    if cfg is None or cfg?.run is None {
        return (0.0, 0.0, 0.0, 0.0);
    }
    run_cfg = cfg.run;
    policy_name: str = str(getattr(run_cfg, "prefetching", ""));
    limit: int = int(getattr(run_cfg, "prefetch_limit", 0) or 0);
    import from jaclang.runtime.prefetch_policy {
        get_prefetch_plan,
        normalize_prefetch_policy_name
    }
    policy = normalize_prefetch_policy_name(policy_name);
    if not policy_name or policy in ("none", "off", "false", "0") {
        return (0.0, 0.0, 0.0, 0.0);
    }
    if limit <= 0 and policy not in ("oracle", "capre") {
        return (0.0, 0.0, 0.0, 0.0);
    }
    if policy == "ttg_dependency" {
        return (0.0, 0.0, 0.0, 0.0);
    }
    if policy == "capre" {
        import from jaclang.runtime.prefetch_policy_capre_runtime {
            start_capre_prefetch
        }
        prefetch_start = _time.perf_counter();
        capre_plan = start_capre_prefetch(ctx, cfg, warch, nd, limit);
        dispatch_ms = (_time.perf_counter() - prefetch_start) * 1000;
        logger.info(
            f"[PREFETCH-POLICY] policy={policy} ids=0 "
            f"topology_ms={float(capre_plan.get('topology_ms', 0.0)):.3f} "
            f"plan_ms={float(capre_plan.get('plan_ms', 0.0)):.3f} "
            f"capre_specs={int(capre_plan.get('specs', 0) or 0)} "
            f"dispatch_ms={dispatch_ms:.3f}"
        );
        return (
            float(capre_plan.get("topology_ms", 0.0)),
            float(capre_plan.get("plan_ms", 0.0)),
            dispatch_ms,
            float(capre_plan.get("resolve_ms", 0.0))
        );
    }
    plan = get_prefetch_plan(
        policy_name, warch, nd, mem=ctx.mem, max_length=limit, config=cfg
    );
    dispatch_ms = 0.0;
    if plan.ids {
        prefetch_start = _time.perf_counter();
        mode: str = str(getattr(run_cfg, "async_prefetch", ""));
        workers: int = int(getattr(run_cfg, "prefetch_workers", 1) or 1);
        if plan.single_query {
            workers = 1;
            mode = "";
        }
        dispatch_prefetch(ctx, plan.ids, mode, workers);
        dispatch_ms = (_time.perf_counter() - prefetch_start) * 1000;
        gil_fn = _sys?._is_gil_enabled;
        gil_enabled = gil_fn() if gil_fn is not None else True;
        logger.info(
            f"[PREFETCH] mode={mode or 'sync'} "
            f"workers={workers} ids={len(plan.ids)} "
            f"dispatch_ms={dispatch_ms:.2f} gil_enabled={gil_enabled}"
        );
    }
    logger.info(
        f"[PREFETCH-POLICY] policy={policy} ids={len(plan.ids)} "
        f"topology_ms={plan.topology_ms:.3f} plan_ms={plan.plan_ms:.3f}"
    );
    return (plan.topology_ms, plan.plan_ms, dispatch_ms, plan.resolve_ms);
}
