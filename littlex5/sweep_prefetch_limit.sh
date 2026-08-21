#!/bin/bash
set -e

# Configuration
# PREFETCH_LIMITS can be overridden by the SWEEP_PREFETCH_LIMITS env var
# (space-separated integers). Same for TRIALS_PER_LIMIT -> SWEEP_TRIALS.
# The sweep_tool frontend uses these to parameterise runs; standalone use
# just picks up the defaults below.
if [ -n "$SWEEP_PREFETCH_LIMITS" ]; then
  read -ra PREFETCH_LIMITS <<< "$SWEEP_PREFETCH_LIMITS"
else
  PREFETCH_LIMITS=(0 2500 5000 7500 10000 12500)
fi
# jac binary to benchmark. Set to a full path to test a specific build, e.g.
#   export JAC_BIN=~/Space/jaseci/jac/zig-out/bin/jac
# Defaults to `jac` on PATH. Exported so quick_run.sh uses the same binary.
export JAC_BIN="${JAC_BIN:-jac}"
export LITTLEX_DUMP="${LITTLEX_DUMP:-backup.dump}"

RESULTS_FILE="sweep_prefetch_limit.csv"

# Clean all previous data
rm -rf logs profiles

echo "=== LittleX Prefetch Limit Sweep ==="
echo "Limits: ${PREFETCH_LIMITS[*]}"
echo "Dump: $LITTLEX_DUMP"
echo ""

# Write CSV header
echo "walker,prefetch_limit,trial,e2e_ms,topo_idx_ms,ttg_ms,prefetch_ms,walker_ms,l1_hit_rate,l1,l2,l3,miss,mongo_q" > "$RESULTS_FILE"

for limit in "${PREFETCH_LIMITS[@]}"; do
  echo "========================================"
  echo "Testing: prefetch_limit=$limit"
  echo "========================================"

  # Patch prefetch_limit in jac.toml
  if grep -q 'prefetch_limit' jac.toml 2>/dev/null; then
    sed -i "s/prefetch_limit = .*/prefetch_limit = $limit/" jac.toml
  fi

  # Ensure prefetching is set correctly
  if [ "$limit" -eq 0 ]; then
    sed -i 's/prefetching = .*/prefetching = "none"/' jac.toml 2>/dev/null || true
  else
    sed -i 's/prefetching = .*/prefetching = "ttg"/' jac.toml 2>/dev/null || true
  fi

  JAC_PROFILE_DIR="profiles/limit_${limit}" \
    JAC_RESULTS_FILE="$RESULTS_FILE" bash quick_run.sh
done

# Restore original settings
sed -i 's/prefetching = .*/prefetching = "ttg"/' jac.toml 2>/dev/null || true
sed -i "s/prefetch_limit = .*/prefetch_limit = 10000/" jac.toml 2>/dev/null || true

echo ""
echo "========================================"
echo "Sweep complete!"
echo "Results saved to: $RESULTS_FILE"
echo "========================================"
cat "$RESULTS_FILE"
