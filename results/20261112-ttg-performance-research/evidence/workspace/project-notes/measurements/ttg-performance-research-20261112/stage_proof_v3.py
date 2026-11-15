"""Light known-owned lifecycle and byte forecast after natural stage exit."""
import argparse,hashlib,json,os,subprocess,time
from pathlib import Path
ROOT=Path.cwd();E=ROOT/'project-notes/measurements/ttg-performance-research-20261112'
OWN=ROOT/'reproduction/ttg-performance-research-20261112'
def read(p):return json.loads(Path(p).read_text())
def ref(p):
 p=Path(p).resolve();return dict(path=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest())
def state(pid):
 try:return (Path('/proc')/str(pid)/'stat').read_text().rsplit(')',1)[1].split()[0]
 except FileNotFoundError:return None
def prove(index_path,cluster,output):
 index_path=Path(index_path).resolve();cluster=Path(cluster).resolve();output=Path(output).resolve()
 assert output.is_relative_to(E) and not output.exists() and cluster.is_relative_to(OWN)
 index=read(index_path);plan=read(index['plan']['path']);owner=read(cluster/'owner.json')
 assert index['passed'] and index['status']=='complete' and index['source_after_passed']
 assert ref(Path(index['plan']['path']))==index['plan']
 assert plan['kind']=='ttg-expanded-performance-20261112-v2-lineage'
 assert all(ref(Path(plan[k]['path']))==plan[k] for k in ('controller','lineage_validator'))
 assert owner['owner']==index['owner'] and owner['creator_pid']==index['creator_pid']
 assert len(index['rows'])==len(plan['stages'][index['stage']])
 events=[json.loads(s) for s in (cluster/'ownership-and-cleanup.jsonl').read_text().splitlines()]
 assert events[-1]['action']=='cluster_stopped' and not events[-1]['retained_databases']
 created={v['database'] for v in events if v['action']=='database_created'}
 drops=[v for v in events if v['action']=='successful_database_dropped']
 assert len(created)==len(drops)==len(index['rows']) and created=={v['database'] for v in drops}
 assert all(v['active_sessions']==0 for v in drops)
 known={index['creator_pid']};cases=[];gil=[]
 for row in index['rows']:
  p=Path(row['gil_proof']['path']);assert ref(p)==row['gil_proof'];g=read(p);assert g['passed'];gil.append(row['gil_proof'])
  case=Path(row['result']['raw']['path']).parent
  known.update(json.loads(s)['pid'] for s in (case/'server-process-memory.jsonl').read_text().splitlines())
  known.update(g['parent_PIDs']);known.update(g['background_PIDs'])
  compression=read(case/'compression.json')
  cases.append(dict(trial=row['trial_id'],retained_bytes=sum(p.stat().st_size for p in case.rglob('*') if p.is_file()),
   trace_expansion_bytes=sum(v['uncompressed_bytes'] for v in compression),case_wall_s=row['case_wall_s']))
 assert all(state(pid) in (None,'Z') for pid in known)
 exclusions=set();pid=os.getpid()
 while pid and pid not in exclusions:
  exclusions.add(pid)
  try:pid=int((Path('/proc')/str(pid)/'stat').read_text().rsplit(')',1)[1].split()[1])
  except (OSError,IndexError,ValueError):break
 matches=[];unreadable=[]
 for p in Path('/proc').iterdir():
  if not p.name.isdigit() or int(p.name) in exclusions:continue
  try:args=[x.decode(errors='replace') for x in (p/'cmdline').read_bytes().split(bytes([0])) if x]
  except FileNotFoundError:continue
  except PermissionError:unreadable.append(int(p.name));continue
  if any(v==str(OWN) or v.startswith(str(OWN)+'/') for v in args) and state(int(p.name)) not in (None,'Z'):
   matches.append(dict(pid=int(p.name),argv=args))
 assert not matches
 pg=subprocess.run(['/home/baichuan/.cache/jac/pg/dist/linux-amd64-18.6.0/bin/pg_ctl','-D',str(cluster/'data'),'status'],capture_output=True,text=True)
 assert pg.returncode==3 and not (cluster/'data/postmaster.pid').exists()
 free=os.statvfs(E).f_bavail*os.statvfs(E).f_frsize
 value=dict(passed=True,index=ref(index_path),plan=ref(Path(index['plan']['path'])),owner=ref(cluster/'owner.json'),
  ownership=ref(cluster/'ownership-and-cleanup.jsonl'),creator_dead=True,known_pids=sorted(known),known_active=[],
  own_argv_active=matches,uninspectable_cmdlines=unreadable,pg_status=3,postmaster_pid_exists=False,retained_databases=[],
  lifecycle_scope='Known owned controller/server/SQL PIDs and exact owned argv markers only; unrelated services retained.',
  source_after_passed=True,controller=plan['controller'],lineage_validator=plan['lineage_validator'],GIL_proofs=gil,completed=len(cases),case_storage=cases,free_bytes=free,
  retained_bytes=sum(v['retained_bytes'] for v in cases),max_observed_trace_expansion_bytes=max(v['trace_expansion_bytes'] for v in cases),
  remaining_forecast=dict(precision57_retained_bound_bytes=(57*32*1024**2 if index['stage']!='precision' else 0),
   cluster_cache_transient_reserve_bytes=512*1024**2,
   residual_after_remaining_bound_bytes=free-((57*32 if index['stage']!='precision' else 0)+512)*1024**2,
   qualification='Conservative precision bound32MiB/case plus512MiB cluster/cache reserve; timing and precision remain separate. Exact storage guards are bound in the plan; no historical deletion.'),
  host=dict(time_ns=time.time_ns(),loadavg=os.getloadavg(),whole_host_quiet_claim=False),source=ref(Path(__file__)))
 output.write_text(json.dumps(value,indent=2)+'\n');print(json.dumps(dict(passed=True,proof=ref(output),free_bytes=free,retained_bytes=value['retained_bytes'],forecast=value['remaining_forecast'])))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--index',type=Path,required=True);p.add_argument('--cluster',type=Path,required=True)
 p.add_argument('--output',type=Path,required=True);a=p.parse_args();prove(a.index,a.cluster,a.output)
