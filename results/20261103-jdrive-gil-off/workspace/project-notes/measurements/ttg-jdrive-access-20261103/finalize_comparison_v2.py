import hashlib,json,subprocess
from pathlib import Path
from statistics import median
R=Path('/home/baichuan/jaseci'); E=R/'project-notes/measurements/ttg-jdrive-freethreaded-20261103/comparison-access-v2'; PG=R/'reproduction/ttg-jdrive-freethreaded/pg-access-v2'
def read(p):return json.loads(Path(p).read_text())
def ref(p):return dict(path=str(p),sha256=hashlib.sha256(Path(p).read_bytes()).hexdigest())
x=read(E/'index.json');result=read(E/'results.json');assert x['passed'] and len(x['rows'])==8 and result['passed']
source=read(E/'sources.json')['files']
for p,h in source.items():assert ref(p)['sha256']==h,p
pids={x['creator_pid']}
for row in x['rows']:
 d=Path(row['result']['raw']['path']).parent
 for f in d.glob('gil-proof-*.jsonl'):
  with f.open() as s:pids.add(json.loads(next(s))['pid'])
alive=[p for p in sorted(pids) if Path('/proc',str(p)).exists()];assert not alive,alive
cmd=['/home/baichuan/.cache/jac/pg/dist/linux-amd64-18.6.0/bin/pg_ctl','-D',str(PG/'data'),'status']
p=subprocess.run(cmd,capture_output=True,text=True);assert p.returncode==3,(p.returncode,p.stdout,p.stderr)
assert not (PG/'data/postmaster.pid').exists()
records=[json.loads(l) for l in (PG/'ownership-and-cleanup.jsonl').read_text().splitlines()]
assert records[-1]['action']=='cluster_stopped' and records[-1]['retained_databases']==[]
life=dict(passed=True,index=ref(E/'index.json'),owner=ref(PG/'owner.json'),ownership=ref(PG/'ownership-and-cleanup.jsonl'),PG_status=p.returncode,PG_output=p.stdout+p.stderr,postmaster_pid_absent=True,creator_and_actual_app_PIDs_dead=sorted(pids),retained_databases=[],matrix_exit_code=0,source_references_verified=len(source))
(E/'lifecycle.json').write_text(json.dumps(life,indent=2)+'\n')
groups=result['groups']; cats={};trees={}
for mode in ('off','thread'):
 s=[v for v in result['samples'] if v['mode']==mode and v['phase']=='measured']
 cats[mode]={k:dict(count=[a['categories'].get(k,0) for a in s]) for k in set().union(*(a['categories'] for a in s))}
 trees[mode]=[]
 for i in range(3):
  rows=[a['trees'][i] for a in s];bycat={}
  for k in set().union(*(q['categories'] for q in rows)):
   vals=[sum(f['protocol_ms'] for f in q['fingerprints'] if f['category']==k) for q in rows]
   bycat[k]=dict(ms=vals,median_ms=median(vals),counts=[q['categories'].get(k,0) for q in rows])
  trees[mode].append(dict(entries=rows[0]['entries'],SQL=[r['SQL'] for r in rows],HTTP_ms=[r['HTTP_ms'] for r in rows],categories=bycat))
a=dict(passed=True,results=ref(E/'results.json'),lifecycle=ref(E/'lifecycle.json'),raw_audit_source=ref(R/'project-notes/measurements/ttg-jdrive-access-20261103/analyze_comparison_v2.py'),categories=cats,trees=trees,relative_change={k:groups['thread'][k]['median']/groups['off'][k]['median']-1 for k in ('SQL','DB_sum_ms','HTTP_sum_ms')},interpretation={'observed':'All three tree requests replace per-node paths with one recursive query and five payload queries each. Total SQL decreases, but median DB protocol time and instrumented summed HTTP response time increase in this small n3 capture. No foreground/background SQL interval overlap observed.','limits':'No server CPU, SQL planning/execution split, or IPC timing inference; no claim for larger data. Native output/graph equality and GIL-off assertions verified.'})
(E/'analysis.json').write_text(json.dumps(a,indent=2)+'\n');print(json.dumps(dict(passed=True,sources=len(source),dead_PIDs=len(pids),relative_change=a['relative_change'],lifecycle=ref(E/'lifecycle.json'),analysis=ref(E/'analysis.json')),indent=2))
