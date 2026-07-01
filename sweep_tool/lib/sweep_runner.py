"""Fire-and-forget sweep runner.

Kicks off `bash <sweep_script>` in the app_dir as a detached subprocess
so the sweep survives Streamlit restarts.  No archiving — the Analyze
and Raw tabs read whatever's currently on disk in the app_dir.
Reproducibility / snapshotting is the user's responsibility (git).
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .manifest import Manifest


@dataclass
class LaunchInfo:
    pid: int
    app: str
    env_overrides: dict[str, str]


def kickoff(manifest: Manifest, form_values: dict) -> LaunchInfo:
    """Start the sweep as a detached subprocess.  Returns immediately."""
    env_overrides = manifest.env_from_form(form_values)
    env = os.environ.copy()
    env.update(env_overrides)

    proc = subprocess.Popen(
        ["bash", manifest.sweep_script],
        cwd=str(manifest.app_dir),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,  # detach — survives Streamlit restart
    )
    return LaunchInfo(pid=proc.pid, app=manifest.name, env_overrides=env_overrides)
