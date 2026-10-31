"""Independent actual48 numeric export audit; standard-library reads only."""
import collections
import csv
import datetime as dt
import hashlib
import json
from pathlib import Path
import re

OUT=Path(__file__).resolve().parent
BASE=Path('/home/baichuan/jaseci')
M=BASE/'project-notes/measurements/ttg-continuation-performance-20261030'
RUN=M/'small-formal-v1';EXPORT=M/'small-export-v1'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
read=lambda p:json.loads(p.read_text())
def ref(v):
    p=Path(v['path']);p=p if p.is_absolute() else BASE/p
    assert p.is_file() and sha(p)==v['sha256'],str(p)
    return p
def union(spans):
    points=collections.Counter()
    for begin,end in spans:
        assert type(begin) is int and type(end) is int and begin<=end
        points[begin]+=1;points[end]-=1
    total=active=0;previous=None
    for point,change in sorted(points.items()):
        if previous is not None and active:total+=point-previous
        active+=change;assert active>=0;previous=point
    assert active==0;return total
def kind(sql):
    match=re.match(r'\s*([a-zA-Z]+)',sql);token=match[1].upper() if match else ''
    if token in {'BEGIN','START','SET','SAVEPOINT','RELEASE','DISCARD','COMMIT','END','ROLLBACK','ABORT','RESET','SHOW','DEALLOCATE','CLOSE'}:return 'control'
    if token in {'SELECT','WITH','INSERT','UPDATE','DELETE','MERGE','VALUES','FETCH'}:return 'data'
    return 'other'
ROLES=('foreground','background_prefetch','background_continuation')
BG=set(ROLES[1:])
def totals(calls):
    dispatched=[c for c in calls if c['send_ns'] is not None]
    spans=[(c['send_ns'],c['ready_ns']) for c in dispatched]
    result=dict(driver_calls=len(calls),sql_dispatches=len(dispatched),sql_data=sum(kind(c['sql'])=='data' for c in dispatched),sql_control=sum(kind(c['sql'])=='control' for c in dispatched),sql_other=sum(kind(c['sql'])=='other' for c in dispatched),command_complete=sum(c['command_complete'] for c in calls),protocol_cycles=sum(c['ready_messages'] for c in calls),server_error_messages=sum(c['error_messages'] for c in calls),pre_send_driver_errors=sum(c['send_ns'] is None for c in calls),data_rows=sum(c['data_rows'] for c in calls),data_row_payload_bytes=sum(c['data_row_payload_bytes'] for c in calls),driver_sum_ns=sum(c['driver_end_ns']-c['driver_start_ns'] for c in calls),driver_union_ns=union([(c['driver_start_ns'],c['driver_end_ns']) for c in calls]),protocol_sum_ns=sum(b-a for a,b in spans),protocol_union_ns=union(spans),roles={})
    for role in ROLES:
        chosen=[c for c in dispatched if c['role']==role];rs=[(c['send_ns'],c['ready_ns']) for c in chosen]
        result['roles'][role]=dict(sql_dispatches=len(chosen),protocol_sum_ns=sum(b-a for a,b in rs),protocol_union_ns=union(rs))
    return result
def overlaps(calls):
    groups=collections.defaultdict(list)
    for c in calls:
        if c['send_ns'] is not None:groups[(c['trial_id'],str(c['server_generation']),c['origin_request_id'],c['clock_domain'])].append(c)
    expected={}
    for key,group in groups.items():
        fg=[c for c in group if c['role']=='foreground'];bg=[c for c in group if c['role'] in BG];diff=[];same=[];process=[]
        for a in bg:
            for b in fg:
                begin=max(a['send_ns'],b['send_ns']);end=min(a['ready_ns'],b['ready_ns'])
                if end<=begin:continue
                if a['backend_pid']==b['backend_pid']:same.append((begin,end))
                else:
                    diff.append((begin,end))
                    if a['client_process_pid']!=b['client_process_pid']:process.append((begin,end))
        expected[key]=dict(foreground_dispatches=len(fg),background_dispatches=len(bg),protocol_sum_ns=sum(c['ready_ns']-c['send_ns'] for c in group),protocol_union_ns=union([(c['send_ns'],c['ready_ns']) for c in group]),distinct_backend_overlap_ns=union(diff),separate_process_distinct_backend_overlap_ns=union(process),same_backend_overlapping_intervals_ns=union(same),background_during_foreground_work_ns=0)
    return expected
def stats(values):
    assert len(values)==3;v=sorted(values);q1=(v[0]+v[1])/2;q3=(v[1]+v[2])/2
    return dict(n=3,median=v[1],minimum=v[0],maximum=v[2],q1=q1,q3=q3,iqr=q3-q1,samples=values)

index=read(RUN/'index.json');data=read(EXPORT/'results.json')
assert sha(EXPORT/'results.json')=='17922e61bcf4ff4ca6814a1b23cd758d0ac371d979f1537ab95dc802233c2f4b'
assert index['status']=='complete' and index['passed'] is True and data['passed'] is True
assert len(index['cases'])==48 and data['warmup_workflows']==12 and data['measured_workflows']==36 and data['logical_cells']==12
authorization=read(ref(index['authorization']));assert index['authorization']==data['authorization'] and authorization['approved'] is True and authorization['approved_by']=='main'
assert sha(Path(index['authorization']['path']))=='d1fc7443300f79ce5bc2185f900182466d60bed336906d99c54540c585d1dc02'
for value in authorization['artifacts'].values():ref(value)
plan=read(ref(index['plan']));assert index['plan']==authorization['artifacts']['plan'] and plan['quiet_window_confirmed'] is True
assert plan['case_ids']==['apps/littlex','apps/issue_desk'] and plan['measured_repeats']==3 and plan['excluded_warmups']==1 and plan['seeds']==[42]
assert index['sources']==data['source_hashes']==read(OUT/'small-review-candidate1-binding/candidate.json')['sources']
for path,digest in index['sources'].items():assert sha(Path(path))==digest
assert index['expected_schedule']==plan['schedule']
assert [{k:r[k] for k in ['app','config_id','phase','repeat','trial_id']} for r in index['cases']]==plan['schedule']
assert len({r['trial_id'] for r in index['cases']})==48 and all(r['passed'] is True for r in index['cases'])
assert ref(data['index'])==RUN/'index.json'
baseline={r['case_id']:r for r in read(ref(authorization['artifacts']['correctness']))['cases'] if r['config_id']=='none'}
sample_map={r['trial_id']:r for r in data['samples']};assert len(sample_map)==48
ownership=[json.loads(line) for line in (BASE/'reproduction/ttg-continuation-performance/pg-small-formal-v1/ownership-and-cleanup.jsonl').read_text().splitlines()]
assert ownership[-1]['action']=='cluster_stopped' and ownership[-1]['retained_databases']==[]
drops={r['database']:r for r in ownership if r['action']=='successful_database_dropped'}
assert len(drops)==48
dbs=set();checks=[];groups=collections.defaultdict(list);all_fields=None;raw_file_hashes=0;all_calls=0
for row in index['cases']:
    directory=RUN/row['trial_id'];seal=read(ref(row['raw_seal']));assert seal['passed'] is True
    actual={str(p.relative_to(directory)) for p in directory.rglob('*') if p.is_file() and p.name!='artifacts.json' and not any(t in {'.jac','__pycache__'} for t in p.relative_to(directory).parts)}
    assert actual==set(seal['files'])
    for name,digest in seal['files'].items():assert sha(directory/name)==digest;raw_file_hashes+=1
    metric=read(ref(row['metrics']));acceptance_path=ref(metric['independent_acceptance']);acceptance=read(acceptance_path);proof=read(directory/'continuation-proof.json');target=read(ref(acceptance['target_binding']))
    assert metric['passed'] is True and acceptance['passed'] is True and metric['raw_seal']==acceptance['raw_seal']==row['raw_seal']
    assert ref(metric['semantic_proof'])==directory/'continuation-proof.json' and metric['semantic_proof']==acceptance['semantic_proof']
    assert proof==row['proof'] and proof['stage']=='formal' and proof['seed']==42 and proof['passed'] is True
    assert all(proof['checks'][k] is True for k in ['native','oracle','fresh_session','restart'])
    assert metric['case_id']==proof['case_id']=='apps/'+row['app'] and metric['config_id']==row['config_id']==proof['config_id']
    assert all(proof[k]==baseline[proof['case_id']][k] for k in ['fixture_sha256','actions_sha256','output_sha256','state_sha256','oracle_sha256'])
    assert acceptance['sources']==index['sources'] and acceptance['verification']['independent_semantic_recheck'] is True
    assert acceptance['cleanup_review']==target['cleanup_review']==authorization['artifacts']['main_review']
    physical=acceptance['database_state'];db=physical['database'];assert db not in dbs;dbs.add(db)
    assert target['database']==db and target['case_directory']==str(directory) and target['run_directory']==str(RUN)
    assert target['app']==row['app'] and target['config_id']==row['config_id'] and target['seed']==42
    assert physical['matches_sealed_final_graph'] is True and physical['final_graph_sha256']==sha(directory/'final-graph-raw.json') and physical['actual_row_count']==len(read(directory/'final-graph-raw.json'))
    drop=drops[db];assert drop['owner']==target['cluster_owner']==physical['cluster_owner'] and drop['active_sessions']==0
    assert ref(drop['validated_acceptance']['acceptance'])==acceptance_path and drop['validated_acceptance']['raw_seal']==row['raw_seal']
    raw=[json.loads(line) for line in (directory/'http-raw.jsonl').read_text().splitlines()]
    calls=[json.loads(line) for p in directory.glob('server-*.calls.jsonl') for line in p.read_text().splitlines() if line]
    events=[json.loads(line) for p in directory.glob('server-*.events.jsonl') for line in p.read_text().splitlines() if line]
    all_calls+=len(calls);requests={(str(r['server_generation']),r['request']):r for r in raw};assert len(requests)==len(raw)
    connections={(str(e['server_generation']),e['backend_pid'],e['client_process_pid']):e for e in events if e['kind']=='connection'}
    phases=collections.defaultdict(list);startup=[];first={}
    for r in raw:
        g=str(r['server_generation']);first[g]=min(first.get(g,r['start_ns']),r['start_ns']);assert r['post_response_drain']['pending']==0
    for c in calls:
        g=str(c['server_generation']);assert c['cell_id']==proof['case_id']+'/'+row['config_id'] and c['trial_id']==row['trial_id'] and c['postgres_instance_id']==target['cluster_owner']
        connection=connections[g,c['backend_pid'],c['client_process_pid']]
        assert c['database']==connection['database']==db and c['application_name']==connection['application_name']
        if c.get('origin_request_id') is None:assert c['driver_end_ns']<=first[g];startup.append(c);continue
        request=requests[g,c['origin_request_id']];assert c['driver_start_ns']>=request['start_ns'] and c['role'] in ROLES
        if c['send_ns'] is not None:
            assert c['driver_start_ns']<=c['send_ns']<=c['ready_ns']<=c['driver_end_ns'] and c['ready_messages']==1 and c['command_complete']+c['error_messages']==1 and c['protocol_mode']=='extended_single_statement'
            assert c['ready_ns']<=request['end_ns'] if c['role']=='foreground' else c['driver_end_ns']<=request['post_response_drain']['end_ns']
        else:assert c['error'] and all(c[k]==0 for k in ['command_complete','data_rows','error_messages','ready_messages'])
        phases[request['phase']].append(c)
    assert totals(startup)==metric['startup_excluded'] and set(phases)==set(metric['phases'])
    for phase,cs in phases.items():assert totals(cs)==metric['phases'][phase],(row['trial_id'],phase)
    primary=phases['workflow'];own_totals=totals(primary)
    assert all(metric['primary'][k]==v for k,v in own_totals.items()),row['trial_id']
    overlap=overlaps(primary);observed={(v['trial_id'],str(v['server_generation']),v['origin_request_id'],v['clock_domain']):v for v in metric['primary']['actual_overlap']['requests']}
    assert set(observed)==set(overlap)
    for key,expected in overlap.items():assert all(observed[key][k]==v for k,v in expected.items())
    parent={c['client_process_pid'] for c in primary if c['role']=='foreground'};assert len(parent)==1
    for c in primary:
        if c['role'] in BG and c['send_ns'] is not None:
            assert c['actual_executor']==proof['run']['async_prefetch']
            assert (c['client_process_pid']!=next(iter(parent)))==(proof['run']['async_prefetch']=='process')
    request_metric={(str(r['server_generation']),r['request']):r for r in metric['request_metrics']}
    assert set(request_metric)==set(requests)
    for key,r in requests.items():
        cs=[c for c in calls if (str(c['server_generation']),c.get('origin_request_id'))==key]
        assert all(request_metric[key][k]==v for k,v in totals(cs).items())
    sample=sample_map[row['trial_id']];assert all(sample[k]==row[k] for k in ['app','config_id','phase','repeat','trial_id'])
    fields=[k for k in sample if k not in ['app','config_id','phase','repeat','trial_id']]
    expected_extra=dict(distinct_backend_overlap_ns=sum(v['distinct_backend_overlap_ns'] for v in overlap.values()),separate_process_overlap_ns=sum(v['separate_process_distinct_backend_overlap_ns'] for v in overlap.values()),business_HTTP_requests=sum(r['phase']=='workflow' for r in raw))
    assert all(sample[k]==(expected_extra[k] if k in expected_extra else own_totals[k]) for k in fields)
    if row['phase']=='measured':groups[row['app'],row['config_id']].append(sample)
    checks.append(dict(trial_id=row['trial_id'],phase=row['phase'],raw_seal=row['raw_seal']['sha256'],metric_sha256=row['metrics']['sha256'],acceptance_sha256=sha(acceptance_path),raw_count_interval_attribution_matches=True))
    all_fields=fields
assert len(groups)==12 and all(len(v)==3 for v in groups.values())
table={(r['app'],r['config_id']):r for r in data['table']};assert set(table)==set(groups)
for key,samples in groups.items():
    samples.sort(key=lambda r:r['repeat']);row=table[key];assert row['n']==3
    for field in row['metrics']:assert row['metrics'][field]==stats([r[field] for r in samples]),(key,field)
    assert row['business_HTTP_requests']==[r['business_HTTP_requests'] for r in samples]
for ratio in data['ratios']:
    key=ratio['app'],ratio['config_id'];base_value=table[ratio['app'],'none']['metrics']['protocol_sum_ns']['median'];value=table[key]['metrics']['protocol_sum_ns']['median']
    assert ratio['ratio_to_off']==(value/base_value if base_value else None)
csv_rows=list(csv.DictReader((EXPORT/'table.csv').open()));assert len(csv_rows)==12
for row in csv_rows:
    t=table[row['app'],row['configuration']]['metrics'];assert int(row['n'])==3
    expected={'protocol_sum_median_ms':t['protocol_sum_ns']['median']/1e6,'protocol_sum_iqr_ms':t['protocol_sum_ns']['iqr']/1e6,'protocol_union_median_ms':t['protocol_union_ns']['median']/1e6,'protocol_union_iqr_ms':t['protocol_union_ns']['iqr']/1e6,'SQL_total_median':t['sql_dispatches']['median'],'SQL_data_median':t['sql_data']['median'],'SQL_control_median':t['sql_control']['median'],'SQL_other_median':t['sql_other']['median'],'cycles_median':t['protocol_cycles']['median'],'foreground_background_overlap_median_ms':t['distinct_backend_overlap_ns']['median']/1e6}
    assert all(float(row[k])==v for k,v in expected.items())
export_seal=read(EXPORT/'artifacts.json');assert export_seal['passed'] is True
for name,digest in export_seal['files'].items():assert sha(EXPORT/name)==digest
report=M/'small-report-v1';integrity=read(report/'report-integrity.json');assert integrity['passed'] is True and integrity['pages']==5
for value in [integrity['renderer'],integrity['input_export'],integrity['input_seal']]:ref(value)
for name,digest in integrity['files'].items():assert sha(report/name)==digest
fig=read(report/'figure-inputs.json');assert fig['tables']==data['table'] and fig['ratios']==data['ratios']
result=dict(passed=True,reviewed_at_utc=dt.datetime.now(dt.UTC).isoformat(),scope='Actual LittleX+IssueDesk subset only:48fresh workflows,12excluded warmups,36measured,n3 per12cells; no all30/paper61/generalCPU release',index_sha256=sha(RUN/'index.json'),authorization_sha256=index['authorization']['sha256'],main_plan_sha256=index['plan']['sha256'],sources_unchanged=38,workflow_trials=48,unique_databases=len(dbs),excluded_warmups=12,measured_workflows=36,cells=12,n_per_cell=3,sealed_raw_files_verified=raw_file_hashes,SQL_driver_records_reconciled=all_calls,primary_phase='workflow',independent_reaggregation='Event-sweep interval unions, raw protocol/driver sums, category/counter/role totals, phases/requests, actual backend/client/DB joins, same-requestFG-BG overlaps and all exported samples/statistics/CSV values match',export=dict(results_sha256=sha(EXPORT/'results.json'),table_sha256=sha(EXPORT/'table.csv'),seal_sha256=sha(EXPORT/'artifacts.json')),figure_pdf_data_binding=dict(figure_sha256=sha(report/'figure-inputs.json'),PDF_sha256=sha(report/'ttg-small-performance.pdf'),integrity_sha256=sha(report/'report-integrity.json'),pages=5,figure_inputs_match_export=True,scope='Hash and numeric-data binding; not a full visual/layout review'),trial_checks=checks,limitations=['Semantic acceptance and freshphysicalcensus are bound actual-source proofs; reviewer did not rerun apps/oracles or query PostgreSQL','Protocol wall includes client row decoding/progress; sum andunion have different meanings; no serverCPU, cleanHTTP, causal or overfetch claim','No measured samples outside exact2appsx6 accepted; n3 dispersion and explicit warmup exclusions retained'],actual_DB_HTTP_app_runtime_jobs=0)
binding=OUT/'small-actual48-binding';binding.mkdir(exist_ok=True)
for label,path in [('index.json',RUN/'index.json'),('authorization.json',Path(index['authorization']['path'])),('main-plan.json',Path(index['plan']['path'])),('results.json',EXPORT/'results.json'),('table.csv',EXPORT/'table.csv'),('export-artifacts.json',EXPORT/'artifacts.json'),('report-integrity.json',report/'report-integrity.json'),('figure-inputs.json',report/'figure-inputs.json')]:(binding/label).write_bytes(path.read_bytes())
(OUT/'small-actual48-independent-review.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({k:v for k,v in result.items() if k not in ['trial_checks','limitations']},indent=2))
