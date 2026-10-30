#!/usr/bin/env python3
"""Dedicated SQL-only instrumentation validation; contains NO application workload."""
import argparse
import asyncio
import json
import os
from pathlib import Path
import statistics
import threading
import time
from types import SimpleNamespace

import jaclang
from jaclang.data import pgwire
from jaclang.server.serving.app import ServingApp
import driver_probe as probe


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--mode', choices=['validation', 'primary_validation', 'control', 'reference', 'light', 'instrumented', 'primary'], default='validation')
    parser.add_argument('--shape', choices=['scalar', 'text16k', 'json16k', 'multirow128'], default='scalar')
    args = parser.parse_args()
    prefix = 'ttg-protocol-only'
    native_close_under_test = {}
    # Exercise the actual observer dispatch wrapper around a deliberately small
    # synthetic handler, without launching or invoking any application.
    if args.mode in ('validation', 'primary_validation'):
        async def synthetic_dispatch(self, request):
            native_close_under_test['close'](native_close_under_test['context'])
            return 'response-complete'
        ServingApp.dispatch = synthetic_dispatch
    connection = lambda name: pgwire.PgWireConnection(user='ttgperf', host='127.0.0.1', port=args.port,
        database='postgres', application_name=name)
    if args.mode not in ('control', 'reference'):
        probe.install()
    if args.mode not in ('validation', 'primary_validation'):
        c = connection(prefix + '-overhead')
        # Independent statement logging is a validation-only diagnostic.
        # Disable it explicitly for every measured overhead-control session.
        c.run("SET log_statement='none'")
        assert c.run('SHOW log_statement') == [('none',)]
        queries = {'scalar': 'SELECT 17', 'text16k': "SELECT repeat('x',16384)",
            'json16k': "SELECT jsonb_build_object('payload',repeat('j',16384))",
            'multirow128': 'SELECT generate_series(1,128)'}
        query = queries[args.shape] + ' /* ttg_probe_overhead */'
        expected_rows = 128 if args.shape == 'multirow128' else 1
        timings = []
        for index in range(520):
            begin = time.perf_counter_ns()
            result = c.run(query)
            end = time.perf_counter_ns()
            assert len(result) == expected_rows
            if args.shape == 'scalar':
                assert result == [(17,)]
            elif args.shape == 'text16k':
                assert result == [('x' * 16384,)]
            elif args.shape == 'json16k':
                assert json.loads(result[0][0]) == {'payload': 'j' * 16384}
            else:
                assert result == [(i,) for i in range(1,129)]
            if index >= 20:
                timings.append((end - begin) / 1e6)
        c.close()
        primary_rows = list(probe.ROWS) + [probe.expand_boundary(row) for row in probe.BOUNDARIES]
        probe.flush()
        reference = getattr(pgwire, '_perf_boundary_records', [])
        reference = [row for row in reference if 'ttg_probe_overhead' in row[0]]
        intervals = [(row[2] - row[1]) / 1e6 for row in reference[20:]]
        if args.mode == 'primary':
            primary_rows = [r for r in primary_rows if 'ttg_probe_overhead' in r['sql']]
            assert len(primary_rows) == 520 and all(r['data_rows'] == expected_rows and r['command_complete'] == 1
                and r['ready_count'] == 1 for r in primary_rows)
            intervals = [(r['ready_ns'] - r['send_ns']) / 1e6 for r in primary_rows[20:]]
        args.output.write_text(json.dumps(dict(mode=args.mode, warmup=20, n=500,
            ms=timings, median_ms=statistics.median(timings), sql=query, shape=args.shape,
            expected_rows=expected_rows, statement_logging='none', passed=True,
            protocol_reference_ms=intervals,
            protocol_reference_median_ms=statistics.median(intervals) if intervals else None), indent=2) + '\n')
        return

    token = probe.REQUEST.set('protocol-fixture')
    c = connection(prefix)
    expected = []
    def run(sql, rows=0, commands=1, error=False, **params):
        sql += ' /* ttg_probe_fixture */'
        try:
            result = c.run(sql, **params)
            assert not error, 'Expected SQL error'
            assert len(result) == rows, (sql, result)
        except pgwire.PgWireError:
            assert error, sql
        expected.append(dict(sql=sql, rows=rows, commands=commands, error=error))
        return result if not error else None
    run('BEGIN')
    run("SET LOCAL statement_timeout='10s'")
    run('CREATE TEMP TABLE perf_probe (value integer)')
    run('INSERT INTO perf_probe SELECT generate_series(1,5) RETURNING value', rows=5)
    run('SAVEPOINT probe_savepoint')
    run('SELECT value FROM perf_probe ORDER BY value', rows=5)
    run('SELECT nonexistent_column FROM perf_probe', commands=0, error=True)
    run('ROLLBACK TO SAVEPOINT probe_savepoint')
    run('RELEASE SAVEPOINT probe_savepoint')
    run('COMMIT')
    assert run("SELECT repeat('x',16384)", rows=1) == [('x' * 16384,)]
    payload = run("SELECT jsonb_build_object('payload',repeat('j',16384))", rows=1)
    assert json.loads(payload[0][0]) == {'payload': 'j' * 16384}
    assert run('SELECT generate_series(1,128)', rows=128) == [(i,) for i in range(1,129)]
    # Parameter conversion deliberately sleeps BEFORE sendall. It must appear
    # only in driver-call time, not protocol completion wall time.
    old_encode = pgwire._encode_param
    def slow_encode(value):
        time.sleep(.030)
        return old_encode(value)
    pgwire._encode_param = slow_encode
    run('SELECT :payload::text', rows=1, payload='encoding-boundary')
    pgwire._encode_param = old_encode
    boundary = probe.ROWS[-1] if probe.ROWS else probe.expand_boundary(probe.BOUNDARIES[-1])
    assert boundary['send_ns'] - boundary['driver_start_ns'] >= 25_000_000, boundary
    c.close()
    probe.REQUEST.reset(token)

    # Native close and synthetic request completion must remain observable
    # while a prefetch worker is blocked. Late worker SQL is flushed by an
    # explicit post-response drain, retaining its original request ID.
    ready, release = threading.Event(), threading.Event()
    def _prefetch_worker():
        ready.set()
        assert release.wait(5), 'Test release was never signaled'
        late = connection(prefix + '-late')
        assert late.run('SELECT 29 /* ttg_probe_late */') == [(29,)]
        late.close()
    rid = 'gated-late-worker'
    tok = probe.REQUEST.set(rid)
    thread = threading.Thread(target=_prefetch_worker, daemon=True)
    thread.start()
    assert ready.wait(2)
    context = SimpleNamespace(mem=SimpleNamespace(_prefetch_threads=[thread]))
    closed = []
    observed_close = probe.wrap_close(lambda self: closed.append('natural-close'))
    native_close_under_test.update(close=observed_close, context=context)
    request = SimpleNamespace(headers={'X-TTG-Perf-Request': rid}, url=SimpleNamespace(path='/synthetic-protocol-fixture'))
    begin = time.perf_counter_ns()
    assert asyncio.run(ServingApp.dispatch(object.__new__(ServingApp), request)) == 'response-complete'
    request_completed = time.perf_counter_ns()
    assert closed == ['natural-close'] and thread.is_alive() and not release.is_set()
    assert request_completed - begin < 1_000_000_000
    probe.flush()
    release.set()
    drained = probe.drain_request(rid)
    assert drained['pending'] == 0
    probe.REQUEST.reset(tok)
    calls = [json.loads(line) for line in probe.OUT.read_text().splitlines()]
    fixture = [r for r in calls if r['request'] == 'protocol-fixture']
    assert len(fixture) == len(expected), (len(fixture), len(expected))
    for actual, wanted in zip(fixture, expected):
        assert actual['sql'] == wanted['sql']
        assert actual['sync_sent'] == actual['ready_count'] == 1
        assert actual['outgoing_types'] == list('PBDES')
        assert actual['command_complete'] == wanted['commands']
        assert actual['data_rows'] == wanted['rows']
        assert bool(actual['error']) == wanted['error']
        assert actual['driver_start_ns'] <= actual['send_ns'] <= actual['ready_ns'] <= actual['driver_end_ns']
        if actual['received_bytes'] is not None:
            assert actual['received_bytes'] >= actual['data_row_payload_bytes']
    late = [r for r in calls if r['request'] == rid and 'ttg_probe_late' in r['sql']]
    assert len(late) == 1 and late[0]['data_rows'] == 1
    assert late[0]['role'] == 'background_prefetch' and late[0]['send_ns'] > request_completed
    args.output.write_text(json.dumps(dict(passed=True, workload='dedicated SQL protocol fixture; not an app',
        fixture_calls=len(fixture), protocol_cycles=sum(r['ready_count'] for r in fixture),
        command_complete=sum(r['command_complete'] for r in fixture),
        data_rows=sum(r['data_rows'] for r in fixture), errors=sum(bool(r['error']) for r in fixture),
        encoding_excluded_ms=(boundary['send_ns'] - boundary['driver_start_ns']) / 1e6,
        native_close_did_not_wait=True, late_worker_rows_retained=True, expected=expected), indent=2) + '\n')
    probe.flush()

if __name__ == '__main__':
    main()
