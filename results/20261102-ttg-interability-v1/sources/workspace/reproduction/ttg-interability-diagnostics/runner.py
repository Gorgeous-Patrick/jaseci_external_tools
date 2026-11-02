"""Exactly two matched LL1000 workflows and four same-connection EXPLAIN plans."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import uuid

OWN = Path(__file__).resolve().parent
ROOT = OWN.parents[1]
PRIMARY = OWN.parent / 'ttg-interability-performance'
EVIDENCE = ROOT / 'project-notes/measurements/ttg-interability-diagnostics-20261102'
sys.path.insert(0, str(PRIMARY))
from ia_interop import require, read_json, reference, sha256, verify_case
import ia_trial
from ia_trial import Trial, load_unsealed
from ia_postgres import OwnedPostgres as ParentPostgres
from ia_config import PREVIOUS
from ia_runner import storage_watch
from owned_postgres import BIN, free_port
from overlay import transform
from diagnostic_storage import compress_closed_traces
from binding import native_user_root


def write(path, value):
    Path(path).write_text(json.dumps(value, indent=2) + '\n')


def checked(value):
    path = Path(value['path'])
    require(reference(path) == value, 'Input reference changed: ' + str(path))
    return path


def prepare_runtime(manifest, target):
    base = read_json(manifest)
    source = Path(base['root'])
    relative = Path('jac/jaclang/data/impl/pgwire.impl.jac')
    before = sha256(source / relative)
    require(before == base['files'][str(relative)], 'Frozen DIRECT driver differs')
    require(target.is_relative_to(OWN) and not target.exists(), 'NEW owned hardlink overlay required')
    shutil.copytree(source, target, copy_function=os.link)
    driver = target / relative
    replacement = driver.with_name(driver.name + '.diagnostic-tmp')
    replacement.write_text(transform(driver.read_text()))
    os.replace(replacement, driver)
    require(sha256(source / relative) == before, 'Immutable primary driver changed')
    for name in ('capture.py', 'explain.py'):
        require(not (target / 'jac' / name).exists(), 'Diagnostic helper collision')
        shutil.copyfile(OWN / name, target / 'jac' / name)
    return dict(root=str(target), base=reference(manifest), driver_before_sha256=before,
                driver_after_sha256=sha256(driver), helpers={n:sha256(OWN/n) for n in ('capture.py','explain.py')},
                method='Immutable hardlinks; atomic copied-driver replacement; unchanged native trial/ANALYZE/oracles')


class Postgres(ParentPostgres):
    def __init__(self, directory, runtime, output, guard):
        # Establish a new ownership namespace without changing the primary class globals.
        self.directory = Path(directory).resolve()
        require(self.directory.is_relative_to(OWN) and not self.directory.exists(), 'NEW owned diagnostic PG required')
        self.runtime, self.run_directory, self.source_guard = Path(runtime), Path(output), guard
        self.port, self.owner = free_port(), str(uuid.uuid4())
        self.started, self.databases, self.services = False, set(), []
        self.admin_process, self.context, self.statement_logging = None, None, False
        self.startup_floor, self.case_floor = 768 * 1024**2, 640 * 1024**2

    def sql(self, sql, database='postgres'):
        self.verify_owner()
        require(self.started, 'Diagnostic PG stopped')
        if self.admin_process is None:
            env = {**os.environ, 'TTG_RUNTIME_SOURCE':str(self.runtime),
                   'TTG_RUNTIME_CACHE':str(OWN/'cache-admin-runtime'), 'TTG_CACHE_DIR':str(OWN/'cache-admin-compiler')}
            for name in list(env):
                if name.startswith(('TTG_PERF_', 'TTG_DIAG_')):
                    env.pop(name)
            self.admin_log = (self.directory/'admin.log').open('a')
            self.admin_process = subprocess.Popen(['bash',str(PREVIOUS/'runtime.sh'),str(PREVIOUS/'sql_admin.py'),'--port',str(self.port)],
                env=env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=self.admin_log,text=True,bufsize=1)
        self.admin_process.stdin.write(json.dumps(dict(database=database,sql=sql))+'\n')
        self.admin_process.stdin.flush()
        while True:
            line = self.admin_process.stdout.readline()
            require(line, 'Owned admin exited')
            if line.startswith('TTG_ADMIN_RESULT='):
                result = json.loads(line[len('TTG_ADMIN_RESULT='):])
                break
            self.admin_log.write(line)
            self.admin_log.flush()
        require(result['ok'], result.get('error','Admin SQL failed'))
        rows = result['rows']
        if not rows:
            return ''
        value = rows[0][0]
        return value if isinstance(value,str) else (json.dumps(value) if value is None or isinstance(value,(dict,list,bool)) else str(value))

    def accept_completed(self, case, cell, name, directory, proof, expected):
        wanted = [t for t in self.selection['targets'] if t['config_id']==cell]
        captures = list((directory/'captures').glob('*.json'))
        require(len(wanted)==len(captures)==1, 'Exactly one unique selected capture required per workflow')
        capture = read_json(captures[0])
        require(capture['target']==wanted[0], 'Capture target differs')
        target = wanted[0]
        calls = list(load_unsealed(directory,'server-*.calls.jsonl*'))
        completed = [c for c in calls if c.get('origin_request_id')==target['request']
            and str(c.get('server_generation'))==str(target['generation'])
            and c.get('role')==target['role'] and c.get('sql')==capture['wire']['positional_sql']
            and c.get('backend_pid')==capture['state']['context'][0][2]
            and c.get('error') is None and c.get('sendall_returned') is True and c.get('ready_messages')==1]
        require(len(completed)==1 and completed[0]['returned_rows']==1000, 'Original selected query did not complete with1000rows')
        import base64
        from uuid import UUID
        bound = dict(zip(capture['parameter_names'], capture['wire']['parameters_base64']))
        mapping = read_json(directory/'mapping-initial.json')
        require(all(name in bound for name in ('origin','actor_uuid','actor_text')), 'Reviewed origin/actor slots missing')
        decode = lambda name: base64.b64decode(bound[name],validate=True).decode('utf-8')
        require(UUID(decode('origin'))==UUID(mapping['item:0']), 'Captured origin differs from actual fixture item:0')
        http_rows = [json.loads(line) for line in (directory/'http-raw.jsonl').open() if line.strip()]
        actor, root_lineage = native_user_root(http_rows)
        require(UUID(decode('actor_uuid'))==actor and UUID(decode('actor_text'))==actor, 'Captured ACL actor differs from actual native user root')
        origin_rows = [row for row in capture['state']['anchors'] if UUID(str(row[0]))==UUID(mapping['item:0'])]
        require(len(origin_rows)==1 and origin_rows[0][2]=='NodeAnchor' and UUID(str(origin_rows[0][5]))==actor, 'Captured origin ownership differs from actual auth root')

        require(capture['state']['statistics']==capture['state']['statistics_after_explain'], 'Column statistics changed during inline plans')
        normalization = read_json(directory/'planner-statistics-before-workflow.json')
        require(normalization['commands']==['ANALYZE anchors','ANALYZE graph_types'] and normalization['passed'], 'Current statistics boundary absent')
        require(len(capture['explain']['repetitions'])==2, 'Exactly first/repeated EXPLAIN required')
        write(directory/'diagnostic-acceptance.json',dict(passed=True,target=target,capture=reference(captures[0]),
            actual_call=completed[0],binding_identity=dict(origin='item:0',actor='SuiteRoot report/SuiteImport roots[user:0]',native_root_lineage=root_lineage,matches_actual_mapping=True,mapping=reference(directory/'mapping-initial.json'),http=reference(directory/'http-raw.jsonl')),normalization=reference(directory/'planner-statistics-before-workflow.json'),
            full_workflow_oracle_passed=True,primary_measurement=False,
            explanation='Plans provisional until original completion and unchanged full native oracle/restart/physical acceptance'))
        write(directory/'artifacts.json',dict(passed=True,files={str(p.relative_to(directory)):sha256(p)
            for p in directory.rglob('*') if p.is_file() and p.name!='artifacts.json'}))
        super().accept_completed(case,cell,name,directory,proof,expected)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('plan','selection','output','cluster'):
        parser.add_argument('--'+name,type=Path,required=True)
    args = parser.parse_args()
    output, cluster = args.output.resolve(), args.cluster.resolve()
    require(output.is_relative_to(EVIDENCE) and not output.exists(), 'NEW diagnostic output required')
    require(cluster.is_relative_to(OWN) and not cluster.exists(), 'NEW diagnostic cluster required')
    plan, selection = read_json(args.plan), read_json(args.selection)
    require(selection['purpose']=='matched_ll1000_read_only_diagnostic' and selection['plan']==reference(args.plan), 'Selection/plan differs')
    require([t['config_id'] for t in selection['targets']]==['baseline9282','interability'], 'Exactly the two approved versions required')
    require(len({t['target_id'] for t in selection['targets']})==2, 'Unique selected targets required')
    for target in selection['targets']:
        require(target['request']=='2:5' and str(target['generation'])=='2' and target['occurrence']==1
                and target['role']=='foreground' and target['read_only_source_reviewed'] is True, 'Exact bounded query selection differs')
    checked(selection['source_targets'])
    # Main checks the final selection/raw-review binding before issuing the run command.
    borrowed = [PRIMARY/name for name in ('ia_trial.py','ia_postgres.py','ia_statistics.py','ia_semantic.py','ia_storage.py','ia_config.py','ia_interop.py','ia_metrics.py','ia_runner.py','serve.py','compact_observer.py')]
    sources = [*sorted(OWN.glob('*.py')),*borrowed,args.selection.resolve()]
    hashes = {str(p):sha256(p) for p in sources}
    def guard():
        require(all(sha256(Path(p))==h for p,h in hashes.items()), 'Diagnostic/imported helper source changed')
    output.mkdir()
    (output/'cases').mkdir()
    write(output/'sources.json',dict(files=hashes,plan=reference(args.plan),primary_source_manifest=plan['sources']))
    runtimes = {}
    for mode in ('baseline9282','interability'):
        original = checked(plan['runtimes'][mode]['overlay'])
        overlay = prepare_runtime(original,OWN/('runtime-'+mode+'-v1'))
        path = output/('runtime-'+mode+'-overlay.json')
        write(path,overlay)
        runtimes[mode] = path
    trial = Trial()
    admin = Path(read_json(checked(plan['runtimes']['baseline9282']['clean']))['root'])
    pg = Postgres(cluster,admin,output,guard)
    pg.selection = selection
    base = next(c for c in plan['correctness_schedule'] if c['case_id']=='finite_list1000' and c['config_id']=='off')
    env_names = ('TTG_DIAG_SELECTION','TTG_DIAG_CONFIG_ID','TTG_DIAG_OUTPUT')
    saved = {key:os.environ.get(key) for key in env_names}
    old_own, old_compressor = ia_trial.OWN, ia_trial.compress_closed_traces
    ia_trial.OWN, ia_trial.compress_closed_traces = OWN, compress_closed_traces
    write(output/'launch.json',dict(creator_pid=os.getpid(),plan=reference(args.plan),selection=reference(args.selection),
        primary_measurement=False,root_redirect='Only this controller process redirects trial serve/cache paths to the NEW diagnostic namespace; source bytes unchanged'))
    results = []
    try:
        with pg:
            for mode in ('baseline9282','interability'):
                guard()
                case = {**base,'config_id':mode,'phase':'diagnostic','trial_id':'finite_list1000-'+mode+'-diagnostic'}
                directory = output/'cases'/case['trial_id']
                os.environ.update(TTG_DIAG_SELECTION=str(args.selection.resolve()),TTG_DIAG_CONFIG_ID=mode,TTG_DIAG_OUTPUT=str(directory/'captures'))
                pg.context = dict(directory=directory,case=case,cell=mode,source_manifest=plan['sources'],prior_metrics={})
                primary = next(t for t in selection['targets'] if t['config_id']==mode)
                expected = read_json(checked(primary['native_proof']))
                with storage_watch(output,case,512*1024**2):
                    trial.run(case,mode,directory,pg,checked(plan['runtimes'][mode]['clean']),runtimes[mode],expected)
                results.append(dict(config_id=mode,result=pg.context['result']))
        guard()
        write(output/'result.json',dict(passed=True,workflows=2,selected_queries=2,explain_plans=4,
            primary_measurement=False,results=results))
    finally:
        ia_trial.OWN, ia_trial.compress_closed_traces = old_own, old_compressor
        for key,value in saved.items():
            if value is None:
                os.environ.pop(key,None)
            else:
                os.environ[key] = value
        status = subprocess.run([str(BIN/'pg_ctl'),'-D',str(cluster/'data'),'status'],capture_output=True)
        write(output/'lifecycle.json',dict(services_stopped=all(p.poll() is not None for p in pg.services),
            services=[dict(pid=p.pid,exit_code=p.poll()) for p in pg.services],pg_ctl_status=status.returncode,
            pidfile=(cluster/'data/postmaster.pid').exists(),retained_databases=sorted(pg.databases),free_bytes=shutil.disk_usage(OWN).free))


if __name__=='__main__':
    main()
