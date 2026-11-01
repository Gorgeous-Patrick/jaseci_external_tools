"""Bounded formal36 SQL/HTTP/connection audit; huge outcomes are hash-streamed.

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
BASE = ROOT / 'project-notes/measurements/ttg-plus-performance-20261031'
RUN = BASE / 'formal-v1'
OUT = HERE / 'formal36-raw-audit'
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
    if 'identity_users' in text or 'identity_identities' in text:
        return 'identity'
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


def events(path, expected_refs):
    """Verify canonical outcome header; stream/hash body, never JSON-decode it."""
    opener = gzip.open if path.suffix == '.gz' else open
    with opener(path, 'rb') as source:
        line_number = 0
        while True:
            head = source.readline(4096)
            if not head:
                break
            line_number += 1
            check(head.strip(), 'Unexpected blank native event record')
            marker = head.find(b',"summary":')
            if marker >= 0:
                header_bytes = head[:marker] + b'}'
                header = json.loads(header_bytes)
                check(list(header) == IDENTITY + ['kind', 'timestamp_ns', 'scope_id', 'scope_instance'],
                      'Unverified outcome header framing')
                check(header['kind'] == 'dependency_outcome', 'Unexpected summary event')
                check(json.dumps(header, separators=(',', ':')).encode() == header_bytes,
                      'Noncanonical outcome header')
                digest = hashlib.sha256(head)
                size = len(head)
                while not head.endswith(b'\n'):
                    head = source.readline(65536)
                    check(head, 'Truncated native event line')
                    digest.update(head)
                    size += len(head)
                STATS['outcomes_stream_skipped'] += 1
                STATS['outcome_bytes_stream_skipped'] += size
                wanted = expected_refs.pop((str(path), line_number), None)
                if wanted:
                    event, raw = wanted
                    check(raw['record_sha256'] == digest.hexdigest(), 'Compact record SHA mismatch')
                    for key, value in header.items():
                        check(event[key] == value, 'Compact/raw header identity mismatch: ' + key)
                    STATS['compact_raw_records_verified'] += 1
                yield header
            else:
                chunks = [head]
                size = len(head)
                while not head.endswith(b'\n'):
                    head = source.readline(65536)
                    check(head, 'Truncated event line')
                    chunks.append(head)
                    size += len(head)
                    check(size <= 1024**2, 'Unexpected large non-outcome event')
                event = json.loads(b''.join(chunks))
                check(event.get('kind') != 'dependency_outcome', 'Missing canonical summary header')
                STATS['small_events_parsed'] += 1
                yield event


result_path = BASE / 'export-v1/results.json'
check(sha(result_path) == '876bf57b582708dfec86e3e153bfd8bac44414ff83ed4ac53848bcc352417c4d', 'Result hash')
export = read(result_path)
check(sha(BASE / 'export-v1/table.csv') == 'bf46389cad647534ad3738548f1d6bacd2c5e3582a5babe41217c5c5d7689e43', 'CSV hash')
check(sha(BASE / 'export-v1/artifacts.json') == 'a1b7d2c00d16008ffcfb0cc62c58a73c30654d81d00f905227d4a5820e7852a4', 'Export seal hash')
for item in read(BASE / 'export-v1/artifacts.json')['outputs']:
    check(sha(item['path']) == item['sha256'], 'Export output binding')
index = ref(export['index'])
plan = ref(export['plan'])
check(index['stage'] == 'formal' and index['status'] == 'complete' and index['passed'], 'Formal index')
check(len(index['rows']) == 36 and index['plan'] == export['plan'], 'Index sample count/plan')
check([{k: row[k] for k in plan['schedule'][0]} for row in index['rows']] == plan['schedule'], 'Exact36 schedule')
check(Counter(r['phase'] for r in index['rows']) == {'excluded_warmup': 9, 'measured': 27}, 'Excluded/measured counts')
check(len({r['trial_id'] for r in index['rows']}) == 36, 'Duplicate trial')
authorization = ref(index['authorization'])
check(index['authorization']['sha256'] == '40c293e1b9828db8bb876792d5725c83c04fba820a4f65bceff31dac52f543e7', 'Release hash')
check(authorization['accepted'] and authorization['quiet_window_confirmed'] and authorization['plan'] == index['plan'], 'Exact quiet release')
for key in ('sources', 'runtime', 'overlay', 'correctness'):
    check(authorization[key] == plan[key], 'Release ref: ' + key)
main_review = ref(authorization['main_review'])
check(main_review['accepted'] and main_review['plan'] == index['plan'], 'Main review')
lifecycle_path = ROOT / 'project-notes/measurements/ttg-plus-main-20261031/formal36-main-lifecycle.json'
lifecycle = read(lifecycle_path)
check(lifecycle['passed'] and lifecycle['index'] == export['index'] and lifecycle['authorization'] == index['authorization'], 'Lifecycle binding')
check(not lifecycle['creator_alive'] and not lifecycle['owned_cwd_processes'] and lifecycle['pg_ctl_status'] == 3
      and not lifecycle['pidfile'] and not lifecycle['retained_databases'], 'Stopped host proof')
sources = ref(plan['sources'])
check(plan['sources']['sha256'] == '47a3ea5c5850c79b23f75502a12fce96f434010290ba2495a7271526253c9a50', 'Source closure')
for name, wanted in sources['files'].items():
    check(sha(name) == wanted, 'Frozen source: ' + name)
probe_path = ROOT / 'reproduction/ttg-continuation-performance/continuation_probe.py'
check(sha(probe_path) == 'a4da9fccb1141c2d7148f5d5da377a6f95511517e2fce06353c43f743bd8b485', 'Source-bound event writer')
lexer_path = ROOT / 'reproduction/ttg-continuation-performance/sql_reconciliation.py'
spec = importlib.util.spec_from_file_location('review_sql_identity', lexer_path)
lexer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lexer)
ownership = [json.loads(x) for x in Path(lifecycle['ownership']['path']).read_text().splitlines()]
check(sha(lifecycle['ownership']['path']) == lifecycle['ownership']['sha256'], 'Ownership log hash')
drops = [r for r in ownership if r['action'] == 'successful_database_dropped']
check(len(drops) == 36 and ownership[-1]['action'] == 'cluster_stopped'
      and ownership[-1]['retained_databases'] == [], '36 owned drops/stop')
samples = []
databases = set()
all_fingerprints = []
for ordinal, row in enumerate(index['rows'], 1):
    refs = row['result']
    proof, acceptance, metric, seal = [ref(refs[k]) for k in ('proof', 'acceptance', 'metrics', 'raw')]
    directory = Path(refs['raw']['path']).parent
    check(row['passed'] and proof['passed'] and acceptance['passed'] and metric['passed'], 'Accepted sample')
    check(proof['case_id'] == metric['case_id'] == row['case_id']
          and proof['config_id'] == metric['config_id'] == row['config_id']
          and proof['stage'] == metric['stage'] == row['phase'], 'Sample identity')
    check(proof['run'] == plan['configs'][row['config_id']] and proof['runtime'] == plan['runtime']
          and proof['overlay'] == plan['overlay'], 'Runtime/config binding')
    check(proof['database'] not in databases, 'Reused DB')
    databases.add(proof['database'])
    check(proof['cluster_owner'] == index['cluster_owner'], 'Cluster owner')
    check(acceptance['semantic_proof'] == refs['proof'] and acceptance['semantic']['passed']
          and acceptance['database_state']['matches_sealed_final_graph'], 'Semantic/physical acceptance')
    check(acceptance['raw_seal'] == metric['raw_seal'] and metric['raw_seal']['sha256'] == refs['raw']['sha256']
          and metric['independent_acceptance'] == refs['acceptance'], 'Accepted raw/metric linkage')
    target = ref(acceptance['target'])
    check(target['database'] == proof['database'] and target['cluster_owner'] == proof['cluster_owner'], 'Owned target')
    drop = next(d for d in drops if d['database'] == proof['database'])
    check(drop['active_sessions'] == 0 and drop['validated_acceptance'] == refs['acceptance']
          and drop['metrics'] == refs['metrics'] and drop['owner'] == index['cluster_owner'], 'Owned success DROP')
    for name, wanted in seal['files'].items():
        check(sha(directory / name) == wanted, 'Case seal: ' + name)
        STATS['case_sealed_files'] += 1
    requests = [json.loads(x) for x in (directory / 'http-raw.jsonl').read_text().splitlines()]
    request_map = {}
    generations = defaultdict(list)
    for request in requests:
        key = (str(request['server_generation']), request['request'])
        check(key not in request_map, 'Duplicate HTTP origin')
        interval(request['start_ns'], request['end_ns'])
        check(request['post_response_drain']['pending'] == 0, 'HTTP drain incomplete')
        request_map[key] = request
        generations[key[0]].append(request)
    business = [r for r in requests if r['phase'] == 'workflow']
    check(len(business) == (9 if row['case_id'] == 'littlex' else 6), 'Original business RPC count')
    expected_raw = {}
    for event in metric['model_outcomes']:
        raw = event['raw_event']
        path = Path(raw['path'])
        check(path.is_relative_to(directory) and raw['sha256'] == seal['files'][str(path.relative_to(directory))], 'Compact raw-file ref')
        key = (str(path), raw['line'])
        check(key not in expected_raw, 'Repeated raw outcome ref')
        expected_raw[key] = (event, raw)
    connections = {}
    resets = []
    dispatches = {}
    def identity(record):
        check(record['cell_id'] == proof['case_id'] + '/' + proof['config_id']
              and record['trial_id'] == directory.name and record['postgres_instance_id'] == index['cluster_owner'],
              'Call/event identity')
        check(record['clock_domain'] == 'same-host-perf_counter_ns', 'Common clock domain')
    for path in sorted(directory.glob('server-*.events.jsonl*')):
        for event in events(path, expected_raw):
            identity(event)
            key = (str(event['server_generation']), event.get('origin_request_id'))
            if event['kind'] == 'connection':
                connections[(str(event['server_generation']), event['client_process_pid'], event['connection'], event['backend_pid'])] = event
            elif event['kind'] == 'explicit_profile_reset' and key in request_map and request_map[key]['phase'] == 'workflow':
                resets.append(event)
            elif event['kind'] == 'native_dispatch_complete':
                check(key in request_map, 'Dispatch lacks HTTP origin')
                check(event['path'] == request_map[key]['path'], 'Dispatch/HTTP path')
                dispatches[key] = event
    check(not expected_raw, 'Compact outcome raw-line refs not found')
    check(len(resets) == 1, 'One workflow profile reset')
    check(resets[0]['origin_request_id'] == min(business, key=lambda r: r['start_ns'])['request'], 'Reset first workflow origin')
    calls = []
    for path in sorted(directory.glob('server-*.calls.jsonl*')):
        opener = gzip.open if path.suffix == '.gz' else open
        with opener(path, 'rt') as source:
            calls.extend(json.loads(line) for line in source if line.strip())
    STATS['driver_records'] += len(calls)
    by_request = defaultdict(list)
    startup = []
    for call in calls:
        identity(call)
        check(hashlib.sha256(call['sql'].encode()).hexdigest() == call['sql_sha256'], 'Actual SQL SHA')
        interval(call['driver_start_ns'], call['driver_end_ns'])
        conn = connections.get((str(call['server_generation']), call['client_process_pid'], call['connection'], call['backend_pid']))
        check(conn and call['database'] == proof['database'] == conn['database']
              and call['application_name'] == conn['application_name'], 'Actual connection/backend/DB binding')
        check(conn['timestamp_ns'] <= call['driver_start_ns'], 'Connection recorded after SQL')
        generation = str(call['server_generation'])
        check(generation in generations, 'Unknown SQL generation')
        origin = call.get('origin_request_id')
        if origin is None:
            check(call['driver_end_ns'] <= min(r['start_ns'] for r in generations[generation]), 'Unattributed nonstartup SQL')
            startup.append(call)
            continue
        key = (generation, origin)
        check(key in request_map and key in dispatches, 'SQL origin/dispatch absent')
        request = request_map[key]
        check(call['driver_start_ns'] >= request['start_ns'] and call['role'] in ROLES, 'SQL origin bounds/role')
        if call['send_ns'] is not None:
            a, b = interval(call['send_ns'], call['ready_ns'])
            check(call['driver_start_ns'] <= a <= b <= call['driver_end_ns'], 'Driver/protocol bounds')
            check(call['ready_messages'] == 1 and call['command_complete'] + call['error_messages'] == 1
                  and call['protocol_mode'] == 'extended_single_statement', 'Protocol completion')
            check(call['frontend']['sync_messages'] == 1 and call['sendall_returned'], 'Actual wire dispatch')
            if call['role'] == 'foreground':
                check(b <= request['end_ns'], 'Foreground SQL after HTTP')
            else:
                check(call['driver_end_ns'] <= request['post_response_drain']['end_ns'], 'Background SQL after drain')
        else:
            check(call['error'] and not any(call[k] for k in ('command_complete', 'data_rows', 'error_messages', 'ready_messages')), 'Unsent driver call')
        by_request[key].append(call)
    phases = defaultdict(list)
    for key, selected in by_request.items():
        phases[request_map[key]['phase']].extend(selected)
    primary = phases['workflow']
    raw_primary = totals(primary)
    compare(raw_primary, metric['primary'], 'Primary')
    compare(totals(startup), metric['startup_excluded'], 'Startup')
    check(set(phases) == set(metric['phases']), 'Phase names')
    for phase, selected in phases.items():
        compare(totals(selected), metric['phases'][phase], 'Phase ' + phase)
    parents = {c['client_process_pid'] for c in primary if c['role'] == 'foreground'}
    check(len(parents) == 1, 'Foreground process')
    background = [c for c in primary if c['role'] != 'foreground' and c['send_ns'] is not None]
    check(all(c['actual_executor'] == 'process' and c['client_process_pid'] not in parents for c in background), 'Process-to-thread fallback')
    check(metric['primary']['HTTP_requests'] == len(business), 'Workflow HTTP count')
    late = sum(c['role'] != 'foreground' and c['send_ns'] is not None
               and c['ready_ns'] > request_map[key]['end_ns']
               for key, selected in by_request.items() if request_map[key]['phase'] == 'workflow' for c in selected)
    check(metric['primary']['late_background_calls'] == late, 'Late background count')
    rpc_rows = []
    for request in requests:
        key = (str(request['server_generation']), request['request'])
        selected = by_request[key]
        actual = totals(selected)
        saved = next(r for r in metric['request_metrics'] if r['request'] == request['request']
                     and str(r['server_generation']) == str(request['server_generation']))
        compare(actual, saved, 'Request')
        if request['phase'] == 'workflow':
            categories = Counter(category(c['sql']) for c in selected if c['send_ns'] is not None)
            check(sum(categories.values()) == actual['sql_dispatches'], 'Exhaustive SQL categories')
            rpc_rows.append(dict(ordinal=len(rpc_rows), walker=request['path'].split('/')[2],
                path=request['path'], request=request['request'], server_generation=request['server_generation'],
                HTTP_e2e_ns=request['end_ns']-request['start_ns'], categories=dict(categories), **actual))
    fingerprint_groups = defaultdict(list)
    for call in primary:
        if call['send_ns'] is not None:
            fingerprint_groups[(lexer.fingerprint(call['sql']), kind(call['sql']), call['role'])].append(call)
    saved_fps = {(r['fingerprint'], r['kind'], r['role']): r for r in metric['SQL_fingerprints']}
    check(set(fingerprint_groups) == set(saved_fps), 'SQL fingerprint inventory')
    fp_rows = []
    for key, selected in fingerprint_groups.items():
        actual = totals(selected)
        compare(actual, saved_fps[key], 'Fingerprint')
        fp_rows.append(dict(fingerprint=key[0], kind=key[1], role=key[2], sql=selected[0]['sql'],
            category=category(selected[0]['sql']), **actual))
    sample = dict(**{k: row[k] for k in ('case_id', 'config_id', 'phase', 'repeat', 'trial_id')},
        refs=refs, database=proof['database'], primary=raw_primary, late_background_calls=late,
        RPCs=rpc_rows, SQL_fingerprints=fp_rows,
        HTTP_workflow_sum_ns=sum(r['HTTP_e2e_ns'] for r in rpc_rows),
        HTTP_workflow_union_ns=union([(r['start_ns'], r['end_ns']) for r in business]))
    samples.append(sample)
    (OUT / (row['trial_id'] + '.json')).write_text(json.dumps(sample, indent=2) + '\n')
    print(json.dumps(dict(audited=ordinal, total=36, trial=row['trial_id'],
        elapsed_seconds=round(time.monotonic()-START, 2), primary_SQL=raw_primary['sql_dispatches'])), flush=True)
    del calls, metric, connections, phases, by_request, primary, startup


def dispersion(values):
    return dict(n=len(values), median=statistics.median(values), min=min(values), max=max(values),
                mean=statistics.mean(values), stdev=statistics.stdev(values) if len(values) > 1 else None)


numeric = ('protocol_sum_ns', 'protocol_union_ns', 'driver_sum_ns', 'driver_union_ns',
           'sql_dispatches', 'sql_data', 'sql_control', 'sql_other', 'data_rows', 'data_row_payload_bytes')
for row in export['rows']:
    chosen = [s for s in samples if s['case_id'] == row['case_id'] and s['config_id'] == row['config_id'] and s['phase'] == 'measured']
    check(len(chosen) == 3 and {s['repeat'] for s in chosen} == {0, 1, 2}, 'n3 exact sample repeats')
    for key in numeric:
        check(dispersion([s['primary'][key] for s in chosen]) == row[key], 'Export aggregate ' + key)
    for role in ROLES:
        for key in ('sql_dispatches', 'protocol_sum_ns', 'protocol_union_ns'):
            check(dispersion([s['primary']['roles'][role][key] for s in chosen]) == row['roles'][role][key], 'Export role aggregate')
    if 'Traverse' in row:
        traversals = [next(r for r in s['RPCs'] if r['walker'] == 'Traverse') for s in chosen]
        for key in ('protocol_sum_ns', 'protocol_union_ns', 'sql_dispatches', 'sql_data', 'sql_control', 'sql_other'):
            check(dispersion([r[key] for r in traversals]) == row['Traverse'][key], 'Export Traverse aggregate')
    else:
        check(row['case_id'] == 'littlex', 'Missing Traverse aggregate')
by_case = {(r['case_id'], r['config_id']): r for r in export['rows']}
for ratio in export['ratios']:
    own, off = by_case[ratio['case_id'], ratio['config_id']], by_case[ratio['case_id'], 'off']
    check(ratio['protocol_sum'] == own['protocol_sum_ns']['median']/off['protocol_sum_ns']['median'], 'Export sum ratio')
    check(ratio['protocol_union'] == own['protocol_union_ns']['median']/off['protocol_union_ns']['median'], 'Export union ratio')
csv_rows = list(csv.DictReader((BASE / 'export-v1/table.csv').open()))
check(len(csv_rows) == 9, 'CSV rows')
for record in csv_rows:
    row = by_case[record['case_id'], record['config_id']]
    check(int(record['n']) == 3, 'CSV n')
    for metric_name, label in [('protocol_sum_ns', 'protocol_sum_ms'), ('protocol_union_ns', 'protocol_union_ms')]:
        for stat in ('median', 'min', 'max'):
            check(float(record[label+'_'+stat]) == row[metric_name][stat]/1e6, 'CSV time conversion')
    for metric_name, label in [('sql_dispatches', 'SQL_total'), ('sql_data', 'SQL_data'), ('sql_control', 'SQL_control'), ('sql_other', 'SQL_other')]:
        check(float(record[label+'_median']) == row[metric_name]['median'], 'CSV SQL')
    if 'Traverse' in row:
        check(int(record['Traverse_visited']) == row['length']
              and float(record['Traverse_SQL_total_median']) == row['Traverse']['sql_dispatches']['median'], 'CSV Traverse')
    else:
        check(not record['Traverse_visited'] and not record['Traverse_SQL_total_median'], 'CSV LittleX blank Traverse')
check(len(databases) == 36, '36 fresh DBs')
check(all(s['primary']['protocol_sum_ns'] == s['primary']['protocol_union_ns'] for s in samples), 'Observed primary sum/union equality')
summary = dict(passed=True, scope='Independent36 SQL/HTTP/numeric/provenance audit; no huge outcome JSON admission',
    result=dict(path=str(result_path), sha256=sha(result_path)), index=export['index'], plan=export['plan'],
    authorization=index['authorization'], lifecycle=dict(path=str(lifecycle_path), sha256=sha(lifecycle_path)),
    sources=plan['sources'], sample_counts=export['sample_counts'], fresh_databases=36,
    owned_active_zero_drops=36, all_export_statistics_and_CSV_match=True,
    all_primary_protocol_sum_equals_union=True,
    canonical_event_writer=dict(path=str(probe_path), sha256=sha(probe_path)),
    raw_processing=dict(STATS), heavy_pass_seconds=time.monotonic()-START,
    interpretations=['Allroles SQL includes controls, catalog, path and payload calls including late background origin work',
        'No foreground/background protocol interval overlap observed in these primary samples; no CPU inference',
        'Heavy dependency_outcome bodies were canonical-header-verified and stream-hashed/skipped, not JSON-decoded',
        'Compact exact raw file/line/record SHA references independently match; no broad fresh native-outcome semantic claim'],
    next='Read-only perRPC/fingerprint attribution and publication binding; diagnostic DB window owned by main/suite',
    reviewer_DB_jobs=0)
(OUT / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
print('HEAVY_AUDIT_COMPLETE ' + json.dumps(dict(passed=True, seconds=round(time.monotonic()-START, 2),
    summary=str(OUT / 'summary.json'), stats=dict(STATS))), flush=True)
