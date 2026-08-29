"""Fire-and-forget sweep runner.

Kicks off `bash <sweep_script>` in the app_dir as a detached subprocess
so the sweep survives Streamlit restarts.  No archiving — the Analyze
and Raw tabs read whatever's currently on disk in the app_dir.
Reproducibility / snapshotting is the user's responsibility (git).
"""

from __future__ import annotations

import os
import shlex
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from lib.prefetch_exp import db as db_config

from .manifest import Manifest


_RUN_ALL_ROOT = Path(__file__).resolve().parent.parent  # sweep_tool/


def default_jac_bin() -> str:
    """Prefer the editable jaseci_env runtime over older standalone builds."""
    if os.environ.get("JAC_BIN"):
        return os.environ["JAC_BIN"]
    candidates = [
        Path.home() / "Space" / "jaseci_env" / "jaseci" / ".venv" / "bin" / "jac",
        Path.home() / "Space" / "jaseci" / "jac" / "zig-out" / "bin" / "jac",
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return "jac"


DEFAULT_JAC_BIN = default_jac_bin()


@dataclass
class LaunchInfo:
    pid: int
    app: str
    env_overrides: dict[str, str]
    stdout_log: Path


def stdout_log_path(manifest: Manifest) -> Path:
    """Where a sweep's combined stdout/stderr is captured for this app.

    One file per app inside the app_dir (git-ignore-friendly and colocated
    with the other sweep outputs).  Overwritten by each fresh launch.
    """
    return manifest.app_dir / "sweep_stdout.log"


def jacord_churn_stdout_log_path(manifest: Manifest) -> Path:
    return manifest.app_dir / "churn_stdout.log"


def pid_file(manifest: Manifest) -> Path:
    """Records the running sweep's PID so we can find and kill it even
    across Streamlit restarts."""
    return manifest.app_dir / "sweep.pid"


def jacord_churn_pid_file(manifest: Manifest) -> Path:
    return manifest.app_dir / "churn.pid"


def is_running(manifest: Manifest) -> tuple[bool, int | None]:
    """(running, pid).  running is True iff the recorded PID is still
    alive."""
    pf = pid_file(manifest)
    if not pf.exists():
        return False, None
    try:
        pid = int(pf.read_text().strip())
    except ValueError:
        return False, None
    try:
        os.kill(pid, 0)  # signal 0 = existence check
    except OSError:
        return False, pid
    return True, pid


def is_jacord_churn_running(manifest: Manifest) -> tuple[bool, int | None]:
    pf = jacord_churn_pid_file(manifest)
    if not pf.exists():
        return False, None
    try:
        pid = int(pf.read_text().strip())
    except ValueError:
        return False, None
    try:
        os.kill(pid, 0)
    except OSError:
        return False, pid
    return True, pid


def kill(manifest: Manifest, timeout_sec: float = 5.0) -> str:
    """Try to stop the running sweep cleanly.

    Because kickoff() used start_new_session=True, the child bash is
    the leader of its own process group — SIGTERM/SIGKILL to that pgid
    reaches every descendant (nested `jac start`, `python`, etc.).
    Returns a short human-readable status.
    """
    pf = pid_file(manifest)
    if not pf.exists():
        return "no sweep is currently running"
    try:
        pid = int(pf.read_text().strip())
    except ValueError:
        pf.unlink(missing_ok=True)
        return "pid file was garbled; removed"

    def _alive() -> bool:
        try:
            os.kill(pid, 0)
        except OSError:
            return False
        return True

    if not _alive():
        pf.unlink(missing_ok=True)
        return f"process {pid} was already gone"

    # Graceful SIGTERM to the whole process group first.
    try:
        os.killpg(pid, signal.SIGTERM)
    except OSError as e:
        pf.unlink(missing_ok=True)
        return f"could not signal pgid {pid}: {e}"

    # Wait for it to actually exit.
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

    # Belt-and-suspenders: sweep_prefetch_limit.sh spawns Jac servers
    # backgrounded; those should be inside the killed pgid already, but
    # older Bash setups sometimes disown.  Best-effort sweep.
    for pattern in ("jac run --serve", "jac start"):
        subprocess.run(
            ["pkill", "-9", "-f", pattern],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    pf.unlink(missing_ok=True)
    return f"stopped pid={pid} via {outcome}"


def kill_jacord_churn(manifest: Manifest, timeout_sec: float = 5.0) -> str:
    pf = jacord_churn_pid_file(manifest)
    if not pf.exists():
        return "no Jacord churn experiment is currently running"
    try:
        pid = int(pf.read_text().strip())
    except ValueError:
        pf.unlink(missing_ok=True)
        return "churn pid file was garbled; removed"

    def _alive() -> bool:
        try:
            os.kill(pid, 0)
        except OSError:
            return False
        return True

    if not _alive():
        pf.unlink(missing_ok=True)
        return f"Jacord churn process {pid} was already gone"

    try:
        os.killpg(pid, signal.SIGTERM)
    except OSError as e:
        pf.unlink(missing_ok=True)
        return f"could not signal Jacord churn pgid {pid}: {e}"

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

    for pattern in ("jac run --serve", "jac start"):
        subprocess.run(
            ["pkill", "-9", "-f", pattern],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    pf.unlink(missing_ok=True)
    return f"stopped Jacord churn pid={pid} via {outcome}"


def kickoff(
    manifest: Manifest, form_values: dict, jac_bin: str | None = None
) -> LaunchInfo:
    """Start the sweep as a detached subprocess.  Returns immediately.

    ``jac_bin`` selects which jac binary the sweep runs against; it is
    exported as JAC_BIN, which the sweep scripts honour via ${JAC_BIN:-jac}.
    """
    env_overrides = manifest.env_from_form(form_values)
    if jac_bin:
        env_overrides["JAC_BIN"] = jac_bin
    env = os.environ.copy()
    env.update(env_overrides)

    log_path = stdout_log_path(manifest)
    # Opened in the parent, inherited by the child.  After detach the
    # parent's handle can be closed safely — the child keeps writing.
    log_fh = open(log_path, "w", buffering=1)  # line-buffered
    try:
        if manifest.runner == "prefetch_python":
            cmd = [
                sys.executable,
                "-m",
                "lib.prefetch_exp.cli",
                "--manifest",
                str(manifest.manifest_path),
            ]
            if jac_bin:
                cmd.extend(["--jac-bin", jac_bin])
            cwd = str(_RUN_ALL_ROOT)
        else:
            cmd = ["bash", manifest.sweep_script]
            cwd = str(manifest.app_dir)
        proc = subprocess.Popen(
            cmd,
            cwd=cwd,
            env=env,
            stdout=log_fh,
            stderr=subprocess.STDOUT,
            start_new_session=True,  # detach — survives Streamlit restart
        )
    finally:
        log_fh.close()
    # Record the PID so a later Streamlit session can find + kill it.
    pid_file(manifest).write_text(str(proc.pid))
    return LaunchInfo(
        pid=proc.pid,
        app=manifest.name,
        env_overrides=env_overrides,
        stdout_log=log_path,
    )


def kickoff_jacord_churn(
    manifest: Manifest,
    form_values: dict,
    jac_bin: str | None = None,
) -> LaunchInfo:
    """Start the dedicated Jacord churn experiment as a detached process."""
    env_overrides = {
        key: str(value)
        for key, value in form_values.items()
        if value is not None and str(value) != ""
    }
    if jac_bin:
        env_overrides["JAC_BIN"] = jac_bin
    env = os.environ.copy()
    env.update(env_overrides)

    log_path = jacord_churn_stdout_log_path(manifest)
    log_fh = open(log_path, "w", buffering=1)
    try:
        cmd = [
            sys.executable,
            str(_RUN_ALL_ROOT / "tools" / "run_jacord_churn.py"),
            "--manifest",
            str(manifest.manifest_path),
        ]
        if jac_bin:
            cmd.extend(["--jac-bin", jac_bin])
        proc = subprocess.Popen(
            cmd,
            cwd=str(_RUN_ALL_ROOT),
            env=env,
            stdout=log_fh,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    finally:
        log_fh.close()

    jacord_churn_pid_file(manifest).write_text(str(proc.pid))
    return LaunchInfo(
        pid=proc.pid,
        app="jacord_churn",
        env_overrides=env_overrides,
        stdout_log=log_path,
    )


# ---------------------------------------------------------------------------
# "Run all" — sequential shepherd over every manifest.  Several app
# docker-compose.yaml files use the same Postgres container name, so parallel
# sweeps would collide; one shepherd process runs them in order.
# ---------------------------------------------------------------------------


def run_all_pid_file() -> Path:
    return _RUN_ALL_ROOT / "run_all.pid"


def run_all_log_path() -> Path:
    return _RUN_ALL_ROOT / "run_all.log"


def is_run_all_running() -> tuple[bool, int | None]:
    pf = run_all_pid_file()
    if not pf.exists():
        return False, None
    try:
        pid = int(pf.read_text().strip())
    except ValueError:
        return False, None
    try:
        os.kill(pid, 0)
    except OSError:
        return False, pid
    return True, pid


def kill_run_all(timeout_sec: float = 5.0) -> str:
    """Same pgid-based stop as kill() but for the shepherd."""
    pf = run_all_pid_file()
    if not pf.exists():
        return "no run-all sweep is currently running"
    try:
        pid = int(pf.read_text().strip())
    except ValueError:
        pf.unlink(missing_ok=True)
        return "pid file was garbled; removed"

    def _alive() -> bool:
        try:
            os.kill(pid, 0)
        except OSError:
            return False
        return True

    if not _alive():
        pf.unlink(missing_ok=True)
        return f"shepherd {pid} was already gone"

    try:
        os.killpg(pid, signal.SIGTERM)
    except OSError as e:
        pf.unlink(missing_ok=True)
        return f"could not signal pgid {pid}: {e}"

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

    for pattern in ("jac run --serve", "jac start"):
        subprocess.run(
            ["pkill", "-9", "-f", pattern],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    pf.unlink(missing_ok=True)
    return f"stopped shepherd pid={pid} via {outcome}"


def kickoff_all(
    manifests: list[Manifest],
    form_values_by_name: dict[str, dict] | None = None,
    jac_bin: str | None = None,
) -> LaunchInfo:
    """Start every manifest's sweep in sequence via one detached shepherd.

    Sweeps share Postgres container names, so they
    cannot run in parallel.  The shepherd cd's into each app_dir and
    runs its sweep script with the app's env overrides; a failure in
    one still lets the next one start (';' not '&&').
    """
    form_values_by_name = form_values_by_name or {}
    parts: list[str] = []
    all_env_overrides: dict[str, dict[str, str]] = {}
    # Between apps, tear down the DB compose project that belongs to the app.
    # In remote_ssh mode this command is emitted as an SSH docker-compose
    # teardown so run-all does not touch local Postgres containers.
    for m in manifests:
        env = m.env_from_form(form_values_by_name.get(m.name, {}))
        if jac_bin:
            env["JAC_BIN"] = jac_bin
        all_env_overrides[m.name] = env
        env_prefix = " ".join(f"{k}={shlex.quote(str(v))}" for k, v in env.items())
        app_dir_q = shlex.quote(str(m.app_dir))
        manifest_q = shlex.quote(str(m.manifest_path))
        jac_arg = f" --jac-bin {shlex.quote(jac_bin)}" if jac_bin else ""
        if m.runner == "prefetch_python":
            run_cmd = (
                f"cd {shlex.quote(str(_RUN_ALL_ROOT))} && "
                f"{env_prefix} {shlex.quote(sys.executable)} "
                f"-m lib.prefetch_exp.cli --manifest {manifest_q}{jac_arg}"
            )
        else:
            run_cmd = f"cd {app_dir_q} && {env_prefix} bash {shlex.quote(m.sweep_script)}"
        section = (
            f'echo; echo "=== {m.name} ==="; '
            f'{run_cmd}; '
            f'echo "--- {m.name} teardown ---"; '
            f'{db_config.run_all_teardown_shell(m.name, m.app_dir, remove_volumes=True)}'
        )
        parts.append(section)
    shepherd_cmd = "; ".join(parts)

    log_path = run_all_log_path()
    log_fh = open(log_path, "w", buffering=1)
    try:
        proc = subprocess.Popen(
            ["bash", "-c", shepherd_cmd],
            env=os.environ.copy(),
            stdout=log_fh,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    finally:
        log_fh.close()
    run_all_pid_file().write_text(str(proc.pid))
    return LaunchInfo(
        pid=proc.pid,
        app="__all__",
        env_overrides={m.name: str(env) for m, env in zip(manifests, all_env_overrides.values())},
        stdout_log=log_path,
    )
