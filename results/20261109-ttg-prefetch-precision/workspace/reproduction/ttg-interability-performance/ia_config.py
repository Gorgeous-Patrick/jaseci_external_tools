"""Fixed bounded portfolio; no runtime or DB import side effects."""
import hashlib,json
from pathlib import Path
OWN=Path(__file__).resolve().parent;ROOT=OWN.parents[1]
EVIDENCE=ROOT/'project-notes/measurements/ttg-interability-performance-20261101'
PREVIOUS=OWN.parent/'ttg-continuation-performance';NEXT=OWN.parent/'ttg-next-performance'
APP_SNAPSHOT=OWN.parent/'ttg-app-performance/suite-final-20261030-v1/snapshot.json'
CASES=(('finite_list32','linked_list','smoke',32),('finite_list1000','linked_list','small',1000),
       ('guard_chain','region_chain','tiny',None),('littlex','littlex','smoke',None))
MODES=('off','baseline9282','interability')
COMMON=dict(topology_index=True,prefetch_limit=2048,prefetch_workers=1,cross_root_resolve=True,
            async_prefetch='process',ttg_prefetch_model='always')
def digest(v):return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
def run_config(mode):
 if mode not in MODES:raise ValueError('Unknown fixed mode')
 return dict(**COMMON,prefetching='none' if mode=='off' else 'ttg_dependency',ttg_fused_sql=mode!='off')
def write_config(directory,mode):
 values=['[project]','name = "ttg-interability-comparison"','entry-point = "server.jac"','[run]']
 values += [k+' = '+json.dumps(v) for k,v in run_config(mode).items()]
 values += ['[serve]','profile = false','[scale.jwt]','secret = "isolated-ttg-suite-development-secret"','algorithm = "HS256"','exp_delta_days = 1']
 (Path(directory)/'jac.toml').write_text('\n'.join(values)+'\n')
def schedule(formal=False):
 rows=[]
 for ci,(case,app,scale,length) in enumerate(CASES):
  stages=[('excluded_warmup',-1)]+[('measured',i) for i in range(3)] if formal else [('correctness',0)]
  for phase,repeat in stages:
   shift=(ci+max(0,repeat))%3 if formal else 0
   for mode in MODES[shift:]+MODES[:shift]:
    rows.append(dict(case_id=case,app=app,scale=scale,length=length,config_id=mode,phase=phase,repeat=repeat,
      guard=True,trial_id=f'{case}-{mode}-{phase}-{repeat}'))
 return rows
def guard_schedule():
 return [dict(case_id='guard_chain_false',app='region_chain',scale='tiny',length=None,config_id=m,
   phase='guard_correctness',repeat=0,guard=False,trial_id=f'guard_chain_false-{m}-guard_correctness-0') for m in MODES]
