#!/bin/bash
# Setup script for stress test
# - Registers a test user
# - Creates nodes via create_node function
# - Saves token and node IDs to a file for use by stress_test_run.sh

set -euo pipefail

PORT=${PORT:-8000}
SETUP_FILE=${SETUP_FILE:-"stress_test_data.json"}

echo "=== HTTP API Stress Test Setup ==="
echo "PORT: ${PORT}"
echo "SETUP_FILE: ${SETUP_FILE}"
echo

# Check if server is responding
echo "Checking if server is running on port $PORT..."
for i in {1..5}; do
  if curl -s "http://localhost:$PORT/docs" > /dev/null 2>&1; then
    echo "✓ Server is ready!"
    break
  fi
  if [ $i -eq 5 ]; then
    echo "✗ ERROR: Server not responding at http://localhost:$PORT"
    echo "Start the server first:"
    echo "  REDIS_URL=redis://localhost:6379 jac start jac/tests/language/fixtures/jac_ttg/basic.jac --port $PORT"
    exit 1
  fi
  echo "  Attempt $i/5..."
  sleep 1
done

# Register user
USERNAME="stresstest_$(date +%s%N | md5sum | cut -c1-8)"
PASSWORD="password123"

echo "Registering test user: $USERNAME"
REGISTER_RESPONSE=$(curl -s -X POST "http://localhost:$PORT/user/register" \
  -H "Content-Type: application/json" \
  -d "{\"username\":\"$USERNAME\",\"password\":\"$PASSWORD\"}")

TOKEN=$(echo "$REGISTER_RESPONSE" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('data', {}).get('token', ''))" 2>/dev/null || echo "")

if [ -z "$TOKEN" ]; then
  echo "ERROR: Failed to get authentication token"
  echo "Response: $REGISTER_RESPONSE"
  exit 1
fi

echo "✓ Token received: ${TOKEN:0:30}..."

# Create nodes and get their IDs
echo "Creating nodes via create_node function..."
CREATE_RESPONSE=$(curl -s -X POST "http://localhost:$PORT/function/create_node" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{}')

NODE_IDS=$(echo "$CREATE_RESPONSE" | python3 -c "import sys, json; data=json.load(sys.stdin).get('data', {}).get('result', []); print(json.dumps(data))" 2>/dev/null || echo "[]")

if [ "$NODE_IDS" = "[]" ]; then
  echo "ERROR: Failed to create nodes"
  echo "Response: $CREATE_RESPONSE"
  exit 1
fi

# Convert to array and display
NODE_IDS_ARRAY=($(echo "$NODE_IDS" | python3 -c "import sys, json; data=json.load(sys.stdin); print(' '.join([str(x) for x in data]))"))
echo "✓ Created ${#NODE_IDS_ARRAY[@]} nodes"

# Save to file
echo "Saving setup data to $SETUP_FILE..."
python3 << EOF
import json

data = {
    "port": $PORT,
    "token": "$TOKEN",
    "username": "$USERNAME",
    "node_ids": $NODE_IDS,
    "timestamp": "$(date -Iseconds)"
}

with open("$SETUP_FILE", "w") as f:
    json.dump(data, f, indent=2)

print(f"✓ Setup data saved")
print(f"  Token: {data['token'][:30]}...")
print(f"  Nodes: {len(data['node_ids'])}")
EOF

echo
echo "Setup complete! Run stress test with:"
echo "  ./stress_test_run.sh"
