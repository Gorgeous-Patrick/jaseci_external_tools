"""Two matched native LittleX recaptures; diagnostic-only owned lifecycle."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import urllib.request
import uuid

OWN = Path(__file__).resolve().parent
ROOT = OWN.parent.parent
MEASURE = ROOT/'project-notes/measurements/ttg-plus-diagnostics-20261031'
PLUS = OWN.parent/'ttg-plus-performance'
sys.path.insert(0, str(PLUS))
from interop import Applications, BasePostgres, checked_ref, require, read_json, reference, sha256, verify_case
from plus_config import write_config
from plus_postgres import OwnedPostgres as PlusPostgres
from semantic import independent_replay
from overlay import transform


def write(path, value):
    path.write_text(json.dumps(value, indent=2)+'\n')


def jsonl(path):
    with path.open() as stream:
        for line in stream:
            if line.strip():
                yield json.loads(line)


class Postgres(PlusPostgres):
    def __init__(self, directory, runtime, output):
        from owned_postgres import free_port
        self.directory = directory.resolve()
        require(self.directory.is_relative_to(OWN) and not self.directory.exists(), 'NEW owned diagnostic cluster only')
        self.runtime, self.run_directory = runtime, output
        self.port, self.owner = free_port(), str(uuid.uuid4())
        self.started, self.databases, self.services = False, set(), []
        self.admin_process, self.context, self.statement_logging = None, None, False
        self.source_guard = lambda: None

    def sql(self, sql, database='postgres'):
        self.verify_owner()
        require(self.started, 'Owned cluster stopped')
        if self.admin_process is None:
            env = environment(self.runtime)
            for key in list(env):
                if key.startswith(('TTG_PERF_', 'TTG_DIAG_')):
                    env.pop(key)
            self.admin_log = (self.directory/'admin.log').open('a')
            self.admin_process = subprocess.Popen(['bash', str(PLUS.parent/'ttg-continuation-performance/runtime.sh'),
                str(PLUS.parent/'ttg-continuation-performance/sql_admin.py'), '--port', str(self.port)],
                env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.admin_log, text=True, bufsize=1)
        self.admin_process.stdin.write(json.dumps(dict(database=database, sql=sql))+'\n')
        self.admin_process.stdin.flush()
        while True:
            line = self.admin_process.stdout.readline()
            require(line, 'Owned admin exited')
            if line.startswith('TTG_ADMIN_RESULT='):
                result = json.loads(line[len('TTG_ADMIN_RESULT='):])
                break
            self.admin_log.write(line)
            self.admin_log.flush()
        require(result['ok'], result.get('error', 'Admin query failed'))
        rows = result['rows']
        if not rows:
            return ''
        scalar = rows[0][0]
        return scalar if isinstance(scalar, str) else json.dumps(scalar)

    def create_database(self):
        require(shutil.disk_usage(self.directory).free >= 1536*1024**2, 'Preserve1.5GiB guard')
        return BasePostgres.create_database(self)


def environment(runtime):
    return {**os.environ, 'TTG_RUNTIME_SOURCE': str(runtime),
            'TTG_RUNTIME_CACHE': str(OWN/'cache-runtime'), 'TTG_CACHE_DIR': str(OWN/'cache-compiler'),
            'PYTHONDONTWRITEBYTECODE': '1'}


def prepare_runtime(base_manifest, target):
    base = read_json(base_manifest)
    root = Path(base['root'])
    require(target.is_relative_to(OWN) and not target.exists(), 'NEW diagnostic runtime only')
    # Hardlink immutable files; break the driver link BEFORE writing the patch.
    shutil.copytree(root, target, copy_function=os.link)
    relative = Path('jac/jaclang/data/impl/pgwire.impl.jac')
    driver = target/relative
    before = driver.read_text()
    require(hashlib.sha256(before.encode()).hexdigest() == base['files'][str(relative)],
            'Base DIRECT driver differs from its immutable manifest')
    driver.unlink()
    driver.write_text(transform(before))
    for name in ('capture.py', 'explain.py'):
        destination = target/'jac'/name
        require(not destination.exists(), 'Diagnostic helper collision')
        shutil.copyfile(OWN/name, destination)
    require((root/relative).read_text() == before, 'Original immutable driver changed')
    return dict(base=reference(base_manifest), root=str(target), driver_before_sha256=hashlib.sha256(before.encode()).hexdigest(),
                driver_after_sha256=sha256(driver), helpers={name:sha256(OWN/name) for name in ('capture.py','explain.py')},
                method='Immutable hardlinks; driver unlinked before patch; helpers copied')


def seal(directory):
    write(directory/'artifacts.json', dict(passed=True, files={str(p.relative_to(directory)):sha256(p)
        for p in directory.rglob('*') if p.is_file() and p.name != 'artifacts.json'
        and not any(part in ('.jac','__pycache__') for part in p.relative_to(directory).parts)}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--selection', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--cluster', type=Path, required=True)
    parser.add_argument('--runtime', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    require(output.is_relative_to(MEASURE) and not output.exists(), 'NEW diagnostic evidence path required')
    plan = read_json(args.plan)
    selection = read_json(args.selection)
    require(selection['purpose'] == 'matched_littlex_read_only_diagnostic', 'Explicit diagnostic selection required')
    require(selection['context_refs'] == {key:plan[key] for key in ('runtime','overlay','app_snapshot')},
            'Selection does not bind the exact accepted runtime/application inputs')
    ids = [target['target_id'] for target in selection['targets']]
    require(len(ids) == len(set(ids)), 'Duplicate selected target IDs')
    bound_paths = [*sorted(OWN.glob('*.py')), args.selection.resolve()]
    bound_hashes = {str(path):sha256(path) for path in bound_paths}
    def source_guard():
        require(all(sha256(Path(path)) == value for path,value in bound_hashes.items()),
                'Diagnostic helper/runner/selection source drift')
    overlay_manifest = checked_ref(plan['overlay'], args.plan.parent)
    clean_manifest = checked_ref(plan['runtime'], args.plan.parent)
    require(read_json(clean_manifest)['commit'] == '85026d486de8e16d4b894aa5a5664c7873893e89', 'Pinned85026d required')
    output.mkdir()
    runtime_proof = prepare_runtime(overlay_manifest, args.runtime.resolve())
    write(output/'runtime-overlay.json', runtime_proof)
    write(output/'sources.json', dict(files=bound_hashes))
    previous = PLUS.parent/'ttg-continuation-performance'
    with (output/'overlay-import.log').open('w') as log:
        subprocess.run(['bash',str(previous/'runtime.sh'),'-c',
            'import jaclang; from jaclang.data.pgwire import PgWireConnection; '
            'import capture, explain; print("DIAGNOSTIC_OVERLAY_IMPORT_PASS")'],
            env=environment(args.runtime.resolve()),stdout=log,stderr=subprocess.STDOUT,check=True)
    apps = Applications()
    w = apps.workloads
    original_server = w.Server
    active = {}
    pg = Postgres(args.cluster, args.runtime.resolve(), output)
    proofs = {}

    class Server(original_server):
        def __init__(self, *values, **kwargs):
            super().__init__(*values, **kwargs)
            active['server'] = self
        def start(self):
            self.generation += 1
            self.log = (self.directory/f'server-{self.generation}.log').open('w')
            env = environment(self.runtime)
            env.update(TTG_HTTP_PORT=str(self.port), TTG_PERF_CONTROL_PORT=str(self.control_port),
                TTG_DATASET=str(self.directory/'dataset'), JAC_DB_URL=self.url, DATABASE_URL=self.url, POSTGRES_URL=self.url,
                TTG_PERF_DIR=str(self.directory), TTG_PERF_CELL_ID='littlex/'+active['cell'],
                TTG_PERF_TRIAL_ID=self.directory.name, TTG_PERF_SERVER_GENERATION=str(self.generation),
                TTG_PERF_CLOCK_DOMAIN='same-host-perf_counter_ns', TTG_PERF_POSTGRES_INSTANCE_ID=pg.owner,
                TTG_DIAG_SELECTION=str(args.selection.resolve()), TTG_DIAG_CONFIG_ID=active['cell'],
                TTG_DIAG_OUTPUT=str(self.directory/'captures'))
            previous = PLUS.parent/'ttg-continuation-performance'
            self.process = subprocess.Popen(['bash', str(previous/'runtime.sh'), str(previous/'perf_serve.py')],
                cwd=self.directory, env=env, stdout=self.log, stderr=subprocess.STDOUT)
            pg.services.append(self.process)
            deadline = time.monotonic()+300
            while time.monotonic() < deadline:
                require(self.process.poll() is None, 'Diagnostic server exited: '+str(self.log.name))
                try:
                    with urllib.request.urlopen(f'http://127.0.0.1:{self.port}/openapi.json', timeout=1) as response:
                        if response.status == 200:
                            return
                except OSError:
                    time.sleep(.2)
            raise TimeoutError('Diagnostic native startup')

    def accept(database, directory):
        source_guard()
        require(not any(p.poll() is None for p in pg.services), 'Owned servers must stop before acceptance')
        cell = active['cell']
        require(sha256(args.runtime/'jac/jaclang/data/impl/pgwire.impl.jac') ==
                runtime_proof['driver_after_sha256'], 'Diagnostic driver drift')
        for name, expected_hash in runtime_proof['helpers'].items():
            require(sha256(args.runtime/'jac'/name) == expected_hash, 'Executed helper drift')
        summary = read_json(directory/'summary.json')
        require(summary['passed'] and summary['restart_persistence'] == 'passed', 'Full native workflow/restart failed')
        semantic = apps.semantic.audit(directory, proofs.get('off',{}).get('full_response'), sealed=False)
        closes = {}
        for path in directory.glob('server-*.events.jsonl'):
            for event in jsonl(path):
                if event['kind'] == 'native_context_close' and event.get('origin_request_id'):
                    require(event['natural_close_completed'], 'Natural session close failed')
                    closes.setdefault(event['origin_request_id'], set()).add(event['session_nonce'])
        used = set()
        for request in active['server'].requests:
            if request['path'].startswith('/walker/'):
                nonces = closes.get(request['request'], set())
                require(nonces and not used.intersection(nonces), 'RPC session missing/reused')
                used.update(nonces)
        captures = sorted((directory/'captures').glob('*.json'))
        wanted = [t for t in selection['targets'] if t['config_id'] == cell]
        require(len(captures) == len(wanted), 'Missing/extra selected query capture')
        actual_ids = [read_json(path)['target']['target_id'] for path in captures]
        require(len(actual_ids) == len(set(actual_ids)) and set(actual_ids) ==
                {target['target_id'] for target in wanted}, 'Duplicate/missing selected target IDs')
        calls = [call for path in directory.glob('server-*.calls.jsonl') for call in jsonl(path)]
        accepted = []
        for path in captures:
            capture = read_json(path)
            target = capture['target']
            require(target in wanted, 'Undeclared selected capture')
            matches = [call for call in calls if call['origin_request_id'] == target['request']
                and str(call['server_generation']) == str(target['generation'])
                and call['sql'] == capture['wire']['positional_sql']
                and call['backend_pid'] == capture['state']['context'][0][2]
                and call['role'] == target['role'] and call.get('error') is None
                and call.get('sendall_returned') is True and call['ready_messages'] == 1]
            require(len(matches) == 1 and matches[0]['returned_rows'] == target['expected_rows'],
                    'Actual selected original completion/row count missing')
            accepted.append(dict(capture=reference(path), actual_call=matches[0], plans_accepted_after_oracle=True))
        full_response = {key:semantic[key] for key in ('full_actions_sha256','full_semantic_sha256')}
        proof = dict(passed=True, case_id='littlex', app='littlex', scale='smoke', length=None,
            config_id=cell, stage='diagnostic', seed=42, database=database, cluster_owner=pg.owner,
            full_response=full_response, output_sha256=semantic['full_semantic_sha256'],
            checks=dict(native=True, oracle=True, fresh_session=True, restart=True), primary_measurement=False)
        write(directory/'plus-proof.json', proof)
        seal(directory)
        independent = independent_replay(directory, dict(app='littlex',scale='smoke',length=None), proofs.get('off'))
        types = sum((list(group) for group in apps.native.TYPES['littlex']), [])
        require(w.census(pg,database,types) == read_json(directory/'final-graph-raw.json'), 'Final physical graph differs')
        write(directory/'diagnostic-acceptance.json', dict(passed=True, full_native_oracles=True,
            independent_replay=independent, full_response=full_response, selected=accepted,
            runtime=runtime_proof, selection=reference(args.selection), primary_measurement=False))
        seal(directory)
        verify_case(directory, required=('diagnostic-acceptance.json','plus-proof.json'))
        source_guard()
        BasePostgres.drop_completed_database(pg, database, directory/'artifacts.json')
        proofs[cell] = proof

    class Proxy:
        def __getattr__(self, name):
            return getattr(pg, name)
        def drop_completed_database(self, name, manifest, server_stopped):
            require(server_stopped, 'Native server still running')
            accept(name, Path(manifest).parent)

    w.Server = Server
    w.config = lambda directory, app, cell: write_config(directory, cell)
    apps.native.corpus.revision = lambda path: dict(source_kind='accepted_immutable_snapshot',
        snapshot=reference(apps.suite_manifest), requested_path=str(path))
    write(output/'launch.json', dict(creator_pid=os.getpid(), plan=reference(args.plan),
        selection=reference(args.selection), runtime=runtime_proof, primary_measurement=False))
    try:
        with pg:
            for cell in ('off','ttg_plus'):
                active['cell'] = cell
                directory = output/('littlex-'+cell)
                w.trial('littlex',cell,directory,Proxy(),apps.native,apps.evaluate,apps.readers,
                        args.runtime.resolve(),'diagnostic',seed=42,scale='smoke',steady_reads=3)
        source_guard()
        write(output/'result.json', dict(passed=True, recaptures=proofs, primary_measurement=False))
    finally:
        source_guard()
        w.Server = original_server
        status = subprocess.run(['/home/baichuan/.cache/jac/pg/dist/linux-amd64-18.6.0/bin/pg_ctl',
            '-D',str(pg.directory/'data'),'status'],capture_output=True,text=True)
        write(output/'lifecycle.json',dict(services_stopped=all(p.poll() is not None for p in pg.services),
            pg_ctl_status=status.returncode, pidfile=(pg.directory/'data/postmaster.pid').exists(),
            retained_databases=sorted(pg.databases), services=[dict(pid=p.pid,exit_code=p.poll()) for p in pg.services]))


if __name__ == '__main__':
    main()
