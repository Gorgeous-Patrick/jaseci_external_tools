#!/bin/bash
set -e

export base_url="localhost:8000"
export JAC_PROFILE_DIR=${JAC_PROFILE_DIR:-profiles}

# Which walkers to benchmark (read-heavy ones)
WALKERS=("load_feed")
# Pick a user with decent connectivity
TEST_USER=${TEST_USER:-sim_user_3}
TEST_PASSWORD=${TEST_PASSWORD:-password}

# Restart docker compose
echo "=== Restarting docker compose ==="
docker compose down
docker compose up -d
sleep 5

# Restore MongoDB from dump if it exists
if [ -f jac_db.dump ]; then
    echo "=== Restoring MongoDB from dump ==="
    docker cp jac_db.dump mongodb:/tmp/jac_db.dump
    docker exec mongodb mongorestore --archive=/tmp/jac_db.dump --drop 2>&1 | tail -3
else
    echo "=== No jac_db.dump found — using existing data ==="
fi

# Clear Redis
echo "=== Clearing Redis ==="
docker exec redis redis-cli FLUSHALL || true

# Clean logs for this run
mkdir -p logs

echo "=== Stopping any running jac server ==="
pkill -f "jac start" 2>/dev/null || true
sleep 2

PREFETCH_LIMIT=$(grep 'prefetch_limit' jac.toml 2>/dev/null | sed 's/.*= *//' || echo "0")

echo "=== E2E Timing (10 trials per walker, server restarted each trial) ==="
echo "prefetch_limit=$PREFETCH_LIMIT  user=$TEST_USER"
echo ""

_tmpfile=$(mktemp)

for walker in "${WALKERS[@]}"; do
  echo "--- Walker: $walker ---"

  for i in 1 2 3; do
    TRIAL_DIR="$JAC_PROFILE_DIR/${walker}/trial_${i}"
    LOG_TRIAL="logs/jac_server_${walker}_limit${PREFETCH_LIMIT}_trial${i}.log"
    _profile_csv="$TRIAL_DIR/profile.csv"

    docker exec redis redis-cli FLUSHALL > /dev/null 2>&1 || true

    mkdir -p "$TRIAL_DIR"
    JAC_PROFILE_DIR="$TRIAL_DIR" JAC_PROFILE_CSV="$_profile_csv" \
      jac start > "$LOG_TRIAL" 2>&1 &
    JAC_PID=$!
    echo "    Waiting for server..."
    for _attempt in $(seq 1 60); do
      curl -sf "http://$base_url/docs" > /dev/null 2>&1 && break
      sleep 1
    done

    token=$(curl -s -X POST "http://$base_url/user/login" \
      -H "Content-Type: application/json" \
      -d "{\"identity\":{\"type\":\"username\",\"value\":\"$TEST_USER\"},\"credential\":{\"type\":\"password\",\"password\":\"$TEST_PASSWORD\"}}" \
      | python3 -c "import sys,json; print(json.load(sys.stdin)['data']['token'])")

    http_out=$(curl -s -w "%{http_code}\n%{time_total}" -o "$_tmpfile" -X POST \
      -H "Authorization: Bearer $token" \
      -H "Content-Type: application/json" \
      -d "{}" \
      "http://$base_url/walker/$walker")
    http_status=$(echo "$http_out" | head -1)
    e2e_time=$(echo "$http_out" | tail -1)
    resp_size=$(wc -c < "$_tmpfile")
    e2e_ms=$(awk "BEGIN {printf \"%.3f\", $e2e_time * 1000}")
    echo "  Trial $i: ${e2e_ms}ms  HTTP=$http_status  resp=${resp_size}bytes"

    # Read breakdown from JAC_PROFILE_CSV if it was written
    topo_idx_ms=""; ttg_ms=""; prefetch_ms=""; walker_ms=""
    if [ -f "$_profile_csv" ]; then
      last_row=$(tail -1 "$_profile_csv")
      topo_idx_ms=$(echo "$last_row" | awk -F',' '{print $6}')
      ttg_ms=$(echo "$last_row" | awk -F',' '{print $7}')
      prefetch_ms=$(echo "$last_row" | awk -F',' '{print $8}')
      walker_ms=$(echo "$last_row" | awk -F',' '{print $9}')
      echo "    breakdown: topo=${topo_idx_ms}ms ttg=${ttg_ms}ms prefetch=${prefetch_ms}ms walker=${walker_ms}ms"
    fi

    # Append to results CSV if provided
    if [ -n "$JAC_RESULTS_FILE" ]; then
      echo "$walker,$PREFETCH_LIMIT,$i,$e2e_ms,$topo_idx_ms,$ttg_ms,$prefetch_ms,$walker_ms" >> "$JAC_RESULTS_FILE"
    fi

    kill $JAC_PID 2>/dev/null || true
    pkill -f "jac start" 2>/dev/null || true
    sleep 2
  done
  echo ""
done

rm -f "$_tmpfile"

echo "=== Done ==="
echo "Server logs: logs/"
