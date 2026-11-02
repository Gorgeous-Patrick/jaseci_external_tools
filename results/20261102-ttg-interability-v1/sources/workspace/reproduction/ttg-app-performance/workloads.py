"""Gated runner engine for actual frozen application walkers and suite oracles.

Importing this module does not start servers or execute a workload. Only runner.py
may call trial(), after enforcing the all30 acceptance gate.
"""
import copy
from datetime import datetime, timezone
import hashlib
import importlib
import json
import os
from pathlib import Path
import random
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request

from gate import APPS, GateError, require, sha
from identity import Identities, encoded
from owned_postgres import free_port

OWN = Path(__file__).resolve().parent
ROOT = OWN.parents[1]
SETUP_WALKERS = {'Seed', 'SuiteRoot', 'SuiteImport', 'SuiteInspect'}
SET_SCHEMAS={}

def write(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')

def digest(value):
    return hashlib.sha256(encoded(value)).hexdigest()

def configure(snapshot):
    global SET_SCHEMAS
    root = snapshot.parent
    schema_path=ROOT/'project-notes/measurements/ttg-app-performance-20261030/set-field-schema-v1.json'
    schema=json.loads(schema_path.read_text())
    require(schema.get('suite_manifest_sha256')==sha(snapshot),'Declared-set schema uses a different frozen suite')
    require(schema.get('apps_scanned')==30,'Declared-set schema must audit all30 apps')
    SET_SCHEMAS=schema['by_app']
    sys.path.insert(0, str(root / 'datasets/ttg'))
    sys.path.insert(0, str(root / 'app_suite'))
    native = importlib.import_module('native')
    evaluate = importlib.import_module('evaluate')
    native.WORKSPACE = ROOT
    native.SOURCES = {
        'linked_list': (root / 'originals/linked_list', ['main.jac']),
        'littlex': (root / 'originals/littlex', ['server.jac']),
        'jacord': (root / 'originals/jacord', ['server.jac', 'server.impl.jac']),
        'jdrive': (root / 'originals/jdrive', ['server.jac', 'server.impl.jac'])}
    registry = json.loads((root / 'app_suite/registry.json').read_text())
    require({r['app'] for r in registry['apps']} == set(APPS), 'Frozen registry must cover all30')
    require(set(evaluate.SCENARIOS) == set(APPS[4:]), 'Frozen SCENARIOS must cover all26 additions')
    return native, evaluate, {row['app']: row for row in registry['apps']}

class Server:
    def __init__(self, directory, url, runtime, mode, reader):
        self.directory, self.url, self.runtime, self.mode, self.reader = directory, url, runtime, mode, reader
        self.port, self.control_port = free_port(), free_port()
        self.process = None
        self.generation = 0
        self.requests, self.transcript = [], []
        self.phase = 'setup'
        self.reset_next = True
        self.fixture = None
        self.capture_fixture = None

    def start(self):
        self.generation += 1
        self.log = (self.directory / f'server-{self.generation}.log').open('w')
        env = {**os.environ, 'TTG_RUNTIME_SOURCE': str(self.runtime),
            'TTG_HTTP_PORT': str(self.port), 'TTG_PERF_CONTROL_PORT': str(self.control_port),
            'TTG_PERF_TRACE': str(self.directory / f'server-{self.generation}.calls.jsonl'),
            'TTG_DATASET': str(self.directory / 'dataset'),
            'JAC_DB_URL': self.url, 'DATABASE_URL': self.url, 'POSTGRES_URL': self.url,
            'TTG_PERF_DRIVER': '1' if self.mode == 'diagnostic' else '0',
            'TTG_PERF_DETAIL': 'detailed' if self.mode in ('diagnostic', 'preflight_diagnostic') else 'light',
            'TTG_PERF_OBSERVER': '0' if self.mode == 'uninstrumented_e2e' else '1'}
        self.process = subprocess.Popen(['bash', str(OWN / 'runtime.sh'), str(OWN / 'perf_serve.py')],
            cwd=self.directory, env=env, stdout=self.log, stderr=subprocess.STDOUT)
        deadline = time.monotonic() + 240
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                raise RuntimeError(f'Server exited: {self.log.name}')
            try:
                with urllib.request.urlopen(f'http://127.0.0.1:{self.port}/openapi.json', timeout=1) as response:
                    if response.status == 200:
                        return
            except OSError:
                time.sleep(.2)
        raise TimeoutError(f'Startup timeout: {self.log.name}')

    def stop(self):
        if self.process is None:
            return
        self.process.terminate()
        try:
            self.process.wait(timeout=30)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait()
        self.process = None
        self.log.close()

    def post(self, path, body, token=None):
        rid = f'{self.generation}:{len(self.requests)}'
        headers = {'Content-Type': 'application/json', 'X-TTG-Perf-Request': rid}
        if token:
            headers['Authorization'] = 'Bearer ' + token
        walker = path.split('/')[2] if path.startswith('/walker/') else None
        phase = 'setup' if not walker or walker in SETUP_WALKERS else self.phase
        if phase == 'workflow' and self.reset_next:
            headers['X-TTG-Perf-Reset-Profile'] = '1'
            self.reset_next = False
        request = urllib.request.Request(f'http://127.0.0.1:{self.port}' + path,
            data=json.dumps(body).encode(), headers=headers)
        wall_start = time.time()
        started = time.perf_counter_ns()
        try:
            with urllib.request.urlopen(request, timeout=180) as response:
                raw, status = response.read(), response.status
        except urllib.error.HTTPError as error:
            raw, status = error.read(), error.code
        ended = time.perf_counter_ns()
        wall_end = time.time()
        result = json.loads(raw)
        # This channel executes only AFTER application HTTP completion and is
        # excluded from http_e2e_ms. It also serializes deferred trace metadata.
        control = urllib.request.Request(f'http://127.0.0.1:{self.control_port}/drain', data=b'',
            headers={'X-TTG-Perf-Drain-Request': rid})
        with urllib.request.urlopen(control, timeout=40) as response:
            drained = json.loads(response.read())
        require(drained['pending'] == 0, f'Late prefetch drain failed: {rid}')
        record = dict(request=rid, phase=phase, path=path, input=body if walker else '<setup credentials omitted>',
            output=result if walker else '<setup authentication omitted>', http_status=status,
            http_e2e_ms=(ended-started)/1e6, start_ns=started, end_ns=ended,
            wall_start=wall_start, wall_end=wall_end, post_response_drain=drained,
            server_generation=self.generation)
        self.requests.append(record)
        with (self.directory / 'http-raw.jsonl').open('a') as file:
            file.write(json.dumps(record) + '\n')
        require(200 <= status < 300 and result.get('ok') is not False and not result.get('error'), f'{path}: {status}: {result}')
        data = result.get('data', result)
        if walker and self.phase == 'workflow':
            self.transcript.append(dict(walker=walker, target=path.split('/')[3:] or [], input=body, output=data))
        if walker in ('Seed', 'SuiteImport') and self.fixture is None and self.capture_fixture:
            self.fixture = self.capture_fixture()
        return data

    def walker(self, name, body, token, target=None):
        result = self.post('/walker/' + name + ('/' + target if target else ''), body, token)
        require(not result.get('diagnostics'), f'{name}: {result.get("diagnostics")}')
        return result['reports']

def config(directory, app, policy):
    name = 'ttg_dependency' if policy.startswith('dependency_') else policy
    model = 'expected_benefit' if policy == 'dependency_expected_benefit' else 'always'
    (directory / 'jac.toml').write_text(f'''[project]
name = "ttg-performance-{app}"
entry-point = "server.jac"
[run]
topology_index = true
prefetching = "{name}"
ttg_prefetch_model = "{model}"
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

def census(postgres, database, types):
    names = ','.join("'" + name + "'" for name in types)
    # Include GenericEdge/root ownership links touching domain objects, not just
    # explicitly declared edge classes. The edge kind was independently verified
    # by census-validation-v2's native persisted fixture.
    raw = postgres.sql("WITH domain AS (SELECT id FROM anchors WHERE arch_type IN (" + names + ")) "
        "SELECT coalesce(json_agg(row_to_json(q)), '[]'::json) FROM ("
        "SELECT id,kind,arch_type,root_id,src,dst,undirected,props FROM anchors WHERE id IN (SELECT id FROM domain) "
        "OR (kind='EdgeAnchor' AND (src IN (SELECT id FROM domain) OR dst IN (SELECT id FROM domain))) ORDER BY seq) q", database)
    return json.loads(raw)

def validate_volatile_timestamps(server):
    """Narrowly validate fields exempted by original verify_snapshot oracle."""
    checked = []
    for request in server.requests:
        if '/walker/SuiteInspect' not in request['path']:
            continue
        result = request['output'].get('data', request['output'])
        for report in result.get('reports', []):
            for logical, node in report.get('nodes', {}).items():
                fields = node.get('fields', {})
                dynamic = logical in ('post:session:0', 'reply:session:0', 'folder:session:0')
                names = ['created_at', 'updated_at'] if dynamic else ['updated_at'] if (
                    logical == 'folder:root/0' and fields.get('trashed') and fields.get('updated_at')) else []
                parsed = {}
                for name in names:
                    if name not in fields:
                        continue
                    value = fields[name]
                    stamp = datetime.fromisoformat(value.replace('Z', '+00:00'))
                    # JDrive deliberately emits datetime.now().isoformat()
                    # without an offset. Interpret it in the inherited local
                    # timezone, exactly as its producer does; never force UTC.
                    seconds = stamp.timestamp()
                    start = min(r['wall_start'] for r in server.requests)
                    require(start - 5 <= seconds <= request['wall_end'] + 5, f'Invalid volatile timestamp: {logical}.{name}')
                    parsed[name] = seconds
                    checked.append(dict(logical_id=logical, field=name, raw=value, valid=True))
                if 'created_at' in parsed and 'updated_at' in parsed:
                    require(parsed['created_at'] <= parsed['updated_at'], f'Timestamp order reversed: {logical}')
    return checked

def trial(app, policy, directory, postgres, native, evaluate, readers, runtime, mode, seed=42, scale='smoke', steady_reads=3,
          expected=None, validate_after=None, kind_validation=None):
    """Actual native app workflow, fresh DB, independent suite oracles, no browser."""
    trial_started = time.perf_counter_ns()
    original = app in native.SOURCES
    if original:
        native.prepare(app, directory, scale, seed, 'none')
        types = sum((list(x) for x in native.TYPES[app]), [])
    else:
        directory.mkdir()
        source = native.SUITE / 'apps' / app
        for path in source.iterdir():
            if path.is_file():
                shutil.copyfile(path, directory / path.name)
        text = '\n'.join(p.read_text() for p in directory.glob('*.jac'))
        types = re.findall(r'\b(?:node|edge)\s+(\w+)\s*\{', text)
    config(directory, app, policy)
    database = postgres.create_database()
    url = f'postgresql://ttgperf@127.0.0.1:{postgres.port}/{database}'
    server = Server(directory, url, runtime, mode, readers[app]['read_walker'])
    server.capture_fixture = lambda: census(postgres, database, types)
    passed = False
    summary = dict(app=app, policy=policy, seed=seed, mode=mode, passed=False,
        scale=scale if original else 'domain_scenario', database=database,
        cache_state='Fresh DB seeded immediately; PostgreSQL/OS pages warm from seed/verification; no OS cache flush',
        model_state='Reset at first workflow request; adaptive during workflow; warmed final-state reader separately',
        session_state='New native session per HTTP request', profile_storage='process-local; no held-out training')
    try:
        server.start()
        password = 'isolated-suite-seed-password'
        def login(username):
            server.post('/user/register', {'identities': [{'type': 'username', 'value': username}],
                'credential': {'type': 'password', 'password': password}})
            return server.post('/user/login', {'identity': {'type': 'username', 'value': username},
                'credential': {'type': 'password', 'password': password}})['token']
        logical_steps = []
        if original:
            graph = native.corpus.make_graph(app, native.corpus.SCALES[scale], random.Random(seed))
            users = [key for key in graph.nodes if key.startswith('user:')] if app in ('littlex', 'jacord') else ['user:0']
            tokens, roots = {}, {}
            for user in users:
                tokens[user] = login('user_' + user.split(':')[1].zfill(4))
                roots[user] = server.walker('SuiteRoot', {}, tokens[user])[0]
            token = tokens['user:0']
            mapping = server.walker('SuiteImport', {'roots': roots}, token)[0]
            write(directory / 'mapping-initial.json', mapping)
            server.stop()
            server.start()
            native.verify_snapshot(server, token, mapping, graph, app)
            server.phase = 'workflow'
            operations = native.corpus.session(app, native.corpus.SCALES[scale], graph)
            for operation in operations:
                operation_expected = native.corpus.result(graph, operation)
                actual = native.replay(app, server, token, mapping, operation)
                require(actual == operation_expected, f'Original logical oracle failed: {app}: {operation}')
                logical_steps.append(dict(operation=operation, expected=operation_expected, actual=actual))
            read_operation = next(op for op in reversed(operations) if op['op'] in ('traverse', 'feed', 'channel', 'tree', 'list_folder'))
            def read_board():
                expected = native.corpus.result(graph, read_operation)
                require(native.replay(app, server, token, mapping, read_operation) == expected, 'Steady reader oracle failed')
        else:
            token = login('user_0000')
            server.phase = 'workflow'
            scenario = evaluate.SCENARIOS[app](server, token, seed, directory)
            def read_board():
                require(server.walker(scenario['read_walker'], {}, token)[0] == scenario['expected_board'], 'Steady reader oracle failed')
        require(bool(server.fixture), 'Initial native domain fixture was not captured or is empty')
        # Warmup/read samples target the final state, with exact native result
        # equality. They are distinct from the ordered read+mutation workflow.
        server.phase = 'steady_warmup'
        for _ in range(3):
            read_board()
        server.phase = 'steady_read'
        for _ in range(steady_reads):
            read_board()
        server.phase = 'verify'
        server.stop()
        server.start()
        if original:
            native.verify_snapshot(server, token, mapping, graph, app)
            summary['volatile_fields'] = validate_volatile_timestamps(server)
            if app == 'jdrive':
                import base64
                file_id = next(key for key in mapping if key.endswith('/file'))
                blob = server.walker('Download', {}, token, mapping[file_id])[0]
                require(base64.b64decode(blob['content_b64']) == (b'TTG corpus file content. ' * 3)[:64].ljust(64, b' ')
                        and blob['size'] == 64, 'Original persisted blob oracle failed')
        else:
            read_board()
        final_graph = census(postgres, database, types)
        identities = Identities(set_schema=SET_SCHEMAS.get(app,{}))
        canonical_fixture = identities.normalize(server.fixture)
        actions = identities.normalize([{k: v for k, v in r.items() if k != 'output'} for r in server.transcript])
        if original:
            # Original logical oracle preserves source ordering/authorship and
            # exact final node/edge semantics, with narrow timestamp exemptions.
            outputs = logical_steps
            fixture = json.loads((directory / 'dataset/manifest.json').read_text())
            canonical_fixture = {'dataset_files': fixture['files'], 'config': fixture['config']}
            write(directory / 'logical-steps.json', logical_steps)
        else:
            outputs = identities.normalize({'transcript': server.transcript, 'final_graph': final_graph})
        write(directory / 'fixture-raw.json', server.fixture)
        write(directory / 'final-graph-raw.json', final_graph)
        write(directory / 'fixture-canonical.json', canonical_fixture)
        write(directory / 'actions-canonical.json', actions)
        write(directory / 'outputs-canonical.json', outputs)
        write(directory / 'identity-map.json', identities.mapping)
        summary.update(restart_persistence='passed',
            fixture_sha256=digest(canonical_fixture), actions_sha256=digest(actions), outputs_sha256=digest(outputs),
            initial_domain_nodes=None, initial_domain_edges=None,
            initial_domain_kind_counts={kind: sum(r['kind'] == kind for r in server.fixture)
                for kind in sorted({r['kind'] for r in server.fixture})},
            steady_read_warmup=3, steady_read_samples=steady_reads)
        if kind_validation is not None:
            require(kind_validation.get('passed') is True, 'Native kind validation incomplete')
            kinds = summary['initial_domain_kind_counts']
            node_kind, edge_kind = kind_validation['native_node_kind'], kind_validation['native_edge_kind']
            require(set(kinds) <= {node_kind, edge_kind}, f'Unexpected persisted domain kind: {kinds}')
            summary['initial_domain_nodes'] = kinds.get(node_kind, 0)
            summary['initial_domain_edges'] = kinds.get(edge_kind, 0)
        if expected is not None:
            for field in ('fixture_sha256', 'actions_sha256', 'outputs_sha256'):
                require(summary[field] == expected[field], f'Trial differs from preflight: {app}/{policy}/{field}')
        if validate_after:
            validate_after()
        summary['passed'] = True
        passed = True
    except Exception as error:
        summary['error'] = f'{type(error).__name__}: {error}'
        raise
    finally:
        server.stop()
        summary['case_total_wall_ms'] = (time.perf_counter_ns() - trial_started) / 1e6
        write(directory / 'summary.json', summary)
        write(directory / 'requests.json', server.requests)
        # Archive manifest includes seed, expected/canonical state, sources,
        # HTTP responses, SQL/model traces, and logs before SQL cleanup.
        artifacts = {str(p.relative_to(directory)): sha(p) for p in directory.rglob('*') if p.is_file()
                     and not any(x in {'__pycache__', '.jac'} for x in p.relative_to(directory).parts)}
        write(directory / 'artifacts.json', {'files': artifacts, 'passed': passed})
        if passed:
            postgres.drop_completed_database(database, directory / 'artifacts.json', server_stopped=server.process is None)
        else:
            postgres.record('failed_database_preserved', database=database, evidence=str(directory))
    return summary
