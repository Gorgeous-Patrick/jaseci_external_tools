#!/usr/bin/env bash
# Sweep test using MongoDB for persistence (via jac-scale).
#
# Equivalent of http_run.sh but uses MONGODB_URI instead of REDIS_URL.
# MongoDB must already be running (e.g. via minikube, Docker, or native).
# No containers are managed by this script.

set -euo pipefail

# ====== Configurable parameters ======
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NODE_NUM=${NODE_NUM:-250}
TWEET_NUM=${TWEET_NUM:-9}
CACHE_SIZE=${CACHE_SIZE:-10000}
CACHE_SIZES=${CACHE_SIZES:-${CACHE_SIZE}}
EDGE_NUMS=${EDGE_NUMS:-"250 500 750 1000"}
PREFETCH_VALUES=${PREFETCH_VALUES:-"0 1"}
JAC_FOLDER=${JAC_FOLDER:-"${SCRIPT_DIR}/jac/tests/language/fixtures/jac_ttg"}
MONGODB_URI=${MONGODB_URI:-"mongodb://localhost:27017/jac_db"}
# =====================================

rm -f "${JAC_FOLDER}/cache_stats.json"
rm -rf "${JAC_FOLDER}"/.jac

echo "Sweeping graph density (MongoDB persistence via jac-scale):"
echo "  NODE_NUM        = ${NODE_NUM}"
echo "  EDGE_NUMS       = ${EDGE_NUMS}"
echo "  CACHE_SIZES     = ${CACHE_SIZES}"
echo "  PREFETCH_VALUES = ${PREFETCH_VALUES}"
echo "  JAC_FOLDER      = ${JAC_FOLDER}"
echo "  MONGODB_URI     = ${MONGODB_URI}"
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
      MONGODB_URI="$MONGODB_URI" \
        ./http_run_once_mongo.sh

      echo "------------------------------------------------------"
    done
  done
done
