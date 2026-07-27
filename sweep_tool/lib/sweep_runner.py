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
import time
from dataclasses import dataclass
from pathlib import Path

from .manifest import Manifest


_RUN_ALL_ROOT = Path(__file__).resolve().parent.parent  # sweep_tool/


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


def pid_file(manifest: Manifest) -> Path:
    """Records the running sweep's PID so we can find and kill it even
    across Streamlit restarts."""
    return manifest.app_dir / "sweep.pid"


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

    # Belt-and-suspenders: sweep_prefetch_limit.sh spawns `jac start`
    # backgrounded; those should be inside the killed pgid already, but
    # older Bash setups sometimes disown.  Best-effort sweep.
    subprocess.run(
        ["pkill", "-9", "-f", "jac start"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    pf.unlink(missing_ok=True)
    return f"stopped pid={pid} via {outcome}"


def kickoff(manifest: Manifest, form_values: dict) -> LaunchInfo:
    """Start the sweep as a detached subprocess.  Returns immediately."""
    env_overrides = manifest.env_from_form(form_values)
    env = os.environ.copy()
    env.update(env_overrides)

    log_path = stdout_log_path(manifest)
    # Opened in the parent, inherited by the child.  After detach the
    # parent's handle can be closed safely — the child keeps writing.
    log_fh = open(log_path, "w", buffering=1)  # line-buffered
    try:
        proc = subprocess.Popen(
            ["bash", manifest.sweep_script],
            cwd=str(manifest.app_dir),
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


# ---------------------------------------------------------------------------
# "Run all" — sequential shepherd over every manifest.  Every app's
# docker-compose.yaml uses the same container names (mongodb, redis), so
# parallel sweeps would collide; one shepherd process runs them in order.
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

    subprocess.run(
        ["pkill", "-9", "-f", "jac start"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    pf.unlink(missing_ok=True)
    return f"stopped shepherd pid={pid} via {outcome}"


def kickoff_all(
    manifests: list[Manifest],
    form_values_by_name: dict[str, dict] | None = None,
) -> LaunchInfo:
    """Start every manifest's sweep in sequence via one detached shepherd.

    Sweeps share MongoDB and Redis (container names collide), so they
    cannot run in parallel.  The shepherd cd's into each app_dir and
    runs its sweep script with the app's env overrides; a failure in
    one still lets the next one start (';' not '&&').
    """
    form_values_by_name = form_values_by_name or {}
    parts: list[str] = []
    all_env_overrides: dict[str, dict[str, str]] = {}
    # Between apps we cd into each app_dir and run `docker compose down -v`
    # so the previous app's containers *and volumes* are cleaned up under
    # the compose file that started them.  Without this the next app's
    # `docker compose up -d` collides on the shared container names
    # (mongodb / redis) or, worse, silently reuses a stale data volume.
    for m in manifests:
        env = m.env_from_form(form_values_by_name.get(m.name, {}))
        all_env_overrides[m.name] = env
        env_prefix = " ".join(f"{k}={shlex.quote(str(v))}" for k, v in env.items())
        app_dir_q = shlex.quote(str(m.app_dir))
        section = (
            f'echo; echo "=== {m.name} ==="; '
            f'cd {app_dir_q} && {env_prefix} bash {shlex.quote(m.sweep_script)}; '
            f'echo "--- {m.name} teardown ---"; '
            f'cd {app_dir_q} && docker compose down -v > /dev/null 2>&1 || true'
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
