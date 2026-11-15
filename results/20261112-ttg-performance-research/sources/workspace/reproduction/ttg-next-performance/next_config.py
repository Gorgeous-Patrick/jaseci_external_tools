"""Fixed six-fixture, five-application selection. No DB/import side effects."""
import hashlib,json
from pathlib import Path
OWN=Path(__file__).resolve().parent
ROOT=OWN.parents[1]
EVIDENCE=ROOT/'project-notes/measurements/ttg-next-performance-20261101'
PREVIOUS=OWN.parent/'ttg-continuation-performance'
PLUS=OWN.parent/'ttg-plus-performance'
APP_SNAPSHOT=OWN.parent/'ttg-app-performance/suite-final-20261030-v1/snapshot.json'
CASES=(('linked_list32','linked_list','smoke',32),('linked_list1000','linked_list','small',1000),
       ('littlex','littlex','smoke',None),('issue_desk','issue_desk','domain_scenario',None),
       ('knowledge_map','knowledge_map','domain_scenario',None),('jdrive','jdrive','smoke',None))
MODES=('off','baseline850','next')
COMMON=dict(topology_index=True,prefetch_limit=2048,prefetch_workers=1,
            cross_root_resolve=True,async_prefetch='process',ttg_prefetch_model='always')
def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
def run_config(mode,extra=None):
    if mode not in MODES:raise ValueError('Unknown mode')
    result=dict(**COMMON,prefetching='none' if mode=='off' else 'ttg_dependency',ttg_fused_sql=mode!='off')
    if extra:
        if set(extra)&set(result):raise ValueError('New flags cannot override the fixed common comparison')
        result.update(extra)
    return result
def write_config(directory,mode,extra=None):
    lines=['[project]','name = "ttg-next-comparison"','entry-point = "server.jac"','[run]']
    lines += [k+' = '+json.dumps(v) for k,v in run_config(mode,extra).items()]
    lines += ['[serve]','profile = false','[scale.jwt]','secret = "isolated-ttg-suite-development-secret"',
              'algorithm = "HS256"','exp_delta_days = 1']
    (Path(directory)/'jac.toml').write_text('\n'.join(lines)+'\n')
def schedule(formal=False):
    result=[]
    for ci,(case,app,scale,length) in enumerate(CASES):
        for phase,repeat in ([('excluded_warmup',-1)]+[('measured',n) for n in range(3)] if formal else [('correctness',0)]):
            shift=(ci+max(0,repeat))%3 if formal else 0
            for mode in MODES[shift:]+MODES[:shift]:
                result.append(dict(case_id=case,app=app,scale=scale,length=length,config_id=mode,phase=phase,
                    repeat=repeat,trial_id=f'{case}-{mode}-{phase}-{repeat}'))
    return result
