#!/usr/bin/env bash
set -euo pipefail
perf_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
workspace_dir=$(cd -- "$perf_dir/../.." && pwd)
# No live-runtime default. Final orchestration validates this immutable overlay.
: "${TTG_RUNTIME_SOURCE:?Main-supplied tested snapshot/overlay required}"
: "${TTG_RUNTIME_CACHE:?Owned isolated runtime cache required}"
: "${TTG_CACHE_DIR:?Owned isolated compiler cache required}"
export JAC_DEV_SOURCE="$TTG_RUNTIME_SOURCE/jac"
export PYTHONPATH="/tmp/jac-ttg-metadata:$JAC_DEV_SOURCE:$perf_dir"
export PYTHONNOUSERSITE=1
export PYTHONDONTWRITEBYTECODE=1
export JAC_PG_DIST=${JAC_PG_DIST:-/home/baichuan/.cache/jac/pg/dist/linux-amd64-18.6.0}
export JAC_PG_VERSION=18
export XDG_CACHE_HOME="$TTG_CACHE_DIR"
export JAC_CACHE_HOME="$TTG_RUNTIME_CACHE"
runtime_python=${TTG_PYTHON:-$workspace_dir/reproduction/runtime/pbs314/python/install/bin/python3.14}
exec "$runtime_python" "$@"
