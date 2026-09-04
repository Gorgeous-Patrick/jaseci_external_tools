"""Launcher support for the LinkedList SeLeP LSTM smoke experiment."""

from __future__ import annotations

import json
import os
import shlex
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path


SWEEP_TOOL_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = SWEEP_TOOL_ROOT.parent
LINKED_LIST_ROOT = REPO_ROOT / "linked_list"
DEFAULT_SELEP_REPO = Path(
    os.environ.get("SELEP_REPO", str(SWEEP_TOOL_ROOT.parents[1] / "SeLeP"))
)
def _default_selep_python() -> Path:
    for candidate in (
        Path("/opt/selep-venv/bin/python"),
        DEFAULT_SELEP_REPO / ".devenv" / "state" / "venv" / "bin" / "python",
        DEFAULT_SELEP_REPO / ".venv-lstm" / "bin" / "python",
        DEFAULT_SELEP_REPO / ".venv" / "bin" / "python",
    ):
        if candidate.exists():
            return candidate
    return DEFAULT_SELEP_REPO / ".devenv" / "state" / "venv" / "bin" / "python"


DEFAULT_SELEP_PYTHON = Path(os.environ.get("SELEP_PYTHON", str(_default_selep_python())))


def _path_exists(path: str | Path) -> bool:
    try:
        return Path(path).exists()
    except PermissionError:
        return False


DEFAULT_SWEEP_PYTHON = (
    REPO_ROOT / ".venv" / "bin" / "python"
    if (REPO_ROOT / ".venv" / "bin" / "python").exists()
    else Path(sys.executable)
)
DEFAULT_JAC_BIN = Path("/home/patrickli/Space/jaseci/jac/zig-out/bin/jac")
DEFAULT_OUT_DIR = LINKED_LIST_ROOT / "selep_smoke"
DEFAULT_SSH_OPTIONS = os.environ.get(
    "SWEEP_DB_SSH_OPTIONS",
    "-F /root/.ssh/config -o UserKnownHostsFile=/tmp/known_hosts -o StrictHostKeyChecking=accept-new"
    if _path_exists("/root/.ssh/config")
    else "-F /home/patrickli/.ssh/config",
)

LOG_PATH = SWEEP_TOOL_ROOT / "selep_lstm.log"
PID_PATH = SWEEP_TOOL_ROOT / "selep_lstm.pid"
METADATA_PATH = SWEEP_TOOL_ROOT / "selep_lstm_last_run.json"


@dataclass(frozen=True)
class SelepSweepConfig:
    selep_repo: Path = DEFAULT_SELEP_REPO
    selep_python: Path = DEFAULT_SELEP_PYTHON
    sweep_python: Path = DEFAULT_SWEEP_PYTHON
    jac_bin: Path = DEFAULT_JAC_BIN
    out_dir: Path = DEFAULT_OUT_DIR
    model_kind: str = "lstm"
    list_size: int = 24
    trials: int = 1
    look_back: int = 2
    top_k: int = 4
    test_fraction: float = 0.30
    lstm_epochs: int = 20
    lstm_batch_size: int = 4
    lstm_validation_fraction: float = 0.10
    lstm_seed: int = 42
    partitions: int = 64
    block_source: str = "pg-buffercache"
    max_block_selects: int = 20
    sql_contains: str = ""
    ssh_target: str = "clarity2"
    ssh_options: str = DEFAULT_SSH_OPTIONS
    postgres_container: str = "postgres"
    postgres_user: str = "jac"
    postgres_db: str = "jac_db"
    partition_size: int = 8
    skip_collect: bool = False
    skip_workload_rebuild: bool = False

    @property
    def summary_path(self) -> Path:
        return self.out_dir / "summary.json"


@dataclass(frozen=True)
class LaunchInfo:
    pid: int
    env_overrides: dict[str, str]
    stdout_log: Path


def _tool_path() -> Path:
    return SWEEP_TOOL_ROOT / "tools" / "run_linked_list_selep_smoke.py"


def _as_path(value: str | Path) -> Path:
    return Path(value).expanduser().resolve()


def validate(config: SelepSweepConfig) -> list[str]:
    problems: list[str] = []
    if config.model_kind not in {"frequency", "lstm"}:
        problems.append("model_kind must be frequency or lstm")
    if config.block_source not in {"hash", "pg-buffercache"}:
        problems.append("block_source must be hash or pg-buffercache")
    for name, path in (
        ("SeLeP repo", config.selep_repo),
        ("SeLeP python", config.selep_python),
        ("Sweep python", config.sweep_python),
        ("LinkedList app", LINKED_LIST_ROOT),
        ("runner script", _tool_path()),
    ):
        if not path.exists():
            problems.append(f"{name} does not exist: {path}")
    if config.model_kind == "lstm" and not (config.selep_repo / "Backend" / "Models" / "LSTM.py").exists():
        problems.append(f"SeLeP LSTM.py is missing under {config.selep_repo}")
    if "/" in str(config.jac_bin) and not config.jac_bin.exists():
        problems.append(f"jac binary does not exist: {config.jac_bin}")
    if config.skip_workload_rebuild and not config.skip_collect:
        problems.append("skip_workload_rebuild requires skip_collect")
    if config.skip_workload_rebuild and not (config.out_dir / "workload.csv").exists():
        problems.append(f"existing workload.csv is missing: {config.out_dir / 'workload.csv'}")
    if config.list_size <= 0:
        problems.append("list_size must be positive")
    if config.trials <= 0:
        problems.append("trials must be positive")
    if config.look_back <= 0:
        problems.append("look_back must be positive")
    if config.top_k <= 0:
        problems.append("top_k must be positive")
    if config.lstm_epochs <= 0:
        problems.append("lstm_epochs must be positive")
    if config.lstm_batch_size <= 0:
        problems.append("lstm_batch_size must be positive")
    if not 0.0 <= config.test_fraction < 1.0:
        problems.append("test_fraction must be in [0, 1)")
    if not 0.0 <= config.lstm_validation_fraction < 1.0:
        problems.append("lstm_validation_fraction must be in [0, 1)")
    if config.block_source == "pg-buffercache" and not config.skip_workload_rebuild and not config.ssh_target:
        problems.append("ssh_target is required for pg-buffercache block collection")
    return problems


def command_from_config(config: SelepSweepConfig) -> list[str]:
    cmd = [
        str(config.selep_python),
        str(_tool_path()),
        "--jac-bin",
        str(config.jac_bin),
        "--python",
        str(config.sweep_python),
        "--out-dir",
        str(config.out_dir),
        "--list-size",
        str(config.list_size),
        "--trials",
        str(config.trials),
        "--look-back",
        str(config.look_back),
        "--top-k",
        str(config.top_k),
        "--test-fraction",
        str(config.test_fraction),
        "--model-kind",
        config.model_kind,
        "--selep-root",
        str(config.selep_repo),
        "--lstm-epochs",
        str(config.lstm_epochs),
        "--lstm-batch-size",
        str(config.lstm_batch_size),
        "--lstm-validation-fraction",
        str(config.lstm_validation_fraction),
        "--lstm-seed",
        str(config.lstm_seed),
        "--partitions",
        str(config.partitions),
        "--block-source",
        config.block_source,
        "--max-block-selects",
        str(config.max_block_selects),
        "--sql-contains",
        config.sql_contains,
        "--ssh-target",
        config.ssh_target,
        "--postgres-container",
        config.postgres_container,
        "--postgres-user",
        config.postgres_user,
        "--postgres-db",
        config.postgres_db,
        "--partition-size",
        str(config.partition_size),
    ]
    for option in shlex.split(config.ssh_options):
        cmd.append(f"--ssh-option={option}")
    if config.skip_collect:
        cmd.append("--skip-collect")
    if config.skip_workload_rebuild:
        cmd.append("--skip-workload-rebuild")
    return cmd


def metadata_from_config(config: SelepSweepConfig, status: str, problems: list[str] | None = None) -> dict[str, object]:
    return {
        "status": status,
        "selep_repo": str(config.selep_repo),
        "selep_python": str(config.selep_python),
        "sweep_python": str(config.sweep_python),
        "jac_bin": str(config.jac_bin),
        "out_dir": str(config.out_dir),
        "model_kind": config.model_kind,
        "list_size": config.list_size,
        "trials": config.trials,
        "look_back": config.look_back,
        "top_k": config.top_k,
        "test_fraction": config.test_fraction,
        "lstm_epochs": config.lstm_epochs,
        "lstm_batch_size": config.lstm_batch_size,
        "lstm_validation_fraction": config.lstm_validation_fraction,
        "lstm_seed": config.lstm_seed,
        "partitions": config.partitions,
        "block_source": config.block_source,
        "max_block_selects": config.max_block_selects,
        "sql_contains": config.sql_contains,
        "ssh_target": config.ssh_target,
        "ssh_options": config.ssh_options,
        "postgres_container": config.postgres_container,
        "postgres_user": config.postgres_user,
        "postgres_db": config.postgres_db,
        "partition_size": config.partition_size,
        "skip_collect": config.skip_collect,
        "skip_workload_rebuild": config.skip_workload_rebuild,
        "command": " ".join(shlex.quote(part) for part in command_from_config(config)),
        "summary": str(config.summary_path),
        "problems": problems or [],
    }


def config_from_metadata(data: dict[str, object]) -> SelepSweepConfig:
    return SelepSweepConfig(
        selep_repo=Path(str(data["selep_repo"])),
        selep_python=Path(str(data["selep_python"])),
        sweep_python=Path(str(data["sweep_python"])),
        jac_bin=Path(str(data["jac_bin"])),
        out_dir=Path(str(data["out_dir"])),
        model_kind=str(data["model_kind"]),
        list_size=int(data["list_size"]),
        trials=int(data["trials"]),
        look_back=int(data["look_back"]),
        top_k=int(data["top_k"]),
        test_fraction=float(data["test_fraction"]),
        lstm_epochs=int(data["lstm_epochs"]),
        lstm_batch_size=int(data["lstm_batch_size"]),
        lstm_validation_fraction=float(data["lstm_validation_fraction"]),
        lstm_seed=int(data["lstm_seed"]),
        partitions=int(data["partitions"]),
        block_source=str(data["block_source"]),
        max_block_selects=int(data["max_block_selects"]),
        sql_contains=str(data["sql_contains"]),
        ssh_target=str(data["ssh_target"]),
        ssh_options=str(data["ssh_options"]),
        postgres_container=str(data["postgres_container"]),
        postgres_user=str(data["postgres_user"]),
        postgres_db=str(data["postgres_db"]),
        partition_size=int(data["partition_size"]),
        skip_collect=bool(data["skip_collect"]),
        skip_workload_rebuild=bool(data["skip_workload_rebuild"]),
    )


def write_metadata(config: SelepSweepConfig, status: str, problems: list[str] | None = None) -> None:
    METADATA_PATH.write_text(
        json.dumps(metadata_from_config(config, status, problems), indent=2, sort_keys=True)
    )


def is_running() -> tuple[bool, int | None]:
    if not PID_PATH.exists():
        return False, None
    try:
        pid = int(PID_PATH.read_text().strip())
    except ValueError:
        return False, None
    try:
        os.kill(pid, 0)
    except OSError:
        return False, pid
    return True, pid


def kill(timeout_sec: float = 5.0) -> str:
    if not PID_PATH.exists():
        return "no SeLeP LSTM experiment is currently running"
    try:
        pid = int(PID_PATH.read_text().strip())
    except ValueError:
        PID_PATH.unlink(missing_ok=True)
        return "SeLeP LSTM pid file was garbled; removed"

    def _alive() -> bool:
        try:
            os.kill(pid, 0)
        except OSError:
            return False
        return True

    if not _alive():
        PID_PATH.unlink(missing_ok=True)
        return f"SeLeP LSTM process {pid} was already gone"

    try:
        os.killpg(pid, signal.SIGTERM)
    except OSError as e:
        PID_PATH.unlink(missing_ok=True)
        return f"could not signal SeLeP LSTM pgid {pid}: {e}"

    deadline = time.time() + timeout_sec
    while time.time() < deadline and _alive():
        time.sleep(0.1)

    if _alive():
        try:
            os.killpg(pid, signal.SIGKILL)
        except OSError:
            pass
        time.sleep(0.2)
        outcome = "SIGKILL (after SIGTERM timeout)"
    else:
        outcome = "SIGTERM (graceful)"

    PID_PATH.unlink(missing_ok=True)
    return f"stopped SeLeP LSTM pid={pid} via {outcome}"


def kickoff(config: SelepSweepConfig) -> LaunchInfo:
    problems = validate(config)
    if problems:
        write_metadata(config, "blocked", problems)
        raise RuntimeError("\n".join(problems))

    env_overrides = {
        "PYTHONUNBUFFERED": "1",
        "TF_CPP_MIN_LOG_LEVEL": "1",
        "OMP_NUM_THREADS": "2",
        "TF_NUM_INTRAOP_THREADS": "2",
        "TF_NUM_INTEROP_THREADS": "1",
    }
    env = os.environ.copy()
    env.update(env_overrides)

    log_fh = open(LOG_PATH, "w", buffering=1)
    try:
        proc = subprocess.Popen(
            [sys.executable, str(SWEEP_TOOL_ROOT / "tools" / "run_selep_lstm.py")],
            cwd=str(REPO_ROOT),
            env=env,
            stdout=log_fh,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    finally:
        log_fh.close()

    PID_PATH.write_text(str(proc.pid))
    write_metadata(config, "running")
    return LaunchInfo(pid=proc.pid, env_overrides=env_overrides, stdout_log=LOG_PATH)
