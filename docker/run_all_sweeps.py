#!/usr/bin/env python3
"""Foreground run-all helper for the experiment container."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

SWEEP_TOOL_DIR = Path(os.environ.get("SWEEP_TOOL_DIR", "/workspace/jaseci_external_tools/sweep_tool"))
JAC_BIN = os.environ.get("JAC_BIN", "/usr/local/bin/jac")


def main(argv: list[str]) -> int:
    sys.path.insert(0, str(SWEEP_TOOL_DIR))
    from lib import manifest as mf
    from lib.prefetch_exp import db as db_config

    manifests = {m.name: m for m in mf.discover(SWEEP_TOOL_DIR / "manifests")}
    selected = argv or sorted(manifests)
    missing = [name for name in selected if name not in manifests]
    if missing:
        print(f"unknown manifest(s): {', '.join(missing)}", file=sys.stderr)
        return 2

    failures: list[tuple[str, int]] = []
    for name in selected:
        manifest = manifests[name]
        print()
        print(f"=== {name} ===", flush=True)
        cmd = [
            sys.executable,
            "-m",
            "lib.prefetch_exp.cli",
            "--manifest",
            str(manifest.manifest_path),
            "--jac-bin",
            JAC_BIN,
        ]
        result = subprocess.run(cmd, cwd=SWEEP_TOOL_DIR, env=os.environ.copy(), check=False)
        if result.returncode:
            failures.append((name, result.returncode))

        print(f"--- {name} teardown ---", flush=True)
        teardown = db_config.run_all_teardown_shell(name, manifest.app_dir, remove_volumes=True)
        subprocess.run(["bash", "-lc", teardown], cwd=SWEEP_TOOL_DIR, check=False)

    if failures:
        print()
        for name, code in failures:
            print(f"FAILED {name}: exit {code}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
