"""Matched JDrive SQL plans, isolated from all primary measurements."""
import json,os,sys,shutil,hashlib,subprocess
from pathlib import Path
O=Path(__file__).resolve().parent;R=O.parents[1];P=O.parent/'ttg-jdrive-freethreaded'
sys.path.insert(0,str(P))
from ia_interop import read_json,reference,require,sha256
from ia_trial import Trial,load_unsealed
from ia_postgres import OwnedPostgres
from ia_runner import Sources,storage_watch
from owned_postgres import BIN
sys.path.insert(0,str(O))
from overlay import transform
E=R/'project-notes/measurements/ttg-jdrive-freethreaded-20261103/sql-diagnostic-v1'
def write(p,x):p.write_text(json.dumps(x,indent=2)+'\n')
class PG(OwnedPostgres):
 def accept_completed(self,case,cell,name,directory,proof,expected):
  t=next(t for t in selection['targets'] if t['config_id']==cell)
  fs=list((directory/'captures').glob('*.json'));assert len(fs)==1
  c=read_json(fs[0]);assert c['target']==t and c['explain']['actual_parameters_verified']
  calls=[v for v in load_unsealed(directory,'server-*.calls.jsonl*') if v.get('origin_request_id')==t['request'] and str(v.get('server_generation'))==str(t['generation']) and v.get('sql')==t['sql'] and v.get('send_ns') is not None]
  assert calls and calls[0]['error'] is None and calls[0]['returned_rows']==t['returned_rows']
  assert calls[0]['backend_pid']==c['state']['context'][0][2]
  assert c['state']['statistics']==c['state']['statistics_after_explain']
  norm=read_json(directory/'planner-statistics-before-workflow.json');assert norm['passed']
  write(directory/'diagnostic-acceptance.json',dict(passed=True,capture=reference(fs[0]),actual_call=calls[0],full_native_proof=reference(directory/'plus-proof.json'),normalization=reference(directory/'planner-statistics-before-workflow.json'),primary_measurement=False))
  write(directory/'artifacts.json',dict(passed=True,files={str(f.relative_to(directory)):sha256(f) for f in directory.rglob('*') if f.is_file() and f.name!='artifacts.json'}))
  return super().accept_completed(case,cell,name,directory,proof,expected)
assert not E.exists();E.mkdir();(E/'cases').mkdir()
base=R/'project-notes/measurements/ttg-jdrive-freethreaded-20261103/comparison-access-v2'
plan=read_json(base/'plan.json');selection=read_json(O/'selection-v1.json')
Sources(plan['sources'])
m=read_json(plan['overlay']['path']);root=Path(m['root']);target=O/'runtime-v1';assert not target.exists()
shutil.copytree(root,target,copy_function=os.link)
p=target/'jac/jaclang/data/impl/pgwire.impl.jac';old=sha256(p);new=p.with_suffix('.diagnostic-tmp');new.write_text(transform(p.read_text()));os.replace(new,p);assert sha256(root/p.relative_to(target))==old
files=dict(m['files']);files[str(p.relative_to(target))]=sha256(p)
for name in ['capture.py','explain.py']:
 dest=target/'jac'/name;assert not dest.exists();shutil.copyfile(O/name,dest);files[str(dest.relative_to(target))]=sha256(dest)
m={**m,'root':str(target),'files':files,'diagnostic_base':plan['overlay']};write(E/'overlay.json',m)
hashes=read_json(base/'sources.json')['files'].copy();hashes.update({str(f):sha256(f) for f in O.glob('*.py')});hashes[str(O/'selection-v1.json')]=sha256(O/'selection-v1.json');hashes.update({str(target/k):v for k,v in files.items()})
write(E/'sources.json',dict(files=hashes));guard=Sources(reference(E/'sources.json'))
os.environ['TTG_PYTHON']=str(O.parent/'ttg-littlex-freethreaded/python.sh')
pg=PG(P/'pg-sql-diagnostic-v1',Path(read_json(plan['clean']['path'])['root']),E,guard,startup_floor=768*1024**2,case_floor=640*1024**2)
write(E/'launch.json',dict(creator_pid=os.getpid(),selection=reference(O/'selection-v1.json'),plan=reference(base/'plan.json')))
rows=[]
try:
 with pg:
  for cell in ['off','thread']:
   case=dict(plan['schedule'][0],config_id=cell,phase='diagnostic',repeat=0,trial_id='jdrive-'+cell+'-diagnostic')
   directory=E/'cases'/case['trial_id'];pg.context=dict(directory=directory,case=case,cell=cell,source_manifest=reference(E/'sources.json'),prior_metrics={})
   os.environ.update(TTG_DIAG_SELECTION=str(O/'selection-v1.json'),TTG_DIAG_CONFIG_ID=cell,TTG_DIAG_OUTPUT=str(directory/'captures'))
   expected=read_json(next(t['native_proof']['path'] for t in selection['targets'] if t['config_id']==cell))
   with storage_watch(E,case,512*1024**2):Trial().run(case,cell,directory,pg,Path(plan['clean']['path']),E/'overlay.json',expected)
   rows.append(dict(mode=cell,result=pg.context['result']));print('ACCEPTED',cell,flush=True)
 guard.verify_hashes();write(E/'result.json',dict(passed=True,rows=rows,primary_measurement=False))
finally:
 status=subprocess.run([str(BIN/'pg_ctl'),'-D',str(pg.directory/'data'),'status'],capture_output=True,text=True)
 write(E/'lifecycle.json',dict(services_stopped=all(p.poll() is not None for p in pg.services),services=[dict(pid=p.pid,exit_code=p.poll()) for p in pg.services],pg_status=status.returncode,pidfile=(pg.directory/'data/postmaster.pid').exists(),retained_databases=sorted(pg.databases)))
