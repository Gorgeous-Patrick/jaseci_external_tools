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
cleanup() {
  rm -rf "$tmpdir"
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
echo "  jaseci source:          $JASECI_SRC"
echo "  jaseci commit label:    $JASECI_COMMIT"

docker buildx build \
  -f "$EXTERNAL_TOOLS_DIR/Dockerfile.experiment" \
  --build-context "jaseci_src=$tmpdir" \
  --build-arg "JASECI_COMMIT=$JASECI_COMMIT" \
  --build-arg "JASECI_SOURCE_LABEL=$JASECI_SRC" \
  -t "$IMAGE" \
  "${extra_args[@]}" \
  "$CONTEXT_ROOT"
