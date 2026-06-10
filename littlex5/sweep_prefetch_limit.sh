#!/bin/bash
set -e

# Configuration
# PREFETCH_LIMITS=(0 5000 10000 15000 20000 25000 30000)
PREFETCH_LIMITS=(20000)
RESULTS_FILE="sweep_prefetch_limit.csv"

# Clean all previous data
rm -rf logs profiles

echo "=== LittleX Prefetch Limit Sweep ==="
echo "Limits: ${PREFETCH_LIMITS[*]}"
echo ""

# Write CSV header
echo "walker,prefetch_limit,trial,e2e_ms,topo_idx_ms,ttg_ms,prefetch_ms,walker_ms" > "$RESULTS_FILE"

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
