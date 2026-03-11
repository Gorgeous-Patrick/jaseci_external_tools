#!/bin/bash

# Analysis script for stress test results
# Generates summary and plots from CSV results

set -euo pipefail

RESULTS_DIR=${1:-.}

if [ ! -d "$RESULTS_DIR" ]; then
  echo "ERROR: Results directory not found: $RESULTS_DIR"
  exit 1
fi

echo "=== Analyzing Stress Test Results ==="
echo "Directory: $RESULTS_DIR"
echo

# Find all results.csv files
csv_files=$(find "$RESULTS_DIR" -name "results.csv" -o -name "profile.csv")

if [ -z "$csv_files" ]; then
  echo "No results found"
  exit 1
fi

for csv_file in $csv_files; do
  echo
  echo "=== $(basename $csv_file) ==="

  if [[ "$csv_file" == *"profile.csv"* ]]; then
    # Profile analysis
    echo "Profile Summary:"
    awk -F',' 'NR>1 {
      printf "Prefetch=%s, Cache=%s: Time=%sms, Mem=%sMB\n",
      $1, $2, $5, $3
    }' "$csv_file"
  else
    # General results analysis
    if grep -q "http_code" "$csv_file"; then
      # HTTP results
      total=$(wc -l < "$csv_file")
      total=$((total - 1))
      success=$(grep "http_code=200" "$csv_file" | wc -l)
      failed=$((total - success))
      avg_time=$(awk -F',' 'NR>1 {sum+=$NF; count++} END {print sum/count}' "$csv_file")

      echo "HTTP Results:"
      echo "  Total Requests: $total"
      echo "  Successful (200): $success"
      echo "  Failed: $failed"
      echo "  Average Time: ${avg_time}ms"
    else
      # Local/scale results
      echo "Execution Results:"
      awk -F',' 'NR>1 {
        key = $1 "_" $2
        times[key] = times[key] " " $NF
      }
      END {
        for (k in times) {
          split(k, parts, "_")
          print "Prefetch=" parts[1] ", Cache=" parts[2] ":" times[k]
        }
      }' "$csv_file"
    fi
  fi
done

echo
echo "=== Recommendations ==="
echo "1. Compare prefetch=0 vs prefetch=1 for performance gains"
echo "2. Find optimal cache_size vs execution time trade-off"
echo "3. Check memory usage growth with larger cache sizes"
echo "4. Verify parallel/concurrent request handling"
