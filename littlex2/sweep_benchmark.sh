#!/bin/bash
set -e

# Configuration - modify these arrays to sweep different values
# Note: max edges = nodes * (nodes - 1), so ensure edge counts are valid
NODE_COUNTS=(25)
EDGE_COUNTS=(0 25 50 75 100 125)
TWEET_NUM=100

# Results file
RESULTS_FILE="sweep_results_e2e.csv"
PROFILE_CSV="profile_results.csv"

echo "=== Sweep Benchmark ==="
echo "Nodes: ${NODE_COUNTS[*]}"
echo "Edges: ${EDGE_COUNTS[*]}"
echo "Tweets per node: $TWEET_NUM"
echo ""

# Write CSV header
echo "node_num,edge_num,tweet_num,ttg_enabled,trial,ttg_ms,prefetch_ms,walker_ms" > "$RESULTS_FILE"

for nodes in "${NODE_COUNTS[@]}"; do
  for edges in "${EDGE_COUNTS[@]}"; do
    echo "========================================"
    echo "Testing: $nodes nodes, $edges edges"
    echo "========================================"

    for ttg_mode in "ttg" "none"; do
      if [ "$ttg_mode" == "ttg" ]; then
        ttg_label="enabled"
      else
        ttg_label="disabledJAC_"
      fi

      echo ""
      echo "--- TTG $ttg_label ---"

      # Update jac.toml with current TTG setting
      sed -i "s/prefetching = \".*\"/prefetching = \"$ttg_mode\"/" jac.toml

      # Clear the profile CSV before each run
      rm -f "$PROFILE_CSV"

      # Run quick_run.sh with profiling enabled
      JAC_NODE_NUM=$nodes JAC_EDGE_NUM=$edges JAC_TWEET_NUM=$TWEET_NUM JAC_PROFILE_CSV=$PROFILE_CSV bash quick_run.sh 2>&1 | tee /dev/null

      # Read results from profile CSV (skip header, get last 3 trials)
      if [ -f "$PROFILE_CSV" ]; then
        trial_num=1
        tail -n 3 "$PROFILE_CSV" | while IFS=, read -r node_num edge_num tweet_num ttg_enabled ttg_ms prefetch_ms walker_ms; do
          echo "  Trial $trial_num: ttg=${ttg_ms}ms, prefetch=${prefetch_ms}ms, walker=${walker_ms}ms"
          echo "$node_num,$edge_num,$tweet_num,$ttg_enabled,$trial_num,$ttg_ms,$prefetch_ms,$walker_ms" >> "$RESULTS_FILE"
          trial_num=$((trial_num + 1))
        done
      else
        echo "  WARNING: Profile CSV not found!"
      fi
    done
  done
done

# Restore TTG to enabled
sed -i 's/prefetching = ".*"/prefetching = "ttg"/' jac.toml

echo ""
echo "========================================"
echo "Benchmark complete!"
echo "Results saved to: $RESULTS_FILE"
echo "========================================"
cat "$RESULTS_FILE"
