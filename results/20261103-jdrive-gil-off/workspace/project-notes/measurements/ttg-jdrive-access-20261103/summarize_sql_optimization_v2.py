from pathlib import Path
import json,hashlib
R=Path('/home/baichuan/jaseci');E=R/'project-notes/measurements/ttg-jdrive-access-20261103';P=R/'project-notes/measurements/ttg-jdrive-freethreaded-20261103'
def read(p):return json.loads(p.read_text())
def ref(p):return dict(path=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest())
proof=read(E/'verification-sql-v2.json')
for name,h in proof['sources'].items():assert ref(R/'jac-ttg'/name)['sha256']==h,name
plans=[];pids=set()
for version in (1,2):
 d=P/f'sql-diagnostic-v{version}';accepted=read(d/'result.json');life=read(d/'lifecycle.json')
 assert accepted['passed'] and life['services_stopped'] and life['pg_status']==3 and not life['pidfile'] and not life['retained_databases']
 pids.add(read(d/'launch.json')['creator_pid']);pids.update(p['pid'] for p in life['services'])
 cpath=next((d/'cases/jdrive-thread-diagnostic/captures').glob('*.json'));c=read(cpath)
 assert len(c['state']['anchors'])==113 and c['explain']['actual_parameters_verified']
 acceptance=read(cpath.parent.parent/'diagnostic-acceptance.json');assert acceptance['passed'] and acceptance['actual_call']['returned_rows']==35
 values=[]
 for x in c['explain']['repetitions']:
  v=x['full_plan'][0];assert v['Plan']['Actual Rows']==35 and v['Plan']['Shared Read Blocks']==0
  values.append(dict(planning_ms=x['planning_ms'],execution_ms=x['execution_ms'],root_shared_hits=v['Plan']['Shared Hit Blocks'],root_shared_reads=v['Plan']['Shared Read Blocks'],JIT=v.get('JIT'),nodes=x['nodes']))
 plans.append(dict(version=version,capture=ref(cpath),result=ref(d/'result.json'),lifecycle=ref(d/'lifecycle.json'),acceptance=ref(cpath.parent.parent/'diagnostic-acceptance.json'),plans=values))
assert all(not Path('/proc',str(pid)).exists() for pid in pids)
perf=read(P/'comparison-access-v3/results.json');assert perf['passed'];source=read(P/'comparison-access-v3/sources.json')
assert all(ref(Path(p))['sha256']==h for p,h in source['files'].items())
output=dict(passed=True,change='Compile output-tree recursion as direct worktable -> edge -> target joins; apply exact bool/dispatch predicates to that same target. Return target properties from the final path join instead of a second anchors join. Native order, ACL, cycle/overflow/malformed fallback and atomic cache contract unchanged.',source_proof=ref(E/'verification-sql-v2.json'),source=ref(R/'jac-ttg/jac/jaclang/runtime/ttg_output_tree.py'),diagnostics=plans,diagnostic_PIDs_dead=sorted(pids),mechanism='Old plan scanned 43 eligible targets outside a correlated path, producing 817 path scans for 19 origins. New recursive step materializes 54 candidate edges once and joins endpoints using primary-key lookups (32 loops); 19 final path assemblies remain for ordered cache records.',primary_results=ref(P/'comparison-access-v3/results.json'),primary_analysis=ref(P/'comparison-access-v3/analysis.json'),primary_lifecycle=ref(P/'comparison-access-v3/lifecycle.json'),primary_groups=perf['groups'],limits=['Server EXPLAIN times are matched recaptures after census and explicit ANALYZE, not primary HTTP samples.','Primary n3 per mode, one excluded warmup; unchanged small JDrive 40 folders/13 files/7 requests.','DB median reduced 41.2%; summed HTTP response median reduced only 2.9%, overlapping ranges. No broad end-to-end speedup claim.','No observed foreground/background SQL overlap. No CPU or residual wall-time causal attribution.'],generator=ref(Path(__file__)))
(E/'sql-optimization-v2.json').write_text(json.dumps(output,indent=2)+'\n');print(json.dumps(dict(passed=True,summary=ref(E/'sql-optimization-v2.json'),diagnostic_pids=len(pids),source_refs=len(source['files'])),indent=2))
