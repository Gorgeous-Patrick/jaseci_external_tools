#!/usr/bin/env bash
set -euo pipefail

SWEEP_TOOL_DIR="${SWEEP_TOOL_DIR:-/workspace/jaseci_external_tools/sweep_tool}"
JAC_BIN="${JAC_BIN:-/usr/local/bin/jac}"

usage() {
  cat <<'EOF'
experiment container commands:
  streamlit                 Run the Streamlit sweep UI on 0.0.0.0:8501
  sweep <app> [args...]     Run one app manifest in the foreground
  run-all [app ...]         Run all/default app manifests sequentially
  check-remote-db [app...]  Validate remote DB setup from inside the container
  jac-info                  Print packaged Jac source/version details
  bash | sh | <command>     Run a shell or arbitrary command

Examples:
  experiment streamlit
  experiment sweep jacord
  experiment run-all linked_list jacord littlex5 jdrive
EOF
}

cmd="${1:-streamlit}"
shift || true

case "$cmd" in
  streamlit)
    cd "$SWEEP_TOOL_DIR"
    exec streamlit run app.py \
      --server.address 0.0.0.0 \
      --server.port "${STREAMLIT_SERVER_PORT:-8501}" \
      "$@"
    ;;
  sweep)
    app="${1:-}"
    if [ -z "$app" ]; then
      usage >&2
      exit 2
    fi
    shift
    manifest="$SWEEP_TOOL_DIR/manifests/${app}.yaml"
    if [ ! -f "$manifest" ]; then
      echo "unknown app manifest: $manifest" >&2
      exit 2
    fi
    cd "$SWEEP_TOOL_DIR"
    exec python -m lib.prefetch_exp.cli --manifest "$manifest" --jac-bin "$JAC_BIN" "$@"
    ;;
  run-all)
    exec run-all-sweeps "$@"
    ;;
  check-remote-db)
    cd /workspace/jaseci_external_tools
    exec python tools/check_remote_db.py "$@"
    ;;
  jac-info)
    exec jac-info "$@"
    ;;
  help|--help|-h)
    usage
    ;;
  bash|sh)
    exec "$cmd" "$@"
    ;;
  *)
    exec "$cmd" "$@"
    ;;
esac
