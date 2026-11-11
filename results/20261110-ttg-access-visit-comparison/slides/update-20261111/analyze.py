"""Recompute payload/demand set differences from sealed raw precision events."""
from collections import Counter, defaultdict
import csv
import gzip
import hashlib
import json
from pathlib import Path
from statistics import median

E = Path(__file__).resolve().parent


def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_text())
def checked(ref):
    assert sha(ref['path'])==ref['sha256'],ref
    return read(ref['path'])
def jsonl(p):
    with (gzip.open(p,'rt') if p.suffix=='.gz' else p.open()) as f:
        for i,line in enumerate(f,1):
            if line.strip():yield i,json.loads(line)
def uid(s):return s.replace('-','')


def request_result(events,mapping):
    batches={e['batch']:e for e in events if e['kind']=='precision_prefetch_batch'}
    ends={e['batch']:e for e in events if e['kind']=='precision_prefetch_batch_end'}
    assert batches.keys()==ends.keys()
    returned=[e for e in events if e['kind']=='precision_payload_returned']
    demand=defaultdict(list);planning=defaultdict(list)
    for e in events:
        if e['kind']=='precision_access':
            table=planning if e['planning'] else demand
            for value in e['ids']:table[(e['session'],uid(value))].append(e['timestamp_ns'])
    entered={uid(e['uid']) for e in events if e['kind']=='precision_osp_entry'}
    promoted={(e['session'],uid(e['uid'])) for e in events
              if e['kind']=='precision_promotion' and not e['planning']}
    fetched=defaultdict(list)
    for e in returned:
        b=batches[e['batch']]
        assert e['session']==b['session'] and e['uid'] in b['ids']
        assert b['timestamp_ns']<=e['timestamp_ns']<=ends[e['batch']]['timestamp_ns']
        fetched[(e['session'],uid(e['uid']))].append(e)
    prefetched=set(fetched)
    unused=prefetched-set(demand)
    # A separate temporal check avoids silently counting a read that only
    # happened before the actual prefetch attempt started.
    no_later_demand={k for k,vs in fetched.items() if not any(t>=min(
        batches[e['batch']]['timestamp_ns'] for e in vs) for t in demand.get(k,[]))}
    assert unused<=no_later_demand
    examples=[]
    for k in sorted(unused):
        e=fetched[k][0]
        examples.append(dict(uid=k[1],logical=mapping.get(k[1]),kind=e['anchor_kind'],
            arch_type=e['arch_type'],props_bytes=e['props_bytes'],record=e['_ref']))
    nodes={k for k,es in fetched.items() if es[0]['anchor_kind']=='NodeAnchor'}
    return dict(payload_objects=len(prefetched),demanded_prefetch_objects=len(prefetched&set(demand)),
        unused_payload_objects=len(unused),unused_rate=len(unused)/len(prefetched) if prefetched else None,
        without_later_demand=len(no_later_demand),only_prior_demand=len(no_later_demand-unused),
        payload_row_deliveries=len(returned),repeated_row_deliveries=len(returned)-len(prefetched),
        discarded_already_materialized_deliveries=sum(e['already_materialized'] for e in returned),
        payload_props_bytes=sum(e['props_bytes'] for e in returned),
        unused_props_bytes=sum(e['props_bytes'] for k in unused for e in fetched[k]),
        successful_demand_objects=len(demand),planning_read_objects=len(planning),
        prefetched_node_ids=sorted(k[1] for k in nodes),
        prefetched_logical_ids=sorted(mapping.get(k[1], 'unmapped:'+k[1]) for k in nodes),
        demanded_prefetched_logical_ids=sorted(mapping.get(k[1], 'unmapped:'+k[1]) for k in nodes if k in demand),
        prefetched_nodes=len(nodes),prefetched_nodes_entered=len({k for k in nodes if k[1] in entered}),
        total_entered_node_ids=len(entered),promoted_prefetch_objects=len(prefetched&promoted),
        unused_types=dict(Counter(fetched[k][0]['arch_type'] for k in unused)),unused_examples=examples)


def main():
    ix=read(E/'run-v1/index.json');assert ix['status']=='complete' and ix['passed'] and ix['source_after_passed']
    plan=checked(ix['plan']);assert len(ix['rows'])==len(plan['schedule'])==8
    samples=[];dbs=set();verified_files=0
    for row,scheduled in zip(ix['rows'],plan['schedule']):
        assert all(row[k]==v for k,v in scheduled.items()) and row['passed']
        proof=checked(row['result']['proof']);metric=checked(row['result']['metrics'])
        acceptance=checked(row['result']['acceptance']);seal=checked(row['result']['raw']);gil=checked(row['gil_proof'])
        assert proof['passed'] and acceptance['passed'] and gil['passed'] and gil['executor_SQL_observed']
        assert proof['database'] not in dbs;dbs.add(proof['database'])
        d=Path(row['result']['raw']['path']).parent
        for name,h in seal['files'].items():assert sha(d/name)==h,name
        verified_files+=len(seal['files'])
        assert read(d/'precision-proof.json')['passed']
        mapping={uid(value):key for key,value in read(d/'mapping-initial.json').items()} if (d/'mapping-initial.json').exists() else {}
        http=[r for _,r in jsonl(d/'http-raw.jsonl') if r['phase']=='workflow']
        keys={(str(r['server_generation']),r['request']) for r in http}
        by_request=defaultdict(list)
        for p in sorted(d.glob('server-*.events.jsonl*')):
            for line,e in jsonl(p):
                key=(str(e['server_generation']),e.get('origin_request_id'))
                if key in keys and e['kind'].startswith('precision_'):
                    e['_ref']=dict(path=str(p),sha256=seal['files'][p.name],line=line)
                    by_request[key].append(e)
        requests=[]
        for h in http:
            key=(str(h['server_generation']),h['request'])
            v=request_result(by_request[key],mapping)
            requests.append(dict(request=h['request'],walker=h['path'].split('/')[2],**v))
        additive=('payload_objects','demanded_prefetch_objects','unused_payload_objects',
            'without_later_demand','only_prior_demand','payload_row_deliveries','repeated_row_deliveries',
            'discarded_already_materialized_deliveries','payload_props_bytes','unused_props_bytes',
            'successful_demand_objects','planning_read_objects','prefetched_nodes','prefetched_nodes_entered',
            'total_entered_node_ids','promoted_prefetch_objects')
        total={k:sum(r[k] for r in requests) for k in additive}
        total['unused_rate']=total['unused_payload_objects']/total['payload_objects'] if total['payload_objects'] else None
        # The two modes must reproduce exactly the original canonical business output.
        samples.append(dict(app=row['app'],mode=row['config_id'],phase=row['phase'],repeat=row['repeat'],
            fixture_sha256=proof['fixture_sha256'],actions_sha256=proof['actions_sha256'],output_sha256=proof['output_sha256'],
            metric=row['result']['metrics'],raw=row['result']['raw'],gil=row['gil_proof'],**total,requests=requests,
            sql_data=metric['primary']['sql_data'],sql_control=metric['primary']['sql_control']))
    groups=[]
    for app in ('recipe_pantry',):
        paired=[s for s in samples if s['app']==app]
        for field in ('fixture_sha256','actions_sha256','output_sha256'):assert len({s[field] for s in paired})==1
        for mode in ('before','after'):
            selected=[s for s in paired if s['mode']==mode and s['phase']=='measured']
            assert sorted(s['repeat'] for s in selected)==[0,1,2]
            fields=(*additive,'unused_rate','sql_data','sql_control')
            groups.append(dict(app=app,mode=mode,n=3,**{k:dict(median=median(s[k] for s in selected),
                values=[s[k] for s in selected]) for k in fields}))
    result=dict(passed=True,captured=8,excluded_warmups=2,measured=6,verified_sealed_files=verified_files,
        index=dict(path=str(E/'run-v1/index.json'),sha256=sha(E/'run-v1/index.json')),
        analysis_source_sha256=sha(__file__),groups=groups,samples=samples,
        definitions=dict(unit='Per HTTP request and Session unique anchor IDs, summed across workflow; not global unique graph nodes',
            overfetch='Actual prefetched payload IDs minus successful foreground Session get/batch_get IDs, excluding prefetch planning',
            later='Additionally check successful demand timestamp after prefetch batch start; prior-only is separate',
            entries='Native OSP entry IDs; objects used by helper/read methods need not be entered, so not entering is NOT automatically waste',
            props_bytes='UTF-8 canonical JSON props byte count, not network bytes or PostgreSQL scan cost',
            late='store_raw callback found object already materialized: actual returned data discarded; recorded independently of unused IDs',
            timing='Symmetric precision instrumentation; not directly comparable with earlier latency runs'))
    (E/'results.json').write_text(json.dumps(result,indent=2)+'\n')
    columns=('payload_objects','demanded_prefetch_objects','unused_payload_objects','unused_rate',
             'discarded_already_materialized_deliveries','unused_props_bytes','sql_data','sql_control')
    with (E/'table.csv').open('w') as f:
        w=csv.writer(f);w.writerow(['app','mode','n',*columns])
        for g in groups:w.writerow([g['app'],g['mode'],g['n'],*[g[k]['median'] for k in columns]])
    print((E/'table.csv').read_text())

if __name__=='__main__':main()
