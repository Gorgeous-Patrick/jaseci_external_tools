#!/bin/bash
set -e

# Configuration — edit these to match your experiment
PREFETCH_LIMITS=(0 2000 4000 6000 8000 10000 12000 14000 16000 18000 20000 22000 24000 26000 28000 30000 32000)
TWEET_NUM=${JAC_TWEET_NUM:-10}
TRIALS=10

RESULTS_FILE="sweep_prefetch_limit.csv"
QUICK_RUN_OUTPUT="quick_run_output.tmp"

echo "=== Prefetch Limit Sweep ==="
echo "Tweet num  : $TWEET_NUM"
echo "Limits     : ${PREFETCH_LIMITS[*]}"
echo ""

# Write CSV header
echo "prefetch_limit,trial,e2e_ms,ttg_bfs_ms,bulk_exists_ms,find_raw_ms,bulk_put_raw_ms,batch_load_ms,l2_hit_rate,get_l2_hit_rate" > "$RESULTS_FILE"

for limit in "${PREFETCH_LIMITS[@]}"; do
  echo "========================================"
  echo "Testing: prefetch_limit=$limit"
  echo "========================================"

  # Patch prefetch_limit in jac.toml
  sed -i "s/prefetch_limit = .*/prefetch_limit = $limit/" jac.toml

  _prof_dir="profiles/limit_${limit}"
  JAC_TWEET_NUM=$TWEET_NUM JAC_PROFILE_DIR="$_prof_dir" bash quick_run.sh 2>&1 | tee "$QUICK_RUN_OUTPUT"

  # Extract e2e times from quick_run output (lines like "Trial 1: 123.4ms")
  mapfile -t e2e_times < <(grep -oP 'Trial \d+: \K[0-9.]+(?=ms)' "$QUICK_RUN_OUTPUT" || true)

  # Extract average L2 hit rate from [BATCH_GET] log lines in server log
  l2_hit_rate=$(grep '\[BATCH_GET\]' logs/jac_server_2.log 2>/dev/null \
    | grep -oP 'l2_rate=\K[0-9.]+' \
    | awk '{sum+=$1; n++} END {if(n>0) printf "%.1f", sum/n; else print "0.0"}' || echo "0.0")

  # Extract profile breakdown from .prof file
  prof_file="$_prof_dir/jac_server.prof"
  if [ -f "$prof_file" ]; then
    prof_data=$(python3 - "$prof_file" "$TRIALS" <<'PYEOF'
import pstats, sys
prof_path, trials = sys.argv[1], int(sys.argv[2])
stats = pstats.Stats(prof_path, stream=open('/dev/null', 'w'))
ct_map = {}
nc_map = {}
for (f, l, fn), (cc, nc, tt, ct, callers) in stats.stats.items():
    ct_map[fn] = ct_map.get(fn, 0) + ct
    nc_map[fn] = nc_map.get(fn, 0) + nc
t = trials
def ms(fn): return f"{ct_map.get(fn, 0) / t * 1000:.3f}"
total_gets = nc_map.get('TieredMemory.get', 0)
l3_gets    = nc_map.get('MongoBackend.get', 0)
get_l2_hit = f"{(1 - l3_gets / total_gets) * 100:.1f}" if total_gets > 0 else "100.0"
print(ms('get_ttg_prefetch_list'), ms('RedisBackend.bulk_exists'), ms('MongoBackend.find_raw'), ms('RedisBackend.bulk_put_raw'), ms('batch_load_nodes'), get_l2_hit)
PYEOF
    )
    read -r ttg_bfs_ms bulk_exists_ms find_raw_ms bulk_put_raw_ms batch_load_ms get_l2_hit_rate <<< "$prof_data"

    for i in $(seq 0 $((TRIALS - 1))); do
      e2e_ms="${e2e_times[$i]:-0.0}"
      echo "  Trial $((i + 1)): e2e=${e2e_ms}ms  ttg_bfs=${ttg_bfs_ms}ms  bulk_exists=${bulk_exists_ms}ms  find_raw=${find_raw_ms}ms  bulk_put_raw=${bulk_put_raw_ms}ms  batch_load=${batch_load_ms}ms  l2_rate=${l2_hit_rate}%  get_l2_rate=${get_l2_hit_rate}%"
      echo "$limit,$((i + 1)),$e2e_ms,$ttg_bfs_ms,$bulk_exists_ms,$find_raw_ms,$bulk_put_raw_ms,$batch_load_ms,$l2_hit_rate,$get_l2_hit_rate" >> "$RESULTS_FILE"
    done
  else
    echo "  WARNING: Profile not found at $prof_file"
    for i in $(seq 0 $((TRIALS - 1))); do
      echo "$limit,$((i + 1)),${e2e_times[$i]:-0.0},0.0,0.0,0.0,0.0,0.0,0.0,0.0" >> "$RESULTS_FILE"
    done
  fi
done

# Restore original prefetch_limit
sed -i "s/prefetch_limit = .*/prefetch_limit = 3000/" jac.toml
rm -f "$QUICK_RUN_OUTPUT"

echo ""
echo "========================================"
echo "Sweep complete!"
echo "Results saved to: $RESULTS_FILE"
echo "========================================"
cat "$RESULTS_FILE"
