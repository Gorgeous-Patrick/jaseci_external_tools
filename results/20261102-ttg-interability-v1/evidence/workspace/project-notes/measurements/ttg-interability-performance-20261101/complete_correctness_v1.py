"""Small stopped-host/reference/capacity proof; no raw trace or source-tree audit."""
import hashlib,json,os,subprocess,time
from pathlib import Path

ROOT=Path.cwd();E=ROOT/'project-notes/measurements/ttg-interability-performance-20261101'
D=E/'correctness-v2';OWN=ROOT/'reproduction/ttg-interability-performance'
def read(p):return json.loads(Path(p).read_text())
def ref(p):
 p=Path(p).resolve();return dict(path=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest())
def save(p,v):p.write_text(json.dumps(v,indent=2)+'\n');return ref(p)
index=read(D/'index.json');assert index['passed'] and index['status']=='complete'
assert len(index['rows'])==12 and len(index['guard_rows'])==3 and index['source_hashes_after']=='passed'
cluster=Path(index['cluster']);owner=read(cluster/'owner.json')
assert owner['owner']==index['cluster_owner'] and owner['run_directory']==str(D)
events=[json.loads(s) for s in (cluster/'ownership-and-cleanup.jsonl').read_text().splitlines()]
assert events[-1]['action']=='cluster_stopped' and events[-1]['retained_databases']==[]
rows=index['rows']+index['guard_rows'];known={index['creator_pid']};details=[]
for row in rows:
 for value in row['result'].values():assert ref(value['path'])==value
 metric=read(row['result']['metrics']['path']);accept=read(row['result']['acceptance']['path'])
 assert metric['passed'] and accept['passed']
 known.update(metric['primary']['executor']['actual_client_process_pids'])
 known.update(metric['primary']['executor']['actual_backend_pids'])
 case=D/'cases'/row['trial_id']
 known.update(json.loads(s)['pid'] for s in (case/'server-process-memory.jsonl').read_text().splitlines())
 compression=read(case/'compression.json')
 details.append(dict(trial=row['trial_id'],retained_bytes=row['compressed_evidence_bytes'],
  uncompressed_trace_bytes=sum(r['uncompressed_bytes'] for r in compression)))
assert len([v for v in events if v['action']=='successful_database_dropped' and v['active_sessions']==0])==15
def state(pid):
 try:
  text=(Path('/proc')/str(pid)/'stat').read_text();return text[text.rfind(')')+2:].split()[0]
 except FileNotFoundError:return None
assert all(state(pid) in (None,'Z') for pid in known),'Recorded owned PID still active'
excluded=set();pid=os.getpid()
while pid and pid not in excluded:
 excluded.add(pid)
 try:
  fields=(Path('/proc')/str(pid)/'stat').read_text().rsplit(')',1)[1].split();pid=int(fields[1])
 except (OSError,ValueError,IndexError):break
live=[];uninspectable=[]
for entry in Path('/proc').iterdir():
 if not entry.name.isdigit() or int(entry.name) in excluded:continue
 try:
  argv=[x.decode(errors='replace') for x in (entry/'cmdline').read_bytes().split(bytes([0])) if x]
 except FileNotFoundError:continue
 except PermissionError:uninspectable.append(int(entry.name));continue
 if any(a==str(OWN) or a.startswith(str(OWN)+'/') or a==str(D) or a.startswith(str(D)+'/') for a in argv):
  if state(int(entry.name)) not in (None,'Z'):live.append(dict(pid=int(entry.name),argv=argv))
assert not live,'Owned command still active'
pg=ROOT.parent/'.cache/jac/pg/dist/linux-amd64-18.6.0/bin/pg_ctl'
check=subprocess.run([str(pg),'-D',str(cluster/'data'),'status'],capture_output=True,text=True)
assert check.returncode==3 and not (cluster/'data/postmaster.pid').exists()
lifecycle=save(E/'correctness-v2-lifecycle.json',dict(passed=True,index=ref(D/'index.json'),
 owner=ref(cluster/'owner.json'),ownership=ref(cluster/'ownership-and-cleanup.jsonl'),
 recorded_pids=sorted(known),recorded_active=[],creator_dead=state(index['creator_pid']) in (None,'Z'),
 owned_command_matches=live,excluded_helper_ancestors=sorted(excluded),uninspectable_cmdlines=uninspectable,
 scan_scope='Recorded server/observed child/backend/creator PIDs plus exact owned argv paths; no universal host absence claim',
 pg_status=check.returncode,pg_output=check.stdout+check.stderr,has_postmaster_pid=False,retained_databases=[],time_ns=time.time_ns()))
free=os.statvfs(E).f_bavail*os.statvfs(E).f_frsize
retained=sum(r['compressed_evidence_bytes'] for r in index['rows'])*4
transient=max(r['uncompressed_trace_bytes']+r['retained_bytes'] for r in details)
allocated=int(subprocess.check_output(['du','-s','-B1',str(cluster/'data')],text=True).split()[0])
new_cluster_reserve=max(128*1024**2,allocated*2);extra=64*1024**2
residual=free-retained-transient-new_cluster_reserve-extra
forecast=save(E/'formal48-capacity-v1.json',dict(passed=residual>640*1024**2,index=ref(D/'index.json'),
 lifecycle=lifecycle,free_bytes=free,primary12_retained_bytes=retained//4,formal48_retained_estimate_bytes=retained,
 max_observed_uncompressed_traces_plus_retained_bytes=transient,observed_cluster_allocated_bytes=allocated,
 new_cluster_reserve_bytes=new_cluster_reserve,additional_cache_metadata_reserve_bytes=extra,
 projected_residual_bytes=residual,startup_floor_bytes=768*1024**2,case_floor_bytes=640*1024**2,
 in_case_stop_bytes=512*1024**2,case_storage=details,
 limitations='End-of-case raw trace sizes bound a conservative evidence transient, not continuous peak sampling. Existing warmed caches reused; controller guard remains active.',
 proposed_command='python3 -B reproduction/ttg-interability-performance/ia_runner.py formal --plan '+str(E/'correctness-plan-v1/plan.json')+' --output '+str(E/'formal-v1')+' --cluster '+str(OWN/'pg-formal-v1')))
print(json.dumps(dict(lifecycle=lifecycle,capacity=forecast,free_bytes=free,projected_residual_bytes=residual,passed=residual>640*1024**2)))
