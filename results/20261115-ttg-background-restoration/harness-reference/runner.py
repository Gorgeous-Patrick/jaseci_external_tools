"""Nov15 sequential controller; accepted Trial/oracles/GIL/cleanup reused."""
import argparse,json,os,time
from pathlib import Path
from ia_config import ROOT,OWN,EVIDENCE,MODES,run_config,schedule,runtime_key
from ia_interop import read_json,reference
from ia_runner import Sources,storage_watch
from ia_trial import Trial
from ia_postgres import OwnedPostgres

def write(p,v):Path(p).write_text(json.dumps(v,indent=2)+'\n')
def run(plan_path,stage,output,cluster):
 plan_path=Path(plan_path).resolve();plan=read_json(plan_path)
 assert plan['kind']=='ttg-background-pushdown-restoration-performance-20261115-v1'
 assert plan['configs']=={m:run_config(m) for m in MODES} and plan['stages'][stage]==schedule(stage)
 assert not plan.get('pending_integration'), 'Runtime/job observer must be integrated and source-bound before launch'
 if stage=='primary':
  release=read_json(EVIDENCE/'formal-run-authorization.json')
  assert release['authorized'] and release['plan']==reference(plan_path)
  correctness=Path(release['correctness_index']['path']);assert reference(correctness)==release['correctness_index']
  completed=read_json(correctness)
  assert completed['plan']==reference(plan_path) and completed['status']=='complete' and completed['passed'] and completed['source_after_passed']
  assert len(completed['rows'])==16 and all(r['passed'] for r in completed['rows'])
  assert all(all(row[k]==v for k,v in expected.items()) for row,expected in zip(completed['rows'],schedule('correctness')))
 output=Path(output).resolve();cluster=Path(cluster).resolve()
 assert output.is_relative_to(EVIDENCE) and not output.exists() and cluster.is_relative_to(OWN) and not cluster.exists()
 os.environ['TTG_PYTHON']=str(ROOT/'reproduction/ttg-littlex-freethreaded/python.sh');os.environ['TTG_RESEARCH_CAPTURE']='timing'
 guard=Sources(plan['sources']);trial=Trial();output.mkdir();(output/'cases').mkdir()
 index=dict(status='running',passed=False,creator_pid=os.getpid(),plan=reference(plan_path),stage=stage,rows=[])
 write(output/'index.json',index);expected={}
 admin_clean=Path(plan['runtimes']['restored']['clean']['path'])
 try:
  with OwnedPostgres(cluster,Path(read_json(admin_clean)['root']),output,guard,startup_floor=plan['storage']['startup'],case_floor=plan['storage']['between']) as pg:
   index.update(owner=pg.owner,settings=pg.settings_ref)
   for row in plan['stages'][stage]:
    guard();directory=output/'cases'/row['trial_id'];mode=row['config_id']
    selected=plan['runtimes'][runtime_key(mode)]
    clean=Path(selected['clean']['path']);overlay=Path(selected['overlay']['path'])
    pg.context=dict(directory=directory,case=row,cell=mode,source_manifest=plan['sources'],prior_metrics={})
    write(output/'active-case.json',row);start=time.monotonic()
    with storage_watch(output,row,plan['storage']['stop']):trial.run(row,mode,directory,pg,clean,overlay,expected.get(row['case_id']))
    if row['case_id'] not in expected:expected[row['case_id']]=read_json(pg.context['result']['proof']['path'])
    index['rows'].append(dict(**row,passed=True,result=pg.context['result'],gil_proof=reference(directory/'gil-proof.json'),case_wall_s=time.monotonic()-start))
    write(output/'index.json',index);print(json.dumps(dict(accepted=len(index['rows']),total=len(plan['stages'][stage]),trial=row['trial_id'])),flush=True)
  guard.verify_hashes();index.update(status='complete',passed=True,source_after_passed=True)
 except BaseException as error:index.update(status='failed',error=type(error).__name__+': '+str(error));raise
 finally:write(output/'index.json',index)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--plan',required=True,type=Path);p.add_argument('--stage',required=True,choices=('correctness','primary'));p.add_argument('--output',required=True,type=Path);p.add_argument('--cluster',required=True,type=Path)
 a=p.parse_args();run(a.plan,a.stage,a.output,a.cluster)
