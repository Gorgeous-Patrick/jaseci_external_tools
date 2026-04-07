#!/bin/bash
set -e

export base_url="localhost:8000"
export JAC_TWEET_NUM=${JAC_TWEET_NUM:-10}

# Clean previous state
echo "=== Cleaning previous state ==="
yes | jac clean || true

# Clear Redis
echo "=== Clearing Redis ==="
docker exec redis redis-cli FLUSHALL || true

# Drop MongoDB databases
echo "=== Dropping MongoDB databases ==="
docker exec mongodb mongosh --quiet --eval 'db.getMongo().getDBNames().forEach(function(d){if(d!="admin"&&d!="local"&&d!="config"){db.getSiblingDB(d).dropDatabase()}})' || true

# Create logs directory
mkdir -p logs
LOG_1="logs/jac_server_1.log"
LOG_2="logs/jac_server_2.log"

echo "=== Starting jac server (log: $LOG_1) ==="
JAC_TWEET_NUM=$JAC_TWEET_NUM jac start > "$LOG_1" 2>&1 &
JAC_PID=$!
sleep 10

echo "=== Registering user ==="
http --ignore-stdin POST $base_url/user/register username=user password=password || true

echo "=== Creating nodes from edges.txt ==="
export token=$(http --ignore-stdin POST $base_url/user/login username=user password=password | jq ".data.token" -r)
export NODE=$(http --ignore-stdin -A bearer -a $token POST "$base_url/function/create_node" | jq ".data.result[0]" -r)
echo "First node: $NODE"

# Wait for sync to MongoDB before clearing Redis
echo "=== Waiting for sync ==="
sleep 5

# Clear Redis after node creation
echo "=== Clearing Redis (post node creation) ==="
docker exec redis redis-cli FLUSHALL || true

echo "=== Restarting jac server (log: $LOG_2) ==="
kill $JAC_PID 2>/dev/null || true
sleep 2
JAC_TWEET_NUM=$JAC_TWEET_NUM JAC_PROFILE_CSV=$JAC_PROFILE_CSV jac start > "$LOG_2" 2>&1 &
JAC_PID=$!
sleep 10

echo "=== Running walker ==="
export token=$(http --ignore-stdin POST $base_url/user/login username=user password=password | jq ".data.token" -r)

echo "=== E2E Timing (3 trials) ==="
for i in 1 2 3; do
  docker exec redis redis-cli FLUSHALL > /dev/null 2>&1 || true
  sleep 1
  response=$(curl -s -w "\n%{size_download}\n%{time_total}" -X POST \
    -H "Authorization: Bearer $token" \
    -H "Content-Type: application/json" \
    -d "{}" \
    "http://$base_url/walker/LoadFeed/$NODE")
  e2e_time=$(echo "$response" | tail -n 1)
  resp_size=$(echo "$response" | tail -n 2 | head -n 1)
  body=$(echo "$response" | head -n -2)
  e2e_ms=$(awk "BEGIN {printf \"%.1f\", $e2e_time * 1000}")
  echo "Trial $i: ${e2e_ms}ms, response_size=${resp_size}bytes"
  # Print the [TTG] breakdown line from the server log for this trial
  ttg_line=$(grep '\[TTG\]' "$LOG_2" 2>/dev/null | tail -n 1 || true)
  if [ -n "$ttg_line" ]; then
    echo "  $ttg_line"
  fi
done

echo ""
echo "=== Done ==="
echo "Server logs: $LOG_1, $LOG_2"

# Kill the server
kill $JAC_PID 2>/dev/null || true
