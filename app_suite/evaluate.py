#!/usr/bin/env python3
"""Evaluate new full applications with native walkers, domain oracles and browsers."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from native import IsolatedPostgres, NativeServer, SUITE, WORKSPACE, corpus, free_port, write_json, runtime_identity, acceptance_sources
from browser import verify_browser, verify_browser_persistence


def issue_desk(server, token, seed, directory):
    """Independent expected state advances only after accepted domain actions."""
    steps = []

    def call(name, body=None, accepted=True):
        result = server.walker(name, body or {}, token)[0]
        if name not in ('ProjectBoard',):
            assert result['ok'] is accepted, f'{name}: expected acceptance={accepted}: {result}'
        steps.append({'walker': name, 'input': body or {}, 'expected_accepted': accepted,
                      'actual': result, 'passed': True})
        write_json(directory / 'native-steps.json', steps)
        return result

    call('Seed', {'seed': seed})
    board = call('ProjectBoard')
    assert len(board['projects']) == 1 and board['projects'][0]['name'] == 'TTG Runtime'
    assert sorted(row['name'] for row in board['engineers']) == ['Avery', 'Morgan']
    issues = {row['title']: row for row in board['issues']}
    assert set(issues) == {'Implement parser fix', 'Ship runtime release'}
    parser = issues['Implement parser fix']['id']
    release = issues['Ship runtime release']['id']
    assert issues['Implement parser fix']['priority'] == 1 + seed % 3
    assert [row['name'] for row in issues['Implement parser fix']['assignees']] == ['Avery']
    assert [row['id'] for row in issues['Ship runtime release']['blockers']] == [parser]
    assert issues['Implement parser fix']['comments'][0]['sequence'] == 1
    call('Seed', {'seed': seed})
    assert call('ProjectBoard') == board, 'Seed must be idempotent'
    project = board['projects'][0]['id']
    morgan = next(row['id'] for row in board['engineers'] if row['name'] == 'Morgan')
    call('CreateIssue', {'project_id': project, 'title': ' ', 'priority': 3}, False)
    call('CreateIssue', {'project_id': project, 'title': 'Invalid priority', 'priority': 6}, False)
    created = call('CreateIssue', {'project_id': project, 'title': 'Review release checklist', 'priority': 2})['issue']
    checklist = created['id']
    assert created['title'] == 'Review release checklist' and created['status'] == 'open'
    call('BlockIssue', {'issue_id': checklist, 'blocker_id': release})
    call('BlockIssue', {'issue_id': checklist, 'blocker_id': release})
    call('CloseIssue', {'issue_id': checklist}, False)
    call('BlockIssue', {'issue_id': parser, 'blocker_id': checklist}, False)
    call('BlockIssue', {'issue_id': checklist, 'blocker_id': checklist}, False)
    call('AssignIssue', {'issue_id': checklist, 'engineer_id': morgan})
    call('AssignIssue', {'issue_id': checklist, 'engineer_id': morgan})
    call('CommentIssue', {'issue_id': checklist, 'body': 'Review dependency handling'})
    call('CommentIssue', {'issue_id': checklist, 'body': 'Verify release notes'})
    call('CommentIssue', {'issue_id': checklist, 'body': ' '}, False)
    call('CloseIssue', {'issue_id': release}, False)
    call('CloseIssue', {'issue_id': parser})
    call('CloseIssue', {'issue_id': release})
    call('CloseIssue', {'issue_id': checklist})
    call('ReopenIssue', {'issue_id': parser}, False)
    call('ReopenIssue', {'issue_id': checklist})
    call('ReopenIssue', {'issue_id': release})
    call('ReopenIssue', {'issue_id': parser})
    final = call('ProjectBoard')
    check = next(row for row in final['issues'] if row['id'] == checklist)
    assert all(row['status'] == 'open' for row in final['issues'])
    assert [row['id'] for row in check['assignees']] == [morgan]
    assert [row['id'] for row in check['blockers']] == [release]
    assert [(row['sequence'], row['body']) for row in check['comments']] == [
        (1, 'Review dependency handling'), (2, 'Verify release notes')]
    # A second actual authenticated user has no project and cannot mutate this one.
    password = 'isolated-suite-seed-password'
    server.post('/user/register', {'identities': [{'type': 'username', 'value': 'other_user'}],
                                  'credential': {'type': 'password', 'password': password}})
    other = server.post('/user/login', {'identity': {'type': 'username', 'value': 'other_user'},
                                       'credential': {'type': 'password', 'password': password}})['token']
    assert server.walker('ProjectBoard', {}, other)[0]['issues'] == []
    assert server.walker('CloseIssue', {'issue_id': checklist}, other)[0]['ok'] is False
    assert call('ProjectBoard') == final, 'Unauthorized action changed the project'
    return {'native_steps': len(steps), 'expected_board': final, 'read_walker': 'ProjectBoard',
            'permission_check': 'passed'}


from scenarios import approval_desk, stock_room, clinic_queue, course_path, library_loans, event_seats, help_queue

SCENARIOS = {'issue_desk': issue_desk, 'approval_desk': approval_desk, 'stock_room': stock_room, 'clinic_queue': clinic_queue, 'course_path': course_path, 'library_loans': library_loans, 'event_seats': event_seats, 'help_queue': help_queue}
from additional_scenarios import SCENARIOS as ADDITIONAL_SCENARIOS
SCENARIOS.update(ADDITIONAL_SCENARIOS)


def run(app, directory, pg_port, seed, policy, browser):
    directory.mkdir()
    source = SUITE / 'apps' / app
    for path in source.glob('*.jac'):
        shutil.copyfile(path, directory / path.name)
    (directory / 'jac.toml').write_text(f'''[project]
name = "{app}"
entry-point = "server.jac"
[run]
topology_index = true
prefetching = "{policy}"
prefetch_limit = 256
cross_root_resolve = true
async_prefetch = "thread"
prefetch_workers = 2
[serve]
profile = false
[scale.jwt]
secret = "isolated-ttg-suite-development-secret"
algorithm = "HS256"
exp_delta_days = 1
''')
    # A distinct database isolates each application even inside this owned cluster.
    admin = directory / 'create_db.jac'
    admin.write_text('import from jaclang.data.pgwire { PgWireConnection }\nwith entry {\n'
                     f' c = PgWireConnection(user="ttgsuite", host="127.0.0.1", port={pg_port}, database="postgres");\n'
                     f' c.run("CREATE DATABASE suite_{app}"); c.close();\n}}\n')
    with (directory / 'database.log').open('w') as log:
        subprocess.run(['bash', str(SUITE / 'runtime.sh'), '-m', 'jaclang', 'run', str(admin)],
                       cwd=directory, stdout=log, stderr=subprocess.STDOUT, check=True)
    url = f'postgresql://ttgsuite@127.0.0.1:{pg_port}/suite_{app}'
    write_json(directory / 'connection.json', {'database_url': url})
    backend = NativeServer(directory, url, free_port())
    summary = {'app': app, 'seed': seed, 'policy': policy, 'status': 'failed',
               'acceptance_source_sha256': acceptance_sources(),
               'source_sha256': {str(path.relative_to(SUITE)): hashlib.sha256(path.read_bytes()).hexdigest()
                                  for path in source.glob('*.jac')},
               'native': 'pending', 'restart_persistence': 'pending', 'browser': 'pending',
               'db_call_ms': None, 'sql_count': None, 'performance_claim': False}
    try:
        backend.start()
        password = 'isolated-suite-seed-password'
        backend.post('/user/register', {'identities': [{'type': 'username', 'value': 'user_0000'}],
                                        'credential': {'type': 'password', 'password': password}})
        token = backend.post('/user/login', {'identity': {'type': 'username', 'value': 'user_0000'},
                                           'credential': {'type': 'password', 'password': password}})['token']
        scenario = SCENARIOS[app](backend, token, seed, directory)
        summary['native'] = 'passed'
        summary['native_steps'] = scenario['native_steps']
        summary['permission_check'] = scenario['permission_check']
        write_json(directory / 'expected-state.json', scenario['expected_board'])
        backend.stop()
        backend.start()
        actual = backend.walker(scenario['read_walker'], {}, token)[0]
        assert actual == scenario['expected_board'], 'Native state changed across a server restart'
        summary['restart_persistence'] = 'passed'
        summary['status'] = 'native_passed'
        if browser:
            summary['browser_result'] = verify_browser(app, backend, directory)
            summary['browser'] = 'passed'
            backend.stop()
            backend.start()
            verify_browser_persistence(app, backend, token, summary['browser_result'])
            summary['browser_mutations_after_restart'] = 'passed'
            summary['status'] = 'verified'
    except Exception as error:
        summary['status'] = 'failed'
        summary['error'] = f'{type(error).__name__}: {error}'
        raise
    finally:
        backend.stop()
        write_json(directory / 'summary.json', summary)
        write_json(directory / 'requests.json', backend.requests)
        print(json.dumps(summary), flush=True)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apps', nargs='+', choices=SCENARIOS, default=list(SCENARIOS))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--policy', choices=['none', 'ttg'], default='none')
    parser.add_argument('--browser', action='store_true')
    parser.add_argument('--runtime-source', type=Path, help='Pinned runtime source root; overrides TTG_RUNTIME_SOURCE')
    args = parser.parse_args()
    if args.runtime_source:
        os.environ['TTG_RUNTIME_SOURCE'] = str(args.runtime_source.resolve())
    args.output = args.output.resolve()
    args.output.mkdir(parents=True, exist_ok=False)
    write_json(args.output / 'manifest.json', {'runtime': runtime_identity(),
                                               'suite_revision': corpus.revision(SUITE),
                                               'seed': args.seed, 'policy': args.policy,
                                               'suite_source_sha256': {str(path.relative_to(SUITE)): hashlib.sha256(path.read_bytes()).hexdigest()
                                                                       for path in SUITE.rglob('*') if path.is_file() and path.suffix in
                                                                       ('.py', '.jac', '.js', '.mjs', '.html', '.css', '.sh')}})
    results = []
    with IsolatedPostgres(args.output / 'postgres', free_port()) as postgres:
        for app in args.apps:
            try:
                results.append(run(app, args.output / app, postgres.port, args.seed, args.policy, args.browser))
            except Exception as error:
                print(f'{app}: {type(error).__name__}: {error}', file=sys.stderr)
                path = args.output / app / 'summary.json'
                results.append(json.loads(path.read_text()) if path.exists() else {'app': app, 'status': 'failed', 'error': str(error)})
            write_json(args.output / 'index.json', results)
    if any(row['status'] == 'failed' for row in results):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
