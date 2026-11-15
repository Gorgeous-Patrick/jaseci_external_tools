"""Failed-stage preservation/known-owned stop/source proof; never retries or drops."""
import hashlib,json,os,subprocess,time
from pathlib import Path
from stage_proof_v2 import ROOT,E,OWN,read,ref,state

d=E/'larger-v1';cluster=OWN/'pg-larger-v1';index=read(d/'index.json');active=read(d/'active-case.json')
assert index['status']=='failed' and not index['passed'] and len(index['rows'])==31
assert active['trial_id']=='linked_list-1000-aggressive-correctness-0'
owner=read(cluster/'owner.json');assert owner['owner']==index['owner']
records=[json.loads(s) for s in (cluster/'ownership-and-cleanup.jsonl').read_text().splitlines()]
created={r['database'] for r in records if r['action']=='database_created'}
drops=[r for r in records if r['action']=='successful_database_dropped']
assert len(created)==32 and len(drops)==31 and all(r['active_sessions']==0 for r in drops)
retained=created-{r['database'] for r in drops}
assert len(retained)==1 and records[-1]['action']=='cluster_stopped' and set(records[-1]['retained_databases'])==retained
failed=d/'cases'/active['trial_id'];target=read(failed/'cleanup-target.json')
assert target['database'] in retained and target['cluster_owner']==index['owner']
known={index['creator_pid']}
for case in list((d/'cases').iterdir()):
 p=case/'server-process-memory.jsonl'
 if p.exists():known.update(json.loads(s)['pid'] for s in p.read_text().splitlines())
assert all(state(pid) in (None,'Z') for pid in known)
excluded=set();pid=os.getpid()
while pid and pid not in excluded:
 excluded.add(pid)
 try:pid=int((Path('/proc')/str(pid)/'stat').read_text().rsplit(')',1)[1].split()[1])
 except (OSError,IndexError,ValueError):break
live=[];unreadable=[]
for entry in Path('/proc').iterdir():
 if not entry.name.isdigit() or int(entry.name) in excluded:continue
 try:
  argv=[s.decode(errors='replace') for s in (entry/'cmdline').read_bytes().split(bytes([0])) if s]
  owned=any(v==str(OWN) or v.startswith(str(OWN)+'/') for v in argv)
  if not owned and any('python' in v or 'postgres' in v for v in argv[:1]):
   environment=(entry/'environ').read_bytes().split(bytes([0]))
   for value in environment:
    k,_,v=value.partition(b'=')
    if k in (b'TTG_RUNTIME_CACHE',b'TTG_CACHE_DIR',b'TTG_PERF_DIR'):
     owned=owned or v.startswith(str(OWN).encode()+b'/') or v.startswith(str(d).encode()+b'/')
 except FileNotFoundError:continue
 except PermissionError:unreadable.append(int(entry.name));continue
 if owned and state(int(entry.name)) not in (None,'Z'):live.append(dict(pid=int(entry.name),argv=argv))
assert not live
pg=subprocess.run(['/home/baichuan/.cache/jac/pg/dist/linux-amd64-18.6.0/bin/pg_ctl','-D',str(cluster/'data'),'status'],capture_output=True,text=True)
assert pg.returncode==3 and not (cluster/'data/postmaster.pid').exists()
plan=read(index['plan']['path']);source=read(plan['sources']['path']);mismatch=[]
for name,wanted in source['files'].items():
 if hashlib.sha256(Path(name).read_bytes()).hexdigest()!=wanted:mismatch.append(name)
assert not mismatch
summary=read(failed/'summary.json')
proof=dict(passed=True,scope='Failed larger-stage natural stop/preservation and once-only effective source postcheck; no native retry or safe-isolation claim',
 index=ref(d/'index.json'),active_case=ref(d/'active-case.json'),plan=index['plan'],source_manifest=plan['sources'],
 source_postcheck=dict(passed=True,files=len(source['files']),mismatches=[],timing='After failed-stage natural stop; no controller source change'),
 owner=ref(cluster/'owner.json'),ownership=ref(cluster/'ownership-and-cleanup.jsonl'),
 known_pids=sorted(known),known_active=[],owned_live=live,uninspectable_pids=unreadable,
 pg_status=3,postmaster_pid_exists=False,retained_databases=sorted(retained),successful_prior_drops=31,
 failed_database=target,failed_raw_seal=ref(failed/'artifacts.json'),failed_summary=ref(failed/'summary.json'),
 failed_requests=ref(failed/'requests.json'),failed_GIL_gate_source=ref(OWN/'gil_audit.py'),
 failure=dict(exception='AssertionError',source='gil_audit.py:44',
  expression="all(f['backend_pid'] != c['backend_pid'] for f in peers)",
  creator_native_summary_passed=summary.get('passed'),independent_case_acceptance_issued=False,
  interpretation='Observed isolation-gate failure. Runtime and validator unchanged; transaction/lifecycle interpretation is not waived.'),
 report_inventory=[dict(case_id='linked_list-1000',config_id='off',status='correctness_only'),
  dict(case_id='linked_list-1000',config_id='aggressive',status='failed_isolation_gate'),
  dict(case_id='linked_list-1000',config_id='conservative',status='not_run_after_first_failure')],
 source=ref(Path(__file__)),time_ns=time.time_ns(),free_bytes=os.statvfs(E).f_bavail*os.statvfs(E).f_frsize)
p=E/'larger-v1-failure-preservation.json';assert not p.exists();p.write_text(json.dumps(proof,indent=2)+'\n')
print(json.dumps(dict(passed=True,proof=ref(p),retained_databases=sorted(retained),source_files=len(source['files']),free_bytes=proof['free_bytes'])))
