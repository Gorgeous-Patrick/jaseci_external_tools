#!/bin/bash
set -e

# Configuration - modify these arrays to sweep different values
# Note: max edges = nodes * (nodes - 1), so ensure edge counts are valid
NODE_COUNTS=(250)
EDGE_COUNTS=(250 500 750 1000 1250 1500 1750 2000 2250 2500 2750 3000)
TWEET_NUM=100

# Results file
RESULTS_FILE="sweep_results.csv"

echo "=== Sweep Benchmark ==="
echo "Nodes: ${NODE_COUNTS[*]}"
echo "Edges: ${EDGE_COUNTS[*]}"
echo "Tweets per node: $TWEET_NUM"
echo ""

# Write CSV header
echo "nodes,edges,tweets,ttg_enabled,trial1_ms,trial2_ms,trial3_ms,avg_ms" > "$RESULTS_FILE"

for nodes in "${NODE_COUNTS[@]}"; do
  for edges in "${EDGE_COUNTS[@]}"; do
    echo "========================================"
    echo "Testing: $nodes nodes, $edges edges"
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

      # Run quick_run.sh and capture output
      output=$(JAC_NODE_NUM=$nodes JAC_EDGE_NUM=$edges JAC_TWEET_NUM=$TWEET_NUM bash quick_run.sh 2>&1)

      # Extract timing from output (format: "Trial N: 123.4ms")
      times=($(echo "$output" | grep "^Trial" | sed 's/Trial [0-9]: //' | sed 's/ms//'))

      trial1_ms=$(printf "%.0f" "${times[0]}")
      trial2_ms=$(printf "%.0f" "${times[1]}")
      trial3_ms=$(printf "%.0f" "${times[2]}")
      avg_ms=$(echo "$trial1_ms $trial2_ms $trial3_ms" | awk '{printf "%.0f", ($1+$2+$3)/3}')

      echo "  Trial 1: ${trial1_ms}ms"
      echo "  Trial 2: ${trial2_ms}ms"
      echo "  Trial 3: ${trial3_ms}ms"
      echo "  Average: ${avg_ms}ms"

      # Append to CSV
      echo "$nodes,$edges,$TWEET_NUM,$ttg_label,$trial1_ms,$trial2_ms,$trial3_ms,$avg_ms" >> "$RESULTS_FILE"
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
