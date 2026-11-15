"""Measured inflight-protocol overlap, not inferred DB execution/CPU parallelism."""
from collections import defaultdict

BACKGROUND_ROLES = {'background_prefetch', 'background_continuation'}


def executor_evidence(calls, requested_executor, parent_process_pid):
    """A no-op cell is unobserved, and a process-to-thread fallback is invalid."""
    background = [c for c in calls if c['role'] in BACKGROUND_ROLES and c.get('send_ns') is not None]
    for call in background:
        if not isinstance(call.get('backend_pid'), int) or call['backend_pid'] <= 0:
            raise ValueError('Actual SQL backend PID required')
        if requested_executor == 'process':
            if call.get('actual_executor') != 'process' or call.get('client_process_pid') == parent_process_pid:
                raise ValueError('Process policy fell back or lacks an actual child SQL process')
            if not isinstance(call.get('client_process_pid'), int) or call['client_process_pid'] <= 0:
                raise ValueError('Missing child SQL process PID')
        elif requested_executor == 'thread':
            if call.get('actual_executor') != 'thread' or call.get('client_process_pid') != parent_process_pid:
                raise ValueError('Thread policy executor attribution mismatch')
        else:
            raise ValueError('Unexpected background executor mode')
    return dict(requested_executor=requested_executor, sql_execution_observed=bool(background),
        background_dispatches=len(background), actual_backend_pids=sorted({c['backend_pid'] for c in background}),
        actual_client_process_pids=sorted({c['client_process_pid'] for c in background}),
        interpretation='Actual child SQL dispatch evidence' if background and requested_executor=='process'
            else 'Actual same-process background SQL dispatch evidence' if background
            else 'No background SQL observed; no executor-concurrency claim')


def interval(begin, end):
    if not isinstance(begin, int) or not isinstance(end, int) or end < begin:
        raise ValueError('Invalid/incomplete measured interval')
    return begin, end


def union_ns(intervals):
    ordered = sorted(interval(a, b) for a, b in intervals)
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


def intersection(a, b):
    left, right = max(a[0], b[0]), min(a[1], b[1])
    return (left, right) if right > left else None


def concurrency(calls, foreground_work=()):
    """Require real backend/process IDs and a common host-clock domain.

    Calls need origin_request_id even if emitted after HTTP completion. Request
    IDs are scoped by trial and server generation. A worker thread's existence
    or foreground HTTP envelope alone is not considered overlap evidence.
    """
    groups = defaultdict(list)
    dispatched = []
    for call in calls:
        if call.get('send_ns') is None:
            continue  # driver-only failure before dispatch, retained in raw data
        interval(call['send_ns'], call['ready_ns'])
        for name in ('backend_pid', 'client_process_pid'):
            if not isinstance(call.get(name), int) or call[name] <= 0:
                raise ValueError('Missing actual ' + name)
        if call['role'] not in BACKGROUND_ROLES | {'foreground'}:
            raise ValueError('Unrecognized SQL role')
        key = tuple(call[name] for name in ('trial_id', 'server_generation',
                    'origin_request_id', 'clock_domain'))
        if not key[-1] or not key[-2]:
            raise ValueError('Missing request/clock attribution')
        groups[key].append(call)
        dispatched.append(call)
    rows = []
    for key, group in groups.items():
        foreground = [c for c in group if c['role'] == 'foreground']
        background = [c for c in group if c['role'] in BACKGROUND_ROLES]
        overlaps, same_backend, process_overlaps, work_overlaps = [], [], [], []
        pairs = []
        for bg in background:
            bg_interval = (bg['send_ns'], bg['ready_ns'])
            for fg in foreground:
                overlap = intersection(bg_interval, (fg['send_ns'], fg['ready_ns']))
                if overlap is None:
                    continue
                if bg['backend_pid'] == fg['backend_pid']:
                    same_backend.append(overlap)
                    continue
                overlaps.append(overlap)
                separate_process = bg['client_process_pid'] != fg['client_process_pid']
                if separate_process:
                    process_overlaps.append(overlap)
                pairs.append(dict(background_backend_pid=bg['backend_pid'],
                    foreground_backend_pid=fg['backend_pid'],
                    background_client_pid=bg['client_process_pid'],
                    foreground_client_pid=fg['client_process_pid'],
                    overlap_start_ns=overlap[0], overlap_end_ns=overlap[1],
                    separate_client_process=separate_process))
            for work in foreground_work:
                work_key = tuple(work[name] for name in ('trial_id', 'server_generation',
                    'origin_request_id', 'clock_domain'))
                if work_key != key:
                    continue
                if work['kind'] != 'foreground_ability_work':
                    raise ValueError('HTTP/wait envelope is not foreground work proof')
                overlap = intersection(bg_interval, interval(work['start_ns'], work['end_ns']))
                if overlap:
                    work_overlaps.append(overlap)
        all_intervals = [(c['send_ns'], c['ready_ns']) for c in group]
        rows.append(dict(trial_id=key[0], server_generation=key[1], origin_request_id=key[2],
            clock_domain=key[3], foreground_dispatches=len(foreground),
            background_dispatches=len(background), protocol_sum_ns=sum(b-a for a,b in all_intervals),
            protocol_union_ns=union_ns(all_intervals), distinct_backend_overlap_ns=union_ns(overlaps),
            separate_process_distinct_backend_overlap_ns=union_ns(process_overlaps),
            same_backend_overlapping_intervals_ns=union_ns(same_backend),
            background_during_foreground_work_ns=union_ns(work_overlaps), actual_pairs=pairs))
    cross_request_pairs = []
    cross_intervals = defaultdict(list)
    for bg in [c for c in dispatched if c['role'] in BACKGROUND_ROLES]:
        for fg in [c for c in dispatched if c['role'] == 'foreground']:
            if any(bg[k] != fg[k] for k in ('trial_id', 'server_generation', 'clock_domain')):
                continue
            if bg['origin_request_id'] == fg['origin_request_id'] or bg['backend_pid'] == fg['backend_pid']:
                continue
            overlap = intersection((bg['send_ns'], bg['ready_ns']), (fg['send_ns'], fg['ready_ns']))
            if overlap:
                cross_intervals[bg['trial_id']].append(overlap)
                cross_request_pairs.append(dict(background_origin=bg['origin_request_id'],
                    foreground_origin=fg['origin_request_id'], background_backend_pid=bg['backend_pid'],
                    foreground_backend_pid=fg['backend_pid'], overlap_start_ns=overlap[0], overlap_end_ns=overlap[1]))
    return dict(requests=rows, cross_request_pairs=cross_request_pairs,
        cross_request_distinct_backend_overlap_ns=sum(union_ns(v) for v in cross_intervals.values()),
        definition='Overlap of client send-to-Z protocol intervals on actual distinct PostgreSQL backends; includes decoding/progress and is not proof of simultaneous server CPU execution',
        unknown=['pure_foreground_blocked_wait', 'server_cpu_parallelism'])
