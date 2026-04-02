#!/bin/bash
set -e

# Configuration - sweep tweet counts
TWEET_COUNTS=(1 10 50 100)

# Results file
RESULTS_FILE="sweep_results_e2e.csv"
PROFILE_CSV="profile_results.csv"
QUICK_RUN_OUTPUT="quick_run_output.tmp"

echo "=== Sweep Benchmark ==="
echo "Graph: edges.txt"
echo "Tweet counts: ${TWEET_COUNTS[*]}"
echo ""

# Write CSV header
echo "tweet_num,ttg_enabled,trial,e2e_ms,ttg_total_ms,topo_idx_ms,ttg_ms,prefetch_ms,walker_ms" > "$RESULTS_FILE"

for tweets in "${TWEET_COUNTS[@]}"; do
  echo "========================================"
  echo "Testing: $tweets tweets per user"
  echo "========================================"

  for ttg_mode in "ttg" "none"; do
    if [ "$ttg_mode" == "ttg" ]; then
      ttg_label="enabled"
    else
      ttg_label="disabled"
    fi

    echo ""
    echo "--- TTG $ttg_label ---"

    # Update jac.toml with current TTG setting
    sed -i "s/prefetching = \".*\"/prefetching = \"$ttg_mode\"/" jac.toml

    # Clear the profile CSV before each run
    rm -f "$PROFILE_CSV"

    # Run quick_run.sh with profiling enabled and capture output
    JAC_TWEET_NUM=$tweets JAC_PROFILE_CSV=$PROFILE_CSV bash quick_run.sh 2>&1 | tee "$QUICK_RUN_OUTPUT"

    # Extract e2e times from quick_run.sh output (lines like "Trial 1: 123.4ms")
    mapfile -t e2e_times < <(grep -oP 'Trial \d+: \K[0-9.]+(?=ms)' "$QUICK_RUN_OUTPUT" || true)

    # Read results from profile CSV (skip header, get last 3 trials)
    if [ -f "$PROFILE_CSV" ]; then
      trial_num=0
      tail -n 3 "$PROFILE_CSV" | while IFS=, read -r p_tweet_num p_ttg_enabled ttg_total_ms topo_idx_ms ttg_ms prefetch_ms walker_ms; do
        e2e_ms="${e2e_times[$trial_num]:-0.0}"
        echo "  Trial $((trial_num + 1)): e2e=${e2e_ms}ms, ttg_total=${ttg_total_ms}ms, topo_idx=${topo_idx_ms}ms, ttg=${ttg_ms}ms, prefetch=${prefetch_ms}ms, walker=${walker_ms}ms"
        echo "$tweets,$ttg_label,$((trial_num + 1)),$e2e_ms,$ttg_total_ms,$topo_idx_ms,$ttg_ms,$prefetch_ms,$walker_ms" >> "$RESULTS_FILE"
        trial_num=$((trial_num + 1))
      done
    else
      echo "  WARNING: Profile CSV not found!"
      # Record e2e times even without profile data
      for i in 0 1 2; do
        e2e_ms="${e2e_times[$i]:-0.0}"
        echo "$tweets,$ttg_label,$((i + 1)),$e2e_ms,0.0,0.0,0.0,0.0,0.0" >> "$RESULTS_FILE"
      done
    fi
  done
done

# Restore TTG to enabled
sed -i 's/prefetching = ".*"/prefetching = "ttg"/' jac.toml

# Cleanup temp files
rm -f "$QUICK_RUN_OUTPUT"

echo ""
echo "========================================"
echo "Benchmark complete!"
echo "Results saved to: $RESULTS_FILE"
echo "========================================"
cat "$RESULTS_FILE"
