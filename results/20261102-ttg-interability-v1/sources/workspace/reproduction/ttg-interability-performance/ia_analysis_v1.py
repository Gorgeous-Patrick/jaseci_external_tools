"""Read-only primary HTTP/SQL/work/startup attribution from audited derivatives."""
import argparse,hashlib,json,statistics
from collections import Counter,defaultdict
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
OWN=Path(__file__).resolve().parent
CASES=('finite_list32','finite_list1000','guard_chain','littlex')
MODES=('off','baseline9282','interability')
WORK=('plan_count','resolved_plan_count','continuation_count','continuation_execution_count',
      'continuation_path_count','feedback_count','submitted_count','promoted_count','unused_cached_count','unavailable_count')
FUSION=('queries','template_queries','region_queries','region_cache_paths','region_reuses','region_fallbacks',
        'frontier_region_attempts','fallback_resolver_calls','payload_dispatches')
def read(p):return json.loads(Path(p).read_text())
def ref(p):
 p=Path(p).resolve();return dict(path=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest())
def checked(value):
 p=Path(value['path']);assert ref(p)==value,'Changed input '+str(p);return p
def stats(v):
 assert len(v)==3
 return dict(n=3,values=v,median=statistics.median(v),min=min(v),max=max(v),
             mean=statistics.mean(v),stdev=statistics.stdev(v))
def build(audit,export,output):
 audit=Path(audit).resolve();export=Path(export).resolve();output=Path(output).resolve()
 assert not output.exists();summary=read(audit/'summary.json');numeric=read(export)
 assert summary['passed'] and summary['result']==ref(export)
 assert summary['sample_counts']==dict(all=48,excluded_warmups=12,measured=36,cells=12,n_per_cell=3)
 index=read(checked(summary['index']));source_refs=[ref(audit/'summary.json'),ref(export),ref(Path(__file__))]
 samples=[];rows=[]
 for case in CASES:
  for mode in MODES:
   selected=[]
   for repeat in range(3):
    trial=f'{case}-{mode}-measured-{repeat}';path=audit/(trial+'.json');d=read(path);source_refs.append(ref(path))
    accepted=next(v for v in index['rows'] if v['trial_id']==trial)
    assert d['refs']==accepted['result']
    mp=checked(d['refs']['metrics']);m=read(mp);source_refs.append(ref(mp))
    assert d['primary']['protocol_sum_ns']==m['primary']['protocol_sum_ns']
    requests=[r for r in d['HTTP_requests'] if r['phase']=='workflow']
    assert len({(str(r['server_generation']),r['request']) for r in requests})==len(requests)
    assert sum(r['end_ns']-r['start_ns'] for r in requests)==d['HTTP_workflow_sum_ns']
    for request in requests:
     assert abs((request['end_ns']-request['start_ns'])/1e6-request['http_e2e_ms'])<1e-6
     assert request['end_ns']<=request['post_response_drain']['start_ns']
    seen={};events=[];fusion=Counter();work=Counter();reasons=Counter()
    for event in m['model_outcomes']:
     s=event['summary'];assert not s.get('errors') and s['payload_error_count']==0
     pids=s.get('worker_process_pids',[]);durations=s.get('worker_process_startup_ms',[])
     assert len(pids)==len(durations)
     for pid,value in zip(pids,durations):
      assert pid not in seen or abs(seen[pid]-value)<1e-9
      seen[pid]=value
     work.update({k:s.get(k,0) for k in WORK})
     f=s.get('fusion',{});fusion.update({k:f.get(k,0) for k in FUSION})
     reasons.update(f.get('region_fallback_reasons',{}))
     events.append(dict(request=event['origin_request_id'],server_generation=event['server_generation'],
       scope_id=event.get('scope_id'),raw_event=event['raw_event'],work={k:s.get(k,0) for k in WORK},
       fusion={k:f.get(k,0) for k in FUSION},fallback_reasons=f.get('region_fallback_reasons',{}),
       startup_pids=pids,startup_ms=durations))
    assert set(seen)<=set(d['processes']['background'])
    sample=dict(trial_id=trial,case_id=case,config_id=mode,repeat=repeat,audit=ref(path),metric=d['refs']['metrics'],
      HTTP_response_sum_ns=d['HTTP_workflow_sum_ns'],HTTP_response_union_ns=d['HTTP_workflow_union_ns'],
      HTTP_response_span_ns=d['HTTP_workflow_span_ns'],recorded_drain_observation_sum_ns=d['HTTP_explicit_drain_sum_ns'],
      first_HTTP_start_to_last_drain_observation_end_ns=d['HTTP_with_drain_span_ns'],HTTP_requests=len(requests),
      recorded_parent_IPC_workers=sum(r['post_response_drain']['observed_threads'] for r in requests),
      startup_unique_pids=seen,startup_unique_count=len(seen),startup_unique_sum_ms=sum(seen.values()),
      dependency_outcome_count=len(events),work=dict(work),fusion=dict(fusion),region_fallback_reasons=dict(reasons),
      counter_events=events,primary=d['primary'],processes=d['processes'],
      RPCs=[{k:r[k] for k in ('ordinal','walker','request','server_generation','path','HTTP_e2e_ns','categories',
                             'sql_dispatches','sql_data','sql_control','protocol_sum_ns','protocol_union_ns',
                             'FG_BG_protocol_overlap_ns','SQL_fingerprints')} for r in d['RPCs']])
    selected.append(sample);samples.append(sample)
   row=dict(case_id=case,config_id=mode,n=3,
    HTTP_response_sum_ms=stats([s['HTTP_response_sum_ns']/1e6 for s in selected]),
    HTTP_response_span_ms=stats([s['HTTP_response_span_ns']/1e6 for s in selected]),
    DB_sum_ms=stats([s['primary']['protocol_sum_ns']/1e6 for s in selected]),
    DB_union_ms=stats([s['primary']['protocol_union_ns']/1e6 for s in selected]),
    SQL_total=stats([s['primary']['sql_dispatches'] for s in selected]),
    startup_unique_count=stats([s['startup_unique_count'] for s in selected]),
    startup_unique_sum_ms=stats([s['startup_unique_sum_ms'] for s in selected]),
    recorded_parent_IPC_workers=stats([s['recorded_parent_IPC_workers'] for s in selected]),
    dependency_outcome_count=stats([s['dependency_outcome_count'] for s in selected]),
    work={k:stats([s['work'].get(k,0) for s in selected]) for k in WORK},
    fusion={k:stats([s['fusion'].get(k,0) for s in selected]) for k in FUSION})
   sequence=[[(r['ordinal'],r['walker']) for r in s['RPCs']] for s in selected]
   assert sequence[0]==sequence[1]==sequence[2]
   row['RPCs']=[]
   for ordinal,walker in sequence[0]:
    rpc=[next(r for r in s['RPCs'] if r['ordinal']==ordinal) for s in selected]
    fingerprints=sorted({q['fingerprint'] for r in rpc for q in r['SQL_fingerprints']})
    contributions=[]
    for fingerprint in fingerprints:
     vectors=[[q for q in r['SQL_fingerprints'] if q['fingerprint']==fingerprint] for r in rpc]
     template=next(q for vector in vectors for q in vector)
     assert all(q['sql']==template['sql'] for vector in vectors for q in vector)
     contributions.append(dict(fingerprint=fingerprint,sql=template['sql'],category=template['category'],
       count=stats([sum(q['sql_dispatches'] for q in v) for v in vectors]),
       DB_sum_ms=stats([sum(q['protocol_sum_ns'] for q in v)/1e6 for v in vectors]),
       rows=stats([sum(q['data_rows'] for q in v) for v in vectors]),
       row_bytes=stats([sum(q['data_row_payload_bytes'] for q in v) for v in vectors])))
    categories=sorted({k for r in rpc for k in r['categories']})
    row['RPCs'].append(dict(ordinal=ordinal,walker=walker,
      HTTP_ms=stats([r['HTTP_e2e_ns']/1e6 for r in rpc]),
      DB_sum_ms=stats([r['protocol_sum_ns']/1e6 for r in rpc]),
      SQL_total=stats([r['sql_dispatches'] for r in rpc]),
      categories={k:stats([r['categories'].get(k,0) for r in rpc]) for k in categories},
      SQL_fingerprints=sorted(contributions,key=lambda q:-q['DB_sum_ms']['median'])))
   rows.append(row)
 source_paths=('runtime/ttg_process_reader.jac','runtime/prefetch.jac','runtime/ttg_dependency_prefetch.jac',
               'runtime/impl/runtime.impl.jac','server/impl/session.impl.jac','data/impl/store.impl.jac')
 source_refs.extend(ref(OWN/'runtime-clean-final-v1/jac/jaclang'/p) for p in source_paths)
 source_refs.extend(ref(ROOT/'reproduction/ttg-continuation-performance'/p) for p in ('boundary_overlay.py','continuation_probe.py'))
 value=dict(passed=True,inputs=source_refs,rows=rows,samples=samples,
  definitions=dict(HTTP='Instrumented client start before urlopen through full response read/context exit; JSON decode and explicit drain afterward.',
   HTTP_span='First primary HTTP start to last response end; gaps include client/control work. One RPC for LL and AB; original multi-RPC LittleX.',
   startup='Native ProcessReader.init before Lock/Popen through child ready JSON/PID validation; imports and lazy PgStore object setup included, later IPC/load/DB connect excluded.',
   startup_aggregation='Sum once per unique actual child PID; identical repeated summary values checked. No critical-path percentage or CPU subtraction.',
   IPC_workers='Explicit process-prefetch worker launch sites bound by reviewed overlay; observed_threads in primary post-response drain counts those parent IPC threads, not timed IPC transfers.',
   drain='Recorded server worker-observation/join interval ends before deferred trace flush; not the complete client control HTTP roundtrip.',
   work='Cumulative native compact outcome counters, not CPU duration or unique-ID unions.',
   lifecycle='runtime.impl spawn is wrapped by configured_dependency_prefetch; its finally joins, outer dependency scope closes readers before native spawn returns. Session.close also cleans an extant process pool.',
   roadmap='Persistent server/DB readers and admission of cold-start cost are proposals; context/transaction/actor/tracing reset required. Always fixed in these measurements.'))
 output.mkdir(parents=True);p=output/'results.json';p.write_text(json.dumps(value,indent=2)+'\n')
 (output/'artifacts.json').write_text(json.dumps(dict(passed=True,source=ref(Path(__file__)),inputs=source_refs,output=ref(p)),indent=2)+'\n')
 print(json.dumps(dict(passed=True,result=ref(p),manifest=ref(output/'artifacts.json'))))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--audit',type=Path,required=True);p.add_argument('--export',type=Path,required=True)
 p.add_argument('--output',type=Path,required=True);a=p.parse_args();build(a.audit,a.export,a.output)
