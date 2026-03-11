#!/usr/bin/env bash
# Stress test runner — MongoDB only (via jac-scale)
#
# Same as stress_test_run.sh but passes MONGODB_URI to jac start
# so ScaleTieredMemory picks up MongoDB as L3 persistence.
# No Redis, no Docker management.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SETUP_FILE=${SETUP_FILE:-"stress_test_data.json"}
JAC_FOLDER=${JAC_FOLDER:-"${SCRIPT_DIR}/jac/tests/language/fixtures/jac_ttg"}
MONGODB_URI=${MONGODB_URI:-"mongodb://localhost:27017/jac_db"}

echo "=== HTTP API Stress Test Runner — MongoDB (restart-per-request) ==="
echo "SETUP_FILE:  $SETUP_FILE"
echo "JAC_FOLDER:  $JAC_FOLDER"
echo "MONGODB_URI: $MONGODB_URI"
echo

# Load setup data
if [ ! -f "$SETUP_FILE" ]; then
  echo "ERROR: Setup file not found: $SETUP_FILE"
  echo "Run setup first: ./stress_test_setup.sh"
  exit 1
fi

echo "Loading setup data from $SETUP_FILE..."
PORT=$(python3 -c "import json; print(json.load(open('$SETUP_FILE'))['port'])")
TOKEN=$(python3 -c "import json; print(json.load(open('$SETUP_FILE'))['token'])")
NODE_IDS_JSON=$(python3 -c "import json; print(json.dumps(json.load(open('$SETUP_FILE'))['node_ids']))")

NODE_IDS_ARRAY=($(python3 -c "import json; print(' '.join(json.loads('$NODE_IDS_JSON')))"))
echo "✓ Loaded config"
echo "  Port: $PORT"
echo "  Token: ${TOKEN:0:30}..."
echo "  Nodes: ${#NODE_IDS_ARRAY[@]}"
echo

# ---------------------------------------------------------------------------
# Server lifecycle helpers
# ---------------------------------------------------------------------------
JAC_PID=""

start_server() {
  pushd "$JAC_FOLDER" > /dev/null
  MONGODB_URI="$MONGODB_URI" timeout 300 jac start --port "$PORT" > /tmp/jac_stress_mongo.log 2>&1 &
  JAC_PID=$!
  popd > /dev/null

  # Wait for server to be ready
  local max_attempts=30
  local attempt=0
  while [ $attempt -lt $max_attempts ]; do
    if curl -s "http://localhost:$PORT/docs" > /dev/null 2>&1; then
      return 0
    fi
    attempt=$((attempt + 1))
    sleep 1
  done

  echo "  [ERROR] Server failed to become ready after $max_attempts seconds"
  return 1
}

stop_server() {
  if [ -n "${JAC_PID:-}" ] && kill -0 "$JAC_PID" 2>/dev/null; then
    kill "$JAC_PID" 2>/dev/null || true
    wait "$JAC_PID" 2>/dev/null || true
  fi
  JAC_PID=""
  # Brief pause so the port is released
  sleep 1
}

# Make sure we clean up on exit
cleanup() {
  stop_server
}
trap cleanup EXIT

# ---------------------------------------------------------------------------
# Results bookkeeping
# ---------------------------------------------------------------------------
mkdir -p stress_test_results
RESULTS_DIR="stress_test_results/mongo_run_$(date +%s)"
mkdir -p "$RESULTS_DIR"

echo "req_id,node_id,http_code,time_ms,startup_ms" > "$RESULTS_DIR/results.csv"
> "$RESULTS_DIR/http_codes.log"

# Save environment config alongside results
python3 << ENVEOF
import json, os
env = {
    'JAC_NODE_NUM': os.environ.get('JAC_NODE_NUM', ''),
    'JAC_EDGE_NUM': os.environ.get('JAC_EDGE_NUM', ''),
    'JAC_TWEET_NUM': os.environ.get('JAC_TWEET_NUM', ''),
    'JAC_CACHE_SIZE': os.environ.get('JAC_CACHE_SIZE', ''),
    'JAC_PREFETCH': os.environ.get('JAC_PREFETCH', ''),
    'MONGODB_URI': '$MONGODB_URI',
    'JAC_FOLDER': '$JAC_FOLDER',
    'PORT': '$PORT',
    'backend': 'mongodb',
}
with open('$RESULTS_DIR/env.json', 'w') as f:
    json.dump(env, f, indent=2)
ENVEOF

# ---------------------------------------------------------------------------
# Main loop — one server lifecycle per request
# ---------------------------------------------------------------------------
echo "Running ${#NODE_IDS_ARRAY[@]} requests (one jac server per request, MongoDB persistence)..."
echo

for ((i=0; i<${#NODE_IDS_ARRAY[@]}; i++)); do
  node_id="${NODE_IDS_ARRAY[$i]}"
  req_id=$((i + 1))

  # -- start server --
  startup_start=$(date +%s%N)
  start_server || { echo "  [FATAL] Server start failed for request $req_id"; continue; }
  startup_end=$(date +%s%N)
  startup_ms=$(( (startup_end - startup_start) / 1000000 ))

  # -- make request (only this part is measured as request time) --
  req_start=$(date +%s%N)

  response=$(curl -s -w "\n%{http_code}" \
    -X POST "http://localhost:$PORT/walker/LoadFeed/$node_id" \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d "{}" 2>/dev/null || echo "\n000")

  req_end=$(date +%s%N)
  elapsed_ms=$(( (req_end - req_start) / 1000000 ))

  http_code=$(echo "$response" | tail -1)
  response_body=$(echo "$response" | sed '$d')

  echo "$req_id,${node_id:0:8}...,$http_code,$elapsed_ms,$startup_ms" >> "$RESULTS_DIR/results.csv"
  echo "$http_code" >> "$RESULTS_DIR/http_codes.log"

  if [ "$http_code" != "200" ]; then
    echo "  [WARN] Request $req_id (node ${node_id:0:8}...) failed with code $http_code"
    if [ -n "$response_body" ]; then
      echo "  [WARN] Response: $response_body"
    fi
  else
    echo "  [$req_id/${#NODE_IDS_ARRAY[@]}] node ${node_id:0:8}... → ${elapsed_ms}ms (startup ${startup_ms}ms)"
  fi

  # -- stop server --
  stop_server
done

echo
echo "Results saved to: $RESULTS_DIR"
echo
echo "=== Summary ==="
total_requests=$(wc -l < "$RESULTS_DIR/http_codes.log")
success_count=$(grep -c '^200$' "$RESULTS_DIR/http_codes.log" || true)
failed_count=$((total_requests - success_count))

echo "Total Requests: $total_requests"
echo "Successful (200): $success_count"
echo "Failed: $failed_count"

if [ $success_count -gt 0 ]; then
  success_rate=$((success_count * 100 / total_requests))
  echo "Success Rate: $success_rate%"

  echo
  echo "Request Timing Stats (successful requests only, excludes server startup):"
  awk -F',' '$3==200 {sum+=$4; count++; if(NR==2 || $4<min) min=$4; if(NR==2 || $4>max) max=$4}
    END {if(count>0) printf "  Average: %.2fms\n  Min: %.2fms\n  Max: %.2fms\n  Total: %.2fms\n", sum/count, min, max, sum}' \
    "$RESULTS_DIR/results.csv"

  echo
  echo "Server Startup Stats:"
  awk -F',' '$3==200 {sum+=$5; count++; if(NR==2 || $5<smin) smin=$5; if(NR==2 || $5>smax) smax=$5}
    END {if(count>0) printf "  Average: %.2fms\n  Min: %.2fms\n  Max: %.2fms\n", sum/count, smin, smax}' \
    "$RESULTS_DIR/results.csv"
fi

echo
echo "To run stress test again:"
echo "  MONGODB_URI=$MONGODB_URI JAC_FOLDER=$JAC_FOLDER ./stress_test_run_mongo.sh"
