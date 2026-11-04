#!/usr/bin/env bash
set -euo pipefail
ft_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
export PYTHONPATH="$ft_dir${PYTHONPATH:+:$PYTHONPATH}"
export TTG_REQUIRE_GIL_OFF=1
unset PYTHON_GIL
exec "$ft_dir/python/cpython-3.14.6+freethreaded-linux-x86_64-gnu/bin/python3.14" "$@"
