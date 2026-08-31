#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EXTERNAL_TOOLS_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
CONTEXT_ROOT="$(cd "$EXTERNAL_TOOLS_DIR/.." && pwd)"

IMAGE="${IMAGE:-ghcr.io/gorgeous-patrick/jaseci_external_tools:free-threaded}"
JASECI_SRC="${JASECI_SRC:-/home/patrickli/Space/jaseci}"
JASECI_COMMIT="${JASECI_COMMIT:-$(git -C "$JASECI_SRC" rev-parse --short HEAD)}"

if [ -n "$(git -C "$JASECI_SRC" status --porcelain --untracked-files=no)" ]; then
  JASECI_COMMIT="${JASECI_COMMIT}-dirty"
fi

tmpdir="$(mktemp -d "${TMPDIR:-/tmp}/jaseci-docker-src.XXXXXX")"
ctxdir="$(mktemp -d "${TMPDIR:-/tmp}/jaseci-experiment-context.XXXXXX")"
cleanup() {
  rm -rf "$tmpdir"
  rm -rf "$ctxdir"
}
trap cleanup EXIT

tar -C "$JASECI_SRC" \
  --exclude='.git' \
  --exclude='.codex' \
  --exclude='.venv' \
  --exclude='.jac' \
  --exclude='**/__pycache__' \
  --exclude='**/*.pyc' \
  --exclude='jac/.zig-cache' \
  --exclude='jac/.pbs-build' \
  --exclude='jac/.llvm-build' \
  --exclude='jac/.bun-build' \
  --exclude='jac/.payload-layers' \
  --exclude='jac/.precompiled-build' \
  --exclude='jac/zig-out' \
  --exclude='jac/zig-pkg' \
  --exclude='jac/jaclang/client/_bun/bun' \
  --exclude='jac/jaclang/runtimelib/client/_bun/bun' \
  --exclude='jac/jaclang/compiler/backends/native/llvm/libjacllvm.so' \
  --exclude='jac/jaclang/compiler/passes/native/llvm/libjacllvm.so' \
  -cf - . | tar -C "$tmpdir" -xf -

tar -C "$CONTEXT_ROOT" \
  --exclude='.git' \
  --exclude='.codex' \
  --exclude='**/.git' \
  --exclude='**/.git/**' \
  --exclude='**/.venv' \
  --exclude='**/.venv/**' \
  --exclude='**/.venv-lstm' \
  --exclude='**/.venv-lstm/**' \
  --exclude='**/.jac' \
  --exclude='**/.jac/**' \
  --exclude='**/__pycache__' \
  --exclude='**/__pycache__/**' \
  --exclude='**/*.pyc' \
  --exclude='**/data' \
  --exclude='**/data/**' \
  --exclude='**/logs' \
  --exclude='**/logs/**' \
  --exclude='**/profiles' \
  --exclude='**/profiles/**' \
  --exclude='**/profiles_newbin' \
  --exclude='**/churn_dumps' \
  --exclude='**/churn_logs' \
  --exclude='**/churn_profiles' \
  --exclude='**/churn_models' \
  --exclude='**/sweep_runs' \
  --exclude='**/oracle_plans' \
  --exclude='**/markov_models' \
  --exclude='**/coaccess_models' \
  --exclude='**/node_modules' \
  --exclude='**/*.prof' \
  --exclude='**/*.log' \
  -cf - \
  jaseci_external_tools/sweep_tool \
  jaseci_external_tools/tools \
  jaseci_external_tools/linked_list \
  jaseci_external_tools/littlex5 \
  jaseci_external_tools/Dockerfile.experiment \
  jaseci_external_tools/Dockerfile.experiment.dockerignore \
  jaseci_external_tools/docker \
  jaseci_external_tools/docker-compose.experiment.yaml \
  jacord \
  jdrive \
  jsearch \
  SeLeP/Backend \
  SeLeP/Configuration \
  SeLeP/Utils \
  SeLeP/Data \
  SeLeP/bid_getter.py \
  SeLeP/main.py \
  SeLeP/partitioning_main.py \
  SeLeP/selep_main.py \
  SeLeP/README.md \
  SeLeP/requirements.txt \
  | tar -C "$ctxdir" -xf -

extra_args=("$@")
has_output=0
for arg in "${extra_args[@]}"; do
  case "$arg" in
    --push|--load|--output|--output=*)
      has_output=1
      ;;
  esac
done
if [ "$has_output" -eq 0 ]; then
  extra_args+=(--load)
fi

echo "Building $IMAGE"
echo "  external tools context: $CONTEXT_ROOT"
echo "  clean build context:    $ctxdir"
echo "  jaseci source:          $JASECI_SRC"
echo "  jaseci commit label:    $JASECI_COMMIT"

docker buildx build \
  -f "$ctxdir/jaseci_external_tools/Dockerfile.experiment" \
  --build-context "jaseci_src=$tmpdir" \
  --build-arg "JASECI_COMMIT=$JASECI_COMMIT" \
  --build-arg "JASECI_SOURCE_LABEL=$JASECI_SRC" \
  -t "$IMAGE" \
  "${extra_args[@]}" \
  "$ctxdir"
