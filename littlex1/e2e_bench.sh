#!/bin/bash
set -e

export base_url="localhost:8000"
export JAC_NODE_NUM=${JAC_NODE_NUM:-500}
export JAC_EDGE_NUM=${JAC_EDGE_NUM:-2000}

# Clean and setup
yes | jac clean 2>/dev/null || true
docker exec redis redis-cli FLUSHALL > /dev/null 2>&1 || true
docker exec mongodb mongosh --quiet --eval 'db.getMongo().getDBNames().forEach(function(d){if(d!="admin"&&d!="local"&&d!="config"){db.getSiblingDB(d).dropDatabase()}})' > /dev/null 2>&1 || true

# Start server
JAC_NODE_NUM=$JAC_NODE_NUM JAC_EDGE_NUM=$JAC_EDGE_NUM jac start > /dev/null 2>&1 &
JAC_PID=$!
sleep 10

# Register and create nodes
http --ignore-stdin POST $base_url/user/register username=user password=password > /dev/null 2>&1 || true
token=$(http --ignore-stdin POST $base_url/user/login username=user password=password 2>/dev/null | jq ".data.token" -r)
NODE=$(http --ignore-stdin -A bearer -a $token POST "$base_url/function/create_node" 2>/dev/null | jq ".data.result.[0]" -r)

# Clear Redis after node creation
docker exec redis redis-cli FLUSHALL > /dev/null 2>&1 || true

# Restart server
kill $JAC_PID 2>/dev/null || true
sleep 2
JAC_NODE_NUM=$JAC_NODE_NUM JAC_EDGE_NUM=$JAC_EDGE_NUM jac start > logs/jac_server_bench.log 2>&1 &
JAC_PID=$!
sleep 10

# Login again
token=$(http --ignore-stdin POST $base_url/user/login username=user password=password 2>/dev/null | jq ".data.token" -r)

# Run walker with curl timing (5 iterations)
echo "=== E2E Timing (curl) ==="
for i in 1 2 3 4 5; do
    # Clear Redis before each run to ensure cold cache
    docker exec redis redis-cli FLUSHALL > /dev/null 2>&1 || true
    sleep 0.5
    
    curl -s -o /dev/null -w "Run $i: %{time_total}s (connect: %{time_connect}s, ttfb: %{time_starttransfer}s)\n" \
        -X POST "http://$base_url/walker/LoadFeed/$NODE" \
        -H "Authorization: Bearer $token" \
        -H "Content-Type: application/json" \
        -d '{}'
done

kill $JAC_PID 2>/dev/null || true
