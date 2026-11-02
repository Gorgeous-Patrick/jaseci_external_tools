"""Bounded arithmetic/source-definition review from saved derivatives and small metrics only."""
import hashlib,json,statistics
from collections import Counter
from pathlib import Path
R=Path('/home/baichuan/jaseci');E=R/'project-notes/measurements/ttg-interability-performance-20261101';O=R/'project-notes/measurements/ttg-interability-review-20261101'
cache={}
def load(p):
 p=Path(p)
 if p not in cache:
  b=p.read_bytes();cache[p]=(hashlib.sha256(b).hexdigest(),json.loads(b) if p.suffix=='.json' else b.decode())
 return cache[p][1]
def ref(p):
 p=Path(p);load(p);return dict(path=str(p),sha256=cache[p][0])
def checked(v):assert ref(v['path'])==v;return load(v['path'])
def stats(v):return dict(n=3,values=v,median=statistics.median(v),min=min(v),max=max(v),mean=statistics.mean(v),stdev=statistics.stdev(v))
a=load(E/'analysis-v1/results.json');startup=load(E/'process-startup-attribution-v1.json');interim=load(E/'primary-http-interim-v1.json');seal=load(E/'analysis-v1/artifacts.json')
assert ref(E/'analysis-v1/results.json')['sha256']=='3225413d9fe11f25fe0054dece9e68ece1772d9e667e2bc0e57dbbf0d2deee18'
assert ref(E/'analysis-v1/artifacts.json')['sha256']=='d0fc68f5308de60bf8684838c6e07c20f9df2fc62e8c93fa5f8b85b43c7c3b35'
assert ref(E/'process-startup-attribution-v1.json')['sha256']=='51e0117eaeddc045ba63047cb19663d6ef005c0cb82b90cd85ad91fdbd4e84f8'
assert a['passed'] and startup['passed'] and len(a['samples'])==36 and len(a['rows'])==12 and len(startup['rows'])==8
checked(seal['source']);assert checked(seal['output'])==a
for r in a['inputs']:checked(r)
for r in startup['sources']:checked(r)
bytrial={};records=[]
for s in a['samples']:
 d=checked(s['audit']);m=checked(s['metric']);bytrial[s['trial_id']]=s
 assert d['refs']['metrics']==s['metric'] and d['primary']==s['primary'] and s['primary']=={k:v for k,v in s['primary'].items()}
 assert s['HTTP_response_sum_ns']==d['HTTP_workflow_sum_ns'] and s['HTTP_response_union_ns']==d['HTTP_workflow_union_ns'] and s['HTTP_response_span_ns']==d['HTTP_workflow_span_ns']
 req=[r for r in d['HTTP_requests'] if r['phase']=='workflow'];assert sum(r['end_ns']-r['start_ns'] for r in req)==s['HTTP_response_sum_ns'] and len(req)==s['HTTP_requests']
 assert s['recorded_parent_IPC_workers']==sum(r['post_response_drain']['observed_threads'] for r in req)
 pids={};work=Counter();fusion=Counter();observations=[]
 for event in m['model_outcomes']:
  v=event['summary'];p=v.get('worker_process_pids',[]);t=v.get('worker_process_startup_ms',[]);assert len(p)==len(t)
  for pid,ms in zip(p,t):
   assert type(pid) is int and pid>0 and ms>=0 and (str(pid) not in pids or pids[str(pid)]==ms)
   pids[str(pid)]=ms;observations.append(dict(pid=pid,startup_ms=ms,request=event['origin_request_id'],server_generation=event['server_generation'],scope_id=event.get('scope_id')))
  for k in s['work']:work[k]+=v.get(k,0)
  for k in s['fusion']:fusion[k]+=v.get('fusion',{}).get(k,0)
 assert dict(work)==s['work'] and dict(fusion)==s['fusion']
 assert pids==s['startup_unique_pids'] and len(pids)==s['startup_unique_count'] and sum(pids.values())==s['startup_unique_sum_ms']
 assert set(map(int,pids))==set(d['processes']['background'])
 s['_independent_observations']=observations
 records.append(dict(trial_id=s['trial_id'],audit=s['audit'],metric=s['metric'],unique_startup_pids=len(pids),startup_ms=sum(pids.values()),HTTP_response_sum_ms=s['HTTP_response_sum_ns']/1e6,HTTP_requests=len(req),recorded_parent_IPC_workers=s['recorded_parent_IPC_workers']))
for row in a['rows']:
 ss=sorted([s for s in a['samples'] if (s['case_id'],s['config_id'])==(row['case_id'],row['config_id'])],key=lambda s:s['repeat']);assert len(ss)==3
 mappings={'HTTP_response_sum_ms':[s['HTTP_response_sum_ns']/1e6 for s in ss],'HTTP_response_span_ms':[s['HTTP_response_span_ns']/1e6 for s in ss],'DB_sum_ms':[s['primary']['protocol_sum_ns']/1e6 for s in ss],'DB_union_ms':[s['primary']['protocol_union_ns']/1e6 for s in ss],'SQL_total':[s['primary']['sql_dispatches'] for s in ss],'startup_unique_count':[s['startup_unique_count'] for s in ss],'startup_unique_sum_ms':[s['startup_unique_sum_ms'] for s in ss],'recorded_parent_IPC_workers':[s['recorded_parent_IPC_workers'] for s in ss],'dependency_outcome_count':[s['dependency_outcome_count'] for s in ss]}
 for k,v in mappings.items():assert stats(v)==row[k],(row['case_id'],row['config_id'],k)
 for k,st in row['work'].items():assert stats([s['work'].get(k,0) for s in ss])==st
 for k,st in row['fusion'].items():assert stats([s['fusion'].get(k,0) for s in ss])==st
 interimrow=next(v for v in interim['rows'] if (v['case'],v['mode'])==(row['case_id'],row['config_id']));assert interimrow['HTTP_ms']==mappings['HTTP_response_sum_ms'] and interimrow['HTTP_median_ms']==row['HTTP_response_sum_ms']['median']
 for sr in row['RPCs']:
  rs=[next(r for r in s['RPCs'] if r['ordinal']==sr['ordinal']) for s in ss]
  assert stats([r['HTTP_e2e_ns']/1e6 for r in rs])==sr['HTTP_ms'] and stats([r['protocol_sum_ns']/1e6 for r in rs])==sr['DB_sum_ms'] and stats([r['sql_dispatches'] for r in rs])==sr['SQL_total']
for row in startup['rows']:
 sums=[];counts=[]
 for t in row['trials']:
  s=next(s for s in a['samples'] if s['case_id']==row['case_id'] and s['config_id']==row['config_id'] and s['repeat']==t['repeat']);assert t['audit']==s['audit'] and t['metric']==s['metric']
  assert t['startup_ms_per_PID']==s['startup_unique_pids'] and t['unique_startup_PIDs']==s['startup_unique_count'] and t['unique_PID_startup_sum_ms']==s['startup_unique_sum_ms']
  assert t['observations']==s['_independent_observations'] and t['HTTP_response_sum_ms']==s['HTTP_response_sum_ns']/1e6
  sums.append(s['startup_unique_sum_ms']);counts.append(s['startup_unique_count'])
 assert sums==row['startup_sum_ms'] and counts==row['unique_PID_counts'] and statistics.median(sums)==row['startup_sum_median_ms']
 assert counts==([6,6,6] if row['case_id']=='littlex' else [1,1,1])
# Source timing definitions were inspected at these bounded functions; bind exact byte identities.
sources=[R/'reproduction/ttg-app-performance/workloads.py',R/'reproduction/ttg-continuation-performance/continuation_probe.py',R/'reproduction/ttg-interability-performance/runtime-clean-final-v1/jac/jaclang/runtime/ttg_process_reader.jac',R/'reproduction/ttg-interability-performance/runtime-clean-final-v1/jac/jaclang/runtime/ttg_dependency_prefetch.jac',R/'reproduction/ttg-interability-performance/runtime-clean-final-v1/jac/jaclang/data/impl/store.impl.jac',R/'reproduction/ttg-interability-performance/runtime-clean-final-v1/jac/jaclang/runtime/impl/runtime.impl.jac',R/'reproduction/ttg-interability-performance/runtime-clean-final-v1/jac/jaclang/server/impl/session.impl.jac']
result=dict(passed=True,scope='Small derivative/metric arithmetic and source timing-definition review only; no primary raw reread, timed rerun/DB/test/CPU experiment.',analysis=ref(E/'analysis-v1/results.json'),analysis_seal=ref(E/'analysis-v1/artifacts.json'),startup=ref(E/'process-startup-attribution-v1.json'),HTTP_interim=ref(E/'primary-http-interim-v1.json'),source_definitions=[ref(p) for p in sources],review_source=ref(Path(__file__)),samples=records,checks=['All36 measured samples/all12n3 response sum/span/DB/count/startup/work statistics and interim HTTP vectors match audited derivatives/small raw-bound metrics.','All24 nonoff startup-trial PID maps/observations/values match; repeated identical PID durations counted once, actual SQL child PID set equals startup PID set. LittleX6uniquePIDs/sixstartup-bearing scopes; LL/AB1PID.','ProcessReader clock begins before typecheck/Lock/Popen/config and ends after ready JSON/PID validation. Child imports+PgStore construction included; PgStore connections lazy afterready. Instrumented wall, not Popen-only or SQL load/connection time.','HTTP client clock starts before urlopen and ends after complete response read/context exit; JSON decoding/control request/drain afterward. Span includes inter-request/client/control gaps. Explicit drain observation end excludes subsequent deferred flush/control roundtrip.','Constructor readiness is blocking source order; configured spawn finally joins and outer dependency finally closes readers before return, with Session.close fallback. No aligned close interval or separate IPC-transfer timer is established.','Recorded IPC workers count parent thread launch handles, distinct from unique child PID count: AB9282 two workers/onePID; new one/one; LittleXsix/six.','Continuation_execution/path counters describe abstract continuation-interpreter work, not actual native application ability entries. Native1000 visits remain unchanged.'],limitations=['No startup/HTTP critical-path percentage or additive CPU attribution; no HTTP-minus-DB or payload-minus-DB CPU/IPC subtraction.','Source order does not measure close/IPC phase duration. Readiness values include common instrumentation/import regime.','Persistent-reader reuse and cold-cost admission remain untested roadmap requiring request/transaction/actor/tracing reset; database prepared reuse deferred.'],findings=[])
p=O/'http-startup-analysis-review.json';p.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(ref(p)))
