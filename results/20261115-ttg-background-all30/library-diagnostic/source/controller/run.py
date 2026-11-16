"""Five bounded LibraryLoans diagnostic workflows; accepted execution reused."""
import argparse,importlib.util,json,os,shutil,subprocess,sys,time,uuid
from pathlib import Path
OWN=Path(__file__).resolve().parent;ROOT=OWN.parents[1]
E=ROOT/'project-notes/measurements/ttg-library-prefetch-performance-20261116'
OLD=OWN.parent/'ttg-background-pushdown-portfolio-performance-20261115'
V2=OWN.parent/'ttg-background-pushdown-portfolio-performance-v2-20261115'
sys.path.insert(0,str(V2))
from runner_v2 import load_runner
base,semantic=load_runner()
from ia_postgres import OwnedPostgres as ParentPG
from ia_runner import Sources,storage_watch
from ia_interop import read_json,reference,require
from owned_postgres import BIN,free_port

def module(name,path):
 spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);sys.modules[name]=m;spec.loader.exec_module(m);return m
def write(p,v):Path(p).write_text(json.dumps(v,indent=2)+'\n')
def checked(r):
 p=Path(r['path']);require(reference(p)==r,'Changed diagnostic input '+str(p));return p

class PG(ParentPG):
 def __init__(self,directory,runtime,run_directory,guard):
  self.directory=Path(directory).resolve();self.runtime=Path(runtime).resolve()
  require(self.directory.is_relative_to(OWN) and not self.directory.exists(),'New diagnostic cluster only')
  self.run_directory=Path(run_directory).resolve();self.source_guard=guard
  self.port=free_port();self.owner=str(uuid.uuid4());self.started=False
  self.databases=set();self.services=[];self.admin_process=None
  self.statement_logging=False;self.context=None
  self.startup_floor=3*1024**3;self.case_floor=2560*1024**2
 def accept_completed(self,case,cell,name,directory,proof,expected):
  directory=Path(directory)
  require(len([r for r in read_json(directory/'requests.json') if r['phase']=='workflow'])==23,
   'Original LibraryLoans23HTTP workflow differs')
  require(bool(list(directory.glob('library-timeliness-*.jsonl*')))==case['timeliness_observer'],
   'Declared observer enablement differs from retained trace')
  check=None
  if case['timeliness_observer']:
   validator=module('_library_timeliness_validator',Path(os.environ['TTG_LIBRARY_OBSERVER']))
   result=validator.validate_trace(list(directory.glob('library-timeliness-*.jsonl')),require_activity=True,require_access_sql=(cell=='off'))
   check=self.run_directory/'diagnostic-checks'/(case['trial_id']+'.json');check.parent.mkdir(exist_ok=True);write(check,result)
   require(result['passed'],'Timeliness trace integrity failed; preserve case/database')
  super().accept_completed(case,cell,name,directory,proof,expected)
  if check:self.context['result']['timeliness_validation']=reference(check)

def run(plan_path,output,cluster):
 plan_path=Path(plan_path).resolve();plan_ref=reference(plan_path);plan=read_json(plan_path)
 require(plan['kind']=='library-prefetch-timeliness-diagnostic-v1' and not plan['observer_pending'],'Final bound observer required')
 require(len(plan['schedule'])==5 and [r['config_id']for r in plan['schedule']]==['off','restored','restored','restored','restored'],'Exact five declared workflows required')
 require([r['timeliness_observer']for r in plan['schedule']]==[True,True,True,True,False],'Exact traced/control sequence differs')
 require(all(r['app']=='library_loans' and r['case_id']=='library_loans-smoke' and r['scale']=='smoke' and r['phase']=='diagnostic' and r['length']is None for r in plan['schedule']),'Only fixed LibraryLoans diagnostic scope is authorized')
 checked(plan['observer']);checked(plan['observer_manifest']);checked(plan['observer_checks'])
 guard=Sources(plan['sources']);output=Path(output).resolve();cluster=Path(cluster).resolve()
 require(output.is_relative_to(E) and not output.exists(),'New owned output required')
 require(cluster.is_relative_to(OWN) and not cluster.exists(),'New owned cluster required')
 output.mkdir(parents=True);(output/'cases').mkdir()
 trial_module=module('_library_diagnostic_accepted_trial',OWN/'trial.py')
 storage=module('_library_diagnostic_owned_storage',OWN/'storage.py')
 trial_module.compress_closed_traces=storage.compress_closed_traces
 os.environ.update(TTG_PYTHON=str(ROOT/'reproduction/ttg-littlex-freethreaded/python.sh'),
  TTG_RESEARCH_CAPTURE='timing',TTG_LIBRARY_SERVE=str(OWN/'serve.py'),TTG_LIBRARY_OBSERVER=plan['observer']['path'])
 clean=checked(plan['runtime']['clean']);overlay=checked(plan['runtime']['overlay'])
 index=dict(kind=plan['kind'],stage='diagnostic',passed=False,status='running',creator_pid=os.getpid(),started_ns=time.time_ns(),plan=plan_ref,planned=5,rows=[])
 write(output/'index.json',index);expected=None
 def source_guard():guard();require(reference(plan_path)==plan_ref,'Diagnostic plan changed')
 pg=PG(cluster,Path(read_json(clean)['root']),output,source_guard)
 try:
  with pg:
   index.update(owner=pg.owner,settings=pg.settings_ref)
   for case in plan['schedule']:
    source_guard();os.environ['TTG_LIBRARY_TRACE']='1' if case['timeliness_observer'] else '0'
    directory=output/'cases'/case['trial_id'];start=time.monotonic()
    pg.context=dict(directory=directory,case=case,cell=case['config_id'],source_manifest=plan['sources'],prior_metrics={})
    write(output/'active-case.json',case)
    with storage_watch(output,case,2*1024**3):
     trial_module.Trial().run(case,case['config_id'],directory,pg,clean,overlay,expected)
    if expected is None:expected=read_json(pg.context['result']['proof']['path'])
    metrics=read_json(pg.context['result']['metrics']['path'])
    requests=read_json(directory/'requests.json');primary=[r for r in requests if r['phase']=='workflow']
    require(len(primary)==23,'Original LibraryLoans23HTTP workflow differs')
    traces=list(directory.glob('library-timeliness-*.jsonl*'))
    require(bool(traces)==case['timeliness_observer'],'Declared observer enablement differs from retained trace')
    index['rows'].append(dict(**case,passed=True,result=pg.context['result'],gil_proof=reference(directory/'gil-proof.json'),
     timeliness_traces=[reference(p)for p in traces],case_wall_s=time.monotonic()-start,
     interpretation='Diagnostic observation only; async SQL/job counts may vary; no historical count equality gate.'))
    write(output/'index.json',index);print(json.dumps(dict(accepted=len(index['rows']),total=5,trial=case['trial_id'],business_HTTP=len(primary))),flush=True)
  guard.verify_hashes();source_guard();index.update(passed=True,status='complete',source_after_passed=True)
 except BaseException as error:
  index.update(status='failed',error=type(error).__name__+': '+str(error));raise
 finally:
  write(output/'index.json',index)
  status=subprocess.run([str(BIN/'pg_ctl'),'-D',str(cluster/'data'),'status'],capture_output=True,text=True)
  write(output/'lifecycle.json',dict(services_stopped=all(p.poll()is not None for p in pg.services),
   services=[dict(pid=p.pid,exit_code=p.poll())for p in pg.services],pg_status=status.returncode,
   postmaster_pid_exists=(cluster/'data/postmaster.pid').exists(),retained_databases=sorted(pg.databases),
   free_bytes=shutil.disk_usage(ROOT).free,source_after_passed=index.get('source_after_passed',False)))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--plan',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--cluster',type=Path,required=True)
 a=p.parse_args();run(a.plan,a.output,a.cluster)
