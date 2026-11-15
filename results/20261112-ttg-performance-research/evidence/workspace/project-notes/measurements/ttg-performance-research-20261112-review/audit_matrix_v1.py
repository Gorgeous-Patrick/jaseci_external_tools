"""Single stopped-data pass: matrix numerics and precision witnesses, no Jac."""
import csv
import gzip
import hashlib
import importlib.util
import json
import re
import statistics
import time
from collections import Counter, defaultdict
from pathlib import Path

E=Path('/home/baichuan/jaseci/project-notes/measurements/ttg-performance-research-20261112')
OWN=Path(__file__).resolve().parent
OUT=OWN/'matrix-raw-audit-v1'
OUT.mkdir(exist_ok=True)
START=time.monotonic()
REFS={}
COUNTS=Counter()
SQL={}
FIELDS=('HTTP_response_sum_ms','HTTP_response_union_ms','HTTP_response_span_ms','DB_sum_ms','DB_union_ms','data_SQL','control_SQL','total_SQL','data_SQL_per_business_request','business_requests')

def sha(raw):return hashlib.sha256(raw).hexdigest()
def load(p,wanted=None):
    p=Path(p);raw=p.read_bytes();h=sha(raw)
    if wanted:assert h==wanted,str(p)
    REFS[str(p)]=h
    return json.loads(raw)
def checked(r):return load(r['path'],r['sha256'])
def bound_file(r):
    p=Path(r['path']);assert sha(p.read_bytes())==r['sha256'],str(p);REFS[str(p)]=r['sha256']
def near(a,b):
    if a is None or b is None:assert a is b,(a,b)
    else:assert abs(a-b)<=max(1e-6,abs(b)*1e-12),(a,b)
def identity(e):return str(e['server_generation']),e.get('origin_request_id')
def union(intervals):
    end=-1;total=0
    for a,b in sorted(intervals):assert a<=b;total+=max(0,b-max(a,end));end=max(end,b)
    return total
def totals(cs):
    sent=[c for c in cs if c['send_ns'] is not None];ints=[(c['send_ns'],c['ready_ns']) for c in sent]
    kinds=Counter(SQL_KIND(c['sql']) for c in sent)
    return dict(driver_calls=len(cs),sql_dispatches=len(sent),sql_data=kinds['data'],sql_control=kinds['control'],sql_other=kinds['other'],protocol_sum_ns=sum(b-a for a,b in ints),protocol_union_ns=union(ints))
def fp_groups(cs):
    groups=defaultdict(list)
    for c in cs:
        if c['send_ns'] is None:continue
        fp=FINGERPRINT(c['sql']);SQL.setdefault(fp,c['sql']);groups[fp,c['role']].append(c)
    return [dict(fingerprint=fp,kind=SQL_KIND(v[0]['sql']),role=role,returned_rows=sum(c['returned_rows'] for c in v),**totals(v)) for (fp,role),v in sorted(groups.items())]

helper=Path('/home/baichuan/jaseci/reproduction/ttg-continuation-performance/sql_reconciliation.py')
REFS[str(helper)]=sha(helper.read_bytes())
spec=importlib.util.spec_from_file_location('_review_sql_lexical_only',helper);mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
FINGERPRINT=mod.fingerprint;SQL_KIND=mod.sql_kind
plan=load(E/'plan-v2/plan.json','62f9bc942105d79c5df678d31b0960e4de03b6a8c1b1eec98218750d00d7447d')
old=checked(plan['lineage']['original_plan'])
exp=load(E/'export-n5-v2/results.json','42d6e527e6c550c038135ee39f79939fc78b10714d7bdb1d74582b534e7f0950')
pexp=load(E/'export-precision-v2/results.json','d89b29f978a628cb3ecd72e052d73b8ad3ca4b8ed2c3dbc9f4ecb8bab4d84d4d')
for dataset in (exp,pexp):
    assert dataset['passed'];bound_file(dataset['source'])
for name in ('export-n5-v2','export-precision-v2'):
    a=load(E/name/'artifacts.json')
    for r in a.get('outputs',[a['output']] if 'output' in a else []):bound_file(r)
for name in ('extend-n5-v2-stopped-capacity.json','precision-v2-stopped-capacity.json'):
    s=load(E/name);assert s['passed'] and s['creator_dead'] and not s['known_active'] and not s['own_argv_active']
    assert s['pg_status']==3 and not s['postmaster_pid_exists'] and s['source_after_passed']
    assert not s['retained_databases']
preserved=checked(plan['lineage']['failed_stage_preservation'])
assert preserved['passed'] and len(preserved['retained_databases'])==1
assert exp['counts']==dict(captured=399,correctness=57,excluded_warmups=57,measured=285,measured_cells=57)
inventory=exp['inventory'];assert len(inventory)==60 and len({(r['case_id'],r['config_id']) for r in inventory})==60
assert [r['status'] for r in inventory if r['case_id']=='linked_list-1000']==['correctness_only','failed_isolation_gate','not_run_after_first_failure']
assert sum(r['completed'] for r in inventory)==57
carried=load(OWN/'first45-raw-audit-v1/summary.json','439433aeee88f341ca671cdc92b8f96749f00d2c6246ada72faac4db79b09e6f')
assert carried['passed'] and checked(plan['lineage']['accepted_prefixes'][0]['index'])['plan']==plan['lineage']['original_plan']
CARRY={s['trial_id']:s for s in carried['samples']}
SAMPLES={s['trial_id']:s for s in exp['samples']};PSAMPLES={s['trial_id']:s for s in pexp['samples']}
assert len(SAMPLES)==399 and len(PSAMPLES)==57
DATABASES=set();PAIR={};AUDITS=[];PRECISION=[]

def audit_case(row,index,precision=False):
    r=row['result'];proof=checked(r['proof']);metric=checked(r['metrics']);acc=checked(r['acceptance']);seal=checked(r['raw']);gil=checked(row['gil_proof'])
    assert all(x['passed'] for x in (proof,metric,acc,gil))
    assert acc['semantic']['passed'] and acc['database_state']['matches_sealed_final_graph']
    assert acc['semantic_proof']==r['proof'] and acc['source_manifest']==plan['sources']
    assert metric['independent_acceptance']==r['acceptance'] and metric['raw_seal']['sha256']==acc['raw_seal']['sha256']==r['raw']['sha256']
    assert proof['cluster_owner']==index['owner'] and proof['database'] not in DATABASES;DATABASES.add(proof['database'])
    state=tuple(proof[k] for k in ('fixture_sha256','actions_sha256','output_sha256'))
    assert PAIR.setdefault(row['case_id'],state)==state
    d=Path(r['raw']['path']).parent
    def sealed(name):return load(d/name,seal['files'][name])
    def lines(pattern):
        bases=set()
        for p in sorted(d.glob(pattern)):
            base=p.name.removesuffix('.gz');assert base not in bases;bases.add(base)
            raw=p.read_bytes();h=sha(raw);assert h==seal['files'][p.name],str(p);REFS[str(p)]=h
            if p.suffix=='.gz':raw=gzip.decompress(raw)
            for number,line in enumerate(raw.splitlines(keepends=True),1):
                if line.strip():yield json.loads(line),dict(path=str(p),line=number,record_sha256=sha(line))
    # Carry numerical raw checks only under identical original references.
    if row['trial_id'] in CARRY:
        prior=CARRY[row['trial_id']];assert not precision and prior['references']==r
        assert row['gil_proof']['sha256']==carried_gils[row['trial_id']]['sha256']
        result=dict(prior);result['carried_numeric_audit']=dict(path=str(OWN/'first45-raw-audit-v1/summary.json'),sha256='439433aeee88f341ca671cdc92b8f96749f00d2c6246ada72faac4db79b09e6f')
        by_metric={(str(q['server_generation']),q['request']):q for q in metric['request_metrics'] if q['phase']=='workflow'}
        for rpc in result['RPCs']:
            q=by_metric[rpc['generation'],rpc['request']]
            rpc['fingerprints_source']='Unchanged sealed accepted metric; carried raw numerical audit, no raw SQL reread'
            rpc['fingerprints']=q['SQL_fingerprints']
            for f in q['SQL_fingerprints']:SQL.setdefault(f['fingerprint'],f['sql'])
        result['native_work']=metric['model_outcomes'];result['native_work_source']='Unchanged accepted compact metric, not independently rechecked event counters in carried45'
        COUNTS['carried_timing_cases']+=1
        return result
    requests=sealed('requests.json');wire=[e for e,_ in lines('http-raw.jsonl*')];assert len(wire)==len(requests)
    for a,b in zip(wire,requests):
        assert {k:v for k,v in a.items() if k not in ('input','output')}=={k:v for k,v in b.items() if k not in ('input','output')}
        if b['phase']=='workflow':assert a['input']==b['input'] and a['output']==b['output']
    by_http={(str(h['server_generation']),h['request']):h for h in requests};assert len(by_http)==len(requests)
    primary={k:h for k,h in by_http.items() if h['phase']=='workflow'};assert primary
    stats=sealed('planner-statistics-before-workflow.json')
    assert stats['passed'] and stats['primary_excluded'] and stats['database']==proof['database']
    assert stats['commands']==['ANALYZE anchors','ANALYZE graph_types'] and stats['admin_end_ns']<=min(h['start_ns'] for h in primary.values())
    if not precision:
        capture=sealed('capture-proof.json');assert capture['capture']=='timing' and capture['precision_observer'] is False
    calls=[e for e,_ in lines('server-*.calls.jsonl*')];connections={};closes=defaultdict(set);outcomes=[];pevents=[];entries=defaultdict(set);installed=False;reset=[]
    for e,rawref in lines('server-*.events.jsonl*'):
        COUNTS['event_records']+=1
        assert e['trial_id']==row['trial_id'] and e['postgres_instance_id']==index['owner']
        if e['kind']=='connection':connections[str(e['server_generation']),e['backend_pid'],e['client_process_pid']]=e
        if e['kind']=='precision_observer_installed':installed=True
        if e['kind']=='native_context_close' and e.get('origin_request_id'):
            assert e['natural_close_completed'];closes[e['client_process_pid'],*identity(e),e['session_object_id']].add(e['session_nonce'])
        if identity(e) not in primary:continue
        if e['kind']=='explicit_profile_reset':reset.append(e)
        if e['kind']=='dependency_outcome':outcomes.append(e)
        if e['kind']=='precision_osp_entry':entries[identity(e)].add(e['uid'])
        if e['kind'].startswith('precision_'):
            pevents.append(dict(e,_ref=rawref))
    assert installed is precision and len(reset)==1
    nonce_requests={}
    for h in requests:
        if not h['path'].startswith('/walker/'):continue
        key=str(h['server_generation']),h['request'];matched=set()
        for (pid,gen,req,obj),nonces in closes.items():
            if (gen,req)==key:matched.update(nonces)
        assert matched
        for nonce in matched:assert nonce_requests.setdefault(nonce,key)==key
    gils=[e for e,_ in lines('gil-proof-*.jsonl*')];assert gils
    assert all(g['gil_enabled'] is False and g['Py_GIL_DISABLED']==1 for g in gils)
    COUNTS['GIL_records']+=len(gils)
    by_pid=defaultdict(list)
    for g in gils:by_pid[g['pid']].append(g)
    for v in by_pid.values():assert v[0]['kind']=='python_startup' and v[-1]['kind']=='python_exit'
    assert Counter((g['pid'],g['thread_id'],str(g['server_generation']),g.get('origin_request_id')) for g in gils if g['kind']=='sql_boundary')==Counter((c['client_process_pid'],c['thread_id'],*identity(c)) for c in calls)
    scoped=defaultdict(list)
    for c in calls:
        COUNTS['SQL_records']+=1
        assert c['trial_id']==row['trial_id'] and c['cell_id']==row['case_id']+'/'+row['config_id']
        assert c['postgres_instance_id']==index['owner'] and c['database']==proof['database']
        conn=connections[str(c['server_generation']),c['backend_pid'],c['client_process_pid']]
        assert conn['database']==c['database'] and conn['application_name']==c['application_name']
        assert c['driver_start_ns']<=c['send_ns']<=c['ready_ns']<=c['driver_end_ns']
        assert c['sendall_returned'] and c['ready_messages']==1 and c['command_complete']==(0 if c['error_messages'] else 1)
        if identity(c) in primary:assert c['error'] is None and c['error_messages']==0
        elif c['error_messages']:COUNTS['excluded_SQL_error_messages']+=c['error_messages']
        if c.get('origin_request_id'):
            k=identity(c);assert k in by_http;scoped[k].append(c)
            h=by_http[k];assert h['start_ns']<=c['send_ns']<=c['ready_ns']<=h['post_response_drain']['end_ns']
    primary_calls=[c for k in primary for c in scoped[k]];total=totals(primary_calls)
    assert all(metric['primary'][k]==v for k,v in total.items())
    fg=[c for c in primary_calls if c['role']=='foreground'];bg=[c for c in primary_calls if c['role']!='foreground'];assert len({c['client_process_pid'] for c in fg})==1
    if row['config_id']=='off':assert not bg
    for c in bg:
        peers=[f for f in fg if identity(f)==identity(c)];assert peers and c['actual_executor']=='thread'
        assert all(f['client_process_pid']==c['client_process_pid'] and f['thread_id']!=c['thread_id'] and f['backend_pid']!=c['backend_pid'] for f in peers)
    for role,v in metric['primary']['roles'].items():
        computed=totals([c for c in primary_calls if c['role']==role]);assert all(computed[k]==n for k,n in v.items())
    rpc=[]
    for k,h in primary.items():
        assert 200<=h['http_status']<300
        drain=h['post_response_drain'];assert drain['pending']==0 and h['end_ns']<=drain['start_ns']<=drain['end_ns']
        near(h['http_e2e_ms'],(h['end_ns']-h['start_ns'])/1e6)
        selected=[q for q in metric['request_metrics'] if (str(q['server_generation']),q['request'])==k];assert len(selected)==1
        rt=totals(scoped[k]);assert all(selected[0][a]==b for a,b in rt.items())
        fps=fp_groups(scoped[k]);decl={(f['fingerprint'],f['role']):f for f in selected[0]['SQL_fingerprints']}
        assert set(decl)=={(f['fingerprint'],f['role']) for f in fps}
        for f in fps:
            q=decl[f['fingerprint'],f['role']];assert all(q[a]==f[a] for a in rt)
        rpc.append(dict(request=k[1],generation=k[0],path=h['path'],start_ns=h['start_ns'],end_ns=h['end_ns'],drain=drain,**rt,roles={role:totals([c for c in scoped[k] if c['role']==role]) for role in {c['role'] for c in scoped[k]}},fingerprints=fps))
    assert len(outcomes)==len(metric['model_outcomes'])
    for raw,saved in zip(outcomes,metric['model_outcomes']):assert raw['summary']==saved['summary'] and identity(raw)==identity(saved)
    ints=[(h['start_ns'],h['end_ns']) for h in primary.values()]
    result=dict(trial_id=row['trial_id'],case_id=row['case_id'],config_id=row['config_id'],phase=row['phase'],repeat=row['repeat'],references=r,GIL_proof=row['gil_proof'],RPCs=rpc,native_work=outcomes,
                primary_roles=metric['primary']['roles'],primary_background_SQL=len(bg),business_requests=len(primary),HTTP_response_sum_ms=sum(b-a for a,b in ints)/1e6,HTTP_response_union_ms=union(ints)/1e6,HTTP_response_span_ms=(max(b for a,b in ints)-min(a for a,b in ints))/1e6,
                DB_sum_ms=total['protocol_sum_ns']/1e6,DB_union_ms=total['protocol_union_ns']/1e6,data_SQL=total['sql_data'],control_SQL=total['sql_control'],total_SQL=total['sql_dispatches'],data_SQL_per_business_request=total['sql_data']/len(primary))
    if precision:result['precision_audit']=audit_precision(row,pevents,closes,entries,PSAMPLES[row['trial_id']])
    COUNTS['fresh_precision_cases' if precision else 'fresh_timing_cases']+=1
    return result

def audit_precision(row,events,closes,entries,declared):
    groups=defaultdict(list);batches={};ends={};kinds=Counter();generic=set()
    for e in events:
        if e['kind']=='precision_prefetch_batch':assert e['batch'] not in batches;batches[e['batch']]=e
        if e['kind']=='precision_prefetch_batch_end':assert e['batch'] not in ends;ends[e['batch']]=e
        if 'session' not in e:continue
        key=e['client_process_pid'],*identity(e),e['session'];assert len(closes[key])==1
        group=key[:3]+(next(iter(closes[key])),);groups[group].append(e)
    assert batches.keys()==ends.keys()
    for e in events:
        if e['kind']!='precision_payload_returned':continue
        b=batches[e['batch']];end=ends[e['batch']]
        assert e['uid'] in b['ids'] and e['session']==b['session']==end['session']
        assert (e['client_process_pid'],*identity(e))==(b['client_process_pid'],*identity(b))==(end['client_process_pid'],*identity(end))
        assert b['timestamp_ns']<=e['timestamp_ns']<=end['timestamp_ns']
    declared_groups={tuple(g['scope']):g for g in declared['groups']};assert set(groups)==set(declared_groups)
    additive=('returned_unique','successful_demand_unique','returned_demand_intersection','post_return_successful_demand_overlap','raw_promotion_served_unique','served_return_before_demand_call_unique','unused_returned_unique','actual_row_deliveries','repeated_row_deliveries','already_materialized_late_deliveries','returned_node_unique','successful_demand_node_unique','confirmed_unused_node_prefetch_lower_bound')
    totals_=Counter();details=[]
    for key,evs in groups.items():
        d=declared_groups[key];ret=[e for e in evs if e['kind']=='precision_payload_returned'];dem=[e for e in evs if e['kind']=='precision_access' and not e['planning'] and e['role']=='foreground'];pro=[e for e in evs if e['kind']=='precision_promotion' and not e['planning'] and e['role']=='foreground']
        P={e['uid'] for e in ret};D=set();DN=set();PN={e['uid'] for e in ret if e['anchor_kind'] in ('NodeAnchor','RootAnchor')};by_d=defaultdict(list);by_p=defaultdict(list)
        for e in ret:by_p[e['uid']].append(e)
        for e in dem:
            assert len(e['ids'])==len(e['kinds']) and e['started_ns']<=e['timestamp_ns']
            for uid,kind in zip(e['ids'],e['kinds']):
                D.add(uid);by_d[uid].append(e);kinds[kind]+=1
                if kind in ('NodeAnchor','RootAnchor'):DN.add(uid)
                elif kind not in ('EdgeAnchor',):generic.add((key,uid,kind))
        DN.update(D&PN)
        post={uid for uid in P&D if any(r['timestamp_ns']<=call['timestamp_ns'] for r in by_p[uid] for call in by_d[uid])}
        served=set();before=set();valid=set();ref_events={tuple(e['_ref'][k] for k in ('path','line','record_sha256')):e for e in evs}
        for promotion in pro:
            uid=promotion['uid'];t=promotion['timestamp_ns'];prior=[r for r in by_p[uid] if r['timestamp_ns']<=t and not r['already_materialized']];calls=[c for c in by_d[uid] if c['started_ns']<=t<=c['timestamp_ns']]
            if prior and calls:
                served.add(uid)
                if any(r['timestamp_ns']<=c['started_ns'] for r in prior for c in calls):before.add(uid)
        for witness in d['service_witnesses']:
            rs=[ref_events[tuple(witness[n][k] for k in ('path','line','record_sha256'))] for n in ('returned','promotion','demand')]
            ret_e,prom_e,dem_e=rs;uid=witness['uid']
            assert ret_e['kind']=='precision_payload_returned' and prom_e['kind']=='precision_promotion' and dem_e['kind']=='precision_access'
            assert uid==ret_e['uid']==prom_e['uid'] and uid in dem_e['ids']
            assert not ret_e['already_materialized'] and not prom_e['planning'] and not dem_e['planning']
            assert prom_e['role']==dem_e['role']=='foreground' and ret_e['timestamp_ns']<=prom_e['timestamp_ns']
            assert dem_e['started_ns']<=prom_e['timestamp_ns']<=dem_e['timestamp_ns'];valid.add(uid)
        assert valid==served
        counts=dict(returned_unique=len(P),successful_demand_unique=len(D),returned_demand_intersection=len(P&D),post_return_successful_demand_overlap=len(post),raw_promotion_served_unique=len(served),served_return_before_demand_call_unique=len(before),unused_returned_unique=len(P-D),actual_row_deliveries=len(ret),repeated_row_deliveries=len(ret)-len(P),already_materialized_late_deliveries=sum(e['already_materialized'] for e in ret),returned_node_unique=len(PN),successful_demand_node_unique=len(DN),confirmed_unused_node_prefetch_lower_bound=len(PN-DN))
        assert all(d[k]==v for k,v in counts.items())
        for field,actual in [('returned_ids',P),('demanded_ids',D),('promotion_served_ids',served),('unused_ids',P-D),('unused_node_ids',PN-DN)]:assert set(d[field])==actual and len(d[field])==len(actual)
        for field,n,dn in [('overlap_coverage',len(P&D),len(D)),('promotion_service_coverage',len(served),len(D)),('returned_demand_fraction',len(P&D),len(P)),('promotion_served_fraction',len(served),len(P))]:near(d[field],n/dn if dn else None)
        totals_.update(counts)
        accessed_not_entered=(PN&D)-entries[key[1],key[2]]
        details.append(dict(scope=list(key),**counts,observed_accessed_returned_nodes_without_request_OSP_entry=len(accessed_not_entered),service_witnesses=d['service_witnesses']))
    assert all(declared[k]==totals_[k] for k in additive)
    for field,n,dn in [('overlap_coverage',totals_['returned_demand_intersection'],totals_['successful_demand_unique']),('promotion_service_coverage',totals_['raw_promotion_served_unique'],totals_['successful_demand_unique']),('returned_demand_fraction',totals_['returned_demand_intersection'],totals_['returned_unique']),('promotion_served_fraction',totals_['raw_promotion_served_unique'],totals_['returned_unique'])]:near(declared[field],n/dn if dn else None)
    assert declared['Session_scopes']==len(groups) and declared['native_OSP_unique_per_request']==sum(len(v) for v in entries.values())
    if row['config_id']=='off':assert totals_['returned_unique']==0 and not batches
    return dict(passed=True,**dict(totals_),demand_kind_record_counts=dict(kinds),generic_demand_unique=len(generic),groups=details,ratios_scope='ALL-anchor coverage/fraction; node-only counts separately',n=1)

original_index=checked(plan['lineage']['accepted_prefixes'][0]['index'])
carried_gils={r['trial_id']:r['gil_proof'] for r in original_index['rows']}
work=[]
for prefix in plan['lineage']['accepted_prefixes']:
    index=checked(prefix['index']);assert index['plan']==plan['lineage']['original_plan']
    rows=index['rows'][prefix['start']:prefix['end']];expected=old['stages'][index['stage']][:len(rows)]
    assert len(rows)==prefix['end']-prefix['start']
    for row,wanted in zip(rows,expected):assert row['passed'] and all(row[k]==v for k,v in wanted.items());work.append((row,index,False))
index=load(E/'extend-n5-v2/index.json');assert index['passed'] and index['source_after_passed'] and index['plan']==exp['plan']
for row,wanted in zip(index['rows'],plan['stages']['extend-n5']):assert row['passed'] and all(row[k]==v for k,v in wanted.items());work.append((row,index,False))
assert len(work)==399 and len({r['trial_id'] for r,i,p in work})==399
index=load(E/'precision-v2/index.json');assert index['passed'] and index['source_after_passed'] and len(index['rows'])==57 and index['plan']==exp['plan']
for row,wanted in zip(index['rows'],plan['stages']['precision']):assert row['passed'] and all(row[k]==v for k,v in wanted.items());work.append((row,index,True))
for n,(row,index,precision) in enumerate(work,1):
    result=audit_case(row,index,precision)
    if precision:PRECISION.append(result)
    else:
        declared=SAMPLES[row['trial_id']];assert declared['references']==row['result']
        for field in FIELDS:near(declared[field],result[field])
        AUDITS.append(result)
    if n%15==0:print(json.dumps(dict(audited=n,total=456,elapsed_s=time.monotonic()-START)),flush=True)
assert len(AUDITS)==399 and len(PRECISION)==57
for row in exp['rows']:
    samples=sorted([a for a in AUDITS if a['phase']=='measured' and (a['case_id'],a['config_id'])==(row['case_id'],row['config_id'])],key=lambda a:a['repeat'])
    assert row['n']==5 and [a['repeat'] for a in samples]==list(range(5))
    for field in FIELDS:
        values=[a[field] for a in samples];decl=row[field];assert decl['n']==5 and decl['values']==values
        for name,fn in [('median',statistics.median),('mean',statistics.mean),('min',min),('max',max),('stdev',statistics.stdev)]:near(decl[name],fn(values))
with (E/'export-n5-v2/table.csv').open() as f:table=list(csv.DictReader(f))
assert len(table)==57
for row,c in zip(exp['rows'],table):
    assert (row['case_id'],row['config_id'])==(c['case_id'],c['config_id']) and int(c['n'])==5
    for col,field,stat in [('HTTP_ms_median','HTTP_response_sum_ms','median'),('HTTP_ms_min','HTTP_response_sum_ms','min'),('HTTP_ms_max','HTTP_response_sum_ms','max'),('DB_sum_ms_median','DB_sum_ms','median'),('DB_union_ms_median','DB_union_ms','median'),('data_SQL_median','data_SQL','median'),('control_SQL_median','control_SQL','median'),('data_SQL_per_request_median','data_SQL_per_business_request','median')]:near(float(c[col]),row[field][stat])
elapsed=time.monotonic()-START
def save(name,value):
    p=OUT/name;p.write_text(json.dumps(value,indent=2)+'\n');return dict(path=str(p),sha256=sha(p.read_bytes()))
timing_ref=save('timing-derivatives.json',dict(samples=AUDITS,scope='354fresh raw plus45explicit immutable numerical carry; metric-only fingerprints/native counters in carried45 explicitly marked'))
precision_ref=save('precision-derivatives.json',dict(samples=PRECISION,scope='57raw cases n1; independently recomputed Session nonce groups and promotion witnesses'))
catalog_ref=save('sql-catalog.json',SQL)
counts=dict(COUNTS)
summary=dict(passed=True,heavy_IO_complete=True,heavy_pass_seconds=elapsed,counts=counts,comparison=exp['counts'],full_inventory=inventory,
             timing=timing_ref,precision=precision_ref,SQL_catalog=catalog_ref,consumed_refs=[dict(path=p,sha256=h) for p,h in REFS.items()],
             source=dict(path=str(Path(__file__)),sha256=sha(Path(__file__).read_bytes())),
             limitations=['No runtime/full-tree re-audit or semantic replay reexecution.','45unchanged cases carry prior raw numerical audit; fingerprints/native work for those45 come from unchanged accepted sealed metrics and are labelled.','Protocol wall includes transport/decoding; instrumented primary, not pure CPU or clean latency.','Precision n1 separate from primary n5, ALL-anchor rates not automatically node hit rates.','Node-unused observational lower bound is not proof of semantic not-needed/filter-only white reads.'])
summary_ref=save('summary.json',summary)
print(json.dumps(dict(passed=True,heavy_IO_complete=True,seconds=elapsed,summary=summary_ref,counts=counts)),flush=True)
