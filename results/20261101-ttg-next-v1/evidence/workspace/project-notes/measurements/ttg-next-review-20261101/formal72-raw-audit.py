"""Bounded formal72 SQL/HTTP/compact-event and numeric audit.

Numeric arithmetic is recomputed here from calls, not from saved metrics.
The unchanged source-bound SQL lexer is reused only for exact SQL identity.
No runtime/app/DB execution and no full native-outcome semantic admission.
"""
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

START = time.monotonic()
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
BASE = ROOT / 'project-notes/measurements/ttg-next-performance-20261101'
RUN = BASE / 'formal-v1'
OUT = HERE / 'formal72-raw-audit'
OUT.mkdir(exist_ok=False)
ROLES = ('foreground', 'background_prefetch', 'background_continuation')
IDENTITY = ['cell_id', 'trial_id', 'server_generation', 'postgres_instance_id',
            'clock_domain', 'origin_request_id', 'client_process_pid',
            'parent_process_pid', 'role', 'actual_executor']
CONTROL = {'BEGIN', 'START', 'SET', 'SAVEPOINT', 'RELEASE', 'DISCARD', 'COMMIT',
           'END', 'ROLLBACK', 'ABORT', 'RESET', 'SHOW', 'DEALLOCATE', 'CLOSE'}
DATA = {'SELECT', 'WITH', 'INSERT', 'UPDATE', 'DELETE', 'MERGE', 'VALUES', 'FETCH'}
STATS = Counter()


def check(value, message):
    if not value:
        raise AssertionError(message)


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            result.update(chunk)
            STATS['hashed_bytes'] += len(chunk)
    return result.hexdigest()


def ref(value):
    check(sha(value['path']) == value['sha256'], 'Reference hash: ' + value['path'])
    return read(value['path'])


def interval(a, b):
    check(type(a) is int and type(b) is int and b >= a, 'Invalid interval')
    return a, b


def union(spans):
    merged = []
    for a, b in sorted(spans):
        interval(a, b)
        if merged and a <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    return sum(b-a for a, b in merged)


def kind(sql):
    found = re.match(r'\s*([A-Za-z]+)', sql)
    token = found[1].upper() if found else ''
    return 'control' if token in CONTROL else 'data' if token in DATA else 'other'


def category(sql):
    text = sql.lstrip()
    if kind(sql) == 'control':
        return 'control'
    if text.startswith('SELECT DISTINCT') and '"arch_type"' in text and '"arch_module"' in text:
        return 'catalog'
    if '"slot"' in text and '"arity"' in text and 'LEFT JOIN LATERAL' in text:
        return 'fused_path'
    if re.match(r'SELECT n[0-9]+\.id, e[0-9]+\.id', text):
        return 'ordinary_path'
    if re.match(r'SELECT a\.id, a\.kind, a\.arch_type', text):
        return 'payload'
    if re.search(r'\bidentity_(?:users|lookups|identities)\b', text):
        return 'identity'
    if re.match(r'(?:INSERT|UPDATE|DELETE|MERGE)\b', text, re.I):
        return 'mutation'
    return 'other_data' if kind(sql) == 'data' else 'other'


def totals(calls):
    sent = [c for c in calls if c['send_ns'] is not None]
    spans = [interval(c['send_ns'], c['ready_ns']) for c in sent]
    drivers = [interval(c['driver_start_ns'], c['driver_end_ns']) for c in calls]
    counts = Counter(kind(c['sql']) for c in sent)
    roles = {}
    for role in ROLES:
        selected = [interval(c['send_ns'], c['ready_ns']) for c in sent if c['role'] == role]
        roles[role] = dict(sql_dispatches=len(selected),
            protocol_sum_ns=sum(b-a for a, b in selected), protocol_union_ns=union(selected))
    return dict(driver_calls=len(calls), sql_dispatches=len(sent), sql_data=counts['data'],
        sql_control=counts['control'], sql_other=counts['other'],
        command_complete=sum(c['command_complete'] for c in calls),
        protocol_cycles=sum(c['ready_messages'] for c in calls),
        server_error_messages=sum(c['error_messages'] for c in calls),
        pre_send_driver_errors=sum(c['send_ns'] is None for c in calls),
        data_rows=sum(c['data_rows'] for c in calls),
        data_row_payload_bytes=sum(c['data_row_payload_bytes'] for c in calls),
        driver_sum_ns=sum(b-a for a, b in drivers), driver_union_ns=union(drivers),
        protocol_sum_ns=sum(b-a for a, b in spans), protocol_union_ns=union(spans), roles=roles)


def compare(actual, expected, label):
    for key, value in actual.items():
        check(expected[key] == value, label + ': ' + key)


def jsonl(path):
    opener = gzip.open if path.suffix == '.gz' else open
    with opener(path, 'rb') as stream:
        for number, line in enumerate(stream, 1):
            if line.strip():
                yield json.loads(line), number, hashlib.sha256(line).hexdigest()


result_path = BASE / 'export-v1/results.json'
check(sha(result_path) == 'd8059a8974828a2a6279d82933a18b0d6592098bd3fc6ee6a0950aa93e32c8ec', 'Result hash')
export = read(result_path)
check(sha(BASE / 'export-v1/table.csv') == '49197925f5a6dfd84ad2e830c62cc9f1e32a0045430f448395a5569515d120e7', 'CSV hash')
check(sha(BASE / 'export-v1/artifacts.json') == 'd7150300c8e552f124f29e480b8e7de71e5f441baf1b5c7c079c9adbdb4520c8', 'Export seal')
for item in read(BASE / 'export-v1/artifacts.json')['outputs']:
    check(sha(item['path']) == item['sha256'], 'Export output binding')
index, plan = ref(export['index']), ref(export['plan'])
check(index['stage'] == 'formal' and index['status'] == 'complete' and index['passed'], 'Complete formal index')
check(len(index['rows']) == 72 and index['plan'] == export['plan'], '72 rows/plan')
check([{k: row[k] for k in plan['formal_schedule'][0]} for row in index['rows']] == plan['formal_schedule'], 'Exact72 schedule')
check(Counter(r['phase'] for r in index['rows']) == {'excluded_warmup': 18, 'measured': 54}, '18/54 phases')
check(len({r['trial_id'] for r in index['rows']}) == 72, 'Unique trials')
authorization = ref(index['authorization'])
check(authorization['accepted'] and authorization['quiet_window_confirmed'] and authorization['plan'] == index['plan'], 'Exact quiet release')
check(authorization['sources'] == plan['sources'] and plan['sources']['sha256'] == '18fc9a390f887c8a7be59665fba42f64b3201bd1fa6e7db9bd8c12a8911d1076', 'Closed capture source identity')
check(sha(export['postprocessor']['path']) == export['postprocessor']['sha256'], 'Postprocessor source hash')
check(export['postprocessor']['sha256'] == 'eb2fe58f08aa3c9ed541cb3205392f7b8af3adea646c27cf2481eaaf75ac60ee', 'Reviewed standalone postprocessor')
lifecycle_path = BASE / 'formal-v1-stopped-capacity-v1.json'
check(sha(lifecycle_path) == 'ba84da096def2c11868987b46ef85c99752899661a8ead48876a1609465dfb86', 'Stopped proof hash')
lifecycle = read(lifecycle_path)
check(lifecycle['passed'] and lifecycle['index'] == export['index'] and lifecycle['controller_exit_code'] == 0, 'Natural complete/stop binding')
check(lifecycle['pg_ctl_status'] == 3 and lifecycle['postmaster_pid_file_absent'] and not lifecycle['retained_databases'], 'Stopped PG/no retained DB')
settings = ref(index['postgres_settings'])
check(settings['passed'] and settings['cluster_owner'] == index['cluster_owner'] and settings['settings']['min_wal_size'] == '32MB' and settings['settings']['max_wal_size'] == '64MB', 'Uniform actual WAL')
ownership = [json.loads(x) for x in Path(lifecycle['ownership']['path']).read_text().splitlines()]
check(sha(lifecycle['ownership']['path']) == lifecycle['ownership']['sha256'], 'Ownership hash')
drops = [r for r in ownership if r['action'] == 'successful_database_dropped']
check(len(drops) == 72 and ownership[-1]['action'] == 'cluster_stopped' and not ownership[-1]['retained_databases'], '72 owned active0 drops/natural stop')
lexer_path = ROOT / 'reproduction/ttg-continuation-performance/sql_reconciliation.py'
sources = ref(plan['sources'])
check(sha(lexer_path) == sources['files'][str(lexer_path)], 'Source-bound SQL lexer')
spec = importlib.util.spec_from_file_location('review72_sql_identity', lexer_path)
lexer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lexer)
samples, databases, semantic_groups = [], set(), {}
for ordinal, row in enumerate(index['rows'], 1):
    bindings = row['result']
    proof, acceptance, metric, seal = [ref(bindings[k]) for k in ('proof', 'acceptance', 'metrics', 'raw')]
    directory = Path(bindings['raw']['path']).parent
    check(row['passed'] and proof['passed'] and acceptance['passed'] and metric['passed'], 'Accepted sample')
    check(proof['case_id'] == metric['case_id'] == row['case_id'] and proof['config_id'] == metric['config_id'] == row['config_id'] and proof['stage'] == metric['stage'] == row['phase'], 'Sample identity')
    rt = plan['runtimes']['baseline850' if row['config_id'] == 'baseline850' else 'next']
    check(proof['run'] == plan['configs'][row['config_id']] and proof['runtime'] == rt['clean'] and proof['overlay'] == rt['overlay'], 'Closed runtime/config references')
    check(proof['database'] not in databases and proof['cluster_owner'] == index['cluster_owner'], 'Fresh owned DB')
    databases.add(proof['database'])
    check(acceptance['source_manifest'] == plan['sources'] and acceptance['semantic_proof'] == bindings['proof'] and acceptance['semantic']['passed'] and acceptance['database_state']['matches_sealed_final_graph'], 'Semantic/physical/source linkage')
    check(acceptance['raw_seal'] == metric['raw_seal'] and metric['raw_seal']['sha256'] == bindings['raw']['sha256'] and metric['independent_acceptance'] == bindings['acceptance'], 'Raw metric acceptance')
    check(all(proof['checks'][k] for k in ('native','oracle','fresh_session','restart')), 'Native checks')
    sg = (proof['fixture_sha256'], proof['actions_sha256'], proof['output_sha256'], acceptance['semantic']['final_logical_state_sha256'])
    check(row['case_id'] not in semantic_groups or semantic_groups[row['case_id']] == sg, 'All mode/repeat semantic identity')
    semantic_groups[row['case_id']] = sg
    target = ref(acceptance['target'])
    check(target['database'] == proof['database'] and target['cluster_owner'] == proof['cluster_owner'] and target['config_id'] == row['config_id'], 'Target binding')
    drop = next(d for d in drops if d['database'] == proof['database'])
    check(drop['active_sessions'] == 0 and drop['validated_acceptance'] == bindings['acceptance'] and drop['metrics'] == bindings['metrics'] and drop['target'] == acceptance['target'] and drop['owner'] == index['cluster_owner'], 'Owned active0 drop')
    for name, wanted in seal['files'].items():
        check(sha(directory / name) == wanted, 'Case sealed file: ' + name)
        STATS['case_sealed_files'] += 1
    requests = [r for r, _, _ in jsonl(directory / 'http-raw.jsonl')]
    request_map, generations = {}, defaultdict(list)
    for request in requests:
        key = (str(request['server_generation']), request['request'])
        check(key not in request_map, 'Unique HTTP origin')
        interval(request['start_ns'], request['end_ns'])
        check(request['post_response_drain']['pending'] == 0 and 200 <= request['http_status'] < 300, 'HTTP completion/status')
        request_map[key] = request
        generations[key[0]].append(request)
    business = [r for r in requests if r['phase'] == 'workflow']
    if row['case_id'].startswith('linked_list'):
        check(len(business) == 6, 'Six actual LL operations')
        traverse = [r for r in business if r['path'].split('/')[2:3] == ['Traverse']]
        check(len(traverse) == 1, 'One actual Traverse')
        value = traverse[0]['output'].get('data', traverse[0]['output'])
        check(value['reports'] == list(range(row['length'])) and value['result']['visited'] == row['length'], 'Exact native ordered reports/visited')
    expected_raw = {}
    for event in metric['model_outcomes']:
        raw = event['raw_event']; path = Path(raw['path'])
        check(path.is_relative_to(directory) and raw['sha256'] == seal['files'][str(path.relative_to(directory))], 'Compact raw file ref')
        key = (str(path), raw['line'])
        check(key not in expected_raw, 'Distinct compact outcome ref')
        expected_raw[key] = (event, raw)
    connections, resets, dispatches, closes = {}, [], {}, {}
    def identity(record):
        check(record['cell_id'] == proof['case_id'] + '/' + proof['config_id'] and record['trial_id'] == directory.name and record['postgres_instance_id'] == index['cluster_owner'] and record['clock_domain'] == 'same-host-perf_counter_ns', 'Actual call/event identity')
    for path in sorted(directory.glob('server-*.events.jsonl*')):
        for event, number, record_sha in jsonl(path):
            STATS['events_parsed'] += 1
            identity(event)
            key = (str(event['server_generation']), event.get('origin_request_id'))
            if event['kind'] == 'dependency_outcome':
                if (str(path), number) in expected_raw:
                    saved, raw = expected_raw.pop((str(path), number))
                    check(raw['record_sha256'] == record_sha and {k:v for k,v in saved.items() if k != 'raw_event'} == event, 'Exact compact record/header/counters')
                    STATS['compact_raw_records_verified'] += 1
                check(event.get('format') == 'ttg-next-compact-v1' and not event['summary']['errors'] and event['summary']['payload_error_count'] == 0, 'Compact native errors')
            elif event['kind'] == 'connection':
                connections[(str(event['server_generation']), event['client_process_pid'], event['connection'], event['backend_pid'])] = event
            elif event['kind'] == 'explicit_profile_reset' and key in request_map and request_map[key]['phase'] == 'workflow':
                resets.append(event)
            elif event['kind'] == 'native_dispatch_complete':
                check(key in request_map and event['path'] == request_map[key]['path'], 'Native dispatch/HTTP binding')
                dispatches[key] = event
            elif event['kind'] == 'native_context_close' and key in request_map:
                check(event.get('natural_close_completed') is True, 'Natural close')
                closes.setdefault(key, set()).add(event['session_nonce'])
    check(not expected_raw and len(resets) == 1, 'All compact refs/one reset')
    check(resets[0]['origin_request_id'] == min(business, key=lambda r:r['start_ns'])['request'], 'Reset first business')
    nonces = {}
    for key, req in request_map.items():
        if req['path'].startswith('/walker/'):
            check(closes.get(key), 'Walker session natural close')
            for nonce in closes[key]:
                check(nonce not in nonces or nonces[nonce] == key, 'Fresh walker session')
                nonces[nonce] = key
    calls = [c for path in sorted(directory.glob('server-*.calls.jsonl*')) for c, _, _ in jsonl(path)]
    STATS['driver_records'] += len(calls)
    by_request, startup = defaultdict(list), []
    for call in calls:
        identity(call)
        check(hashlib.sha256(call['sql'].encode()).hexdigest() == call['sql_sha256'], 'Actual SQL SHA')
        interval(call['driver_start_ns'], call['driver_end_ns'])
        conn = connections.get((str(call['server_generation']), call['client_process_pid'], call['connection'], call['backend_pid']))
        check(conn and call['database'] == proof['database'] == conn['database'] and call['application_name'] == conn['application_name'] and conn['timestamp_ns'] <= call['driver_start_ns'], 'Actual connection/backend/database/order')
        generation, origin = str(call['server_generation']), call.get('origin_request_id')
        check(generation in generations, 'SQL generation')
        if origin is None:
            check(call['driver_end_ns'] <= min(r['start_ns'] for r in generations[generation]), 'Only startup unassigned SQL')
            startup.append(call); continue
        key = (generation, origin)
        check(key in request_map and key in dispatches, 'SQL origin/dispatch')
        request = request_map[key]
        check(call['driver_start_ns'] >= request['start_ns'] and call['role'] in ROLES, 'Call request start/role')
        if call['send_ns'] is not None:
            a,b = interval(call['send_ns'], call['ready_ns'])
            check(call['driver_start_ns'] <= a <= b <= call['driver_end_ns'], 'Driver/send/Z bounds')
            check(call['ready_messages'] == 1 and call['command_complete'] + call['error_messages'] == 1 and call['protocol_mode'] == 'extended_single_statement', 'Protocol completion')
            check(call['frontend']['sync_messages'] == 1 and call['sendall_returned'], 'Actual wire dispatch')
            check(b <= request['end_ns'] if call['role'] == 'foreground' else call['driver_end_ns'] <= request['post_response_drain']['end_ns'], 'FG response/BG drain bounds')
        else:
            check(call['error'] and not any(call[k] for k in ('command_complete','data_rows','error_messages','ready_messages')), 'Unsent call')
        by_request[key].append(call)
    phases = defaultdict(list)
    for key, selected in by_request.items():
        phases[request_map[key]['phase']].extend(selected)
    primary = phases['workflow']; raw_primary = totals(primary)
    compare(raw_primary, metric['primary'], 'Primary')
    compare(totals(startup), metric['startup_excluded'], 'Startup')
    check(set(phases) == set(metric['phases']), 'Phase names')
    for phase, selected in phases.items():compare(totals(selected), metric['phases'][phase], 'Phase')
    parents = {c['client_process_pid'] for c in primary if c['role'] == 'foreground'}
    check(len(parents) == 1, 'Actual foreground PID')
    background = [c for c in primary if c['role'] != 'foreground' and c['send_ns'] is not None]
    check(all(c['actual_executor'] == 'process' and c['client_process_pid'] not in parents and c['parent_process_pid'] in parents for c in background), 'Actual process executor/parent PID')
    check(metric['primary']['HTTP_requests'] == len(business), 'Workflow HTTP count')
    late = sum(c['role'] != 'foreground' and c['send_ns'] is not None and c['ready_ns'] > request_map[key]['end_ns'] for key, cs in by_request.items() if request_map[key]['phase'] == 'workflow' for c in cs)
    check(metric['primary']['late_background_calls'] == late, 'Late BG count')
    rpc_rows = []
    for request in requests:
        key = (str(request['server_generation']), request['request']); selected = by_request[key]
        actual = totals(selected)
        saved = next(r for r in metric['request_metrics'] if r['request'] == request['request'] and str(r['server_generation']) == str(request['server_generation']))
        compare(actual, saved, 'Request')
        if request['phase'] == 'workflow':
            categories = Counter(category(c['sql']) for c in selected if c['send_ns'] is not None)
            check(sum(categories.values()) == actual['sql_dispatches'], 'Exhaustive query categories')
            rpc_rows.append(dict(ordinal=len(rpc_rows), walker=request['path'].split('/')[2] if request['path'].startswith('/walker/') else request['path'], path=request['path'], request=request['request'], server_generation=request['server_generation'], HTTP_e2e_ns=request['end_ns']-request['start_ns'], categories=dict(categories), **actual))
    groups = defaultdict(list)
    for call in primary:
        if call['send_ns'] is not None:groups[(lexer.fingerprint(call['sql']),kind(call['sql']),call['role'])].append(call)
    saved_fps = {(r['fingerprint'],r['kind'],r['role']):r for r in metric['SQL_fingerprints']}
    check(set(groups) == set(saved_fps), 'Fingerprint inventory')
    fp_rows = []
    for key, selected in groups.items():
        actual = totals(selected); compare(actual,saved_fps[key],'Fingerprint')
        fp_rows.append(dict(fingerprint=key[0],kind=key[1],role=key[2],sql=selected[0]['sql'],category=category(selected[0]['sql']),**actual))
    sample = dict(**{k:row[k] for k in ('case_id','config_id','phase','repeat','trial_id')}, refs=bindings,database=proof['database'],primary=raw_primary,late_background_calls=late,RPCs=rpc_rows,SQL_fingerprints=fp_rows,processes=dict(foreground=sorted(parents),background=sorted({c['client_process_pid'] for c in background})),HTTP_workflow_sum_ns=sum(r['HTTP_e2e_ns'] for r in rpc_rows),HTTP_workflow_union_ns=union([(r['start_ns'],r['end_ns']) for r in business]))
    samples.append(sample)
    (OUT/(row['trial_id']+'.json')).write_text(json.dumps(sample,indent=2)+'\n')
    print(json.dumps(dict(audited=ordinal,total=72,trial=row['trial_id'],elapsed_seconds=round(time.monotonic()-START,2),primary_SQL=raw_primary['sql_dispatches'])),flush=True)
    del calls,metric,connections,phases,by_request,primary,startup


def dispersion(values):
    return dict(n=len(values),median=statistics.median(values),min=min(values),max=max(values),mean=statistics.mean(values),stdev=statistics.stdev(values) if len(values)>1 else None)


numeric = ('protocol_sum_ns','protocol_union_ns','driver_sum_ns','driver_union_ns','sql_dispatches','sql_data','sql_control','sql_other','data_rows','data_row_payload_bytes')
check(len(export['rows']) == 18 and len({(r['case_id'],r['config_id']) for r in export['rows']}) == 18, '18 unique exported cells')
for row in export['rows']:
    chosen = [s for s in samples if s['case_id'] == row['case_id'] and s['config_id'] == row['config_id'] and s['phase'] == 'measured']
    check(len(chosen) == 3 and {s['repeat'] for s in chosen} == {0,1,2}, 'All cells exact n3')
    for key in numeric:check(dispersion([s['primary'][key] for s in chosen]) == row[key], 'Export aggregate '+key)
    for role in ROLES:
        for key in ('sql_dispatches','protocol_sum_ns','protocol_union_ns'):
            check(dispersion([s['primary']['roles'][role][key] for s in chosen]) == row['roles'][role][key], 'Export role aggregate')
    if 'Traverse' in row:
        ts = [next(r for r in s['RPCs'] if r['walker'] == 'Traverse') for s in chosen]
        for key in ('protocol_sum_ns','protocol_union_ns','sql_dispatches','sql_data','sql_control','sql_other'):
            check(dispersion([r[key] for r in ts]) == row['Traverse'][key], 'Export Traverse aggregate')
by_case = {(r['case_id'],r['config_id']):r for r in export['rows']}
for ratio in export['ratios']:
    own,off = by_case[ratio['case_id'],ratio['config_id']],by_case[ratio['case_id'],'off']
    for metric_name in ('protocol_sum','protocol_union'):
        check(ratio[metric_name] == own[metric_name+'_ns']['median']/off[metric_name+'_ns']['median'], 'Export ratio')
csv_rows = list(csv.DictReader((BASE/'export-v1/table.csv').open()))
check(len(csv_rows) == 18, '18 CSV rows')
for record in csv_rows:
    row = by_case[record['case_id'],record['config_id']];check(int(record['n']) == 3,'CSV n')
    for metric_name,label in [('protocol_sum_ns','protocol_sum_ms'),('protocol_union_ns','protocol_union_ms')]:
        for stat in ('median','min','max'):check(float(record[label+'_'+stat]) == row[metric_name][stat]/1e6,'CSV time')
    for metric_name,label in [('sql_dispatches','SQL_total'),('sql_data','SQL_data'),('sql_control','SQL_control'),('sql_other','SQL_other')]:
        check(float(record[label+'_median']) == row[metric_name]['median'],'CSV SQL')
    if 'Traverse' in row:check(int(record['Traverse_visited']) == row['length'] and float(record['Traverse_SQL_total_median']) == row['Traverse']['sql_dispatches']['median'],'CSV Traverse')
    else:check(not record['Traverse_visited'] and not record['Traverse_SQL_total_median'],'CSV absent Traverse')
summary = dict(passed=True,scope='Independent72 SQL/HTTP/compact event/numeric audit; accepted semantic replay/physical proofs source-bound, not rerun',result=dict(path=str(result_path),sha256=sha(result_path)),index=export['index'],plan=export['plan'],authorization=index['authorization'],lifecycle=dict(path=str(lifecycle_path),sha256=sha(lifecycle_path)),sources=plan['sources'],postprocessor=export['postprocessor'],sample_counts=export['sample_counts'],fresh_databases=len(databases),owned_active_zero_drops=len(drops),all_export_statistics_and_CSV_match=True,all_primary_protocol_sum_equals_union=all(s['primary']['protocol_sum_ns']==s['primary']['protocol_union_ns'] for s in samples),samples_with_protocol_overlap=[s['trial_id'] for s in samples if s['primary']['protocol_sum_ns']!=s['primary']['protocol_union_ns']],raw_processing=dict(STATS),heavy_pass_seconds=time.monotonic()-START,interpretations=['Actual all-role dispatches include controls/path/payload/catalog and late business-origin work.','Child actualprocess/parent/backend/connection identities verified; no CPU inference from send-to-Z intervals.','Compact exact raw line/file/record/counter identity verified; no huge native suffix body exists.','Matching complete action/output/final logical graph accepted proofs across all modes/repeats; all native Traverse reports independently checked.','Per-RPC and fingerprint categories are exhaustive structural labels, exact SQL retained for diagnosis.'],next='Heavy pass finished; QUIET for P7 CPU then P6 selected SQL diagnostics, writeup uses derivatives only')
(OUT/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
print(json.dumps(dict(QUIET=True,passed=True,seconds=round(time.monotonic()-START,2),summary=str(OUT/'summary.json'),stats=dict(STATS))),flush=True)


