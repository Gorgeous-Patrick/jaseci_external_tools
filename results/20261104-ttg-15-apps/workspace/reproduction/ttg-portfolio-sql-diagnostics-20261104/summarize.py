"""Read-only exact diagnostic-plan and same-logical-state summary."""
import json,hashlib,uuid
from pathlib import Path
R=Path(__file__).resolve().parents[2];E=R/'project-notes/measurements/ttg-portfolio-sql-diagnostics-20261104';run=E/'run-v2'
def ref(p):return dict(path=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest())
def canonical(c):
 a=c['state']['anchors'];mapping={str(uuid.UUID(str(x[0]))):'seq:'+str(x[1]) for x in a}
 def norm(x):
  if isinstance(x,str):
   try:return mapping.get(str(uuid.UUID(x)),x)
   except ValueError:return x
  if isinstance(x,list):return [norm(y) for y in x]
  if isinstance(x,dict):return {norm(k):norm(v) for k,v in x.items()}
  return x
 rows=[]
 for x in a:
  x=list(x)
  if isinstance(x[-1],str):x[-1]=json.loads(x[-1])
  rows.append(norm(x))
 return rows
result=json.loads((run/'result.json').read_text());life=json.loads((run/'lifecycle.json').read_text());assert result['passed'] and len(result['rows'])==4 and life['services_stopped'] and life['pg_status']==3 and not life['pidfile'] and not life['retained_databases']
rows=[];graphs={}
for f in sorted(run.glob('cases/*/captures/*.json')):
 c=json.loads(f.read_text());t=c['target'];assert c['explain']['actual_parameters_verified'];assert c['state']['statistics']==c['state']['statistics_after_explain'];plans=[]
 for p in c['explain']['repetitions']:
  v=p['full_plan'][0];assert v['Planning Time']==p['planning_ms'] and v['Execution Time']==p['execution_ms'];assert v['Plan']['Actual Rows']==t['returned_rows'];nodes=[]
  def walk(n):
   nodes.append({k:n.get(k) for k in ['Node Type','Relation Name','Index Name','Plan Rows','Actual Rows','Actual Loops','Rows Removed by Filter','Rows Removed by Join Filter','Shared Hit Blocks','Shared Read Blocks']})
   for x in n.get('Plans',[]):walk(x)
  walk(v['Plan']);plans.append(dict(repetition=p['repetition'],planning_ms=p['planning_ms'],execution_ms=p['execution_ms'],root_hits=v['Plan'].get('Shared Hit Blocks'),root_reads=v['Plan'].get('Shared Read Blocks'),nodes=nodes))
 graphs.setdefault(t['app'],[]).append(canonical(c));rows.append(dict(app=t['app'],mode=t['mode'],target=t['target_id'],request=t['request'],returned_rows=t['returned_rows'],capture=ref(f),isolation=c['state']['context'][0][3],anchor_count=len(c['state']['anchors']),plans=plans))
assert len(rows)==8
same={app:all(x==xs[0] for x in xs) for app,xs in graphs.items()}
# Preserve any mismatch explicitly instead of asserting a stronger experiment than witnessed.
out=dict(passed=True,primary_measurement=False,result=ref(run/'result.json'),lifecycle=ref(run/'lifecycle.json'),selection=ref(E/'selection.json'),rows=rows,same_logical_state_under_seq_uuid_bijection=same,
 scope='Eight matched actual SELECT Bind packets / sixteen server plans from four accepted full-native workflows. Same-connection census and repeated EXPLAIN warm buffers. Uniform ANALYZE retained. Root counters inclusive; not summed across plan nodes. Primary parameters were not recorded/replayed. HelpQueue sampled generic-path occurrence is not a replacement for every path in its full board.')
(E/'summary.json').write_text(json.dumps(out,indent=2)+'\n');print(same)
for x in rows:
 if x['app']=='littlex':
  print(x['target'],[(p['planning_ms'],p['execution_ms'],p['root_hits']) for p in x['plans']])
