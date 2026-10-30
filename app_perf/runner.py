#!/usr/bin/env python3
"""Fail-closed all30 correctness preflight and main-authorized formal matrix."""
import argparse
import json
import os
from pathlib import Path
import shutil
import sys
import time

import gate

def write(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')

def ref(path):
    return {'path': str(path.resolve()), 'sha256': gate.sha(path)}

def source_check(runtime, overlay, suite):
    gate.verify_snapshot(runtime, 'runtime')
    overlay_data = gate.verify_snapshot(overlay, 'runtime_overlay')
    gate.require(overlay_data.get('base_runtime_manifest_sha256') == gate.sha(runtime), 'Overlay base mismatch')
    gate.verify_snapshot(suite, 'suite', check_origins=True)

def harness_sources():
    own = Path(__file__).resolve().parent
    names = ('runner.py', 'workloads.py', 'driver_probe.py', 'perf_serve.py', 'control_server.py',
             'owned_postgres.py', 'sql_admin.py', 'runtime.sh', 'gate.py', 'identity.py', 'freeze.py')
    sources={str(own / name): gate.sha(own / name) for name in names}
    schema=gate.EVIDENCE/'set-field-schema-v1.json'
    sources[str(schema)]=gate.sha(schema)
    return sources

def execute_preflight(args):
    # All acceptance checks occur BEFORE importing application modules, creating
    # output directories, allocating ports or starting any application process.
    for name in ('runtime', 'overlay', 'suite', 'acceptance', 'output'):
        gate.require(getattr(args, name) is not None, f'Preflight requires --{name}')
    runtime, overlay, suite, acceptance = [getattr(args, n).resolve() for n in ('runtime', 'overlay', 'suite', 'acceptance')]
    source_check(runtime, overlay, suite)
    gate.verify_acceptance(gate.read(acceptance), gate.sha(suite), acceptance.parent, gate.read(suite))
    from owned_postgres import OwnedPostgres
    from workloads import configure, trial
    native, evaluate, readers = configure(suite)
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    result = dict(schema_version=1, purpose='Correctness preflight only; no application performance claims',
        runtime_manifest_sha256=gate.sha(runtime), overlay_manifest_sha256=gate.sha(overlay),
        suite_manifest_sha256=gate.sha(suite), acceptance_manifest_sha256=gate.sha(acceptance), cases=[],
        status='running', harness_sources_before=harness_sources())
    write(out / 'preflight.json', result)
    kind_path = gate.EVIDENCE / 'census-validation-v2/census.json'
    kinds = gate.read(kind_path)
    result['kind_validation'] = ref(kind_path)
    def check():
        source_check(runtime, overlay, suite)
        gate.require(harness_sources() == result['harness_sources_before'], 'Preflight harness mutated; start a NEW run')
    try:
        with OwnedPostgres(out / 'postgres') as postgres:
            for app in gate.APPS:
                baseline = None
                for policy in gate.POLICIES:
                    result['active_case'] = dict(app=app, policy=policy)
                    check()
                    summary = trial(app, policy, out / f'{app}-{policy}', postgres, native, evaluate, readers,
                        overlay.parent, 'preflight_diagnostic', expected=baseline, kind_validation=kinds,
                        validate_after=check)
                    baseline = baseline or summary
                    case = {key: summary[key] for key in ('app', 'policy', 'seed', 'passed', 'fixture_sha256', 'actions_sha256', 'outputs_sha256')}
                    case['evidence'] = ref(out / f'{app}-{policy}/summary.json')
                    result['cases'].append(case)
                    write(out / 'preflight.json', result)
                    print(f'Correctness {len(result["cases"])}/120: {app}/{policy}', flush=True)
        result['status'] = 'complete'
        result['harness_sources_after'] = harness_sources()
        write(out / 'preflight.json', result)
    except Exception as error:
        result.update(status='invalidated_or_failed', error=f'{type(error).__name__}: {error}',
            harness_sources_after=harness_sources())
        write(out / 'preflight.json', result)
        raise
    gate.verify_preflight(result, gate.sha(runtime), gate.sha(suite), out, gate.sha(overlay))
    print(str(out / 'preflight.json'))

def execute_formal(args):
    # Fixed path only. There is intentionally no authorization-path CLI flag,
    # bypass environment variable, approval generator, or allow-incomplete mode.
    release = gate.validate_formal_release()
    gate.require(args.output is not None, 'Formal mode requires --output')
    plan = gate.read(release.experiment_plan)
    gate.require(plan.get('quiet_window_confirmed') is True, 'Quiet-window coordination is incomplete')
    from owned_postgres import OwnedPostgres
    from workloads import configure, trial
    native, evaluate, readers = configure(release.suite_manifest)
    preflight = gate.read(release.preflight_manifest)
    expected = {(r['app'], r['policy']): r for r in preflight['cases']}
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    write(out / 'experiment.json', dict(status='running', authorization_sha256=release.authorization_sha256,
        artifacts={name: ref(getattr(release, name)) for name in (
            'runtime_manifest', 'overlay_manifest', 'suite_manifest', 'acceptance_manifest', 'preflight_manifest', 'instrument_manifest', 'experiment_plan')},
        plan=plan, started_ns=time.time_ns()))
    rows = []
    try:
        with OwnedPostgres(out / 'postgres') as postgres:
            for app_index, app in enumerate(gate.APPS):
                for repeat in range(plan['measured_trials'] + 1):
                    # One excluded fresh-state workflow warmup, then >=3
                    # independent measured fresh-state workflow repetitions.
                    shift = (repeat + app_index) % 4
                    order = gate.POLICIES[shift:] + gate.POLICIES[:shift]
                    for policy in order:
                        modes = ['primary']
                        for mode in modes:
                            gate.revalidate(release)
                            gate.require(shutil.disk_usage(out).free >= 4 * 1024**3, 'Storage guard: <4 GiB free; experiment stopped')
                            directory = out / f'{app}-{policy}-r{repeat}-{mode}'
                            summary = trial(app, policy, directory, postgres, native, evaluate, readers,
                                release.overlay_manifest.parent if mode == 'primary' else release.runtime_manifest.parent,
                                mode, seed=42, scale=plan.get('original_scale', 'smoke'),
                                expected=expected[(app, policy)], validate_after=lambda: gate.revalidate(release))
                            summary.update(repeat=repeat, measured=repeat > 0, order=list(order),
                                mode_order=modes, directory=str(directory))
                            rows.append(summary)
                            write(out / 'trials.json', {'rows': rows, 'status': 'running'})
                            print(f'{app} {policy} r{repeat} {mode}: correctness passed', flush=True)
            # Clean HTTP control data has its own explicitly scoped subset and
            # sample counts. No automatic duplication of the all30 DB matrix.
            for app_index, app in enumerate(plan.get('clean_e2e_apps', [])):
                for repeat in range(plan.get('clean_e2e_trials', 3) + 1):
                    shift = (repeat + app_index) % 4
                    order = gate.POLICIES[shift:] + gate.POLICIES[:shift]
                    for policy in order:
                        gate.revalidate(release)
                        directory = out / f'{app}-{policy}-r{repeat}-uninstrumented_e2e'
                        summary = trial(app, policy, directory, postgres, native, evaluate, readers,
                            release.runtime_manifest.parent, 'uninstrumented_e2e',
                            expected=expected[(app, policy)], validate_after=lambda: gate.revalidate(release))
                        summary.update(repeat=repeat, measured=repeat > 0, order=list(order), directory=str(directory))
                        rows.append(summary)
                        write(out / 'trials.json', {'rows': rows, 'status': 'running'})
        gate.revalidate(release)
        write(out / 'trials.json', {'rows': rows, 'status': 'complete'})
    except Exception as error:
        write(out / 'trials.json', {'rows': rows, 'status': 'invalidated_or_failed',
            'error': f'{type(error).__name__}: {error}', 'resume_policy': 'Do not resume; review and authorize a NEW experiment'})
        raise

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['check-release', 'preflight', 'formal'])
    parser.add_argument('--runtime', type=Path, help='Clean base snapshot.json (preflight only)')
    parser.add_argument('--overlay', type=Path, help='Primary effective overlay snapshot.json (preflight only)')
    parser.add_argument('--suite', type=Path, help='Final coherent suite snapshot.json (preflight only)')
    parser.add_argument('--acceptance', type=Path, help='All30 none+ttg accepted evidence index (preflight only)')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    try:
        if args.mode == 'formal':
            execute_formal(args)
        elif args.mode == 'preflight':
            execute_preflight(args)
        else:
            release = gate.validate_formal_release()
            print('Approved exact release: ' + release.authorization_sha256)
    except gate.GateError as error:
        print('REFUSED: ' + str(error), file=sys.stderr)
        raise SystemExit(2)

if __name__ == '__main__':
    main()
