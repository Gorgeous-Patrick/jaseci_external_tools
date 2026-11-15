#!/usr/bin/env bash
set -euo pipefail
suite_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
workspace_dir=$(cd -- "$suite_dir/../.." && pwd)
export JAC_DEV_SOURCE=${TTG_RUNTIME_SOURCE:-$workspace_dir/jac-ttg}
export JAC_PG_DIST=${JAC_PG_DIST:-/home/baichuan/.cache/jac/pg/dist/linux-amd64-18.6.0}
export JAC_PG_VERSION=18
export PYTHONPATH="/tmp/jac-ttg-metadata:$JAC_DEV_SOURCE/jac${PYTHONPATH:+:$PYTHONPATH}"
export PYTHONNOUSERSITE=1
export XDG_CACHE_HOME=${TTG_CACHE_DIR:-/tmp/ttg-app-suite-cache}
export JAC_CACHE_HOME=${TTG_RUNTIME_CACHE:-/tmp/ttg-app-suite-runtime}
runtime_python=${TTG_PYTHON:-$workspace_dir/reproduction/runtime/pbs314/python/install/bin/python3.14}
exec "$runtime_python" "$@"
