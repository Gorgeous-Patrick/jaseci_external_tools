"""Predeclared TTG+ comparison. Imports do not start any runtime or service."""
import hashlib
import json
from pathlib import Path

OWN=Path(__file__).resolve().parent
ROOT=OWN.parent.parent
EVIDENCE=ROOT/'project-notes/measurements/ttg-plus-performance-20261031'
PREVIOUS=OWN.parent/'ttg-continuation-performance'
APP_SNAPSHOT=OWN.parent/'ttg-app-performance/suite-final-20261030-v1/snapshot.json'
APP_CASES=(('linked_list32','linked_list','smoke',32),
           ('linked_list1000','linked_list','small',1000),
           ('littlex','littlex','smoke',None))
CELLS=('off','prefusion','ttg_plus')
COMMON=dict(topology_index=True,prefetch_limit=2048,prefetch_workers=1,
            cross_root_resolve=True,async_prefetch='process',ttg_prefetch_model='always')
MAX_STEPS=32768


def run_config(cell):
    if cell not in CELLS:raise ValueError('Unknown TTG+ comparison cell')
    return dict(**COMMON,prefetching='none' if cell=='off' else 'ttg_dependency',
                ttg_fused_sql=cell=='ttg_plus')


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()


def write_config(directory,cell):
    lines=['[project]','name = "ttg-plus-comparison"','entry-point = "server.jac"','[run]']
    lines += [key+' = '+json.dumps(value) for key,value in run_config(cell).items()]
    lines += ['[serve]','profile = false','[scale.jwt]',
              'secret = "isolated-ttg-suite-development-secret"','algorithm = "HS256"','exp_delta_days = 1']
    (Path(directory)/'jac.toml').write_text('\n'.join(lines)+'\n')


def schedule(measured=True):
    result=[]
    for ci,(case,app,scale,length) in enumerate(APP_CASES):
        for phase,repeat in ([('excluded_warmup',-1)]+[('measured',i) for i in range(3)]
                             if measured else [('correctness',0)]):
            shift=(ci+max(0,repeat))%len(CELLS)
            order=CELLS[shift:]+CELLS[:shift]
            if not measured:order=CELLS
            for cell in order:
                result.append(dict(case_id=case,app=app,scale=scale,length=length,
                    config_id=cell,phase=phase,repeat=repeat,
                    trial_id=f'{case}-{cell}-{phase}-{repeat}'))
    return result
