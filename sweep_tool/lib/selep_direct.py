"""Direct runner support for the original SeLeP SQL/block baseline.

This module intentionally keeps SeLeP separate from Jac UUID prefetch
policies.  The original SeLeP code consumes SQL workload text files and
Postgres block/partition metadata; it should be launched as its own
baseline rather than translated into a Jac prefetch plan.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path


SWEEP_TOOL_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SELEP_REPO = SWEEP_TOOL_ROOT.parents[1] / "SeLeP"
def _default_selep_python() -> Path:
    for candidate in (
        DEFAULT_SELEP_REPO / ".devenv" / "state" / "venv" / "bin" / "python",
        DEFAULT_SELEP_REPO / ".venv-lstm" / "bin" / "python",
        DEFAULT_SELEP_REPO / ".venv" / "bin" / "python",
    ):
        if candidate.exists():
            return candidate
    return DEFAULT_SELEP_REPO / ".devenv" / "state" / "venv" / "bin" / "python"


DEFAULT_SELEP_PYTHON = _default_selep_python()
LOG_PATH = SWEEP_TOOL_ROOT / "selep_direct.log"
PID_PATH = SWEEP_TOOL_ROOT / "selep_direct.pid"
METADATA_PATH = SWEEP_TOOL_ROOT / "selep_direct_last_run.json"

SELEP_TEST_NAMES = (
    "test1_1gen",
    "test1_2",
    "test2_1",
    "test2_2",
    "test3_1",
    "test3_2",
    "testMixed2",
    "testMixed9",
)


@dataclass(frozen=True)
class SelepDirectConfig:
    repo: Path = DEFAULT_SELEP_REPO
    python: Path = DEFAULT_SELEP_PYTHON
    mode: str = "train-test"
    db_name: str = "sdss_1"
    db_user: str = "user"
    db_password: str = "pass"
    db_host: str = "127.0.0.1"
    db_port: str = "5432"
    model_name: str = "binary_cross_entropy2"
    result_name: str = "binary_lstm2"
    config_suffix: str = ""
    test_repeat: int = 1
    total_repeat: int = 1
    cache_size: int = 66000
    prefetching_k: int = 42
    max_partition_size: int = 128
    logical_block_size: int = 8
    look_back: int = 4
    measure_time: bool = False
    optimize: bool = False
    read_table_manager: bool = False
    read_partition_manager: bool = False
    read_affinity_matrix: bool = False
    save_to_file: bool = True

    @property
    def do_train(self) -> bool:
        return self.mode == "train-test"

    @property
    def do_test(self) -> bool:
        return self.mode in {"test", "train-test"}


@dataclass(frozen=True)
class LaunchInfo:
    pid: int
    env_overrides: dict[str, str]
    stdout_log: Path


def _bool(value: str | bool | int | None, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return bool(value)
    return value.strip().lower() in {"1", "true", "yes", "on"}


def config_from_env(env: dict[str, str] | None = None) -> SelepDirectConfig:
    env = env or os.environ
    repo = Path(env.get("SELEP_REPO", str(DEFAULT_SELEP_REPO))).expanduser()
    python = Path(env.get("SELEP_PYTHON", str(_default_selep_python()))).expanduser()
    return SelepDirectConfig(
        repo=repo.resolve(),
        python=python.resolve(),
        mode=env.get("SELEP_MODE", "train-test"),
        db_name=env.get("SELEP_DB_NAME", "sdss_1"),
        db_user=env.get("SELEP_DB_USER", "user"),
        db_password=env.get("SELEP_DB_PASSWORD", "pass"),
        db_host=env.get("SELEP_DB_HOST", "127.0.0.1"),
        db_port=env.get("SELEP_DB_PORT", "5432"),
        model_name=env.get("SELEP_MODEL_NAME", "binary_cross_entropy2"),
        result_name=env.get("SELEP_RESULT_NAME", "binary_lstm2"),
        config_suffix=env.get("SELEP_CONFIG_SUFFIX", ""),
        test_repeat=int(env.get("SELEP_TEST_REPEAT", "1")),
        total_repeat=int(env.get("SELEP_TOTAL_REPEAT", "1")),
        cache_size=int(env.get("SELEP_CACHE_SIZE", "66000")),
        prefetching_k=int(env.get("SELEP_PREFETCHING_K", "42")),
        max_partition_size=int(env.get("SELEP_MAX_PARTITION_SIZE", "128")),
        logical_block_size=int(env.get("SELEP_LOGICAL_BLOCK_SIZE", "8")),
        look_back=int(env.get("SELEP_LOOK_BACK", "4")),
        measure_time=_bool(env.get("SELEP_MEASURE_TIME")),
        optimize=_bool(env.get("SELEP_OPTIMIZE")),
        read_table_manager=_bool(env.get("SELEP_READ_TABLE_MANAGER")),
        read_partition_manager=_bool(env.get("SELEP_READ_PARTITION_MANAGER")),
        read_affinity_matrix=_bool(env.get("SELEP_READ_AFFINITY_MATRIX")),
        save_to_file=_bool(env.get("SELEP_SAVE_TO_FILE"), default=True),
    )


def env_from_config(config: SelepDirectConfig) -> dict[str, str]:
    return {
        "SELEP_REPO": str(config.repo),
        "SELEP_PYTHON": str(config.python),
        "SELEP_MODE": config.mode,
        "SELEP_DB_NAME": config.db_name,
        "SELEP_DB_USER": config.db_user,
        "SELEP_DB_PASSWORD": config.db_password,
        "SELEP_DB_HOST": config.db_host,
        "SELEP_DB_PORT": config.db_port,
        "SELEP_MODEL_NAME": config.model_name,
        "SELEP_RESULT_NAME": config.result_name,
        "SELEP_CONFIG_SUFFIX": config.config_suffix,
        "SELEP_TEST_REPEAT": str(config.test_repeat),
        "SELEP_TOTAL_REPEAT": str(config.total_repeat),
        "SELEP_CACHE_SIZE": str(config.cache_size),
        "SELEP_PREFETCHING_K": str(config.prefetching_k),
        "SELEP_MAX_PARTITION_SIZE": str(config.max_partition_size),
        "SELEP_LOGICAL_BLOCK_SIZE": str(config.logical_block_size),
        "SELEP_LOOK_BACK": str(config.look_back),
        "SELEP_MEASURE_TIME": "1" if config.measure_time else "0",
        "SELEP_OPTIMIZE": "1" if config.optimize else "0",
        "SELEP_READ_TABLE_MANAGER": "1" if config.read_table_manager else "0",
        "SELEP_READ_PARTITION_MANAGER": "1" if config.read_partition_manager else "0",
        "SELEP_READ_AFFINITY_MATRIX": "1" if config.read_affinity_matrix else "0",
        "SELEP_SAVE_TO_FILE": "1" if config.save_to_file else "0",
    }


def workload_stem(config: SelepDirectConfig, name: str) -> str:
    return (
        f"{config.db_name}_{name}{config.config_suffix}"
        f"WB{config.logical_block_size}WP{config.max_partition_size}"
    )


def expected_workload_files(config: SelepDirectConfig) -> list[Path]:
    files: list[Path] = []
    if config.do_train:
        files.append(config.repo / f"{workload_stem(config, 'all_train')}.txt")
    if config.do_test:
        files.extend(config.repo / f"{workload_stem(config, name)}.txt" for name in SELEP_TEST_NAMES)
    return files


def expected_saved_files(config: SelepDirectConfig) -> list[Path]:
    files = [
        config.repo / "Data" / f"{config.db_name}_tableLookUp.txt",
        config.repo / "Data" / "pcaExclude.txt",
    ]
    if config.mode == "test":
        files.extend(
            [
                config.repo / "SavedFiles" / "Models" / f"{config.model_name}.json",
                config.repo / "SavedFiles" / "Models" / f"{config.model_name}.h5",
            ]
        )
    return files


def validate(config: SelepDirectConfig) -> list[str]:
    problems: list[str] = []
    if config.mode not in {"test", "train-test"}:
        problems.append("SELEP_MODE must be one of: test, train-test")
    if not config.repo.exists():
        problems.append(f"SeLeP repo does not exist: {config.repo}")
    if not config.python.exists():
        problems.append(f"SeLeP python does not exist: {config.python}")
    if not (config.repo / "selep_main.py").exists():
        problems.append(f"Missing original SeLeP entrypoint: {config.repo / 'selep_main.py'}")
    for path in expected_saved_files(config):
        if not path.exists():
            problems.append(f"Missing required SeLeP file: {path}")
    for path in expected_workload_files(config):
        if not path.exists():
            problems.append(f"Missing workload file: {path}")
    return problems


def write_metadata(config: SelepDirectConfig, status: str, problems: list[str] | None = None) -> None:
    data = {
        "status": status,
        "repo": str(config.repo),
        "python": str(config.python),
        "mode": config.mode,
        "db_name": config.db_name,
        "db_host": config.db_host,
        "db_port": config.db_port,
        "model_name": config.model_name,
        "result_name": config.result_name,
        "config_suffix": config.config_suffix,
        "test_repeat": config.test_repeat,
        "total_repeat": config.total_repeat,
        "cache_size": config.cache_size,
        "prefetching_k": config.prefetching_k,
        "max_partition_size": config.max_partition_size,
        "logical_block_size": config.logical_block_size,
        "look_back": config.look_back,
        "measure_time": config.measure_time,
        "optimize": config.optimize,
        "read_table_manager": config.read_table_manager,
        "read_partition_manager": config.read_partition_manager,
        "read_affinity_matrix": config.read_affinity_matrix,
        "save_to_file": config.save_to_file,
        "expected_workloads": [str(p) for p in expected_workload_files(config)],
        "problems": problems or [],
    }
    METADATA_PATH.write_text(json.dumps(data, indent=2, sort_keys=True))


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
        return "no direct SeLeP run is currently running"
    try:
        pid = int(PID_PATH.read_text().strip())
    except ValueError:
        PID_PATH.unlink(missing_ok=True)
        return "SeLeP pid file was garbled; removed"

    def _alive() -> bool:
        try:
            os.kill(pid, 0)
        except OSError:
            return False
        return True

    if not _alive():
        PID_PATH.unlink(missing_ok=True)
        return f"direct SeLeP process {pid} was already gone"

    try:
        os.killpg(pid, signal.SIGTERM)
    except OSError as e:
        PID_PATH.unlink(missing_ok=True)
        return f"could not signal direct SeLeP pgid {pid}: {e}"

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
    return f"stopped direct SeLeP pid={pid} via {outcome}"


def kickoff(config: SelepDirectConfig) -> LaunchInfo:
    problems = validate(config)
    if problems:
        write_metadata(config, "blocked", problems)
        raise RuntimeError("\n".join(problems))

    env_overrides = env_from_config(config)
    env = os.environ.copy()
    env.update(env_overrides)

    log_fh = open(LOG_PATH, "w", buffering=1)
    try:
        cmd = [
            str(config.python),
            str(SWEEP_TOOL_ROOT / "tools" / "run_selep_direct.py"),
            "--from-env",
        ]
        proc = subprocess.Popen(
            cmd,
            cwd=str(SWEEP_TOOL_ROOT),
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
