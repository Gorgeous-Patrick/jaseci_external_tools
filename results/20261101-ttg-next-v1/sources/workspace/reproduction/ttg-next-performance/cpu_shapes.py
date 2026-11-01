"""Bind construction microbenchmarks to actual emitted modules/sites and fixture IDs."""
import hashlib,json
from pathlib import Path
from uuid import UUID
ROOT=Path(__file__).resolve().parents[2]
E=ROOT/'project-notes/measurements/ttg-next-performance-20261101'
def ref(p):return dict(path=str(p.resolve()),sha256=hashlib.sha256(p.read_bytes()).hexdigest())
for case,walker,fixture in [('linked_list32','Traverse','linked_list1000'),('littlex','load_feed','littlex')]:
 plans_path=E/('cpu-compile-next-'+case+'-v1')/'emitted-checkpoint-plans.json'
 emitted=json.loads(plans_path.read_text());plan=next(p for p in emitted['plans'] if p['walker_name']==walker)
 folder=E/'formal-v1/cases'/(fixture+'-next-excluded_warmup--1')
 seal=json.loads((folder/'artifacts.json').read_text())['files']
 for name in ['fixture-raw.json','mapping-initial.json']:
  assert ref(folder/name)['sha256']==seal[name]
 mapping=json.loads((folder/'mapping-initial.json').read_text());state=json.loads((folder/'fixture-raw.json').read_text())
 logical='item:0' if case=='linked_list32' else 'user:0'
 origin=UUID(mapping[logical]);node=next(n for n in state if UUID(n['id'])==origin);actor=str(UUID(node['root_id']))
 sites=plan['sql_templates']['sites']
 if case=='linked_list32':
  active=sites;kind='linear';event=active[0]['event']
  contract=dict(kind=kind,rules=active,source_type=node['arch_type'],source_module=node['props']['archetype']['__module__'],max_origins=2048)
  values=dict(origin=str(origin),source_type=contract['source_type'],source_module=contract['source_module'],max_depth=2047,row_limit=2049)
 else:
  active=[s for s in sites if next(e for e in plan['events'] if e['id']==s['event'])['ability']=='collect'];kind='batch';event=-1
  assert len(active)==2
  contract=dict(kind=kind,rules=active)
  values={'origins_'+str(i):[str(origin)] if s in active else [] for i,s in enumerate(sites)}
  values['row_limit']=2049
 values.update(actor_uuid=actor,actor_text=actor)
 spec=dict(shapes=[dict(name=case+'-'+kind+'-gated',module=emitted['module'],walker=walker,kind=kind,event=event,actor=actor,
   dynamic_contract=contract,dynamic_origins=[str(origin)]*len(active),max_rows=2048,bind_values=values,
   fixture_mapping=ref(folder/'mapping-initial.json'),fixture_state=ref(folder/'fixture-raw.json'))],
   source=ref(Path(__file__)),compiler_emitted_plans=ref(plans_path),
   scope='Construction-only same-input contract: actual emitted sites and fixture UUIDs/types; explicit common2048 bound. These are declared microbenchmark binds, not captured primary Bind packets. Inactive emitted sites use empty arrays.')
 target=E/'cpu-inputs-v1'/case/'runtime-shapes.json';assert not target.exists();target.write_text(json.dumps(spec,indent=2)+'\n');print(ref(target))
