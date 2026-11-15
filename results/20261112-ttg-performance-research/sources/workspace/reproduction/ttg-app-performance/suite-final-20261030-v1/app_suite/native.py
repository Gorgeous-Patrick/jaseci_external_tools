#!/usr/bin/env python3
"""Reproduce original-four corpus import and replay on an isolated native Jac DB."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import os
import re
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

SUITE = Path(__file__).resolve().parent
EXTERNAL = SUITE.parent
WORKSPACE = EXTERNAL.parent
sys.path.insert(0, str(EXTERNAL / 'datasets' / 'ttg'))
import build as corpus

SOURCES = {
    'linked_list': (EXTERNAL / 'linked_list', ['main.jac']),
    'littlex': (EXTERNAL / 'littlex5', ['server.jac']),
    'jacord': (WORKSPACE / 'Jacord', ['server.jac', 'server.impl.jac']),
    'jdrive': (WORKSPACE / 'JDrive', ['server.jac', 'server.impl.jac']),
}
TYPES = {
    'linked_list': (['Item'], ['Next']),
    'littlex': (['Profile', 'Tweet'], ['Follow', 'Post']),
    'jacord': (['User', 'Workspace', 'Channel', 'Message'],
               ['Contains', 'HasChannel', 'Posted', 'ReplyTo', 'AuthoredBy', 'Member']),
    'jdrive': (['Drive', 'Folder', 'File'], ['Contains']),
}


def runtime_identity():
    source = Path(os.environ.get('TTG_RUNTIME_SOURCE', WORKSPACE / 'jac-ttg')).resolve()
    snapshot = source / 'snapshot.json'
    if snapshot.exists():
        return {'path': str(source), 'snapshot_sha256': hashlib.sha256(snapshot.read_bytes()).hexdigest(),
                'snapshot': json.loads(snapshot.read_text())}
    revision = corpus.revision(source)
    revision['source_mode'] = 'Live shared checkout; source may change between server generations'
    revision['local_runtime_sha256'] = {
        str(path.relative_to(source)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in (source / 'jac' / 'jaclang').rglob('*') if path.is_file() and path.suffix in ('.jac', '.py')
        and not any(part in ('.jac', '__pycache__', 'node_modules') for part in path.parts)}
    return revision


def acceptance_sources():
    """Pin shared UI, transport and correctness-oracle versions for acceptance."""
    names = ['native.py', 'native_seed.py', 'evaluate.py', 'scenarios.py', 'additional_scenarios.py',
             'browser.py', 'browser.mjs', 'additional_browser.mjs', 'ui_server.py', 'serve.py', 'runtime.sh']
    paths = [SUITE / name for name in names] + list((SUITE / 'web').glob('*'))
    return {str(path.relative_to(SUITE)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in paths if path.is_file()}


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n')


def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


class IsolatedPostgres:
    def __init__(self, directory, port):
        self.directory = directory
        self.port = port
        self.bin = Path(os.environ.get('JAC_PG_DIST', '/home/baichuan/.cache/jac/pg/dist/linux-amd64-18.6.0')) / 'bin'
        self.started = False

    def __enter__(self):
        self.directory.mkdir()
        with (self.directory / 'init.log').open('w') as log:
            subprocess.run([str(self.bin / 'initdb'), '-D', str(self.directory / 'data'),
                            '-U', 'ttgsuite', '-A', 'trust', '--no-locale', '--encoding=UTF8'],
                           stdout=log, stderr=subprocess.STDOUT, check=True)
        subprocess.run([str(self.bin / 'pg_ctl'), '-D', str(self.directory / 'data'),
                        '-l', str(self.directory / 'server.log'), '-o',
                        f'-h 127.0.0.1 -p {self.port} -k {self.directory}', '-w', 'start'], check=True)
        self.started = True
        return self

    def __exit__(self, *args):
        if self.started:
            subprocess.run([str(self.bin / 'pg_ctl'), '-D', str(self.directory / 'data'),
                            '-m', 'fast', '-w', 'stop'], check=True)


class NativeServer:
    def __init__(self, directory, database_url, port):
        self.directory = directory
        self.database_url = database_url
        self.port = port
        self.process = None
        self.generation = 0
        self.requests = []

    def start(self):
        self.generation += 1
        while (self.directory / f'server-{self.generation}.log').exists():
            self.generation += 1
        self.log = (self.directory / f'server-{self.generation}.log').open('w')
        environment = {**os.environ, 'TTG_HTTP_PORT': str(self.port),
                       'JAC_DB_URL': self.database_url, 'DATABASE_URL': self.database_url,
                       'POSTGRES_URL': self.database_url,
                       'TTG_DATASET': str(self.directory / 'dataset')}
        self.process = subprocess.Popen(['bash', str(SUITE / 'runtime.sh'), str(SUITE / 'serve.py')],
                                        cwd=self.directory, env=environment,
                                        stdout=self.log, stderr=subprocess.STDOUT)
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                raise RuntimeError(f'Native server exited; see {self.log.name}')
            try:
                with urllib.request.urlopen(f'http://127.0.0.1:{self.port}/openapi.json', timeout=1) as response:
                    if response.status == 200:
                        return
            except (OSError, urllib.error.URLError):
                time.sleep(0.2)
        raise TimeoutError(f'Native server startup timed out; see {self.log.name}')

    def stop(self):
        if self.process is not None:
            self.process.terminate()
            try:
                self.process.wait(timeout=20)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
            self.process = None
            self.log.close()

    def post(self, path, body, token=None):
        headers = {'Content-Type': 'application/json'}
        if token:
            headers['Authorization'] = 'Bearer ' + token
        request = urllib.request.Request(f'http://127.0.0.1:{self.port}' + path,
                                         data=json.dumps(body).encode(), headers=headers)
        start = time.perf_counter_ns()
        try:
            with urllib.request.urlopen(request, timeout=180) as response:
                raw = response.read()
                status = response.status
        except urllib.error.HTTPError as error:
            raise RuntimeError(f'{path}: HTTP {error.code}: {error.read().decode()}') from error
        elapsed = (time.perf_counter_ns() - start) / 1e6
        result = json.loads(raw)
        assert result.get('ok') is not False and not result.get('error'), f'{path}: {result}'
        self.requests.append({'path': path, 'http_status': status, 'http_e2e_ms': elapsed,
                              'server_generation': self.generation, 'db_call_ms': None,
                              'sql_count': None})
        return result.get('data', result)

    def walker(self, name, body, token, target=None):
        path = '/walker/' + name + ('/' + target if target else '')
        result = self.post(path, body, token)
        assert not result.get('diagnostics'), f'{name}: {result["diagnostics"]}'
        return result['reports']


def prepare(app, directory, scale, seed, policy):
    directory.mkdir()
    corpus.build(directory / 'dataset', app, scale, seed, WORKSPACE)
    source, filenames = SOURCES[app]
    hashes = {}
    for filename in filenames:
        content = (source / filename).read_bytes()
        target = 'server.jac' if filename == 'main.jac' else filename
        hashes[str(source / filename)] = hashlib.sha256(content).hexdigest()
        if app == 'jacord':
            text = content.decode()
            for old, new in [('WritePerm', 'AccessLevel.WRITE'), ('ConnectPerm', 'AccessLevel.CONNECT'),
                             ('ReadPerm', 'AccessLevel.READ')]:
                text = re.sub(r'\b' + old + r'\b', new, text)
            doc_end = text.index('"""', text.index('"""') + 3) + 3
            content = (text[:doc_end] + '\nimport from jaclang.runtime.archetype { AccessLevel }\n' + text[doc_end:]).encode()
        (directory / target).write_bytes(content)
    write_json(directory / 'source-adaptation.json', {
        'original_source_sha256': hashes,
        'changes': ['Replace legacy permission constants with AccessLevel enum in isolated Jacord snapshot'] if app == 'jacord' else [],
        'adapted_source_sha256': {name: hashlib.sha256((directory / name).read_bytes()).hexdigest()
                                  for name in ['server.jac', 'server.impl.jac'] if (directory / name).exists()}})
    shutil.copyfile(SUITE / 'native_seed.py', directory / 'native_seed.py')
    nodes, edges = TYPES[app]
    node_map = '{' + ', '.join(f'"{name}": {name}' for name in nodes) + '}'
    edge_map = '{' + ', '.join(f'"{name}": {name}' for name in edges) + '}'
    extension = '''
import from native_seed { import_graph, inspect_graph }
walker SuiteRoot {
    can identify with Root entry { report jid(root); }
}
walker SuiteImport {
    has roots: dict;
    can load with Root entry {
        report import_graph(NODE_MAP, EDGE_MAP, self.roots, STORAGE);
    }
}
walker SuiteInspect {
    has mapping: dict;
    can inspect with Root entry { report inspect_graph(self.mapping); }
}
'''.replace('NODE_MAP', node_map).replace('EDGE_MAP', edge_map).replace('STORAGE', 'storage' if app == 'jdrive' else 'None')
    with (directory / 'server.jac').open('a') as file:
        file.write(extension)
    (directory / 'jac.toml').write_text(f'''[project]
name = "ttg-suite-{app}"
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
    return hashes


def replay(app, server, token, mapping, operation):
    target = mapping[operation['target']]
    name = operation['op']
    reverse = {value.replace('-', ''): key for key, value in mapping.items()}

    def logical(native_id):
        return reverse[native_id.replace('-', '')]

    def walk(walker, body=None, node=None):
        return server.walker(walker, body or {}, token, node)

    if name == 'traverse':
        values = walk('Traverse', node=target)
        # Corpus values/index are unique and exactly match source fields.
        return [f'item:{value}' for value in values]
    if name == 'sum':
        reports = walk('Sum', node=target)
        assert reports and all(value == reports[0] for value in reports), 'Inconsistent Sum exit reports'
        return reports[0]
    if name == 'find':
        reports = walk('Find', {'target': operation['value']}, target)
        if not reports:
            return None
        assert len(reports) == 1, 'Find must stop on the first matching item'
        return 'item:' + str(reports[0]['index'])
    if name == 'feed':
        reports = walk('load_feed', {'search_query': operation.get('search', '')})[0]
        ids = [logical(row['id']) for row in reports]
        assert len(ids) == len(set(ids)), 'Duplicate feed results'
        timestamps = [row['created_at'] for row in reports]
        assert timestamps == sorted(timestamps, reverse=True), 'Feed ordering differs from API contract'
        assert all(row['is_mine'] == (row['author_username'] == 'user_0000') for row in reports)
        return sorted(ids)
    if name == 'like':
        return sorted(walk('like_tweet', {'tweet_id': target})[0]['likes'])
    if name == 'follow':
        walk('follow_user', {'target_id': mapping[operation['other']]})
        profile = walk('get_profile')[0]
        return sorted(logical(row['id']) for row in profile['following'])
    if name == 'create_tweet':
        result = walk('create_tweet', {'content': operation['content']})[0]
        assert result['content'] == operation['content'] and result['author_username'] == 'user_0000'
        mapping[operation['new_id']] = result['id']
        return operation['new_id']
    if name == 'channel':
        reports = walk('load_channel', node=target)
        ids = [logical(row['id']) for row in reports]
        assert len(ids) == len(set(ids)), 'Duplicate channel messages'
        assert all(row['author_username'].startswith('user_') for row in reports), 'Missing native authorship'
        return sorted(ids)
    if name == 'post_reply':
        native_id = walk('PostReply', {'parent_message_id': target, 'content': operation['content']})[0]
        assert native_id, 'PostReply did not create a reply'
        mapping[operation['new_id']] = native_id
        return operation['new_id']
    if name == 'tree':
        rows = walk('VisibleFolderTree', node=target)[0]['entries']
        assert [row['path'] for row in rows] == sorted(row['path'] for row in rows)
        ids = [logical(row['id']) for row in rows]
        assert len(ids) == len(set(ids)), 'Duplicate tree folders'
        return sorted(ids)
    if name == 'list_folder':
        rows = walk('ListFolder', node=target)[0]['entries']
        return sorted(logical(row['id']) for row in rows)
    if name == 'trash':
        walk('TrashFolder', node=target)
        return True
    if name == 'mkdir':
        row = walk('NewFolder', {'name': 'new-folder'}, target)[0]
        mapping[operation['new_id']] = row['id']
        return operation['new_id']
    raise ValueError(f'Unsupported native operation: {name}')


def verify_snapshot(server, token, mapping, graph, app):
    actual = server.walker('SuiteInspect', {'mapping': mapping}, token)[0]
    assert set(actual['nodes']) == set(graph.nodes), 'Native node membership differs'
    for key, expected in graph.nodes.items():
        node = actual['nodes'][key]
        assert node['type'] == expected['type'], f'Native type mismatch: {key}'
        for name, value in expected['fields'].items():
            if name == 'blob_key':
                continue
            # Session mutation timestamps are assigned by original native walkers.
            if key in ('post:session:0', 'reply:session:0', 'folder:session:0') and name in ('created_at', 'updated_at'):
                continue
            if app == 'jdrive' and name == 'updated_at' and expected['fields'].get('trashed'):
                continue
            assert node['fields'][name] == value, f'Native field mismatch: {key}.{name}: {node["fields"][name]!r} != {value!r}'
    key = lambda edge: (edge['source'], edge['type'], edge['target'])
    assert Counter(map(key, actual['edges'])) == Counter(map(key, graph.edges)), 'Native domain topology differs'
    return {'node_count': len(actual['nodes']), 'edge_count': len(actual['edges']),
            'type_counts': actual['type_counts']}


def run_app(app, directory, pg_port, policy, scale, seed, browser=False):
    hashes = prepare(app, directory, scale, seed, policy)
    database_url = f'postgresql://ttgsuite@127.0.0.1:{pg_port}/postgres?options=-csearch_path%3D{app}'
    # Each app gets a separate database via the runtime's native driver.
    admin = directory / 'create_db.jac'
    database = 'suite_' + app
    admin.write_text('import from jaclang.data.pgwire { PgWireConnection }\nwith entry {\n'
                     f' c = PgWireConnection(user="ttgsuite", host="127.0.0.1", port={pg_port}, database="postgres");\n'
                     f' c.run("CREATE DATABASE {database}"); c.close();\n}}\n')
    with (directory / 'database.log').open('w') as log:
        subprocess.run(['bash', str(SUITE / 'runtime.sh'), '-m', 'jaclang', 'run', str(admin)],
                       cwd=directory, stdout=log, stderr=subprocess.STDOUT, check=True)
    database_url = f'postgresql://ttgsuite@127.0.0.1:{pg_port}/{database}'
    write_json(directory / 'connection.json', {'database_url': database_url})
    server = NativeServer(directory, database_url, free_port())
    summary = {'app': app, 'scale': scale, 'seed': seed, 'policy': policy,
               'acceptance_source_sha256': acceptance_sources(),
               'source_sha256': hashes, 'status': 'failed', 'native_import': 'pending',
               'native_replay': 'pending', 'restart_persistence': 'pending',
               'browser': 'pending', 'db_call_ms': None, 'sql_count': None,
               'performance_claim': False}
    steps = []
    try:
        server.start()
        rows = corpus.make_graph(app, corpus.SCALES[scale], __import__('random').Random(seed))
        user_keys = [key for key in rows.nodes if key.startswith('user:')] if app in ('littlex', 'jacord') else ['user:0']
        tokens, roots = {}, {}
        password = 'isolated-suite-seed-password'
        for key in user_keys:
            username = 'user_' + key.split(':')[1].zfill(4)
            server.post('/user/register', {'identities': [{'type': 'username', 'value': username}],
                                          'credential': {'type': 'password', 'password': password}})
            result = server.post('/user/login', {'identity': {'type': 'username', 'value': username},
                                                 'credential': {'type': 'password', 'password': password}})
            tokens[key] = result['token']
            roots[key] = server.walker('SuiteRoot', {}, result['token'])[0]
        token = tokens['user:0']
        mapping = server.walker('SuiteImport', {'roots': roots}, token)[0]
        write_json(directory / 'mapping.json', mapping)
        server.stop()
        server.start()
        summary['initial_snapshot'] = verify_snapshot(server, token, mapping, rows, app)
        summary['native_import'] = 'passed'
        for operation in corpus.session(app, corpus.SCALES[scale], rows):
            expected = corpus.result(rows, operation)
            result = replay(app, server, token, mapping, operation)
            step = {'operation': operation, 'expected': expected, 'actual': result, 'passed': result == expected}
            steps.append(step)
            write_json(directory / 'steps.json', steps)
            assert result == expected, f'Native replay mismatch: {operation}: {result!r} != {expected!r}'
        summary['native_replay'] = 'passed'
        server.stop()
        server.start()
        summary['final_snapshot'] = verify_snapshot(server, token, mapping, rows, app)
        if app == 'jdrive':
            import base64
            file_id = next(key for key in mapping if key.endswith('/file'))
            result = server.walker('Download', {}, token, mapping[file_id])[0]
            downloaded = base64.b64decode(result['content_b64'])
            expected_payload = (b'TTG corpus file content. ' * 3)[:64].ljust(64, b' ')
            assert downloaded == expected_payload and result['size'] == 64
            summary['blob_download_after_restart'] = 'passed'
            summary['blob_sha256_after_restart'] = hashlib.sha256(downloaded).hexdigest()
        summary['restart_persistence'] = 'passed'
        summary['status'] = 'native_passed'
        write_json(directory / 'mapping.json', mapping)
        if browser and app != 'linked_list':
            from browser import verify_browser
            summary['browser_result'] = verify_browser(app, server, directory)
            summary['browser'] = 'passed'
            server.stop()
            server.start()
            from browser import verify_browser_persistence
            verify_browser_persistence(app, server, token, summary['browser_result'])
            summary['browser_mutations_after_restart'] = 'passed'
            summary['status'] = 'verified'
        elif app == 'linked_list':
            summary['browser'] = 'exempt_microbenchmark'
    except Exception as error:
        summary['status'] = 'failed'
        summary['error'] = f'{type(error).__name__}: {error}'
        raise
    finally:
        server.stop()
        write_json(directory / 'summary.json', summary)
        write_json(directory / 'requests.json', server.requests)
        print(json.dumps(summary), flush=True)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True, help='New evidence directory; existing output is preserved')
    parser.add_argument('--apps', nargs='+', choices=list(SOURCES), default=list(SOURCES))
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--scale', choices=corpus.SCALES, default='smoke')
    parser.add_argument('--policy', choices=['none', 'ttg'], default='none')
    parser.add_argument('--browser', action='store_true', help='Also execute real Chromium UI workflows')
    parser.add_argument('--interactive', choices=['littlex', 'jacord', 'jdrive'],
                        help='After validation, keep one application open until Ctrl-C')
    args = parser.parse_args()
    args.output = args.output.resolve()
    args.output.mkdir(parents=True, exist_ok=False)
    write_json(args.output / 'run-manifest.json', {
        'runtime': runtime_identity(),
        'external_tools': corpus.revision(EXTERNAL),
        'scale': args.scale, 'seed': args.seed, 'policy': args.policy,
        'browser_requested': args.browser,
        'suite_source_sha256': {str(path.relative_to(SUITE)): hashlib.sha256(path.read_bytes()).hexdigest()
                                for path in SUITE.rglob('*') if path.is_file() and path.suffix in
                                ('.py', '.jac', '.js', '.mjs', '.html', '.css', '.sh')},
        'measurement_scope': 'Semantic validation; recorded HTTP latency is diagnostic, DB-call time and SQL count unmeasured',
        'dependency_policy_status': 'ttg_dependency was not configured or verified by this suite'})
    results = []
    with IsolatedPostgres(args.output / 'postgres', free_port()) as postgres:
        for app in args.apps:
            try:
                results.append(run_app(app, args.output / app, postgres.port, args.policy, args.scale, args.seed, args.browser))
            except Exception as error:
                print(f'{app}: {type(error).__name__}: {error}', file=sys.stderr)
                result_path = args.output / app / 'summary.json'
                results.append(json.loads(result_path.read_text()) if result_path.exists() else
                               {'app': app, 'status': 'failed', 'error': str(error)})
            write_json(args.output / 'index.json', results)
        if args.interactive:
            if args.interactive not in args.apps:
                parser.error('--interactive must be included in --apps')
            directory = args.output / args.interactive
            if json.loads((directory / 'summary.json').read_text())['native_replay'] != 'passed':
                raise RuntimeError('Interactive mode requires a successful native replay')
            connection = json.loads((directory / 'connection.json').read_text())
            backend = NativeServer(directory, connection['database_url'], free_port())
            backend.start()
            config = directory / 'ui-config.json'
            write_json(config, {})
            frontend_port = free_port()
            frontend = subprocess.Popen([sys.executable, str(SUITE / 'ui_server.py'), '--app', args.interactive,
                                         '--backend', f'http://127.0.0.1:{backend.port}', '--config', str(config),
                                         '--port', str(frontend_port)])
            try:
                print(f'Open http://127.0.0.1:{frontend_port}; username user_0000; password isolated-suite-seed-password', flush=True)
                print('Press Ctrl-C to stop only this suite frontend, backend and PostgreSQL cluster.', flush=True)
                frontend.wait()
            except KeyboardInterrupt:
                pass
            finally:
                frontend.terminate()
                frontend.wait(timeout=10)
                backend.stop()
    write_json(args.output / 'index.json', results)
    if any(row['status'] == 'failed' for row in results):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
