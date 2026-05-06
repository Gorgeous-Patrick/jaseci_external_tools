#!/bin/bash
set -e

# Configuration — edit these to match your experiment
PREFETCH_LIMITS=(0 2000 4000 6000 8000 10000 12000 14000 16000)
TWEET_NUM=${JAC_TWEET_NUM:-10}
TRIALS=10

RESULTS_FILE="sweep_prefetch_limit.csv"
QUICK_RUN_OUTPUT="quick_run_output.tmp"

echo "=== Prefetch Limit Sweep ==="
echo "Tweet num  : $TWEET_NUM"
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
  JAC_TWEET_NUM=$TWEET_NUM JAC_PROFILE_DIR="$_prof_dir" JAC_PROFILE_CSV="$_profile_csv" bash quick_run.sh 2>&1 | tee "$QUICK_RUN_OUTPUT"

  # Extract e2e times from quick_run output (lines like "Trial 1: 123.4ms")
  mapfile -t e2e_times < <(grep -oP 'Trial \d+: \K[0-9.]+(?=ms)' "$QUICK_RUN_OUTPUT" || true)

  # Read per-trial breakdown from profile CSV (columns: topo_idx_ms=6, ttg_ms=7, prefetch_ms=8, walker_ms=9)
  if [ -f "$_profile_csv" ]; then
    mapfile -t topo_idx_ms_arr < <(awk -F',' 'NR>1 {print $6}' "$_profile_csv")
    mapfile -t ttg_ms_arr      < <(awk -F',' 'NR>1 {print $7}' "$_profile_csv")
    mapfile -t prefetch_ms_arr < <(awk -F',' 'NR>1 {print $8}' "$_profile_csv")
    mapfile -t walker_ms_arr   < <(awk -F',' 'NR>1 {print $9}' "$_profile_csv")

    for i in $(seq 0 $((TRIALS - 1))); do
      e2e_ms="${e2e_times[$i]:-0.0}"
      topo_idx_ms="${topo_idx_ms_arr[$i]:-0.0}"
      ttg_ms="${ttg_ms_arr[$i]:-0.0}"
      prefetch_ms="${prefetch_ms_arr[$i]:-0.0}"
      walker_ms="${walker_ms_arr[$i]:-0.0}"
      echo "  Trial $((i + 1)): e2e=${e2e_ms}ms  walker=${walker_ms}ms  prefetch=${prefetch_ms}ms  ttg=${ttg_ms}ms  topo_idx=${topo_idx_ms}ms"
      echo "$limit,$((i + 1)),$e2e_ms,$topo_idx_ms,$ttg_ms,$prefetch_ms,$walker_ms" >> "$RESULTS_FILE"
    done
  else
    echo "  WARNING: Profile CSV not found at $_profile_csv"
    for i in $(seq 0 $((TRIALS - 1))); do
      echo "$limit,$((i + 1)),${e2e_times[$i]:-0.0},0.0,0.0,0.0,0.0" >> "$RESULTS_FILE"
    done
  fi
done

# Restore original prefetch_limit
sed -i "s/prefetch_limit = .*/prefetch_limit = 3000/" jac.toml
rm -f "$QUICK_RUN_OUTPUT"

echo ""
echo "========================================"
echo "Sweep complete!"
echo "Results saved to: $RESULTS_FILE"
echo "========================================"
cat "$RESULTS_FILE"
