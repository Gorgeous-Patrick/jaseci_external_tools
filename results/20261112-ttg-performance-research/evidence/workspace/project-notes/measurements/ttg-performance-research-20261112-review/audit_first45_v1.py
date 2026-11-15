"""Bounded stopped-pilot raw audit; no Jac imports or service access."""
import csv
import gzip
import hashlib
import json
import re
import statistics
import time
from collections import Counter, defaultdict
from pathlib import Path

E = Path('/home/baichuan/jaseci/project-notes/measurements/ttg-performance-research-20261112')
OUT = Path(__file__).resolve().parent / 'first45-raw-audit-v1'
OUT.mkdir(exist_ok=True)
started = time.monotonic()
consumed = {}

def load(path, wanted=None):
    p = Path(path)
    raw = p.read_bytes()
    h = hashlib.sha256(raw).hexdigest()
    if wanted is not None:
        assert h == wanted, str(p)
    consumed[str(p)] = h
    return json.loads(raw)

def checked(ref):
    return load(ref['path'], ref['sha256'])

def union(intervals):
    total = 0
    end = -1
    for a, b in sorted(intervals):
        assert a <= b
        total += max(0, b - max(a, end))
        end = max(end, b)
    return total

def near(a, b):
    assert abs(a-b) <= max(1e-6, abs(b)*1e-12), (a, b)

def identity(r):
    return str(r['server_generation']), r.get('origin_request_id')

def kind(sql):
    match = re.match(r'\s*([A-Za-z]+)', sql)
    token = match.group(1).upper() if match else ''
    if token in {'BEGIN','START','SET','SAVEPOINT','RELEASE','DISCARD','COMMIT','END','ROLLBACK','ABORT','RESET','SHOW','DEALLOCATE','CLOSE'}:
        return 'control'
    if token in {'SELECT','WITH','INSERT','UPDATE','DELETE','MERGE','VALUES','FETCH'}:
        return 'data'
    return 'other'

def totals(calls):
    sent = [c for c in calls if c['send_ns'] is not None]
    intervals = [(c['send_ns'], c['ready_ns']) for c in sent]
    classes = Counter(kind(c['sql']) for c in sent)
    return dict(driver_calls=len(calls), sql_dispatches=len(sent), sql_data=classes['data'],
                sql_control=classes['control'], sql_other=classes['other'],
                protocol_sum_ns=sum(b-a for a,b in intervals), protocol_union_ns=union(intervals))

index = load(E/'first-v1/index.json')
stop = load(E/'first-v1-stopped-capacity.json')
plan = checked(index['plan'])
export = load(E/'export-first-v1/results.json')
artifact = load(E/'export-first-v1/artifacts.json')
assert index['status']=='complete' and index['passed'] and index['source_after_passed']
assert stop['passed'] and stop['creator_dead'] and not stop['known_active'] and not stop['own_argv_active']
assert stop['pg_status']==3 and not stop['postmaster_pid_exists'] and not stop['retained_databases']
assert checked(stop['index']) == index
assert len(index['rows']) == len(plan['stages']['first']) == 45
assert export['passed'] and export['counts']==dict(captured=45,correctness=9,excluded_warmups=9,measured=27,measured_cells=9)
checked(export['source']) if False else None
source = Path(export['source']['path'])
assert hashlib.sha256(source.read_bytes()).hexdigest()==export['source']['sha256']
consumed[str(source)] = export['source']['sha256']
for ref in artifact['outputs']:
    p=Path(ref['path']); assert hashlib.sha256(p.read_bytes()).hexdigest()==ref['sha256']
    consumed[str(p)]=ref['sha256']
samples = {s['trial_id']:s for s in export['samples']}
assert len(samples)==45
audits=[]
dbs=set()
paired={}
raw_records=Counter()

for row, scheduled in zip(index['rows'],plan['stages']['first']):
    assert all(row[k]==v for k,v in scheduled.items()) and row['passed']
    r=row['result']; proof=checked(r['proof']); metric=checked(r['metrics'])
    acceptance=checked(r['acceptance']); seal=checked(r['raw']); gil=checked(row['gil_proof'])
    assert all(x['passed'] for x in (proof,metric,acceptance,gil))
    assert acceptance['semantic']['passed'] and acceptance['database_state']['matches_sealed_final_graph']
    assert acceptance['semantic_proof']==r['proof'] and acceptance['source_manifest']==plan['sources']
    assert metric['independent_acceptance']==r['acceptance']
    assert metric['raw_seal']['sha256']==r['raw']['sha256']==acceptance['raw_seal']['sha256']
    assert proof['cluster_owner']==index['owner'] and proof['database'] not in dbs
    dbs.add(proof['database'])
    state=tuple(proof[k] for k in ('fixture_sha256','actions_sha256','output_sha256'))
    assert paired.setdefault(row['case_id'],state)==state
    directory=Path(r['raw']['path']).parent
    def sealed(name):
        return load(directory/name,seal['files'][name])
    def lines(pattern):
        for p in sorted(directory.glob(pattern)):
            raw=p.read_bytes(); h=hashlib.sha256(raw).hexdigest()
            assert h==seal['files'][p.name],str(p)
            consumed[str(p)]=h
            if p.suffix=='.gz':raw=gzip.decompress(raw)
            for line in raw.splitlines():
                if line.strip():yield json.loads(line)
    requests=sealed('requests.json')
    wire_http=list(lines('http-raw.jsonl*'))
    assert len(wire_http)==len(requests)
    for wire,saved in zip(wire_http,requests):
        assert {k:v for k,v in wire.items() if k not in ('output','input')}=={k:v for k,v in saved.items() if k not in ('output','input')}
        if saved['phase']=='workflow':
            assert wire['output']==saved['output'] and wire['input']==saved['input']
    by_http={(str(h['server_generation']),h['request']):h for h in requests}
    assert len(by_http)==len(requests)
    primary={k:h for k,h in by_http.items() if h['phase']=='workflow'}
    statistics_proof=sealed('planner-statistics-before-workflow.json')
    assert statistics_proof['passed'] and statistics_proof['primary_excluded']
    assert statistics_proof['commands']==['ANALYZE anchors','ANALYZE graph_types']
    assert statistics_proof['database']==proof['database']
    assert statistics_proof['admin_end_ns']<=min(h['start_ns'] for h in primary.values())
    capture=sealed('capture-proof.json');assert capture['capture']=='timing' and capture['precision_observer'] is False
    calls=list(lines('server-*.calls.jsonl*')); events=lines('server-*.events.jsonl*')
    connections={}; closes=defaultdict(set); resets=[]
    for e in events:
        raw_records['events']+=1
        assert e['trial_id']==row['trial_id'] and e['postgres_instance_id']==index['owner']
        if e['kind']=='connection':connections[(str(e['server_generation']),e['backend_pid'],e['client_process_pid'])]=e
        if e['kind']=='native_context_close' and e.get('origin_request_id'):
            assert e['natural_close_completed'];closes[identity(e)].add(e['session_nonce'])
        if e['kind']=='explicit_profile_reset' and identity(e) in primary:resets.append(e)
        assert e['kind']!='precision_observer_installed'
    assert len(resets)==1
    nonce_requests={}
    for k,h in by_http.items():
        if h['path'].startswith('/walker/'):
            assert closes[k]
            for nonce in closes[k]:assert nonce_requests.setdefault(nonce,k)==k
    gils=list(lines('gil-proof-*.jsonl*'))
    assert all(g['gil_enabled'] is False and g['Py_GIL_DISABLED']==1 for g in gils)
    by_pid=defaultdict(list)
    for g in gils:by_pid[g['pid']].append(g)
    for records in by_pid.values():assert records[0]['kind']=='python_startup' and records[-1]['kind']=='python_exit'
    observed=Counter((g['pid'],g['thread_id'],str(g['server_generation']),g.get('origin_request_id')) for g in gils if g['kind']=='sql_boundary')
    expected=Counter((c['client_process_pid'],c['thread_id'],str(c['server_generation']),c.get('origin_request_id')) for c in calls)
    assert observed==expected
    scoped=defaultdict(list)
    for c in calls:
        raw_records['calls']+=1
        assert c['trial_id']==row['trial_id'] and c['cell_id']==row['case_id']+'/'+row['config_id']
        assert c['postgres_instance_id']==index['owner'] and c['database']==proof['database']
        conn=connections[str(c['server_generation']),c['backend_pid'],c['client_process_pid']]
        assert conn['database']==c['database'] and conn['application_name']==c['application_name']
        assert c['driver_start_ns']<=c['send_ns']<=c['ready_ns']<=c['driver_end_ns']
        assert c['sendall_returned'] and c['ready_messages']==1
        assert c['command_complete']==(0 if c['error_messages'] else 1)
        if c['error_messages']:
            raw_records['request_excluded_errors' if identity(c) not in primary else 'primary_errors']+=c['error_messages']
        if identity(c) in primary:assert c['error'] is None and c['error_messages']==0
        if c.get('origin_request_id'):
            k=identity(c);assert k in by_http;scoped[k].append(c)
            h=by_http[k];assert h['start_ns']<=c['send_ns']<=c['ready_ns']<=h['post_response_drain']['end_ns']
    primary_calls=[c for k in primary for c in scoped[k]]
    total=totals(primary_calls)
    for k,v in total.items():assert metric['primary'][k]==v,(row['trial_id'],k)
    fg=[c for c in primary_calls if c['role']=='foreground'];bg=[c for c in primary_calls if c['role']!='foreground']
    assert len({c['client_process_pid'] for c in fg})==1
    if row['config_id']=='off':assert not bg
    for c in bg:
        peers=[f for f in fg if identity(f)==identity(c)]
        assert peers and c['actual_executor']=='thread'
        assert all(f['client_process_pid']==c['client_process_pid'] and f['thread_id']!=c['thread_id'] and f['backend_pid']!=c['backend_pid'] for f in peers)
    for role,value in metric['primary']['roles'].items():
        role_calls=[c for c in primary_calls if c['role']==role]; rt=totals(role_calls)
        assert all(rt[k]==v for k,v in value.items())
    rpc=[]
    for k,h in primary.items():
        assert 200<=h['http_status']<300
        drain=h['post_response_drain'];assert drain['pending']==0 and h['end_ns']<=drain['start_ns']<=drain['end_ns']
        near(h['http_e2e_ms'],(h['end_ns']-h['start_ns'])/1e6)
        candidates=[q for q in metric['request_metrics'] if (str(q['server_generation']),q['request'])==k]
        assert len(candidates)==1;rt=totals(scoped[k])
        assert all(candidates[0][a]==b for a,b in rt.items())
        rpc.append(dict(request=k[1],generation=k[0],path=h['path'],start_ns=h['start_ns'],end_ns=h['end_ns'],drain=drain,**rt))
    intervals=[(h['start_ns'],h['end_ns']) for h in primary.values()]
    numeric=dict(HTTP_response_sum_ms=sum(b-a for a,b in intervals)/1e6,HTTP_response_union_ms=union(intervals)/1e6,
                 HTTP_response_span_ms=(max(b for a,b in intervals)-min(a for a,b in intervals))/1e6,
                 DB_sum_ms=total['protocol_sum_ns']/1e6,DB_union_ms=total['protocol_union_ns']/1e6,
                 data_SQL=total['sql_data'],control_SQL=total['sql_control'],total_SQL=total['sql_dispatches'],
                 data_SQL_per_business_request=total['sql_data']/len(primary),business_requests=len(primary))
    sample=samples[row['trial_id']]
    for k,v in numeric.items():near(sample[k],v)
    assert len(sample['RPCs'])==len(rpc)
    audits.append(dict(trial_id=row['trial_id'],case_id=row['case_id'],config_id=row['config_id'],phase=row['phase'],repeat=row['repeat'],
                       references=r,raw_call_records=len(calls),GIL_records=len(gils),primary_background_SQL=len(bg),RPCs=rpc,**numeric))
    print(json.dumps(dict(audited=len(audits),total=45,trial=row['trial_id'])),flush=True)

fields=('HTTP_response_sum_ms','HTTP_response_union_ms','HTTP_response_span_ms','DB_sum_ms','DB_union_ms','data_SQL','control_SQL','total_SQL','data_SQL_per_business_request','business_requests')
for row in export['rows']:
    selected=sorted([a for a in audits if a['phase']=='measured' and a['case_id']==row['case_id'] and a['config_id']==row['config_id']],key=lambda a:a['repeat'])
    assert [a['repeat'] for a in selected]==[0,1,2] and row['n']==3
    for field in fields:
        vals=[a[field] for a in selected];decl=row[field]
        assert vals==decl['values'] and decl['n']==3
        for key,fn in [('median',statistics.median),('min',min),('max',max),('mean',statistics.mean),('stdev',statistics.stdev)]:near(decl[key],fn(vals))
with (E/'export-first-v1/table.csv').open() as f:
    csv_rows=list(csv.DictReader(f))
assert len(csv_rows)==9
for row,c in zip(export['rows'],csv_rows):
    assert (row['case_id'],row['config_id'])==(c['case_id'],c['config_id']) and int(c['n'])==3
    for column,field,stat in [('HTTP_ms_median','HTTP_response_sum_ms','median'),('HTTP_ms_min','HTTP_response_sum_ms','min'),('HTTP_ms_max','HTTP_response_sum_ms','max'),('DB_sum_ms_median','DB_sum_ms','median'),('DB_union_ms_median','DB_union_ms','median'),('data_SQL_median','data_SQL','median'),('control_SQL_median','control_SQL','median'),('data_SQL_per_request_median','data_SQL_per_business_request','median')]:near(float(c[column]),row[field][stat])
heavy_elapsed=time.monotonic()-started
result=dict(passed=True,scope='Initial45 pilot raw numeric/HTTP/GIL/semantic-reference audit; reused semantic replay not rerun',
            counts=export['counts'],raw_records=dict(raw_records),heavy_read_seconds=heavy_elapsed,heavy_IO_complete=True,
            consumed_refs=[dict(path=p,sha256=h) for p,h in consumed.items()],samples=audits,
            source=dict(path=str(Path(__file__)),sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()),
            limitations=['Instrumented protocol/HTTP timings; no pure DB server CPU or uninstrumented claim.','Semantic acceptance/hash/state/session/restart links checked; independent business algorithm not reexecuted.','Only initial3apps/n3 pilot, not final17app/n5/scale or precision acceptance.','Consumed raw files hashed; no full source tree or JIR/unused raw rehash.'])
(OUT/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(dict(passed=True,heavy_IO_complete=True,seconds=heavy_elapsed,summary=str(OUT/'summary.json'))),flush=True)
