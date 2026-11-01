"""Source/control-path explanation linked to one accepted native request; read-only."""
import gzip,hashlib,json,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];E=ROOT/'project-notes/measurements/ttg-next-performance-20261101'
def ref(p):return dict(path=str(p.resolve()),sha256=hashlib.sha256(p.read_bytes()).hexdigest())
def read(p):return json.loads(p.read_text())
O=ROOT/'reproduction/ttg-next-performance';D=E/'formal-v1/cases/littlex-next-measured-0'
seal=read(D/'artifacts.json')['files'];calls=[];raw=[]
for name,digest in seal.items():
 if name.startswith('server-2-') and '.calls.jsonl' in name:
  p=D/name;assert ref(p)['sha256']==digest;raw.append(ref(p))
  with gzip.open(p,'rt') if name.endswith('.gz') else p.open() as f:
   for line in f:
    c=json.loads(line)
    if c.get('origin_request_id')=='2:20' and str(c['server_generation'])=='2':
     calls.append({k:c.get(k) for k in ('send_ns','ready_ns','sql','role','backend_pid','client_process_pid','data_rows')})
calls.sort(key=lambda c:c['send_ns']);assert len(calls)==16
metric=read(E/'formal-v1/metrics/littlex-next-measured-0.json')
outcome=next(o for o in metric['model_outcomes'] if o['origin_request_id']=='2:20')
compiled=E/'cpu-compile-next-littlex-v1/emitted-checkpoint-plans.json';emitted=read(compiled)
plan=next(p for p in emitted['plans'] if p['walker_name']=='load_feed')
source=O/'runtime-clean-9282-v1/jac/jaclang/runtime/ttg_dependency_prefetch.jac'
lines=source.read_text().splitlines()
sections=[dict(start=a,end=b,text='\n'.join(lines[a-1:b])) for a,b in [(257,276),(322,343),(365,374),(398,425)]]
result=dict(passed=True,source=ref(Path(__file__)),attribution=ref(E/'attribution-v1/results.json'),
 emitted=ref(compiled),module=emitted['module'],walker='load_feed',events=plan['events'],sites=plan['sql_templates']['sites'],
 native_source=ref(source),source_excerpts=sections,raw_seal=ref(D/'artifacts.json'),consumed_calls=raw,
 metric=ref(E/'formal-v1/metrics/littlex-next-measured-0.json'),compact_outcome=outcome,actual_SQL_sequence=calls,
 explanation=[
 'Recorded first feed: one root linear template query, two ordinary collect path queries, one native cached root path hit; no payload or observer error.',
 'Source initializes frontier_attempted once for each prefetch_continuation invocation. First resolver sets it before attempting emitted frontier. Later resolver calls in that invocation skip another frontier attempt.',
 'Root run visit event1 consumes that attempt; its emitted linear descriptor covers the root/Profile path only. The outer continuation resolves collect events4/5 through ordinary per-path fallback. Later hooks find those scope/path reuse-cache entries before the frontier branch.',
 'This control-flow interpretation is supported by exact source, emitted event IDs, native compact reached-point counts and actual SQL sequence; compact capture does not log each failed/skipped frontier invocation separately.',
 'The recorded barrier at gather:277 limits the predicted tail. Its presence alone does not explain missing collect batching.'],
 next_step='Untested: allow another emitted-frontier attempt per distinct region/activation, with path-result reuse/dedup and independent native equivalence tests; retain guard and queue semantics.')
p=E/'littlex-mechanism-v1.json';assert not p.exists();p.write_text(json.dumps(result,indent=2)+'\n');print(ref(p))
