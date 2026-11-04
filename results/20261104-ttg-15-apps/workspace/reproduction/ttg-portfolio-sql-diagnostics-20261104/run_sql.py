"""Four bounded full-native diagnostic workflows and eight matched SELECTs."""
import json,os,shutil,subprocess
from pathlib import Path
from ia_config import OWN,EVIDENCE
from ia_interop import read_json,reference,sha256
from ia_runner import Sources,storage_watch
from ia_trial import Trial,load_unsealed
from ia_postgres import OwnedPostgres
from owned_postgres import BIN
from overlay import transform
R=OWN.parents[1];B=R/'project-notes/measurements/ttg-portfolio-v2-20261104'
def write(p,x):p.write_text(json.dumps(x,indent=2)+'\n')
def main():
 plan=read_json(B/'plan.json');index=read_json(B/'run-v1/index.json');selection=read_json(EVIDENCE/'selection.json')
 E=EVIDENCE/'run-v1';assert not E.exists();E.mkdir();(E/'cases').mkdir()
 m=read_json(plan['overlay']['path']);root=Path(m['root']);target=OWN/'runtime-v1';assert not target.exists()
 shutil.copytree(root,target,copy_function=os.link)
 p=target/'jac/jaclang/data/impl/pgwire.impl.jac';old=sha256(p);new=p.with_suffix('.diagnostic-tmp');new.write_text(transform(p.read_text()));os.replace(new,p);assert sha256(root/p.relative_to(target))==old
 files=dict(m['files']);files[str(p.relative_to(target))]=sha256(p)
 for name in ['capture.py','explain.py']:
  dest=target/'jac'/name;assert not dest.exists();shutil.copyfile(OWN/name,dest);files[str(dest.relative_to(target))]=sha256(dest)
 m={**m,'root':str(target),'files':files,'diagnostic_base':plan['overlay']};write(E/'overlay.json',m)
 hashes=read_json(plan['sources']['path'])['files'].copy();hashes.update({str(f):sha256(f) for f in OWN.glob('*.py')});hashes[str(EVIDENCE/'selection.json')]=sha256(EVIDENCE/'selection.json');hashes.update({str(target/k):v for k,v in files.items()})
 write(E/'sources.json',dict(files=hashes));guard=Sources(reference(E/'sources.json'))
 class PG(OwnedPostgres):
  def accept_completed(self,case,cell,name,directory,proof,expected):
   ts=[t for t in selection['targets'] if t['app']==case['app'] and t['mode']==cell]
   fs=list((directory/'captures').glob('*.json'));assert len(fs)==len(ts)
   calls=load_unsealed(directory,'server-*.calls.jsonl*');accepted=[]
   for t in ts:
    f=next(f for f in fs if read_json(f)['target']==t);c=read_json(f);assert c['explain']['actual_parameters_verified']
    actual=sorted([v for v in calls if v.get('origin_request_id')==t['request'] and str(v.get('server_generation'))==str(t['generation']) and v.get('sql')==t['sql'] and v.get('role')=='foreground' and v.get('send_ns') is not None],key=lambda x:x['send_ns'])
    assert actual and actual[0]['error'] is None and actual[0]['returned_rows']==t['returned_rows']
    assert actual[0]['backend_pid']==c['state']['context'][0][2]
    assert c['state']['statistics']==c['state']['statistics_after_explain']
    accepted.append(dict(capture=reference(f),actual_call=actual[0]))
   assert read_json(directory/'planner-statistics-before-workflow.json')['passed']
   write(directory/'diagnostic-acceptance.json',dict(passed=True,selected=accepted,full_native_proof=reference(directory/'plus-proof.json'),normalization=reference(directory/'planner-statistics-before-workflow.json'),primary_measurement=False))
   write(directory/'artifacts.json',dict(passed=True,files={str(f.relative_to(directory)):sha256(f) for f in directory.rglob('*') if f.is_file() and f.name!='artifacts.json'}))
   return super().accept_completed(case,cell,name,directory,proof,expected)
 os.environ['TTG_PYTHON']=str(R/'reproduction/ttg-littlex-freethreaded/python.sh')
 pg=PG(OWN/'pg-v1',Path(read_json(plan['clean']['path'])['root']),E,guard,startup_floor=768*1024**2,case_floor=640*1024**2)
 write(E/'launch.json',dict(creator_pid=os.getpid(),selection=reference(EVIDENCE/'selection.json'),plan=reference(B/'plan.json')));rows=[]
 try:
  with pg:
   for app in ('help_queue','littlex'):
    for mode in ('off','thread'):
     original=next(r for r in index['rows'] if r['app']==app and r['config_id']==mode and r['phase']=='measured' and r['repeat']==0)
     case={k:original[k] for k in plan['schedule'][0]};case.update(phase='diagnostic',trial_id=app+'-'+mode+'-sql')
     directory=E/'cases'/case['trial_id'];pg.context=dict(directory=directory,case=case,cell=mode,source_manifest=reference(E/'sources.json'),prior_metrics={})
     os.environ.update(TTG_DIAG_SELECTION=str(EVIDENCE/'selection.json'),TTG_DIAG_CONFIG_ID=app+'-'+mode,TTG_DIAG_OUTPUT=str(directory/'captures'))
     expected=read_json(original['result']['proof']['path'])
     with storage_watch(E,case,512*1024**2):Trial().run(case,mode,directory,pg,Path(plan['clean']['path']),E/'overlay.json',expected)
     rows.append(dict(app=app,mode=mode,result=pg.context['result']));print('ACCEPTED SQL',app,mode,flush=True)
  guard.verify_hashes();write(E/'result.json',dict(passed=True,rows=rows,primary_measurement=False))
 finally:
  s=subprocess.run([str(BIN/'pg_ctl'),'-D',str(pg.directory/'data'),'status'],capture_output=True,text=True)
  write(E/'lifecycle.json',dict(services_stopped=all(p.poll() is not None for p in pg.services),services=[dict(pid=p.pid,exit_code=p.poll()) for p in pg.services],pg_status=s.returncode,pidfile=(pg.directory/'data/postmaster.pid').exists(),retained_databases=sorted(pg.databases)))
if __name__=='__main__':main()
