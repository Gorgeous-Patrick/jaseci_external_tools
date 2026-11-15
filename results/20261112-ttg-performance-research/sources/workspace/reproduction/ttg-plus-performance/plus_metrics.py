"""Sealed TTG+ protocol/count results; actual request origin, backend and process."""
from collections import Counter,defaultdict
import gzip
import hashlib
import json
from pathlib import Path
from interop import require,read_json,verify_case,load_jsonl,reference,payload_errors,scope_calls,totals
from interop import concurrency,executor_evidence
from sql_reconciliation import fingerprint,sql_kind


def iter_events(directory):
    """One native JSONL record at a time; no list of huge native summaries."""
    directory=Path(directory).resolve();paths=sorted(directory.glob('server-*.events.jsonl*'))
    verify_case(directory,required=[str(p.relative_to(directory)) for p in paths])
    listed=read_json(directory/'artifacts.json')['files']
    for path in paths:
        opener=gzip.open if path.suffix=='.gz' else open
        with opener(path,'rb') as file:
            for number,line in enumerate(file,1):
                if line.strip():
                    yield json.loads(line),dict(path=str(path),sha256=listed[str(path.relative_to(directory))],
                        line=number,record_sha256=hashlib.sha256(line).hexdigest())


def compact_outcome(event,raw_ref):
    """Exact derived counters/identity; full plans/features/certificates stay raw."""
    s=event['summary'];plans=s.get('plans',[]);continuations=s.get('continuations',[])
    fusion=s.get('fusion',{});regions=fusion.get('regions',[])
    summary={key:s.get(key) for key in ('model','executor','feature_provider','errors',
        'worker_process_pids','worker_process_startup_ms')}
    summary.update(fusion={k:v for k,v in fusion.items() if k!='regions'},
        submitted_count=len(s.get('submitted_ids',[])),promoted_count=len(s.get('promoted_ids',[])),
        unused_cached_count=len(s.get('unused_cached_ids',[])),unavailable_count=len(s.get('unavailable_ids',[])),
        plan_count=len(plans),resolved_plan_count=sum(p.get('resolved_nodes',0)>0 for p in plans),
        resolved_targets_cumulative=sum(p.get('resolved_nodes',0) for p in plans),
        plan_status_counts=dict(Counter(p.get('status','<missing>') for p in plans)),
        continuation_count=len(continuations),
        continuation_path_count=sum(len(c.get('paths',[])) for c in continuations),
        continuation_execution_count=sum(len(c.get('executions',[])) for c in continuations),
        continuation_stop_counts=dict(Counter(c.get('stop','<missing>') for c in continuations)),
        feedback_count=len(s.get('feedback',[])),region_count=len(regions),
        region_kind_counts=dict(Counter(c.get('kind','<missing>') for c in regions)),
        checkpoint_count=len(event.get('checkpoints',[])),hit_count=len(event.get('hits',[])))
    return dict(**{k:v for k,v in event.items() if k not in ('summary','checkpoints','hits')},
        summary=summary,raw_event=raw_ref,format='compact-outcome-v1')


def summarize(directory,acceptance_path):
    directory=Path(directory).resolve()
    seal=verify_case(directory,required=('plus-proof.json','cleanup-target.json','http-raw.jsonl','summary.json'))
    proof=read_json(directory/'plus-proof.json');acceptance=read_json(acceptance_path)
    require(proof['passed'] and acceptance['passed'] and acceptance['raw_seal']==seal,'Acceptance/raw seal mismatch')
    require(acceptance['semantic_proof']==reference(directory/'plus-proof.json'),'Semantic proof changed')
    require(acceptance['target']==reference(directory/'cleanup-target.json'),'Owned target changed')
    require(acceptance['semantic']['passed'] and acceptance['database_state']['matches_sealed_final_graph'],
        'Independent domain replay/physical census absent')
    calls=load_jsonl(directory,'server-*.calls.jsonl*')
    requests=load_jsonl(directory,'http-raw.jsonl*');require(calls,'Missing SQL evidence')
    def identity(record):
        require(record['cell_id']==proof['case_id']+'/'+proof['config_id'] and
            record['trial_id']==directory.name and record['postgres_instance_id']==proof['cluster_owner'],
            'Trace cell/trial/owned instance mismatch')
    business=[r for r in requests if r['phase']=='workflow']
    keys={(str(r['server_generation']),r['request']) for r in business}
    connections={};outcomes=[];resets=[];event_count=0
    for event,raw_ref in iter_events(directory):
        event_count+=1;identity(event)
        require(not payload_errors(event),'Nested dependency payload_error')
        if event['kind']=='connection':
            connections[(str(event['server_generation']),event['backend_pid'],event['client_process_pid'])]=event
        elif (str(event['server_generation']),event.get('origin_request_id')) in keys:
            if event['kind']=='dependency_outcome':outcomes.append(compact_outcome(event,raw_ref))
            elif event['kind']=='explicit_profile_reset':resets.append(event)
        del event
    require(event_count,'Missing event observation files')
    for call in calls:
        identity(call)
        conn=connections.get((str(call['server_generation']),call['backend_pid'],call['client_process_pid']))
        require(conn and call['database']==proof['database']==conn['database'] and
            call['application_name']==conn['application_name'],'SQL lacks matching owned actual backend connection')
    assigned,startup=scope_calls(calls,requests);phases=defaultdict(list)
    for call,row in assigned:phases[row['phase']].append(call)
    primary=phases['workflow']
    require(business and primary,'Missing actual business SQL')
    for outcome in outcomes:require(not outcome['summary'].get('errors'),'Native dependency outcome error')
    require(len(resets)==1,'Exactly one reset before first business request required')
    parents={c['client_process_pid'] for c in primary if c['role']=='foreground'}
    require(len(parents)==1,'Missing/ambiguous actual foreground process')
    groups=defaultdict(list)
    for call in primary:
        if call['send_ns'] is not None:groups[(fingerprint(call['sql']),sql_kind(call['sql']),call['role'])].append(call)
    request_metrics=[]
    for row in requests:
        selected=[c for c,r in assigned if r is row]
        request_metrics.append(dict(request=row['request'],phase=row['phase'],path=row['path'],
            server_generation=row['server_generation'],**totals(selected),actual_overlap=concurrency(selected)))
    return dict(passed=True,case_id=proof['case_id'],config_id=proof['config_id'],stage=proof['stage'],seed=42,
        raw_seal=seal,independent_acceptance=reference(acceptance_path),semantic_proof=acceptance['semantic_proof'],
        primary=dict(**totals(primary),actual_overlap=concurrency(primary),
            executor=executor_evidence(primary,'process',next(iter(parents))),HTTP_requests=len(business),
            late_background_calls=sum(c['send_ns'] is not None and c['ready_ns']>r['end_ns']
                for c,r in assigned if r['phase']=='workflow' and c['role']!='foreground')),
        phases={k:totals(v) for k,v in sorted(phases.items())},startup_excluded=totals(startup),
        request_metrics=request_metrics,Traverse_requests=proof['Traverse_requests'],model_outcomes=outcomes,
        model_outcome_format='compact-outcome-v1',
        profile_reset_events=resets,SQL_fingerprints=[dict(fingerprint=k[0],kind=k[1],role=k[2],
            sql=v[0]['sql'],**totals(v)) for k,v in sorted(groups.items())],
        definitions=dict(primary='Actual sendall-to-ReadyForQuery protocol completion wall; decoding progress included',
            sum='Sum of actual DB intervals, possibly overlapping',union='Union of actual DB intervals',
            count='All real SQL dispatches including foreground/background path, payload and controls',
            training='Always model; one reset after setup; no learned-model comparison'))
