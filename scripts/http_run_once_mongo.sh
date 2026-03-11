#!/usr/bin/env bash
# HTTP API persistence test — MongoDB only (via jac-scale)
#
# Equivalent of http_run_once.sh but uses MONGODB_URI instead of REDIS_URL.
# Starts an ephemeral MongoDB Docker container (no persistent volume).
# Container lives for the duration of this script and is cleaned up on exit.
#
# Two-step workflow:
#   1. Start MongoDB + jac start + setup (register user, create graph)
#   2. Kill server, restart, stress test (verify data persists in MongoDB)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PORT=${PORT:-8000}
JAC_FOLDER=${JAC_FOLDER:-"${SCRIPT_DIR}/jac/tests/language/fixtures/jac_ttg"}
MONGO_PORT=${MONGO_PORT:-27017}
MONGODB_URI=${MONGODB_URI:-"mongodb://localhost:${MONGO_PORT}/jac_db"}
SETUP_FILE=${SETUP_FILE:-"stress_test_data.json"}
NUM_REQUESTS=${NUM_REQUESTS:-50}

echo "=== HTTP API Persistence Test — MongoDB (One Cycle) ==="
echo "PORT:         ${PORT}"
echo "JAC_FOLDER:   ${JAC_FOLDER}"
echo "MONGODB_URI:  ${MONGODB_URI}"
echo "SETUP_FILE:   ${SETUP_FILE}"
echo "NUM_REQUESTS: ${NUM_REQUESTS}"
echo

# --------------------------------------------------------------------------
# Cleanup
# --------------------------------------------------------------------------
JAC_PID=""
MONGO_CONTAINER=""
JACTASTIC_PUSHED="false"

cleanup() {
  echo
  echo "=== Cleaning up ==="

  if [ ! -z "${JACTASTIC_PUSHED:-}" ] && [ "$JACTASTIC_PUSHED" = "true" ]; then
    popd > /dev/null 2>&1 || true
    JACTASTIC_PUSHED="false"
  fi

  if [ ! -z "${JAC_PID:-}" ] && kill -0 "$JAC_PID" 2>/dev/null; then
    echo "Terminating jac start (PID: $JAC_PID)..."
    kill "$JAC_PID" 2>/dev/null || true
    wait "$JAC_PID" 2>/dev/null || true
  fi

  if [ -n "${MONGO_CONTAINER:-}" ]; then
    echo "Stopping MongoDB container ($MONGO_CONTAINER)..."
    docker stop "$MONGO_CONTAINER" 2>/dev/null || true
    docker rm "$MONGO_CONTAINER" 2>/dev/null || true
  fi
}
trap cleanup EXIT

# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
wait_for_server() {
  local max_attempts=30
  local attempt=0

  echo "Waiting for server to be ready on port $PORT..."
  while [ $attempt -lt $max_attempts ]; do
    if curl -s "http://localhost:$PORT/docs" > /dev/null 2>&1; then
      echo "✓ Server is ready!"
      return 0
    fi
    attempt=$((attempt + 1))
    echo "  Attempt $attempt/$max_attempts..."
    sleep 1
  done

  echo "✗ ERROR: Server failed to become ready after $max_attempts attempts"
  return 1
}

# ==========================================================================
# STEP 1: Start MongoDB, start jac server, and run setup
# ==========================================================================
echo
echo "========== STEP 1: Setup Phase =========="
echo

# Start ephemeral MongoDB (no persistent volume)
echo "Starting MongoDB in Docker (port ${MONGO_PORT}, no persistent volume)..."
MONGO_CONTAINER=$(docker run -d -p "${MONGO_PORT}:27017" \
  --name "jac_mongo_$$" \
  mongo:6.0)
echo "✓ MongoDB started (container: $MONGO_CONTAINER)"
sleep 3

echo "Starting jac server with MongoDB backend..."
echo "  MONGODB_URI=$MONGODB_URI"
pushd "$JAC_FOLDER" > /dev/null
JACTASTIC_PUSHED="true"
MONGODB_URI="$MONGODB_URI" timeout 300 jac start --port "$PORT" > /tmp/jac_start_mongo_1.log 2>&1 &
JAC_PID=$!
echo "✓ jac start launched (PID: $JAC_PID)"

if [ ! -z "${JACTASTIC_PUSHED:-}" ] && [ "$JACTASTIC_PUSHED" = "true" ]; then
  popd > /dev/null
  JACTASTIC_PUSHED="false"
fi

wait_for_server || exit 1

echo
echo "Running stress_test_setup.sh..."
SETUP_FILE="$SETUP_FILE" PORT="$PORT" bash ./stress_test_setup.sh
echo "✓ Setup completed"

# ==========================================================================
# STEP 2: Kill server, restart, stress test (MongoDB persists)
# ==========================================================================
echo
echo "========== STEP 2: Persistence Phase =========="
echo

# Kill jac server from setup phase
echo "Terminating setup jac server..."
kill "$JAC_PID" 2>/dev/null || true
wait "$JAC_PID" 2>/dev/null || true
JAC_PID=""
sleep 1

# MongoDB container stays running — data persists across jac server restarts.
echo "MongoDB container remains running (data persists across server restarts)."

echo
# Build env-var prefix — only forward JAC_* vars that are actually set
ENV_PREFIX=""
[ -n "${JAC_NODE_NUM:-}" ]   && ENV_PREFIX="${ENV_PREFIX}JAC_NODE_NUM=${JAC_NODE_NUM} "
[ -n "${JAC_EDGE_NUM:-}" ]   && ENV_PREFIX="${ENV_PREFIX}JAC_EDGE_NUM=${JAC_EDGE_NUM} "
[ -n "${JAC_TWEET_NUM:-}" ]  && ENV_PREFIX="${ENV_PREFIX}JAC_TWEET_NUM=${JAC_TWEET_NUM} "
[ -n "${JAC_CACHE_SIZE:-}" ] && ENV_PREFIX="${ENV_PREFIX}JAC_CACHE_SIZE=${JAC_CACHE_SIZE} "
[ -n "${JAC_PREFETCH:-}" ]   && ENV_PREFIX="${ENV_PREFIX}JAC_PREFETCH=${JAC_PREFETCH} "

echo "Running stress_test_run_mongo.sh (server restarts per request)..."
env ${ENV_PREFIX} \
SETUP_FILE="$SETUP_FILE" \
JAC_FOLDER="$JAC_FOLDER" \
MONGODB_URI="$MONGODB_URI" \
  bash ./stress_test_run_mongo.sh
echo "✓ Stress test completed"

echo
echo "=== Test Completed Successfully ==="
echo "Setup data preserved in: $SETUP_FILE"
echo "Logs:"
echo "  Setup run: /tmp/jac_start_mongo_1.log"
echo "  Stress per-request: /tmp/jac_stress_mongo.log (last request only)"
