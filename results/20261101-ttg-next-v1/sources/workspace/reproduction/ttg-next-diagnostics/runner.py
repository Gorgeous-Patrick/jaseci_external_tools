"""Two oracle-checked LL1000 recaptures; real Bind and same-transaction plans."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import uuid

OWN = Path(__file__).resolve().parent
ROOT = OWN.parent.parent
NEXT = OWN.parent / 'ttg-next-performance'
EVIDENCE = ROOT / 'project-notes/measurements/ttg-next-diagnostics-20261101'
sys.path.insert(0, str(NEXT))
from next_interop import read_json, reference, require, sha256, verify_case
from next_postgres import OwnedPostgres as ParentPostgres
import next_trial
from next_trial import Trial, load_unsealed
from diagnostic_storage import compress_closed_traces
next_trial.compress_closed_traces = compress_closed_traces
from next_config import PREVIOUS
from owned_postgres import BIN, free_port
from overlay import transform


def write(path, value):
    Path(path).write_text(json.dumps(value, indent=2) + '\n')


def prepare_runtime(manifest, target):
    base = read_json(manifest)
    source = Path(base['root'])
    require(sha256(source / 'jac/jaclang/data/impl/pgwire.impl.jac') == base['files']['jac/jaclang/data/impl/pgwire.impl.jac'], 'Pinned base driver differs')
    require(target.is_relative_to(OWN), 'Owned hardlink overlay only')
    if target.exists():
        require(target.is_dir() and not target.is_symlink(), 'Existing diagnostic overlay is not an owned directory')
        expected_driver = transform((source / 'jac/jaclang/data/impl/pgwire.impl.jac').read_text())
        require((target / 'jac/jaclang/data/impl/pgwire.impl.jac').read_text() == expected_driver, 'Reused diagnostic driver differs')
        for helper in ('capture.py', 'explain.py'):
            require(sha256(target / 'jac' / helper) == sha256(OWN / helper), 'Reused diagnostic helper differs')
        return dict(root=str(target), base=reference(manifest), driver_before_sha256=sha256(source / 'jac/jaclang/data/impl/pgwire.impl.jac'), driver_after_sha256=sha256(target / 'jac/jaclang/data/impl/pgwire.impl.jac'), helpers={name:sha256(OWN/name) for name in ('capture.py','explain.py')}, method='Exact existing owned overlay reused after driver/helper equality; original failed evidence retained')
    shutil.copytree(source, target, copy_function=os.link)
    relative = Path('jac/jaclang/data/impl/pgwire.impl.jac')
    driver = target / relative
    original = driver.read_text()
    # DIRECT manifests preserve the exact driver checksum as an overlay output.
    before = sha256(driver)
    require(before == base['files'][str(relative)] == sha256(source / relative), 'Pinned DIRECT driver differs')
    replacement = driver.with_name(driver.name + '.diagnostic-tmp')
    replacement.write_text(transform(original))
    os.replace(replacement, driver)
    require(sha256(source / relative) == before, 'Immutable original driver changed')
    for name in ('capture.py', 'explain.py'):
        require(not (target / 'jac' / name).exists(), 'Helper collision')
        shutil.copyfile(OWN / name, target / 'jac' / name)
    proof = dict(root=str(target), base=reference(manifest), driver_before_sha256=before,
                 driver_after_sha256=sha256(driver), helpers={name: sha256(OWN / name) for name in ('capture.py', 'explain.py')},
                 method='Immutable hardlinks; atomic replacement breaks driver link; diagnostic Python helpers added')
    return proof


class Postgres(ParentPostgres):
    def __init__(self, directory, runtime, output, guard):
        self.directory = directory.resolve()
        require(self.directory.is_relative_to(OWN) and not self.directory.exists(), 'NEW owned diagnostic PG only')
        self.runtime, self.run_directory, self.source_guard = runtime, output, guard
        self.port, self.owner = free_port(), str(uuid.uuid4())
        self.started, self.databases, self.services = False, set(), []
        self.admin_process, self.context, self.statement_logging = None, None, False
        self.startup_floor, self.case_floor = 768 * 1024**2, 640 * 1024**2

    def sql(self, sql, database='postgres'):
        self.verify_owner()
        require(self.started, 'Diagnostic PG stopped')
        if self.admin_process is None:
            env = {**os.environ, 'TTG_RUNTIME_SOURCE': str(self.runtime),
                   'TTG_RUNTIME_CACHE': str(OWN / 'cache-admin-runtime'),
                   'TTG_CACHE_DIR': str(OWN / 'cache-admin-compiler')}
            for key in list(env):
                if key.startswith(('TTG_PERF_', 'TTG_DIAG_')):
                    env.pop(key)
            self.admin_log = (self.directory / 'admin.log').open('a')
            self.admin_process = subprocess.Popen(['bash', str(PREVIOUS / 'runtime.sh'), str(PREVIOUS / 'sql_admin.py'), '--port', str(self.port)],
                env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.admin_log, text=True, bufsize=1)
        self.admin_process.stdin.write(json.dumps(dict(database=database, sql=sql)) + '\n')
        self.admin_process.stdin.flush()
        while True:
            line = self.admin_process.stdout.readline()
            require(line, 'Owned diagnostic admin exited')
            if line.startswith('TTG_ADMIN_RESULT='):
                result = json.loads(line[len('TTG_ADMIN_RESULT='):])
                break
            self.admin_log.write(line)
            self.admin_log.flush()
        require(result['ok'], result.get('error', 'Admin SQL error'))
        rows = result['rows']
        if not rows:
            return ''
        scalar = rows[0][0]
        return scalar if isinstance(scalar, str) else (json.dumps(scalar) if scalar is None or isinstance(scalar, (dict, list, bool)) else str(scalar))

    def accept_completed(self, case, cell, name, directory, proof, expected):
        captures = list((directory / 'captures').glob('*.json'))
        wanted = [t for t in self.selection['targets'] if t['config_id'] == cell]
        require(len(captures) == len(wanted) == 1, 'Exactly one selected recursive query per workflow')
        capture = read_json(captures[0])
        require(capture['target'] == wanted[0], 'Selected target mismatch')
        target = wanted[0]
        calls = list(load_unsealed(directory, 'server-*.calls.jsonl*'))
        completed = [c for c in calls if c.get('origin_request_id') == target['request']
            and str(c.get('server_generation')) == str(target['generation'])
            and c.get('sql') == capture['wire']['positional_sql']
            and c.get('backend_pid') == capture['state']['context'][0][2]
            and c.get('role') == target['role'] and c.get('error') is None
            and c.get('sendall_returned') is True and c.get('ready_messages') == 1]
        require(len(completed) == 1 and completed[0]['returned_rows'] == 1000, 'Actual original selected query did not complete with1000 rows')
        require(capture['state']['statistics'] == capture['state']['statistics_after_explain'], 'Column statistics changed during selected EXPLAIN')
        accepted = dict(passed=True, target=target, capture=reference(captures[0]), actual_call=completed[0],
                        full_workflow_oracle_passed=True, primary_measurement=False,
                        explanation='Plans accepted only after full native workflow, restart and scalar/ordered response checks')
        write(directory / 'diagnostic-acceptance.json', accepted)
        seal = dict(passed=True, files={str(p.relative_to(directory)): sha256(p) for p in directory.rglob('*') if p.is_file() and p.name != 'artifacts.json'})
        write(directory / 'artifacts.json', seal)
        super().accept_completed(case, cell, name, directory, proof, expected)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--selection', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--cluster', type=Path, required=True)
    args = parser.parse_args()
    output, cluster = args.output.resolve(), args.cluster.resolve()
    require(output.is_relative_to(EVIDENCE) and not output.exists(), 'NEW owned evidence output only')
    require(cluster.is_relative_to(OWN) and not cluster.exists(), 'NEW owned PG cluster only')
    plan, selection = read_json(args.plan), read_json(args.selection)
    require(selection['purpose'] == 'matched_ll1000_read_only_diagnostic', 'Selection purpose')
    require(selection['plan'] == reference(args.plan), 'Selection plan binding')
    require([t['config_id'] for t in selection['targets']] == ['baseline850', 'next'], 'Exact two targets')
    require(len({t['target_id'] for t in selection['targets']}) == 2, 'Unique targets required')
    sources = [*sorted(OWN.glob('*.py')), args.selection.resolve()]
    hashes = {str(p): sha256(p) for p in sources}
    def guard():
        require(all(sha256(Path(p)) == h for p, h in hashes.items()), 'Diagnostic source changed')
    output.mkdir()
    (output / 'cases').mkdir()
    write(output / 'sources.json', dict(files=hashes, plan=reference(args.plan), primary_source_manifest=plan['sources']))
    runtimes = {}
    for cell in ('baseline850', 'next'):
        overlay = Path(plan['runtimes'][cell]['overlay']['path'])
        require(reference(overlay) == plan['runtimes'][cell]['overlay'], 'Frozen DIRECT manifest changed')
        value = prepare_runtime(overlay, OWN / ('runtime-' + cell + '-v1'))
        path = output / ('runtime-' + cell + '-overlay.json')
        write(path, value)
        runtimes[cell] = path
    trial = Trial()
    admin = Path(read_json(plan['runtimes']['baseline850']['clean']['path'])['root'])
    pg = Postgres(cluster, admin, output, guard)
    pg.selection = selection
    base_case = next(c for c in plan['correctness_schedule'] if c['case_id'] == 'linked_list1000' and c['config_id'] == 'off')
    env_keys = ('TTG_DIAG_SELECTION', 'TTG_DIAG_CONFIG_ID', 'TTG_DIAG_OUTPUT')
    saved = {key: os.environ.get(key) for key in env_keys}
    write(output / 'launch.json', dict(creator_pid=os.getpid(), plan=reference(args.plan), selection=reference(args.selection), primary_measurement=False))
    expected = None
    try:
        with pg:
            for cell in ('baseline850', 'next'):
                guard()
                case = {**base_case, 'config_id': cell, 'phase': 'diagnostic', 'trial_id': 'linked_list1000-' + cell + '-diagnostic'}
                directory = output / 'cases' / case['trial_id']
                os.environ.update(TTG_DIAG_SELECTION=str(args.selection.resolve()), TTG_DIAG_CONFIG_ID=cell, TTG_DIAG_OUTPUT=str(directory / 'captures'))
                pg.context = dict(directory=directory, case=case, cell=cell, source_manifest=plan['sources'])
                trial.run(case, cell, directory, pg, Path(plan['runtimes'][cell]['clean']['path']), runtimes[cell], expected)
                if expected is None:
                    expected = read_json(pg.context['result']['proof']['path'])
        guard()
        write(output / 'result.json', dict(passed=True, workflows=2, selected_queries=2, explain_plans=4, primary_measurement=False))
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        status = subprocess.run([str(BIN / 'pg_ctl'), '-D', str(cluster / 'data'), 'status'], capture_output=True, text=True)
        write(output / 'lifecycle.json', dict(services_stopped=all(p.poll() is not None for p in pg.services), pg_ctl_status=status.returncode,
            pidfile=(cluster / 'data/postmaster.pid').exists(), retained_databases=sorted(pg.databases),
            services=[dict(pid=p.pid, exit_code=p.poll()) for p in pg.services], free_bytes=shutil.disk_usage(OWN).free))


if __name__ == '__main__':
    main()
