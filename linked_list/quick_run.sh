#!/bin/bash
set -e

export base_url="localhost:8000"
export JAC_LIST_SIZE=${JAC_LIST_SIZE:-100}
export JAC_PROFILE_DIR=${JAC_PROFILE_DIR:-profiles}

# Restart docker compose
echo "=== Restarting docker compose ==="
docker compose down
docker compose up -d
sleep 5

# Clean previous state
echo "=== Cleaning previous state ==="
yes | jac clean || true

# Clear Redis
echo "=== Clearing Redis ==="
docker exec redis redis-cli FLUSHALL || true

# Drop MongoDB databases
echo "=== Dropping MongoDB databases ==="
docker exec mongodb mongosh --quiet --eval 'db.getMongo().getDBNames().forEach(function(d){if(d!="admin"&&d!="local"&&d!="config"){db.getSiblingDB(d).dropDatabase()}})' || true

# Clean logs for this run
mkdir -p logs
LOG_1="logs/jac_server_setup.log"

echo "=== Starting jac server (log: $LOG_1) ==="
JAC_LIST_SIZE=$JAC_LIST_SIZE jac start > "$LOG_1" 2>&1 &
JAC_PID=$!
sleep 10

echo "=== Registering user ==="
http --ignore-stdin POST $base_url/user/register username=user password=password || true

echo "=== Building linked list ==="
export token=$(http --ignore-stdin POST $base_url/user/login username=user password=password | jq ".data.token" -r)
mapfile -t NODES < <(http --ignore-stdin -A bearer -a $token POST "$base_url/function/setup_graph" | jq -r '.data.result[]')
echo "Nodes: ${#NODES[@]} items"

# Wait for sync to MongoDB before clearing Redis
echo "=== Waiting for sync ==="
sleep 5

# Clear Redis after node creation
echo "=== Clearing Redis (post node creation) ==="
docker exec redis redis-cli FLUSHALL || true

echo "=== Stopping setup server ==="
kill $JAC_PID 2>/dev/null || true
pkill -f "jac start" 2>/dev/null || true
sleep 2

PREFETCH_LIMIT=$(grep 'prefetch_limit' jac.toml | sed 's/.*= *//')

echo "=== E2E Timing (10 trials, server restarted each trial, prefetch_limit=$PREFETCH_LIMIT) ==="
_tmpfile=$(mktemp)
for i in 1 2 3 4 5 6 7 8 9 10; do
  NODE="${NODES[0]}"
  TRIAL_DIR="$JAC_PROFILE_DIR/trial_${i}"
  LOG_TRIAL="logs/jac_server_limit${PREFETCH_LIMIT}_trial${i}.log"

  docker exec redis redis-cli FLUSHALL > /dev/null 2>&1 || true

  JAC_LIST_SIZE=$JAC_LIST_SIZE JAC_PROFILE_DIR="$TRIAL_DIR" \
    jac start > "$LOG_TRIAL" 2>&1 &
  JAC_PID=$!
  sleep 10

  token=$(http --ignore-stdin POST $base_url/user/login username=user password=password | jq ".data.token" -r)

  http_out=$(curl -s -w "%{http_code}\n%{time_total}" -o "$_tmpfile" -X POST \
    -H "Authorization: Bearer $token" \
    -H "Content-Type: application/json" \
    -d "{}" \
    "http://$base_url/walker/Traverse/$NODE")
  http_status=$(echo "$http_out" | head -1)
  e2e_time=$(echo "$http_out" | tail -1)
  resp_size=$(wc -c < "$_tmpfile")
  e2e_ms=$(awk "BEGIN {printf \"%.3f\", $e2e_time * 1000}")
  echo "Trial $i: ${e2e_ms}ms  HTTP=$http_status  response_size=${resp_size}bytes  (log: $LOG_TRIAL)"

  # Append to results CSV if provided
  if [ -n "$JAC_RESULTS_FILE" ] && [ -f "$JAC_PROFILE_CSV" ]; then
    last_row=$(tail -1 "$JAC_PROFILE_CSV")
    topo_idx_ms=$(echo "$last_row" | awk -F',' '{print $6}')
    ttg_ms=$(echo "$last_row" | awk -F',' '{print $7}')
    prefetch_ms=$(echo "$last_row" | awk -F',' '{print $8}')
    walker_ms=$(echo "$last_row" | awk -F',' '{print $9}')
    echo "$PREFETCH_LIMIT,$i,$e2e_ms,$topo_idx_ms,$ttg_ms,$prefetch_ms,$walker_ms" >> "$JAC_RESULTS_FILE"
  fi

  kill $JAC_PID 2>/dev/null || true
  pkill -f "jac start" 2>/dev/null || true
  sleep 2
done

rm -f "$_tmpfile"

echo ""
echo "=== Done ==="
echo "Server logs: logs/jac_server_trial*.log"
