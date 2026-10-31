"""Bounded READ-ONLY attribution of18 accepted LittleX primary traces.

No DB jobs, source audit, CPU profile or change to the frozen48-trial exporter.
"""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
from itertools import combinations
from evidence import read_json,sha256,checked_ref,verify_case,load_jsonl
from intervals import BACKGROUND_ROLES,union_ns,intersection
from small_metrics_v1 import scope_calls,totals
from sql_reconciliation import fingerprint,sql_kind


def gap_segments(calls):
    events=defaultdict(list)
    for i,c in enumerate(calls):
        if c['send_ns'] is None or c['ready_ns']==c['send_ns']:continue
        events[c['send_ns']].append((1,i));events[c['ready_ns']].append((-1,i))
    active=set();previous=None;segments=[];weighted=Counter()
    for stamp,changes in sorted(events.items()):
        if previous is not None and stamp>previous and len(active)>1:
            selected=[calls[i] for i in sorted(active)]
            bg=[c for c in selected if c['role'] in BACKGROUND_ROLES]
            label='BG_only' if len(bg)==len(selected) else 'FG_only' if not bg else 'FG_and_BG'
            relation='distinct_backends' if len({c['backend_pid'] for c in selected})>1 else 'same_backend'
            excess=(len(selected)-1)*(stamp-previous)
            weighted[label+'/'+relation]+=excess
            segments.append(dict(start_ns=previous,end_ns=stamp,active_count=len(active),
                excess_integral_ns=excess,classification=label+'/'+relation,call_indices=sorted(active),
                backend_pids=sorted({c['backend_pid'] for c in selected}),
                client_pids=sorted({c['client_process_pid'] for c in selected})))
        for delta,i in sorted(changes):
            if delta<0:active.remove(i)
            else:active.add(i)
        previous=stamp
    if active:raise ValueError('Unclosed SQL interval')
    return segments,dict(weighted)


def pairs(calls):
    result=[];spans=defaultdict(list)
    for (ai,a),(bi,b) in combinations(enumerate(calls),2):
        if a['send_ns'] is None or b['send_ns'] is None:continue
        if a['clock_domain']!=b['clock_domain']:raise ValueError('Different host clock domains')
        overlap=intersection((a['send_ns'],a['ready_ns']),(b['send_ns'],b['ready_ns']))
        if not overlap:continue
        bg=sum(c['role'] in BACKGROUND_ROLES for c in (a,b))
        label=('FG_FG','FG_BG','BG_BG')[bg]
        backend='same_backend' if a['backend_pid']==b['backend_pid'] else 'distinct_backends'
        client='same_client' if a['client_process_pid']==b['client_process_pid'] else 'separate_clients'
        request='same_request' if (a['server_generation'],a['origin_request_id'])==(
            b['server_generation'],b['origin_request_id']) else 'cross_request'
        key='/'.join((label,backend,client,request));spans[key].append(overlap)
        result.append(dict(call_indices=[ai,bi],classification=key,overlap_start_ns=overlap[0],
            overlap_end_ns=overlap[1],backend_pids=[a['backend_pid'],b['backend_pid']],
            client_pids=[a['client_process_pid'],b['client_process_pid']],
            roles=[a['role'],b['role']],origin_requests=[a['origin_request_id'],b['origin_request_id']]))
    return result,{key:union_ns(value) for key,value in spans.items()}


def model_counts(events):
    # Preserve EVERY finish event; use the final cumulative summary per scope
    # for totals, avoiding double counting a repeated finish of one scope.
    last={};history=[]
    for seq,event in enumerate(events):
        key=event['scope_id'];last[key]=event
        history.append(dict(event_sequence=seq,scope_id=key,request=event['origin_request_id'],
            timestamp_ns=event['timestamp_ns'],model=event['summary']['model'],
            plans=len(event['summary']['plans']),continuation_snapshots=len(event['summary']['continuations']),
            explicit_capture_records=len(event['checkpoints']),explicit_capture_hits=len(event['hits'])))
    counts=Counter(outcome_events=len(events),unique_scopes=len(last));unique=defaultdict(set)
    statuses=Counter();reasons=Counter();stops=Counter();source_points=Counter();starts=[]
    for event in last.values():
        summary=event['summary']
        for field in ('submitted_ids','promoted_ids','unused_cached_ids','unavailable_ids'):
            counts[field+'_cumulative']+=len(summary[field]);unique[field].update(summary[field])
        plans=summary['plans'];counts['plans']+=len(plans)
        counts['multi_hop_plans']+=sum(len(p.get('hops',[]))>1 for p in plans)
        starts.extend(summary['worker_process_startup_ms'])
        for plan in plans:
            statuses[str(plan['status'])]+=1
            for decision in plan.get('decisions',[]):
                output=decision['output'];inputs=decision['inputs']
                counts['model_decisions']+=1;counts['probe_decisions']+=bool(output['probe'])
                counts['admit_decisions']+=bool(output['admit']);counts['skip_decisions']+=not output['admit']
                counts['decisions_below3samples']+=inputs['samples']<3
                reasons[inputs['phase']+': '+output['reason']]+=1
        for point in summary['continuations']:
            counts['native_continuation_snapshots']+=1
            stops[str(point['stop'])]+=1;source_points[str(point['ability'])+':'+str(point['point'])]+=1
        counts['explicit_capture_records']+=len(event['checkpoints'])
        counts['explicit_capture_hits']+=len(event['hits'])
    return dict(counts=dict(counts),unique_payload_ID_counts={k:len(v) for k,v in unique.items()},
        plan_statuses=dict(statuses),decision_reasons=dict(reasons),native_snapshot_stops=dict(stops),
        native_snapshot_points=dict(source_points),worker_startup_ms=starts,event_scope_history=history,
        scope_aggregation='Every event preserved; last cumulative summary per unique scope used for totals',
        checkpoint_note='Explicit capture arrays may be empty in native-default primary mode; native continuation snapshots show reached point/barrier activity; empty arrays do not mean no checkpoints',
        payload_note='Submitted/promoted/unused_cached/unavailable are exact native categories, not inferred overfetch/consumption')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();run=args.run.resolve();out=args.output.resolve();index=read_json(run/'index.json')
    if index.get('status')!='complete' or not index['passed']:raise ValueError('Completed formal run required')
    rows=[r for r in index['cases'] if r['app']=='littlex' and r['phase']=='measured']
    if len(rows)!=18:raise ValueError('Exactly18 LittleX measured workflows required')
    trials=[];groups=defaultdict(list)
    for row in rows:
        directory=run/row['trial_id'];metric_path=checked_ref(row['metrics'],run);metric=read_json(metric_path)
        if verify_case(directory)!=row['raw_seal'] or metric['raw_seal']!=row['raw_seal']:raise ValueError('Raw seal mismatch')
        calls=load_jsonl(directory,'server-*.calls.jsonl*');requests=load_jsonl(directory,'http-raw.jsonl*')
        assigned,_=scope_calls(calls,requests);primary=[c for c,r in assigned if r['phase']=='workflow']
        total=totals(primary)
        if total['protocol_sum_ns']!=metric['primary']['protocol_sum_ns'] or total['protocol_union_ns']!=metric['primary']['protocol_union_ns']:
            raise ValueError('Accepted primary interval totals differ')
        segments,weights=gap_segments(primary);pair_rows,pair_unions=pairs(primary)
        gap=total['protocol_sum_ns']-total['protocol_union_ns']
        if sum(weights.values())!=gap:raise ValueError('Sweep does not account exactly for sum-minus-union')
        categories={kind:totals([c for c in primary if sql_kind(c['sql'])==kind]) for kind in ('data','control','other')}
        compact=[dict(call_index=i,sql_fingerprint=fingerprint(c['sql']),kind=sql_kind(c['sql']),
            role=c['role'],backend_pid=c['backend_pid'],client_pid=c['client_process_pid'],
            server_generation=c['server_generation'],origin_request_id=c['origin_request_id'],
            send_ns=c['send_ns'],ready_ns=c['ready_ns']) for i,c in enumerate(primary)]
        trial=dict(config_id=row['config_id'],repeat=row['repeat'],trial_id=row['trial_id'],
            raw_seal=row['raw_seal'],metric_ref=row['metrics'],totals=total,category_totals=categories,
            role_totals=total['roles'],SQL_fingerprints=metric['SQL_fingerprints'],
            sum_minus_union_ns=gap,excess_integral_by_segment_class_ns=weights,
            overlapping_segments=segments,pairs=pair_rows,pair_union_by_class_ns=pair_unions,
            call_identity_intervals=compact,models=model_counts(metric['model_outcomes']))
        trials.append(trial);groups[row['config_id']].append(trial)
    pooled=[]
    for config,values in groups.items():
        sql_groups={}
        for t in values:
            for record in t['SQL_fingerprints']:
                key=(record['fingerprint'],record['kind'],record['role'])
                g=sql_groups.setdefault(key,dict(fingerprint=key[0],kind=key[1],role=key[2],sql=record['sql'],
                    counts_by_repeat=[0,0,0],protocol_ns_by_repeat=[0,0,0],rows_by_repeat=[0,0,0],bytes_by_repeat=[0,0,0]))
                for field,value in (('counts_by_repeat',record['sql_dispatches']),('protocol_ns_by_repeat',record['protocol_sum_ns']),
                                    ('rows_by_repeat',record['data_rows']),('bytes_by_repeat',record['data_row_payload_bytes'])):
                    g[field][t['repeat']]=value
        fingerprints=sorted(sql_groups.values(),key=lambda r:sum(r['protocol_ns_by_repeat']),reverse=True)
        for g in fingerprints:g.update(pooled_calls=sum(g['counts_by_repeat']),pooled_protocol_ns=sum(g['protocol_ns_by_repeat']))
        if sum(g['pooled_calls'] for g in fingerprints)!=sum(t['totals']['sql_dispatches'] for t in values):raise ValueError('Fingerprint count conservation failed')
        if sum(g['pooled_protocol_ns'] for g in fingerprints)!=sum(t['totals']['protocol_sum_ns'] for t in values):raise ValueError('Fingerprint time conservation failed')
        pooled.append(dict(config_id=config,n=3,fingerprints=fingerprints))
    out.mkdir(parents=True,exist_ok=False)
    result=dict(passed=True,scope='Read-only LittleX18 measured traces; no new DB execution or CPU profiling',
        input_index=dict(path=str(run/'index.json'),sha256=sha256(run/'index.json')),
        source=dict(path=str(Path(__file__).resolve()),sha256=sha256(__file__)),trials=trials,pooled_SQL=pooled,
        definition='Fingerprint times are protocol completion wall contributions. Sum-minus-union is an excess-active-interval integral, not a pairwise-overlap sum. Role/backend classes preserve the distinction.',
        CPU_cause='Not established')
    (out/'attribution.json').write_text(json.dumps(result,indent=2)+'\n')
    lines=['# LittleX: measured SQL and interval attribution','',
        'Read-only analysis of18 accepted measured workflows. Protocol completion wall includes client decoding/progress. No CPU-cause inference or new DB execution.','',
        '## Exact accounting of summed DB calls minus interval union','',
        '| Configuration | Repeat | Gap ms | Excess integral by actual role/backend class (ms) |',
        '|---|---:|---:|---|']
    for t in trials:
        detail='; '.join(k+': '+f'{v/1e6:.6f}' for k,v in sorted(t['excess_integral_by_segment_class_ns'].items())) or 'None'
        lines.append(f"| {t['config_id']} | {t['repeat']} | {t['sum_minus_union_ns']/1e6:.6f} | {detail} |")
    lines+=['','Every gap is exactly accounted for by sweep segments. Pairwise intersections can overlap each other and are not added to explain a triple-overlap gap. Actual call indices, backend/client PIDs and pair intervals are retained in attribution.json.','',
        '## SQL fingerprint contributions','',
        'Counts/times below are pooled across THREE measured workflows, not median workflow times. Every exact fingerprint and data/control classification is retained in JSON.','']
    for p in pooled:
        lines+=['### '+p['config_id'],'','| Fingerprint prefix | Kind / role | Pooled calls | Pooled protocol ms | SQL excerpt |','|---|---|---:|---:|---|']
        for g in p['fingerprints'][:8]:
            excerpt=' '.join(g['sql'].split())[:130].replace('|','/')
            lines.append(f"| {g['fingerprint'][:12]} | {g['kind']} / {g['role']} | {g['pooled_calls']} | {g['pooled_protocol_ns']/1e6:.6f} | {excerpt} |")
        lines.append('')
    lines+=['## Native model/checkpoint evidence','',
        'Every dependency_outcome is retained with event/scope identity. Totals use each scope\'s final cumulative summary. Submitted/promoted/unused_cached/unavailable are separate native categories. Empty explicit capture arrays are not interpreted as zero native checkpoint activity.','',
        '| Configuration | Repeat | Scope events / unique scopes | Plans / multihop | Native continuation snapshots | Decisions / probes / below3 samples |','|---|---:|---|---|---:|---|']
    for t in trials:
        c=t['models']['counts'];get=lambda k:c.get(k,0)
        lines.append(f"| {t['config_id']} | {t['repeat']} | {get('outcome_events')}/{get('unique_scopes')} | {get('plans')}/{get('multi_hop_plans')} | {get('native_continuation_snapshots')} | {get('model_decisions')}/{get('probe_decisions')}/{get('decisions_below3samples')} |")
    (out/'attribution.md').write_text('\n'.join(lines)+'\n')
    (out/'artifacts.json').write_text(json.dumps(dict(passed=True,files={p.name:sha256(p) for p in out.iterdir() if p.is_file()}),indent=2)+'\n')
    print(json.dumps(dict(passed=True,trials=len(trials),output=str(out))))


if __name__=='__main__':main()
