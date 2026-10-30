"""Measured interval/count aggregation; no invented RTT or wait estimates."""
import gzip
import json
from pathlib import Path
import statistics
import hashlib
import re

def verify_artifacts(directory,required=()):
    directory=Path(directory)
    manifest_path=directory/'artifacts.json'
    if not manifest_path.is_file():raise ValueError('Missing raw artifact manifest: '+str(directory))
    manifest=json.loads(manifest_path.read_text())
    if manifest.get('passed') is not True:raise ValueError('Raw artifacts belong to failed case: '+str(directory))
    for name in required:
        if name not in manifest['files']:raise ValueError('Consumed raw file is not sealed: '+str(directory/name))
    raw_patterns=('server-*.calls.jsonl*','server-*.calls.events.jsonl*','http-raw.jsonl','requests.json','foreground-profiles/*.pstats')
    raw_seen=set()
    for pattern in raw_patterns:
        for path in directory.glob(pattern):
            name=str(path.relative_to(directory))
            canonical=name.removesuffix('.gz')
            if canonical in raw_seen:raise ValueError('Duplicate raw/compressed input: '+canonical)
            raw_seen.add(canonical)
            if name not in manifest['files']:raise ValueError('Matching raw input is unsealed: '+str(path))
    for name,digest in manifest['files'].items():
        path=directory/name
        if not path.resolve().is_relative_to(directory.resolve()):raise ValueError('Artifact path escapes case')
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=digest:
            raise ValueError('Raw artifact hash mismatch: '+str(path))
    return dict(manifest=str(manifest_path),sha256=hashlib.sha256(manifest_path.read_bytes()).hexdigest(),files_checked=len(manifest['files']))

def union_ns(intervals):
    ordered = sorted((a, b) for a, b in intervals if a is not None and b is not None and b >= a)
    if not ordered:
        return 0
    left, right = ordered[0]
    total = 0
    for begin, end in ordered[1:]:
        if begin <= right:
            right = max(right, end)
        else:
            total += right - left
            left, right = begin, end
    return total + right - left

def load_calls(directory):
    calls = []
    paths = sorted(Path(directory).glob('server-*.calls.jsonl*'))
    seen = set()
    for path in paths:
        authoritative_name = path.name.removesuffix('.gz')
        if authoritative_name in seen:
            raise ValueError(f'Duplicate raw/compressed SQL trace: {authoritative_name}')
        seen.add(authoritative_name)
    verify_artifacts(directory)
    for path in paths:
        match=re.fullmatch(r'server-(\d+)\.calls\.jsonl(?:\.gz)?',path.name)
        if not match:raise ValueError('Unexpected driver trace filename: '+path.name)
        generation=int(match.group(1))
        opener = gzip.open if path.suffix == '.gz' else open
        with opener(path, 'rt') as file:
            for line in file:
                if line.strip():
                    row=json.loads(line);row['trace_generation']=generation;row['source_trace']=path.name;calls.append(row)
    return calls

def audit_scope(requests,calls,strict=True):
    """Prove excluded startup per server generation; never use a trial-wide span."""
    lookup={r['request']:r for r in requests};generations={r['server_generation'] for r in requests}
    by_generation={};issues=[];assigned=0;startup=0
    for generation in sorted(generations|{r.get('trace_generation') for r in calls if r.get('trace_generation') is not None}):
        reqs=[r for r in requests if r['server_generation']==generation]
        first=min((r['start_ns'] for r in reqs),default=None)
        last=max((r['end_ns'] for r in reqs),default=None)
        record=dict(server_generation=generation,recorded_http_requests=len(reqs),first_recorded_http_start_ns=first,
            last_recorded_http_end_ns=last,verified_startup_calls=0,assigned_calls=0,unexplained=[])
        for call in [c for c in calls if c.get('trace_generation')==generation]:
            rid=call.get('request')
            if rid in lookup:
                if lookup[rid]['server_generation']!=generation:
                    issue=dict(category='assigned_request_generation_mismatch',request=rid,trace=call['source_trace'])
                    issues.append(issue);record['unexplained'].append(issue)
                else:assigned+=1;record['assigned_calls']+=1
                continue
            begin,end=call.get('driver_start_ns'),call.get('driver_end_ns')
            valid=isinstance(begin,int) and isinstance(end,int) and end>=begin
            if first is not None and valid and end<=first:
                startup+=1;record['verified_startup_calls']+=1;continue
            overlaps=[r for r in reqs if valid and begin<r['end_ns'] and end>r['start_ns']]
            category=('missing_generation_http_envelope' if first is None else 'invalid_driver_interval' if not valid
                else 'overlapping_recorded_http' if overlaps else 'after_last_recorded_http' if begin>=last else 'between_recorded_requests')
            issue=dict(category=category,request=rid,trace=call.get('source_trace'),driver_start_ns=begin,driver_end_ns=end,
                sql_sha256=call.get('sql_sha256'),overlapping_requests=[{'request':r['request'],'phase':r['phase']} for r in overlaps])
            issues.append(issue);record['unexplained'].append(issue)
        by_generation[str(generation)]=record
    if any(c.get('trace_generation') is None for c in calls):issues.append({'category':'missing_trace_generation'})
    result=dict(passed=not issues,assigned_calls=assigned,verified_startup_calls=startup,unexplained=issues,
        by_generation=by_generation,scope='Verified startup/readiness before first recorded HTTP in the same server generation is excluded from request-scoped workload totals; all raw calls retained')
    if strict and issues:raise ValueError('Unassigned SQL not verified as same-generation startup: '+str(issues[:2]))
    return result

def aggregate(requests, calls, phase):
    selected_requests = ([next(row for row in requests if row['phase']=='workflow')]
        if phase=='first_workflow_request' and any(row['phase']=='workflow' for row in requests)
        else [] if phase=='first_workflow_request' else [row for row in requests if row['phase']==phase])
    lookup = {row['request']: row for row in selected_requests}
    selected = [row for row in calls if row.get('request') in lookup]
    protocol = [(r['send_ns'], r['ready_ns']) for r in selected if r.get('send_ns') is not None and r.get('ready_ns') is not None]
    foreground = [r for r in selected if r['role'] == 'foreground']
    background = [r for r in selected if r['role'] == 'background_prefetch']
    result = dict(requests=len(selected_requests), driver_calls=len(selected),
        sql_dispatches=sum(r.get('send_ns') is not None for r in selected),
        command_complete_count=sum(r['command_complete'] for r in selected),
        protocol_cycles=sum(r['ready_count'] for r in selected),
        control_dispatches=sum(bool(r['control']) and r.get('send_ns') is not None for r in selected),
        foreground_dispatches=sum(r.get('send_ns') is not None for r in foreground),
        background_dispatches=sum(r.get('send_ns') is not None for r in background),
        errors=sum(bool(r.get('error')) for r in selected),
        returned_rows=sum(r['returned_rows'] or 0 for r in selected),
        protocol_sum_ms=sum(b-a for a,b in protocol)/1e6, protocol_union_ms=union_ns(protocol)/1e6,
        driver_sum_ms=sum(r['driver_end_ns']-r['driver_start_ns'] for r in selected)/1e6,
        foreground_protocol_sum_ms=sum(r['ready_ns']-r['send_ns'] for r in foreground if r.get('ready_ns') is not None)/1e6,
        foreground_protocol_union_ms=union_ns((r['send_ns'],r['ready_ns']) for r in foreground)/1e6,
        background_protocol_sum_ms=sum(r['ready_ns']-r['send_ns'] for r in background if r.get('ready_ns') is not None)/1e6,
        late_db_calls=sum(r.get('ready_ns') is not None and r['ready_ns'] > lookup[r['request']]['end_ns'] for r in selected),
        http_instrumented_sum_ms=sum(r['http_e2e_ms'] for r in selected_requests),
        pure_foreground_wait_ms=None, consumed_prefetch_bytes=None)
    for label, control in [('control', True), ('data', False)]:
        subset = [r for r in selected if bool(r['control']) is control]
        result[label + '_protocol_sum_ms'] = sum(r['ready_ns']-r['send_ns'] for r in subset if r.get('ready_ns') is not None)/1e6
        result[label + '_command_complete'] = sum(r['command_complete'] for r in subset)
    return result

def dispersion(values):
    values = list(values)
    if not values:
        return dict(n=0, median=None, minimum=None, maximum=None, q1=None, q3=None, stdev=None)
    quartiles = statistics.quantiles(values, n=4, method='inclusive') if len(values)>1 else [values[0]]*3
    return dict(n=len(values), median=statistics.median(values), minimum=min(values), maximum=max(values),
        q1=quartiles[0], q3=quartiles[2], stdev=statistics.stdev(values) if len(values)>1 else 0)
