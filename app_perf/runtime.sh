#!/usr/bin/env bash
set -euo pipefail
perf_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
workspace_dir=$(cd -- "$perf_dir/../.." && pwd)
runtime_source=${TTG_RUNTIME_SOURCE:-$perf_dir/runtime-5f94eb62d-v2}
export JAC_DEV_SOURCE=$runtime_source/jac
export JAC_PG_DIST=${JAC_PG_DIST:-/home/baichuan/.cache/jac/pg/dist/linux-amd64-18.6.0}
export JAC_PG_VERSION=18
export PYTHONPATH="/tmp/jac-ttg-metadata:$JAC_DEV_SOURCE:$perf_dir${PYTHONPATH:+:$PYTHONPATH}"
export PYTHONNOUSERSITE=1
export XDG_CACHE_HOME=${TTG_CACHE_DIR:-/tmp/ttg-perf-compiler-cache}
export JAC_CACHE_HOME=${TTG_RUNTIME_CACHE:-/tmp/ttg-perf-runtime-cache}
runtime_python=${TTG_PYTHON:-$workspace_dir/reproduction/runtime/pbs314/python/install/bin/python3.14}
exec "$runtime_python" "$@"
