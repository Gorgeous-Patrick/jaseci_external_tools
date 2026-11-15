"""Sealed primary DB metrics for the explicitly selected two-app experiment.

No services, SQL or high-level session timing. Every consumed trace is sealed.
"""
from collections import Counter, defaultdict
import json
from pathlib import Path
from evidence import read_json, sha256, verify_case, load_jsonl
from intervals import BACKGROUND_ROLES, interval, union_ns, concurrency, executor_evidence
from sql_reconciliation import sql_kind, fingerprint
from gate import payload_errors


def require(value, message):
    if not value:
        raise ValueError(message)


def scope_calls(calls, requests):
    """Prove request/startup attribution independently in each generation."""
    keys = {}
    generations = defaultdict(list)
    for row in requests:
        key = (str(row['server_generation']), row['request'])
        require(key not in keys, 'Duplicate HTTP request identity')
        interval(row['start_ns'], row['end_ns'])
        require(row['post_response_drain']['pending'] == 0, 'Incomplete post-response drain')
        keys[key] = row
        generations[key[0]].append(row)
    require(bool(keys), 'Empty HTTP workload')
    attributed, startup = [], []
    for call in calls:
        interval(call['driver_start_ns'], call['driver_end_ns'])
        generation = str(call['server_generation'])
        require(generation in generations, 'SQL from a generation without HTTP evidence')
        origin = call.get('origin_request_id')
        if origin is None:
            first = min(r['start_ns'] for r in generations[generation])
            require(call['driver_end_ns'] <= first, 'Unexplained unassigned SQL overlap/gap/late call')
            startup.append(call)
            continue
        key = (generation, origin)
        require(key in keys, 'SQL has no matching same-generation HTTP origin')
        row = keys[key]
        require(call['driver_start_ns'] >= row['start_ns'], 'SQL predates its assigned request')
        require(call['role'] in BACKGROUND_ROLES | {'foreground'}, 'Unknown SQL role')
        if call['send_ns'] is not None:
            interval(call['send_ns'], call['ready_ns'])
            require(call['driver_start_ns'] <= call['send_ns'] <= call['ready_ns'] <= call['driver_end_ns'],
                    'Driver/protocol clocks are inconsistent')
            require(call['ready_messages'] == 1 and call['protocol_mode'] == 'extended_single_statement',
                    'Incomplete/unsupported protocol cycle')
            require(call['command_complete'] + call['error_messages'] == 1,
                    'Single-statement CommandComplete/error count differs')
            require(isinstance(call['backend_pid'], int) and call['backend_pid'] > 0,
                    'Actual backend PID missing')
            if call['role'] == 'foreground':
                require(call['ready_ns'] <= row['end_ns'], 'Foreground DB completion after HTTP response')
            else:
                require(call['driver_end_ns'] <= row['post_response_drain']['end_ns'],
                        'Late background SQL outlives explicit post-response drain')
        else:
            require(call.get('error') and not any(call[k] for k in
                ('command_complete', 'data_rows', 'error_messages', 'ready_messages')),
                'Unsent call has SQL/protocol counters or no driver error')
        attributed.append((call, row))
    return attributed, startup


def totals(calls):
    dispatched = [c for c in calls if c['send_ns'] is not None]
    spans = [(c['send_ns'], c['ready_ns']) for c in dispatched]
    roles = {}
    for role in ('foreground', 'background_prefetch', 'background_continuation'):
        chosen = [c for c in dispatched if c['role'] == role]
        intervals = [(c['send_ns'], c['ready_ns']) for c in chosen]
        roles[role] = dict(sql_dispatches=len(chosen), protocol_sum_ns=sum(b-a for a,b in intervals),
                           protocol_union_ns=union_ns(intervals))
    counts = Counter(sql_kind(c['sql']) for c in dispatched)
    return dict(driver_calls=len(calls), sql_dispatches=len(dispatched),
        sql_data=counts['data'], sql_control=counts['control'], sql_other=counts['other'],
        command_complete=sum(c['command_complete'] for c in calls),
        protocol_cycles=sum(c['ready_messages'] for c in calls),
        server_error_messages=sum(c['error_messages'] for c in calls),
        pre_send_driver_errors=sum(c['send_ns'] is None for c in calls),
        data_rows=sum(c['data_rows'] for c in calls),
        data_row_payload_bytes=sum(c['data_row_payload_bytes'] for c in calls),
        driver_sum_ns=sum(c['driver_end_ns']-c['driver_start_ns'] for c in calls),
        driver_union_ns=union_ns([(c['driver_start_ns'], c['driver_end_ns']) for c in calls]),
        protocol_sum_ns=sum(b-a for a,b in spans), protocol_union_ns=union_ns(spans), roles=roles)


def summarize(directory, acceptance_path):
    directory = Path(directory).resolve()
    seal = verify_case(directory, required=('continuation-proof.json', 'http-raw.jsonl', 'summary.json'))
    proof = read_json(directory/'continuation-proof.json')
    require(proof['passed'] is True and proof['stage'] == 'formal', 'Formal semantic proof required')
    acceptance = read_json(acceptance_path)
    require(acceptance.get('passed') is True and acceptance.get('raw_seal') == seal,
            'Independent acceptance does not bind this raw seal')
    require(acceptance['semantic_proof'] == dict(path=str(directory/'continuation-proof.json'),
            sha256=sha256(directory/'continuation-proof.json')), 'Independent semantic proof hash mismatch')
    require(acceptance.get('verification', {}).get('independent_semantic_recheck') is True,
            'Independent response oracle replay absent')
    require(acceptance['database_state']['matches_sealed_final_graph'] is True and
            acceptance['database_state']['final_graph_sha256'] == sha256(directory/'final-graph-raw.json'),
            'Independent physical state proof mismatch')
    calls = load_jsonl(directory, 'server-*.calls.jsonl*')
    events = load_jsonl(directory, 'server-*.events.jsonl*')
    requests = load_jsonl(directory, 'http-raw.jsonl*')
    require(calls and events, 'Missing SQL/event observation files')
    for record in calls+events:
        require(record['cell_id']==proof['case_id']+'/'+proof['config_id'] and
                record['trial_id']==directory.name and
                record['postgres_instance_id']==acceptance['database_state']['cluster_owner'],
                'Trace cell/trial/cluster identity differs from accepted workload')
    connections={(str(e['server_generation']),e['backend_pid'],e['client_process_pid']):e
                 for e in events if e['kind']=='connection'}
    for call in calls:
        key=(str(call['server_generation']),call['backend_pid'],call['client_process_pid'])
        require(key in connections and call['database']==acceptance['database_state']['database'] and
                connections[key]['database']==call['database'] and
                connections[key]['application_name']==call['application_name'],
                'SQL lacks matching actual owned connection/backend evidence')
    require(not payload_errors(events), 'Nested model payload_error')
    assigned, startup = scope_calls(calls, requests)
    phases = defaultdict(list)
    for call, row in assigned:
        phases[row['phase']].append(call)
    primary = phases['workflow']
    require(any(r['phase'] == 'workflow' for r in requests), 'No primary workflow requests')
    business = {(str(r['server_generation']), r['request']) for r in requests if r['phase'] == 'workflow'}
    outcomes = [e for e in events if e['kind'] == 'dependency_outcome' and
                (str(e['server_generation']), e.get('origin_request_id')) in business]
    parents = {c['client_process_pid'] for c in primary if c['role'] == 'foreground'}
    require(len(parents) == 1, 'Business foreground server process is missing/ambiguous')
    executor = proof['run']['async_prefetch']
    parallel = concurrency(primary)
    evidence = executor_evidence(primary, executor, next(iter(parents)))
    for event in outcomes:
        require(not event['summary'].get('errors'), 'Dependency outcome errors')
    resets = [e for e in events if e['kind'] == 'explicit_profile_reset' and
              (str(e['server_generation']), e.get('origin_request_id')) in business]
    require(len(resets) == 1, 'Exactly one business profile reset required')
    fingerprints = defaultdict(list)
    for call in primary:
        if call['send_ns'] is not None:
            fingerprints[(fingerprint(call['sql']), sql_kind(call['sql']), call['role'])].append(call)
    query_rows = [dict(fingerprint=k[0], kind=k[1], role=k[2], sql=v[0]['sql'], **totals(v))
                  for k,v in sorted(fingerprints.items())]
    return dict(passed=True, case_id=proof['case_id'], config_id=proof['config_id'], seed=proof['seed'],
        raw_seal=seal, semantic_proof=acceptance['semantic_proof'],
        independent_acceptance=dict(path=str(Path(acceptance_path).resolve()),sha256=sha256(acceptance_path)),
        primary=dict(**totals(primary), actual_overlap=parallel, executor=evidence,
                     HTTP_requests=sum(r['phase']=='workflow' for r in requests),
                     late_background_calls=sum(c['send_ns'] is not None and c['ready_ns']>r['end_ns']
                         for c,r in assigned if r['phase']=='workflow' and c['role'] in BACKGROUND_ROLES)),
        phases={p:totals(v) for p,v in sorted(phases.items())}, startup_excluded=totals(startup),
        request_metrics=[dict(request=r['request'],phase=r['phase'],server_generation=r['server_generation'],
                         **totals([c for c,row in assigned if row is r])) for r in requests],
        SQL_fingerprints=query_rows, model_outcomes=outcomes, profile_reset_events=resets,
        definition='Primary workflow only: send-to-Z protocol completion wall; sum can overlap; union retains actual intervals',
        CPU_claim='No CPU attribution; no CPU diagnostic captured', clean_HTTP_e2e=None,
        measured_payload_consumption_bytes=None)
