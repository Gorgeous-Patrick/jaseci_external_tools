"""Fixed expanded portfolio; standard library only, no service side effects."""
import hashlib,json
from pathlib import Path
OWN=Path(__file__).resolve().parent;ROOT=OWN.parents[1]
EVIDENCE=ROOT/'project-notes/measurements/ttg-performance-research-20261112'
PREVIOUS=OWN.parent/'ttg-continuation-performance';NEXT=OWN.parent/'ttg-next-performance'
APP_SNAPSHOT=OWN.parent/'ttg-app-performance/suite-final-20261030-v1/snapshot.json'
MODES=('off','aggressive','conservative')
APPS=('jdrive','littlex','recipe_pantry','linked_list','issue_desk','stock_room','clinic_queue',
      'budget_ledger','knowledge_map','course_path','approval_desk','library_loans','event_seats',
      'help_queue','delivery_route','volunteer_shift','incident_room')
COMMON=dict(topology_index=True,prefetch_limit=2048,prefetch_workers=1,cross_root_resolve=True,
            async_prefetch='thread',ttg_prefetch_model='always')
def digest(v):return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
def run_config(mode):
 assert mode in MODES
 return dict(**COMMON,prefetching={'off':'none','aggressive':'ttg','conservative':'ttg_dependency'}[mode],
             ttg_fused_sql=mode=='conservative')
def write_config(directory,mode):
 values=['[project]','name = "ttg-performance-research-20261112"','entry-point = "server.jac"','[run]']
 values += [k+' = '+json.dumps(v) for k,v in run_config(mode).items()]
 values += ['[serve]','profile = false','[scale.jwt]','secret = "isolated-ttg-suite-development-secret"',
            'algorithm = "HS256"','exp_delta_days = 1']
 (Path(directory)/'jac.toml').write_text('\n'.join(values)+'\n')
def cases():
 small=[dict(case_id=a+'-smoke',app=a,scale='smoke',length=None) for a in APPS]
 large=[dict(case_id='jdrive-depth5',app='jdrive',scale='small',length=None),
        dict(case_id='littlex-50x20',app='littlex',scale='small',length=None),
        dict(case_id='linked_list-1000',app='linked_list',scale='small',length=None)]
 return small+large
def schedule(stage):
 selected=cases()
 if stage=='first':selected=selected[:3]
 elif stage=='small-rest':selected=selected[3:17]
 elif stage=='larger':selected=selected[17:]
 elif stage=='extend-n5':pass
 elif stage=='precision':pass
 else:raise ValueError('Unknown explicit stage')
 rows=[]
 for ci,case in enumerate(selected):
  phases=([('measured',3),('measured',4)] if stage=='extend-n5' else
          [('precision',0)] if stage=='precision' else
          [('correctness',0),('excluded_warmup',-1)]+[('measured',r) for r in range(3)])
  for phase,repeat in phases:
   offset=(APPS.index(case['app'])+max(0,repeat))%3
   order=MODES if phase=='correctness' else MODES[offset:]+MODES[:offset]
   for mode in order:
    rows.append(dict(**case,config_id=mode,phase=phase,repeat=repeat,guard=True,
      trial_id=f"{case['case_id']}-{mode}-{phase}-{repeat}"))
 return rows
def guard_schedule():return []
