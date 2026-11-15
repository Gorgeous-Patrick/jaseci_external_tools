"""Fresh fixed restoration comparison; old timing samples are never pooled."""
import hashlib,json
from pathlib import Path
OWN=Path(__file__).resolve().parent;ROOT=OWN.parents[1]
EVIDENCE=ROOT/'project-notes/measurements/ttg-background-pushdown-restoration-performance-20261115'
PREVIOUS=OWN.parent/'ttg-continuation-performance';NEXT=OWN.parent/'ttg-next-performance'
APP_SNAPSHOT=OWN.parent/'ttg-app-performance/suite-final-20261030-v1/snapshot.json'
MODES=('off','conservative','background','restored')
APPS=('littlex','linked_list','jdrive','recipe_pantry')
COMMON=dict(topology_index=True,prefetch_limit=2048,prefetch_workers=1,cross_root_resolve=True,async_prefetch='thread',ttg_prefetch_model='always')
def digest(v):return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
def run_config(mode):
 assert mode in MODES
 return dict(**COMMON,prefetching='none' if mode=='off' else 'ttg_dependency',ttg_fused_sql=mode!='off',ttg_background_sql=mode in ('background','restored'))
def write_config(directory,mode):
 values=['[project]','name = "ttg-background-pushdown-restoration-performance-20261115"','entry-point = "server.jac"','[run]']
 values += [k+' = '+json.dumps(v) for k,v in run_config(mode).items()]
 values += ['[serve]','profile = false','[scale.jwt]','secret = "isolated-ttg-suite-development-secret"','algorithm = "HS256"','exp_delta_days = 1']
 (Path(directory)/'jac.toml').write_text('\n'.join(values)+'\n')
def cases():
 return [dict(case_id='littlex-smoke',app='littlex',scale='smoke',length=None),dict(case_id='linked_list-smoke',app='linked_list',scale='smoke',length=None),dict(case_id='jdrive-depth5',app='jdrive',scale='small',length=None),dict(case_id='recipe_pantry-smoke',app='recipe_pantry',scale='smoke',length=None)]
def runtime_key(mode):
 assert mode in MODES
 return 'previous_background' if mode in ('conservative','background') else 'restored'
def schedule(stage):
 assert stage in ('correctness','primary')
 phases=[('correctness',0)] if stage=='correctness' else [('excluded_warmup',-1)]+[('measured',r) for r in range(5)]
 rows=[]
 for ci,case in enumerate(cases() if stage=='correctness' else [cases()[2]]):
  for phase,repeat in phases:
   offset=(ci+max(0,repeat))%len(MODES)
   order=MODES if phase=='correctness' else MODES[offset:]+MODES[:offset]
   for mode in order:rows.append(dict(**case,config_id=mode,phase=phase,repeat=repeat,guard=True,trial_id=f"{case['case_id']}-{mode}-{phase}-{repeat}"))
 return rows
def guard_schedule():return []
