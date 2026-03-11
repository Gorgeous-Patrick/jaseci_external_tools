#!/bin/bash
set -euo pipefail

# ====== Configurable parameters ======
NODE_NUM=${NODE_NUM:-250}         # number of nodes (can override: NODE_NUM=100 ./sweep.sh)
TWEET_NUM=${TWEET_NUM:-9}         # JAC_TWEET_NUM
CACHE_SIZE=${CACHE_SIZE:-10000}      # JAC_CACHE_SIZE for walker cache
CACHE_SIZES=${CACHE_SIZES:-${CACHE_SIZE}}
EDGE_NUMS=${EDGE_NUMS:-"250 500 750 1000"}  # List of edge numbers to iterate over
PREFETCH_VALUES=${PREFETCH_VALUES:-"0 1"}
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
JAC_FOLDER=${JAC_FOLDER:-"${SCRIPT_DIR}/jac/tests/language/fixtures/jac_ttg"}
# =====================================

rm -f "${JAC_FOLDER}/cache_stats.json"
rm -rf "${JAC_FOLDER}"/.jac

echo "Sweeping graph density:"
echo "  NODE_NUM  = ${NODE_NUM}"
echo "  EDGE_NUMS = ${EDGE_NUMS}"
echo "  CACHE_SIZES = ${CACHE_SIZES}"
echo "  PREFETCH_VALUES = ${PREFETCH_VALUES}"
echo "  JAC_FOLDER  = ${JAC_FOLDER}"
echo

for edges in ${EDGE_NUMS}; do
  echo "==> Sweeping with JAC_EDGE_NUM=${edges}"
  for cache_size in ${CACHE_SIZES}; do
    echo "  -> JAC_CACHE_SIZE=${cache_size}"
    for prefetch in ${PREFETCH_VALUES}; do
      echo "Running with JAC_NODE_NUM=${NODE_NUM}, JAC_EDGE_NUM=${edges}, JAC_TWEET_NUM=${TWEET_NUM}, JAC_PREFETCH=${prefetch}"

      JAC_NODE_NUM="${NODE_NUM}" \
      JAC_EDGE_NUM="${edges}" \
      JAC_TWEET_NUM="${TWEET_NUM}" \
      JAC_CACHE_SIZE="${cache_size}" \
      JAC_PREFETCH="${prefetch}" \
      JAC_FOLDER="$JAC_FOLDER" \
        ./http_run_once.sh

      echo "------------------------------------------------------"
    done
  done
done
