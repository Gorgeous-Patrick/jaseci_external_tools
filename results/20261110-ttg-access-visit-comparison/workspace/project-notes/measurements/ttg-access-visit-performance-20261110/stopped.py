"""Read-only host verification of this comparison's recorded processes and PG."""
import hashlib
import json
from pathlib import Path
import subprocess

E = Path(__file__).resolve().parent
ROOT = E.parents[2]
OWN = ROOT/'reproduction/ttg-access-visit-performance-20261110'
index = json.loads((E/'run-v1/index.json').read_text())
assert index['status'] == 'complete' and index['passed']
owner = json.loads((OWN/'pg-v1/owner.json').read_text())
assert owner['creator_pid'] == index['creator_pid']
pids = {index['creator_pid']}
for file in (E/'run-v1/cases').glob('*/server-process-memory.jsonl'):
    pids.update(json.loads(line)['pid'] for line in file.read_text().splitlines())
records = [json.loads(line) for line in (OWN/'pg-v1/ownership-and-cleanup.jsonl').read_text().splitlines()]
assert all(r['owner'] == owner['owner'] for r in records)
assert records[-1]['action'] == 'cluster_stopped' and records[-1]['retained_databases'] == []
drops = [r for r in records if r['action'] == 'successful_database_dropped']
assert len(drops) == 24 and all(r['active_sessions'] == 0 for r in drops)
assert len({r['database'] for r in drops}) == 24
live = [pid for pid in sorted(pids) if (Path('/proc')/str(pid)).exists()]
assert not live, live
status = subprocess.run(['/home/baichuan/.cache/jac/pg/dist/linux-amd64-18.6.0/bin/pg_ctl',
    '-D', str(OWN/'pg-v1/data'), 'status'], capture_output=True, text=True)
assert status.returncode == 3 and not (OWN/'pg-v1/data/postmaster.pid').exists()
result = dict(passed=True,creator_pid=index['creator_pid'],recorded_pids=sorted(pids),live_recorded_pids=live,
    pg_status=status.returncode,postmaster_pid_absent=True,owned_successful_drops=24,retained_databases=[],
    index_sha256=hashlib.sha256((E/'run-v1/index.json').read_bytes()).hexdigest(),
    ownership_log_sha256=hashlib.sha256((OWN/'pg-v1/ownership-and-cleanup.jsonl').read_bytes()).hexdigest())
(E/'stopped.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result))
