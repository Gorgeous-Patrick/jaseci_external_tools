#!/bin/bash
# HTTP API persistence test script
# Tests the two-step workflow:
# 1. Run redis + jac start + setup
# 2. Terminate servers, restart, and run stress test
# This verifies that data persists across server restarts

set -euo pipefail

PORT=${PORT:-8000}
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
JAC_FOLDER=${JAC_FOLDER:-"${SCRIPT_DIR}/jac/tests/language/fixtures/jac_ttg"}
REDIS_URL=${REDIS_URL:-"redis://localhost:6379"}
SETUP_FILE=${SETUP_FILE:-"stress_test_data.json"}
NUM_REQUESTS=${NUM_REQUESTS:-50}

echo "=== HTTP API Persistence Test (One Cycle) ==="
echo "PORT: ${PORT}"
echo "JAC_FOLDER: ${JAC_FOLDER}"
echo "REDIS_URL: ${REDIS_URL}"
echo "SETUP_FILE: ${SETUP_FILE}"
echo "NUM_REQUESTS: ${NUM_REQUESTS}"
echo

# Cleanup function
cleanup() {
  echo
  echo "=== Cleaning up ==="

  # Pop directory if we're in a pushed state
  if [ ! -z "${JACTASTIC_PUSHED:-}" ] && [ "$JACTASTIC_PUSHED" = "true" ]; then
    popd > /dev/null 2>&1 || true
    JACTASTIC_PUSHED="false"
  fi

  # Kill jac start if running
  if [ ! -z "${JAC_PID:-}" ] && kill -0 "$JAC_PID" 2>/dev/null; then
    echo "Terminating jac start (PID: $JAC_PID)..."
    kill "$JAC_PID" 2>/dev/null || true
    wait "$JAC_PID" 2>/dev/null || true
  fi

  # Stop redis container if running
  if [ ! -z "${REDIS_CONTAINER:-}" ]; then
    echo "Stopping redis container ($REDIS_CONTAINER)..."
    docker stop "$REDIS_CONTAINER" 2>/dev/null || true
    docker rm "$REDIS_CONTAINER" 2>/dev/null || true
  fi
}

# Set trap to cleanup on exit
trap cleanup EXIT

# Helper function to wait for server to be ready
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

# =============================================================================
# STEP 1: Start Redis, start jac server, and run setup
# =============================================================================
echo
echo "========== STEP 1: Setup Phase =========="
echo

# Start Redis in Docker with custom config
echo "Starting Redis in Docker with config (100MB limit, LRU eviction)..."
REDIS_CONTAINER=$(docker run -d -p 6379:6379 \
  -v "$(pwd)/redis.conf:/usr/local/etc/redis/redis.conf" \
  redis:latest redis-server /usr/local/etc/redis/redis.conf)
echo "✓ Redis started (container: $REDIS_CONTAINER)"
sleep 2

# Start jac server
echo "Starting jac server..."
echo "Starting jac server in folder: $JAC_FOLDER"
pushd "$JAC_FOLDER" > /dev/null
JACTASTIC_PUSHED="true"
REDIS_URL="$REDIS_URL" timeout 300 jac start --port "$PORT" > /tmp/jac_start_1.log 2>&1 &
JAC_PID=$!
echo "✓ jac start launched (PID: $JAC_PID)"

# Pop directory after starting server
if [ ! -z "${JACTASTIC_PUSHED:-}" ] && [ "$JACTASTIC_PUSHED" = "true" ]; then
  popd > /dev/null
  JACTASTIC_PUSHED="false"
fi

# Wait for server to be ready
wait_for_server || exit 1

# Run setup script
echo
echo "Running stress_test_setup.sh..."
SETUP_FILE="$SETUP_FILE" PORT="$PORT" bash ./stress_test_setup.sh
echo "✓ Setup completed"

# =============================================================================
# STEP 2: Terminate setup server, restart Redis, run stress test
# =============================================================================
echo
echo "========== STEP 2: Persistence Phase =========="
echo

# Terminate jac server from setup phase
echo "Terminating setup jac server..."
kill "$JAC_PID" 2>/dev/null || true
wait "$JAC_PID" 2>/dev/null || true
JAC_PID=""
sleep 1

# Restart Redis (stop → start) to test persistence
echo "Stopping Redis container..."
docker stop "$REDIS_CONTAINER" 2>/dev/null || true
docker rm "$REDIS_CONTAINER" 2>/dev/null || true
REDIS_CONTAINER=""
sleep 2

echo "Restarting Redis in Docker with config (100MB limit, LRU eviction)..."
REDIS_CONTAINER=$(docker run -d -p 6379:6379 \
  -v "$(pwd)/redis.conf:/usr/local/etc/redis/redis.conf" \
  redis:latest redis-server /usr/local/etc/redis/redis.conf)
echo "✓ Redis restarted (container: $REDIS_CONTAINER)"
sleep 2

echo
echo "Running stress_test_run.sh (server restarts per request)..."
SETUP_FILE="$SETUP_FILE" JAC_FOLDER="$JAC_FOLDER" REDIS_URL="$REDIS_URL" bash ./stress_test_run.sh
echo "✓ Stress test completed"

echo
echo "=== Test Completed Successfully ==="
echo "Setup data preserved in: $SETUP_FILE"
echo "Logs:"
echo "  Setup run: /tmp/jac_start_1.log"
echo "  Stress per-request: /tmp/jac_stress.log (last request only)"
