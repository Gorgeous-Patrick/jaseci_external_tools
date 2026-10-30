#!/usr/bin/env python3
"""Run allowed dedicated SQL checks with independent PostgreSQL CSV logging."""
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import statistics
import subprocess
from owned_postgres import OwnedPostgres

OWN = Path(__file__).resolve().parent

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--shapes', nargs='+', choices=['scalar', 'text16k', 'json16k', 'multirow128'], default=['scalar'])
    parser.add_argument('--census-only', action='store_true', help='Dedicated native two-node/one-edge encoding fixture, no app')
    parser.add_argument('--admin-only', action='store_true', help='Synthetic owned admin lifecycle, no app')
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    if args.admin_only:
        from admin_probe import validate
        validate(out)
        return
    if args.census_only:
        with OwnedPostgres(out / 'postgres') as postgres:
            with (out / 'census.log').open('w') as log:
                subprocess.run(['bash', str(OWN / 'runtime.sh'), str(OWN / 'census_probe.py'), '--port', str(postgres.port),
                    '--output', str(out / 'census.json')], stdout=log, stderr=subprocess.STDOUT, check=True)
        print((out / 'census.json').read_text())
        return
    summaries = []
    with OwnedPostgres(out / 'postgres', statement_logging=True) as postgres:
        jobs = [('validation', 'validation'), ('validation', 'primary_validation')]
        for order in [('control', 'primary', 'light', 'instrumented'), ('light', 'instrumented', 'control', 'primary'), ('instrumented', 'primary', 'control', 'light')]:
            jobs.extend(('outer', mode) for mode in order)
        for order in [('reference', 'primary', 'light', 'instrumented'), ('light', 'instrumented', 'reference', 'primary'), ('instrumented', 'primary', 'reference', 'light')]:
            jobs.extend(('protocol', mode) for mode in order)
        expanded = [(group, mode, shape) for group, mode in jobs
                    for shape in (['scalar'] if group == 'validation' else args.shapes)]
        for index, (group, mode, shape) in enumerate(expanded):
            name = f'{index}-{group}-{mode}-{shape}'
            summary = out / f'{name}.json'
            environment = {**os.environ, 'TTG_PERF_TRACE': str(out / f'{name}.calls.jsonl')}
            environment['TTG_PERF_DETAIL'] = 'light' if mode == 'light' else 'detailed'
            if group == 'protocol':
                environment['TTG_RUNTIME_SOURCE'] = str(OWN / 'runtime-protocol-reference-v2-5f94eb62d')
            if mode in ('primary', 'primary_validation'):
                environment.update(TTG_RUNTIME_SOURCE=str(OWN / 'runtime-primary-boundary-5f94eb62d-v1'),
                    TTG_PERF_DRIVER='0', TTG_PERF_DETAIL='light')
            with (out / f'{name}.log').open('w') as log:
                subprocess.run(['bash', str(OWN / 'runtime.sh'), str(OWN / 'sql_probe.py'), '--port', str(postgres.port),
                    '--output', str(summary), '--mode', mode, '--shape', shape], env=environment, stdout=log, stderr=subprocess.STDOUT, check=True)
            value = json.loads(summary.read_text())
            value['group'] = group
            summaries.append(value)
    # Collector is stopped and flushed before independent source comparison.
    server_rows = []
    for path in (out / 'postgres/data/logs').glob('*.csv'):
        with path.open(newline='') as file:
            server_rows.extend(csv.reader(file))
    statements = [row[13] for row in server_rows if len(row) > 13 and 'execute <unnamed>:' in row[13]
                  and 'ttg_probe_fixture' in row[13]]
    # Error statement did not execute. The independent server ERROR record is
    # counted separately from successful extended-protocol execute log entries.
    errors = [row for row in server_rows if len(row) > 19 and row[11] == 'ERROR' and 'ttg_probe_fixture' in row[19]]
    assert len(statements) == 2 * (summaries[0]['fixture_calls'] - summaries[0]['errors']), len(statements)
    assert len(errors) == 2 * summaries[0]['errors'], len(errors)
    by_shape = {}
    for shape in args.shapes:
        selected = [s for s in summaries if s.get('shape') == shape]
        controls = [s['median_ms'] for s in selected if s.get('mode') == 'control' and s['group'] == 'outer']
        options = {}
        for mode in ('primary', 'light', 'instrumented'):
            outer = [s['median_ms'] for s in selected if s.get('mode') == mode and s['group'] == 'outer']
            protocol = [s['protocol_reference_median_ms'] for s in selected if s.get('mode') == mode and s['group'] == 'protocol']
            reference = [s['protocol_reference_median_ms'] for s in selected if s.get('mode') == 'reference']
            assert all(x is not None for x in protocol + reference)
            options[mode] = dict(outer_trial_medians_ms=outer,
                outer_median_ms=statistics.median(outer),
                outer_added_ms=statistics.median(outer) - statistics.median(controls),
                outer_ratio=statistics.median(outer) / statistics.median(controls),
                protocol_trial_medians_ms=protocol, reference_trial_medians_ms=reference,
                protocol_ratio=statistics.median(protocol) / statistics.median(reference),
                protocol_added_ms=statistics.median(protocol) - statistics.median(reference))
        by_shape[shape] = dict(control_median_ms=statistics.median(controls), control_trial_medians_ms=controls, options=options)
    result = dict(protocol_validation_passed=True, independent_server_validation_passed=True,
        server_successful_execute_logs=len(statements), server_error_logs=len(errors),
        overhead_control_completed=True, by_shape=by_shape,
        measured_sessions_statement_logging='none; verified by SHOW in each session',
        overhead_control_passed=False,
        note='SQL-only probe. Main review must assess overhead before release; no application performance results.')
    (out / 'validation-summary.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))

if __name__ == '__main__':
    main()
