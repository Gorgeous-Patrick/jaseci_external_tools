"""Command-line entry point for Python prefetch policy sweeps."""

from __future__ import annotations

import argparse
import signal
from pathlib import Path

from lib import manifest as mf
from lib.prefetch_exp.models import SweepOptions
from lib.prefetch_exp.runner import run_sweep


def _raise_keyboard_interrupt(signum, frame) -> None:
    raise KeyboardInterrupt


def main() -> None:
    signal.signal(signal.SIGTERM, _raise_keyboard_interrupt)
    signal.signal(signal.SIGINT, _raise_keyboard_interrupt)
    parser = argparse.ArgumentParser(description="Run a Python prefetch policy sweep")
    parser.add_argument("--manifest", required=True, help="Path to a sweep_tool manifest YAML")
    parser.add_argument("--jac-bin", default="", help="Jac binary to benchmark")
    args = parser.parse_args()

    manifest = mf.load(Path(args.manifest).resolve())
    options = SweepOptions.from_env(manifest, jac_bin=args.jac_bin or None)
    run_sweep(options)


if __name__ == "__main__":
    main()
