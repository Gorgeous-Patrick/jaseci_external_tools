"""Audit actual Access demand, not hypothetical ID-only query rewrites. No DB."""
from collections import defaultdict,Counter
from pathlib import Path
import gzip,hashlib,json
HERE=Path(__file__).resolve().parent;E=HERE.parent
R=Path('/home/baichuan/jaseci')
APP=R/'reproduction/ttg-app-performance/suite-final-20261030-v1/app_suite/apps/recipe_pantry/server.jac'
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def ref(p):return dict(path=str(p),sha256=sha(p))
def uid(v):return v.replace('-','')
def lines(p):
 with (gzip.open(p,'rt') if p.suffix=='.gz' else p.open()) as f:
  for n,line in enumerate(f,1):
   if line.strip():yield n,json.loads(line)
results=read(E/'results.json');audit=[];inputs={str(APP):sha(APP)}
source=APP.read_text()
assert 'return isinstance(item, kind) and jid(item) in [jid(n) for n in [root-->]];' in source
assert 'visit [-->[?:Meal, status=="planned"]];' in source
reason={
 'PantryBoard':'Unfiltered typed Accesses and their Purchase/Consumption fields contribute to the returned board.',
 'PlanMeal':'Direct Recipe lookup and the unfiltered _owns root-neighbor Access; jid-only neighbors are valid demand.',
 'BuyIngredient':'Direct Ingredient lookup and unfiltered _owns root-neighbor Access; native validation/writes retained.',
 'CookMeal':'Direct Meal lookup, unfiltered _owns neighbors and _requirements graph Accesses; native guards decide the suffix.',
 'ShoppingList':'Recipe/Requirement/Ingredient Accesses feed requirements/shortages; status-filtered Meal candidates are checked separately.'}
for s in results['samples']:
 if s['phase']!='measured' or s['mode']!='after':continue
 raw=Path(s['raw']['path']);assert sha(raw)==s['raw']['sha256'];inputs[str(raw)]=sha(raw);base=raw.parent;seal=read(raw)['files']
 def checked(name):
  p=base/name;assert sha(p)==seal[name];inputs[str(p)]=seal[name];return p
 assert sha(checked('server.jac'))==sha(APP)
 nodes={uid(x['id']):x for x in read(checked('fixture-raw.json'))+read(checked('final-graph-raw.json')) if x['kind']=='NodeAnchor'}
 http={ (str(e['server_generation']),e['request']):e for _,e in lines(checked('http-raw.jsonl')) if e['phase']=='workflow'}
 ev=defaultdict(list)
 for f in sorted(base.glob('server-*.events.jsonl*')):
  checked(f.name)
  for line,e in lines(f):
   key=(str(e['server_generation']),e.get('origin_request_id'))
   if key in http and e['kind'].startswith('precision_'):ev[key].append((f.name,line,e))
 request_rows=[]
 for key,h in http.items():
  es=ev[key];demands=defaultdict(list);returned=defaultdict(list)
  batches={e['batch']:e for _,_,e in es if e['kind']=='precision_prefetch_batch'}
  for file,line,e in es:
   if e['kind']=='precision_access' and not e['planning']:
    for v in e['ids']:demands[e['session'],uid(v)].append(dict(file=file,line=line,timestamp_ns=e['timestamp_ns']))
   if e['kind']=='precision_payload_returned':returned[e['session'],uid(e['uid'])].append((file,line,e))
  pset=set(returned);dset=set(demands);assert pset<=dset
  w=h['path'].split('/')[-1];assert w in reason
  objects=[]
  for k,deliveries in sorted(returned.items()):
   assert k[1] in nodes,(w,k)
   first=min(batches[e['batch']]['timestamp_ns'] for _,_,e in deliveries)
   later=[x for x in demands[k] if x['timestamp_ns']>=first];assert later
   assert all(not e['already_materialized'] for _,_,e in deliveries)
   node=nodes[k[1]]
   objects.append(dict(uid=k[1],session=k[0],type=node['arch_type'],name=node['props']['archetype'].get('name'),
    payload_refs=[dict(file=f,line=l) for f,l,_ in deliveries],later_demand_refs=later))
  # This app's only node-property filter inside a graph query is ShoppingList's
  # planned-Meal selection. Current prefetch returns no Meal in these requests,
  # so it cannot include any excluded cooked-Meal payload. All _owns neighbors
  # are intentionally in the unfiltered Access result, including jid-only use.
  filtered_candidates=[x for x in objects if w=='ShoppingList' and x['type']=='Meal']
  assert not filtered_candidates
  expected=next(x for x in s['requests'] if x['request']==key[1])
  assert len(pset)==expected['payload_objects']==expected['demanded_prefetch_objects']
  assert len(dset)==expected['successful_demand_objects']
  request_rows.append(dict(request=key[1],walker=w,prefetched=len(pset),used=len(pset&dset),unused=len(pset-dset),
    excluded_graph_filter_payloads=len(filtered_candidates),reason=reason[w],objects=objects))
 total=sum(x['prefetched'] for x in request_rows);assert total==118 and s['payload_objects']==118
 assert sum(x['unused'] for x in request_rows)==s['unused_payload_objects']==0
 audit.append(dict(repeat=s['repeat'],prefetched=total,used=total,unused=0,excluded_graph_filter_payloads=0,
  confirmed_unnecessary=0,requests=request_rows,raw=s['raw']))
assert len(audit)==3
out=dict(passed=True,app='recipe_pantry',mode='repaired_conservative',n=3,prefetched=[118]*3,used=[118]*3,
 unused=[0]*3,excluded_graph_filter_payloads=[0]*3,confirmed_unnecessary=[0]*3,samples=audit,
 definition='White reads are prefetch nodes not needed by the actual user-program Access demand; include unused nodes and source-validated candidates excluded by explicit graph-query filters. Merely using jid rather than node properties is valid Access demand, not waste.',
 qualifications=['Per-request/Session distinct node IDs summed over the workflow, not global graph-node counts.',
 '0 confirmed in the unused and excluded-query-filter classes; not a claim that all fetched properties are required or that no SQL/projection optimization exists.',
 'Read-only audit of existing captures; no new native/DB execution, no hypothetical membership-query rewrite.'],
 source_cases=reason,inputs=inputs,results=ref(E/'results.json'),audit_source=ref(Path(__file__)))
(HERE/'results.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps({k:out[k] for k in ('passed','n','prefetched','used','unused','excluded_graph_filter_payloads','confirmed_unnecessary')},indent=2))
