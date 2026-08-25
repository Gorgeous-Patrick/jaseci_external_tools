#!/usr/bin/env bash
set -euo pipefail

ROOT="/home/patrickli/Space/jaseci_env"
SWEEP_TOOL="$ROOT/jaseci_external_tools/sweep_tool"
APP_DIR="$ROOT/jaseci_external_tools/linked_list"
PYTHON="$ROOT/jaseci/.venv/bin/python"
JAC_BIN="$ROOT/jaseci/.venv/bin/jac"
LOG="$APP_DIR/sweep_stdout.log"
PID_FILE="$APP_DIR/sweep.pid"

: > "$LOG"

export LD_LIBRARY_PATH="/nix/store/chqq8mpmpyfi9kgsngya71akv5xicn03-gcc-15.2.0-lib/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export PATH="/run/current-system/sw/bin:/home/patrickli/.nix-profile/bin:/nix/profile/bin:/home/patrickli/.local/state/nix/profile/bin:/etc/profiles/per-user/patrickli/bin:/nix/var/nix/profiles/default/bin:$PATH"
export PYTHONUNBUFFERED=1
export SWEEP_DB_SSH_OPTIONS="-F /home/patrickli/.ssh/config"

printf "%s\n" "$$" > "$PID_FILE"

{
  printf "started linked_list full sweep pid=%s at %s\n" "$$" "$(date -Is)"
  printf "log=%s\n" "$LOG"
  cd "$SWEEP_TOOL"
  exec "$PYTHON" -m lib.prefetch_exp.cli \
    --manifest manifests/linked_list.yaml \
    --jac-bin "$JAC_BIN"
} > "$LOG" 2>&1
