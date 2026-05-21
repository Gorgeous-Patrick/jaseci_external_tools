set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
JAC_VENV="$HOME/Space/jaseci_env/jaseci/.venv"
BENCH_VENV="$SCRIPT_DIR/../.venv"

export base_url="localhost:8000"
export JAC_LIST_SIZE=${JAC_LIST_SIZE:-5000}

echo "=== Restarting docker compose ==="
cd "$SCRIPT_DIR"
docker compose down
docker compose up -d
sleep 5

echo "=== Cleaning previous state ==="
source "$JAC_VENV/bin/activate"
yes | jac clean || true

echo "=== Clearing Redis ==="
docker exec redis redis-cli FLUSHALL || true

echo "=== Dropping MongoDB databases ==="
docker exec mongodb mongosh --quiet --eval \
  'db.getMongo().getDBNames().forEach(function(d){if(d!="admin"&&d!="local"&&d!="config"){db.getSiblingDB(d).dropDatabase()}})' || true

echo "=== Starting jac server ==="
JAC_LIST_SIZE=$JAC_LIST_SIZE jac start > /dev/null 2>&1 &
JAC_PID=$!
sleep 10

echo "=== Registering user ==="
http --ignore-stdin POST $base_url/user/register username=user password=password || true

echo "=== Building linked list (JAC_LIST_SIZE=$JAC_LIST_SIZE) ==="
token=$(http --ignore-stdin POST $base_url/user/login username=user password=password | jq ".data.token" -r)
http --ignore-stdin -A bearer -a "$token" POST "$base_url/function/setup_graph" > /dev/null
echo "Linked list created."

echo "=== Waiting for sync to MongoDB ==="
sleep 5

echo "=== Stopping jac server ==="
kill $JAC_PID 2>/dev/null || true
pkill -f "jac start" 2>/dev/null || true
sleep 2

echo "=== Running benchmark ==="
source "$BENCH_VENV/bin/activate"
python "$SCRIPT_DIR/bench_batch_fetch.py" "$@"

echo "=== Done ==="
