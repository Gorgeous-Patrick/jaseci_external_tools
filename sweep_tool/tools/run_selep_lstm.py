"""Run the LinkedList SeLeP LSTM experiment from Streamlit metadata."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


SWEEP_TOOL_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SWEEP_TOOL_ROOT))

from lib import selep_sweep  # noqa: E402


def main() -> int:
    if not selep_sweep.METADATA_PATH.exists():
        print(f"missing SeLeP metadata: {selep_sweep.METADATA_PATH}", file=sys.stderr)
        return 2
    data = json.loads(selep_sweep.METADATA_PATH.read_text())
    config = selep_sweep.config_from_metadata(data)
    problems = selep_sweep.validate(config)
    if problems:
        selep_sweep.write_metadata(config, "blocked", problems)
        print("SeLeP LSTM experiment is not ready:", file=sys.stderr)
        for problem in problems:
            print(f"- {problem}", file=sys.stderr)
        return 2

    command = selep_sweep.command_from_config(config)
    print("=== LinkedList SeLeP LSTM launcher ===", flush=True)
    print(f"cwd={selep_sweep.REPO_ROOT}", flush=True)
    print("cmd=" + " ".join(command), flush=True)
    selep_sweep.write_metadata(config, "running")
    proc = subprocess.run(
        command,
        cwd=str(selep_sweep.REPO_ROOT),
        env=os.environ.copy(),
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        selep_sweep.write_metadata(config, "failed", [f"returncode={proc.returncode}"])
        return proc.returncode
    selep_sweep.write_metadata(config, "done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
