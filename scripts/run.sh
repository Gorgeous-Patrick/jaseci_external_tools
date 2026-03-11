#!/bin/bash
set -euo pipefail
if [ -f "timer.json" ]; then
  rm timer.json
fi
if [ -f "cache_stats.json" ]; then
  rm cache_stats.json
fi


# ====== Configurable parameters ======
NODE_NUM=${NODE_NUM:-250}         # number of nodes (can override: NODE_NUM=100 ./sweep.sh)
TWEET_NUM=${TWEET_NUM:-1}         # JAC_TWEET_NUM
CACHE_SIZE=${CACHE_SIZE:-10}      # JAC_CACHE_SIZE for walker cache
CACHE_SIZES=${CACHE_SIZES:-${CACHE_SIZE}}
EDGE_NUMS=${EDGE_NUMS:-"0 250 500 750 1000"}  # List of edge numbers to iterate over
PREFETCH_VALUES=${PREFETCH_VALUES:-"0 1"}
JAC_FILE=${JAC_FILE:-jac/tests/language/fixtures/jac_ttg/littlex2.jac}
# =====================================

echo "Sweeping graph density:"
echo "  NODE_NUM  = ${NODE_NUM}"
echo "  EDGE_NUMS = ${EDGE_NUMS}"
echo "  CACHE_SIZES = ${CACHE_SIZES}"
echo "  PREFETCH_VALUES = ${PREFETCH_VALUES}"
echo "  JAC_FILE  = ${JAC_FILE}"
echo

for prefetch in ${PREFETCH_VALUES}; do
  echo "==> Sweeping with JAC_PREFETCH=${prefetch}"
  for cache_size in ${CACHE_SIZES}; do
    echo "  -> JAC_CACHE_SIZE=${cache_size}"
    for edges in ${EDGE_NUMS}; do
      echo "Running with JAC_NODE_NUM=${NODE_NUM}, JAC_EDGE_NUM=${edges}, JAC_TWEET_NUM=${TWEET_NUM}"

      JAC_NODE_NUM="${NODE_NUM}" \
      JAC_EDGE_NUM="${edges}" \
      JAC_TWEET_NUM="${TWEET_NUM}" \
      JAC_CACHE_SIZE="${cache_size}" \
      JAC_PREFETCH="${prefetch}" \
        jac run "${JAC_FILE}" > out.txt

      echo "------------------------------------------------------"
    done
  done
done
