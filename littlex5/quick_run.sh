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

# Ensure `[run] access_log = ""` exists in jac.toml so we can sed it per trial.
# Idempotent: only adds the line if missing.
if ! grep -q '^access_log' jac.toml; then
  sed -i '/^\[run\]/a access_log = ""' jac.toml
fi

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
    # Per-trial access_log path (sed-patch jac.toml — the [run] section read at startup).
    _access_log="logs/access_log_${walker}_limit${PREFETCH_LIMIT}_trial${i}.csv"
    rm -f "$_access_log"
    sed -i "s|^access_log = .*|access_log = \"$_access_log\"|" jac.toml

    docker exec redis redis-cli FLUSHALL > /dev/null 2>&1 || true

    mkdir -p "$TRIAL_DIR"
    JAC_PROFILE_DIR="$TRIAL_DIR" JAC_PROFILE_CSV="$_profile_csv" \
      JAC_DISABLE_GC=1 \
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

    # Mongo op-counter diff. Sampled *after* login (login itself hits the
    # users collection) so the diff isolates the walker's own DB load.
    mongo_q_before=""; mongo_q_after=""; mongo_q=""
    if [ -n "$JAC_COUNT_MONGO" ]; then
      mongo_q_before=$(docker exec mongodb mongosh jac_db --quiet --eval 'print(Number(db.serverStatus().opcounters.query))' 2>/dev/null)
    fi

    _resp_file="logs/walker_resp_${walker}_limit${PREFETCH_LIMIT}_trial${i}.json"
    http_out=$(curl -s -w "%{http_code}\n%{time_total}" -o "$_resp_file" -X POST \
      -H "Authorization: Bearer $token" \
      -H "Content-Type: application/json" \
      -d "{}" \
      "http://$base_url/walker/$walker")
    http_status=$(echo "$http_out" | head -1)
    e2e_time=$(echo "$http_out" | tail -1)
    resp_size=$(wc -c < "$_resp_file")
    e2e_ms=$(awk "BEGIN {printf \"%.3f\", $e2e_time * 1000}")
    echo "  Trial $i: ${e2e_ms}ms  HTTP=$http_status  resp=${resp_size}bytes"

    if [ -n "$JAC_COUNT_MONGO" ]; then
      mongo_q_after=$(docker exec mongodb mongosh jac_db --quiet --eval 'print(Number(db.serverStatus().opcounters.query))' 2>/dev/null)
      mongo_q=$((mongo_q_after - mongo_q_before))
      echo "    mongo queries: $mongo_q"
    fi

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

    # Roll up the per-anchor access_log into one-line tier counts + L1 hit-rate.
    # Rows now include plan-execution events (sentinel id) alongside per-anchor
    # gets — they're indistinguishable from real reads in the counter, which is
    # intentional: each row is "one tier-touch", whether by a get or a plan.
    hit_rate=""; l1=""; l2=""; l3=""; miss=""
    if [ -s "$_access_log" ]; then
      read hit_rate l1 l2 l3 miss < <(python3 -c "
import csv
from collections import Counter
c = Counter()
with open('$_access_log') as f:
    for r in csv.DictReader(f):
        c[r['tier']] += 1
total = sum(c.values()) or 1
print(f\"{c['L1']*100/total:.1f} {c['L1']} {c['L2']} {c['L3']} {c['MISS']}\")
")
      echo "    hit rate: L1=${hit_rate}%  L1=${l1} L2=${l2} L3=${l3} MISS=${miss}"
    fi

    # Append to results CSV if provided
    if [ -n "$JAC_RESULTS_FILE" ]; then
      echo "$walker,$PREFETCH_LIMIT,$i,$e2e_ms,$topo_idx_ms,$ttg_ms,$prefetch_ms,$walker_ms,$hit_rate,$l1,$l2,$l3,$miss,$mongo_q" >> "$JAC_RESULTS_FILE"
    fi

    kill $JAC_PID 2>/dev/null || true
    pkill -f "jac start" 2>/dev/null || true
    sleep 2
  done
  echo ""
done

# Restore access_log to empty so a stray `jac start` outside the sweep doesn't
# silently keep writing into the last trial's path.
sed -i 's|^access_log = .*|access_log = ""|' jac.toml

rm -f "$_tmpfile"

echo "=== Done ==="
echo "Server logs: logs/"
