#!/bin/bash
set -e

# Configuration — edit these to match your experiment
PREFETCH_LIMITS=(0 200 400 600 800 1000 1200 1400 1600 1800 2000 2200 2400)
LIST_SIZE=${JAC_LIST_SIZE:-1000}
TRIALS=10

RESULTS_FILE="sweep_prefetch_limit.csv"

echo "=== Prefetch Limit Sweep ==="
echo "List size  : $LIST_SIZE"
echo "Limits     : ${PREFETCH_LIMITS[*]}"
echo ""

# Write CSV header
echo "prefetch_limit,trial,e2e_ms,topo_idx_ms,ttg_ms,prefetch_ms,walker_ms" > "$RESULTS_FILE"

for limit in "${PREFETCH_LIMITS[@]}"; do
  echo "========================================"
  echo "Testing: prefetch_limit=$limit"
  echo "========================================"

  # Patch prefetch_limit in jac.toml
  sed -i "s/prefetch_limit = .*/prefetch_limit = $limit/" jac.toml

  _prof_dir="profiles/limit_${limit}"
  _profile_csv="$_prof_dir/profile.csv"
  JAC_LIST_SIZE=$LIST_SIZE JAC_PROFILE_DIR="$_prof_dir" JAC_PROFILE_CSV="$_profile_csv" \
    JAC_RESULTS_FILE="$RESULTS_FILE" bash quick_run.sh
done

# Restore original prefetch_limit
sed -i "s/prefetch_limit = .*/prefetch_limit = 3000/" jac.toml

echo ""
echo "========================================"
echo "Sweep complete!"
echo "Results saved to: $RESULTS_FILE"
echo "========================================"
cat "$RESULTS_FILE"
