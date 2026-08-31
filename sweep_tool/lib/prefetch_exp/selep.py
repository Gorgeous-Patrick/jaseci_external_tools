"""SeLeP sidecar integration for prefetch sweeps."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

from lib.prefetch_exp import process
from lib.prefetch_exp.config_edit import RunConfigEditor
from lib.prefetch_exp.models import CaseState, RequestSpec, SweepOptions


SWEEP_TOOL_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = SWEEP_TOOL_ROOT.parent
DEFAULT_SELEP_REPO = REPO_ROOT.parent / "SeLeP"
SIDECAR_SCRIPT = SWEEP_TOOL_ROOT / "tools" / "run_selep_sidecar.py"


@dataclass(frozen=True)
class SelepModelConfig:
    model_path: Path
    workload_path: Path
    train_trace_path: Path
    train_access_log: Path
    train_log_path: Path
    model_kind: str
    block_source: str
    look_back: int
    top_k: int
    block_limit: int
    max_block_selects: int
    sql_contains: str


@dataclass(frozen=True)
class SelepTrialPaths:
    trace_path: Path
    sidecar_log: Path
    sidecar_stats: Path
    ready_file: Path


def describe(options: SweepOptions) -> str:
    return (
        f"mode={env_value(options, 'SELEP_MODEL_KIND', 'lstm')} "
        f"top_k={selep_top_k(options)} "
        f"look_back={env_int(options, 'SELEP_LOOK_BACK', 4)} "
        f"blocks={env_value(options, 'SELEP_BLOCK_SOURCE', 'pg-buffercache')}"
    )


def collect_and_train(
    adapter: Any,
    editor: RunConfigEditor,
    state: CaseState,
    spec: RequestSpec,
    limit: int,
    options: SweepOptions,
    config_values_fn,
) -> SelepModelConfig:
    cfg = model_config(adapter, spec, limit, options)
    collect_training_trace(adapter, editor, state, spec, cfg, config_values_fn)
    run_training_script(adapter, cfg, options)
    return cfg


def model_config(
    adapter: Any,
    spec: RequestSpec,
    limit: int,
    options: SweepOptions,
) -> SelepModelConfig:
    safe_walker = safe(spec.walker)
    safe_request = safe(request_id(spec))[:80]
    base_dir = env_path(options, "SELEP_MODEL_DIR", adapter.app_dir / "selep_models", adapter.app_dir)
    model_dir = base_dir / safe_walker / safe_request / f"limit_{limit}"
    logs_dir = adapter.app_dir / options.manifest.logs_dir
    return SelepModelConfig(
        model_path=model_dir / "model.json",
        workload_path=model_dir / "workload.csv",
        train_trace_path=logs_dir / f"selep_train_trace_{safe_walker}_limit{limit}.jsonl",
        train_access_log=logs_dir / f"selep_train_access_{safe_walker}_limit{limit}.csv",
        train_log_path=logs_dir / f"selep_train_{safe_walker}_limit{limit}.log",
        model_kind=env_value(options, "SELEP_MODEL_KIND", "lstm").lower(),
        block_source=env_value(options, "SELEP_BLOCK_SOURCE", "pg-buffercache").lower(),
        look_back=env_int(options, "SELEP_LOOK_BACK", 4),
        top_k=selep_top_k(options),
        block_limit=env_int(options, "SELEP_BLOCK_LIMIT", limit),
        max_block_selects=env_int(options, "SELEP_MAX_BLOCK_SELECTS", 256),
        sql_contains=env_value(options, "SELEP_SQL_CONTAINS", "anchors"),
    )


def collect_training_trace(
    adapter: Any,
    editor: RunConfigEditor,
    state: CaseState,
    spec: RequestSpec,
    cfg: SelepModelConfig,
    config_values_fn,
) -> None:
    cfg.train_trace_path.unlink(missing_ok=True)
    cfg.train_access_log.unlink(missing_ok=True)
    editor.patch(
        config_values_fn(
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
    try:
        proc = adapter.start_server(
            cfg.train_log_path,
            extra_env={"JAC_SELEP_TRACE": str(cfg.train_trace_path)},
        )
        resp = adapter.post(spec.path, spec.body, token=spec.token or state.token)
        adapter.validate_response(spec, resp.json())
    finally:
        process.stop_process(proc)
        adapter.stop_stale_servers()
    if not cfg.train_trace_path.exists() or cfg.train_trace_path.stat().st_size == 0:
        raise RuntimeError(f"SeLeP training produced no SQL trace: {cfg.train_trace_path}")


def run_training_script(adapter: Any, cfg: SelepModelConfig, options: SweepOptions) -> None:
    cfg.model_path.parent.mkdir(parents=True, exist_ok=True)
    selep_python = selep_python_path(options)
    selep_repo = selep_repo_path(options)
    cmd = [
        str(selep_python),
        str(SIDECAR_SCRIPT),
        "train",
        "--trace",
        str(cfg.train_trace_path),
        "--model-out",
        str(cfg.model_path),
        "--workload-out",
        str(cfg.workload_path),
        "--selep-root",
        str(selep_repo),
        "--model-kind",
        cfg.model_kind,
        "--look-back",
        str(cfg.look_back),
        "--top-k",
        str(cfg.top_k),
        "--test-fraction",
        env_value(options, "SELEP_TEST_FRACTION", "0.20"),
        "--partition-size",
        str(env_int(options, "SELEP_PARTITION_SIZE", 8)),
        "--partitions",
        str(env_int(options, "SELEP_HASH_PARTITIONS", 64)),
        "--block-source",
        cfg.block_source,
        "--max-block-selects",
        str(cfg.max_block_selects),
        "--sql-contains",
        cfg.sql_contains,
        "--db-mode",
        adapter.db_manager.settings.mode,
        "--postgres-container",
        adapter.db_manager.postgres_container,
        "--postgres-user",
        adapter.db_manager.postgres_user,
        "--postgres-db",
        adapter.db_manager.postgres_db,
        "--lstm-epochs",
        str(env_int(options, "SELEP_LSTM_EPOCHS", 5)),
        "--lstm-batch-size",
        str(env_int(options, "SELEP_LSTM_BATCH_SIZE", 16)),
        "--lstm-validation-fraction",
        env_value(options, "SELEP_LSTM_VALIDATION_FRACTION", "0.10"),
        "--lstm-seed",
        str(env_int(options, "SELEP_LSTM_SEED", 42)),
    ]
    settings = adapter.db_manager.settings
    if settings.mode == "remote_ssh":
        cmd.extend(["--ssh-target", settings.ssh_target])
        for opt in settings.ssh_options:
            cmd.append(f"--ssh-option={opt}")

    with cfg.train_log_path.open("a", buffering=1) as log:
        log.write("\n=== SeLeP training command ===\n")
        log.write(" ".join(str(part) for part in cmd) + "\n")
        proc = subprocess.run(
            cmd,
            cwd=str(SWEEP_TOOL_ROOT),
            env={**os.environ.copy(), **options.env},
            text=True,
            stdout=log,
            stderr=subprocess.STDOUT,
            check=False,
        )
    if proc.returncode != 0:
        raise RuntimeError(f"SeLeP training failed; see {cfg.train_log_path}")
    if not cfg.model_path.exists():
        raise RuntimeError(f"SeLeP training did not write model: {cfg.model_path}")


def trial_paths(adapter: Any, spec: RequestSpec, limit: int, trial: int) -> SelepTrialPaths:
    logs_dir = adapter.app_dir / adapter.options.manifest.logs_dir
    safe_walker = safe(spec.walker)
    suffix = f"{safe_walker}_policyselep_limit{limit}_trial{trial}"
    return SelepTrialPaths(
        trace_path=logs_dir / f"selep_live_trace_{suffix}.jsonl",
        sidecar_log=logs_dir / f"selep_sidecar_{suffix}.log",
        sidecar_stats=logs_dir / f"selep_sidecar_{suffix}.json",
        ready_file=logs_dir / f"selep_sidecar_{suffix}.ready",
    )


@contextmanager
def start_sidecar(
    adapter: Any,
    cfg: SelepModelConfig,
    paths: SelepTrialPaths,
    options: SweepOptions,
) -> Iterator[None]:
    for path in (paths.trace_path, paths.sidecar_stats, paths.ready_file):
        path.unlink(missing_ok=True)
    selep_python = selep_python_path(options)
    selep_repo = selep_repo_path(options)
    cmd = [
        str(selep_python),
        str(SIDECAR_SCRIPT),
        "serve",
        "--model",
        str(cfg.model_path),
        "--trace",
        str(paths.trace_path),
        "--postgres-uri",
        adapter.postgres_uri,
        "--stats",
        str(paths.sidecar_stats),
        "--ready-file",
        str(paths.ready_file),
        "--selep-root",
        str(selep_repo),
        "--top-k",
        str(cfg.top_k),
        "--block-limit",
        str(cfg.block_limit),
    ]
    log_fh = paths.sidecar_log.open("w", buffering=1)
    log_fh.write(" ".join(cmd) + "\n")
    proc = subprocess.Popen(
        cmd,
        cwd=str(SWEEP_TOOL_ROOT),
        env={**os.environ.copy(), **options.env},
        stdout=log_fh,
        stderr=subprocess.STDOUT,
        text=True,
        start_new_session=True,
    )
    try:
        wait_ready(proc, paths.ready_file, paths.sidecar_log)
        yield
    finally:
        stop_process_group(proc)
        log_fh.close()


def load_stats(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def wait_ready(proc: subprocess.Popen, ready_file: Path, log_path: Path, timeout_sec: float = 60.0) -> None:
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        if ready_file.exists():
            return
        if proc.poll() is not None:
            tail = ""
            try:
                tail = "\n".join(log_path.read_text(errors="replace").splitlines()[-40:])
            except FileNotFoundError:
                pass
            raise RuntimeError(f"SeLeP sidecar exited before ready; see {log_path}\n{tail}")
        time.sleep(0.2)
    raise TimeoutError(f"SeLeP sidecar did not become ready; see {log_path}")


def stop_process_group(proc: subprocess.Popen | None, timeout_sec: float = 5.0) -> None:
    if proc is None or proc.poll() is not None:
        return
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except OSError:
        return
    deadline = time.time() + timeout_sec
    while time.time() < deadline and proc.poll() is None:
        time.sleep(0.1)
    if proc.poll() is None:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except OSError:
            pass


def env_value(options: SweepOptions, name: str, default: str) -> str:
    value = options.env.get(name)
    return str(value).strip() if value not in (None, "") else default


def env_int(options: SweepOptions, name: str, default: int) -> int:
    raw = options.env.get(name)
    if raw in (None, ""):
        return default
    return int(str(raw).strip())


def env_bool(options: SweepOptions, name: str, default: bool = False) -> bool:
    raw = options.env.get(name)
    if raw in (None, ""):
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def selep_top_k(options: SweepOptions) -> int:
    raw = options.env.get("SELEP_TOP_K") or options.env.get("SELEP_PREFETCHING_K")
    return int(raw) if raw else 42


def env_path(options: SweepOptions, name: str, default: Path, base_dir: Path) -> Path:
    raw = options.env.get(name)
    if not raw:
        return default
    path = Path(raw).expanduser()
    return path if path.is_absolute() else base_dir / path


def selep_repo_path(options: SweepOptions) -> Path:
    raw = options.env.get("SELEP_REPO")
    if raw:
        return Path(raw).expanduser().resolve()
    if Path("/workspace/SeLeP").exists():
        return Path("/workspace/SeLeP")
    return DEFAULT_SELEP_REPO.resolve()


def selep_python_path(options: SweepOptions) -> Path:
    raw = options.env.get("SELEP_PYTHON")
    if raw:
        return Path(raw).expanduser()
    image_python = Path("/opt/selep-venv/bin/python")
    if image_python.exists():
        return image_python
    repo = selep_repo_path(options)
    for candidate in (repo / ".venv-lstm" / "bin" / "python", repo / ".venv" / "bin" / "python"):
        if candidate.exists():
            return candidate
    return Path("python3")


def request_id(spec: RequestSpec) -> str:
    if spec.request_id:
        return str(spec.request_id)
    if spec.target_id:
        return str(spec.target_id)
    return f"{spec.walker}:{spec.path}:{json.dumps(spec.body, sort_keys=True)}"


def safe(raw: str) -> str:
    return "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in raw) or "default"
