"""Fire-and-forget sweep runner.

Kicks off `bash <sweep_script>` in the app_dir as a detached subprocess
so the sweep survives Streamlit restarts.  No archiving — the Analyze
and Raw tabs read whatever's currently on disk in the app_dir.
Reproducibility / snapshotting is the user's responsibility (git).
"""

from __future__ import annotations

import os
import signal
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from .manifest import Manifest


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
