"""Small matched SQL-only diagnostic; no application timing claim."""
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import statistics
import subprocess
import time
from unittest.mock import patch
from uuid import UUID

ROOT = Path('/home/baichuan/jaseci')
OUT = ROOT / 'project-notes/measurements/ttg-standard-access-20261109/sql-v1'
PG = ROOT / 'reproduction/ttg-standard-access-20261109/pg-sql-v1'
BIN = Path('/home/baichuan/.cache/jac/pg/dist/linux-amd64-18.6.0/bin')


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def save(name, data):
    (OUT / name).write_text(json.dumps(data, indent=2, default=str) + '\n')




def compare(app, capture_path, port):
    from jaclang.data.pgwire import PgWireConnection, _named_to_positional, _encode_param
    from jaclang.runtime.ttg_region_dag import compile_dag_sql
    from jaclang.runtime.ttg_output_tree import compile_tree_sql
    import jaclang.runtime.ttg_fusion_sql as fusion
    capture = json.loads(capture_path.read_text())
    bundle_path = ROOT / f'jaseci_external_tools/ttg_visualizer/public/data/{app}.json'
    cert = json.loads(bundle_path.read_text())['compiler']['plan']['interability_regions']['regions']['0']
    build = (lambda: compile_dag_sql(cert['rules'], True)) if app == 'littlex' else (lambda: compile_tree_sql(cert, True))
    from types import SimpleNamespace
    baseline_path = ROOT / ('project-notes/measurements/ttg-type-pruning-20261107/run-v1/' + app + '.json')
    baseline = json.loads(baseline_path.read_text())
    assert baseline['passed']
    old = baseline['sql']['after']
    before = SimpleNamespace(sql=old['text'], params=old['params'])
    after = build()
    original = {k: None if v is None else base64.b64decode(v).decode()
                for k, v in zip(capture['parameter_names'], capture['wire']['parameters_base64'])}
    positional, values = _named_to_positional(capture['original_sql'], original)
    assert positional == capture['wire']['positional_sql']
    assert [None if v is None else base64.b64encode(_encode_param(v)).decode() for v in values] == capture['wire']['parameters_base64']
    slots = {k: (UUID(original[k]) if k in ('origin', 'actor_uuid') else
                 int(original[k]) if k == 'row_limit' else original[k])
             for k in ('origin', 'actor_uuid', 'actor_text', 'row_limit', 'node_module') if k in original}
    variants = {'before': before, 'after': after.bind(slots)}
    admin = PgWireConnection(user='ttgperf', host='127.0.0.1', port=port, database='postgres')
    admin.run('CREATE DATABASE type_pruning_' + app)
    admin.close()
    c = PgWireConnection(user='ttgperf', host='127.0.0.1', port=port, database='type_pruning_' + app)
    result = dict(app=app, baseline_sql_evidence=str(baseline_path), baseline_sha256=sha(baseline_path), capture=str(capture_path), capture_sha256=sha(capture_path),
                  compiler_bundle=str(bundle_path), compiler_bundle_sha256=sha(bundle_path),
                  anchors=len(capture['state']['anchors']), samples=[], passed=False,
                  regime='Matched restored captured state, explicit ANALYZE, SERIALIZABLE READ ONLY; 3 excluded + 21 measured alternating pairs; SQL-only warmed EXPLAIN')
    try:
        schema_path = ROOT / 'jac-ttg/jac/jaclang/data/impl/store.impl.jac'
        source = schema_path.read_text().split('impl ConnInfo.dsn')[0]
        for ddl in re.findall(r'"""(.*?)"""', source, re.S):
            if re.search(r'CREATE TABLE IF NOT EXISTS (anchors|graph_types)\b|ON anchors\b', ddl):
                c.run(ddl)
        c.run('BEGIN')
        for row in capture['state']['anchors']:
            c.run('INSERT INTO anchors(id,seq,kind,arch_type,arch_module,root_id,src,dst,undirected,props) '
                  'VALUES(CAST(:v0 AS uuid),CAST(:v1 AS bigint),:v2,:v3,:v4,CAST(:v5 AS uuid),'
                  'CAST(:v6 AS uuid),CAST(:v7 AS uuid),CAST(:v8 AS boolean),CAST(:v9 AS jsonb))',
                  **{f'v{i}': v for i, v in enumerate(row)})
        for name, ancestor in capture['state']['graph_types']:
            c.run('INSERT INTO graph_types VALUES(:name,:ancestor)', name=name, ancestor=ancestor)
        c.run('COMMIT')
        def normalize(rows):
            return [list(r[:9]) + [json.loads(r[9]) if isinstance(r[9], str) else r[9]] for r in rows]
        assert normalize(c.run('SELECT id,seq,kind,arch_type,arch_module,root_id,src,dst,undirected,props FROM anchors ORDER BY seq,id')) == normalize(capture['state']['anchors'])
        assert [list(r) for r in c.run('SELECT type_name,ancestor FROM graph_types ORDER BY type_name,ancestor')] == capture['state']['graph_types']
        c.run('ANALYZE anchors'); c.run('ANALYZE graph_types')
        result['indexes'] = c.run("SELECT indexname,indexdef FROM pg_indexes WHERE schemaname='public' ORDER BY indexname")
        result['server_version'] = c.run('SHOW server_version')[0][0]
        c.run('BEGIN ISOLATION LEVEL SERIALIZABLE READ ONLY')
        c.run("SET LOCAL statement_timeout='10s'")
        captured = c.run(capture['original_sql'], **original)
        expected = [r for r in captured if int(r[0]) != -1] if app == 'littlex' else captured
        result['returned_rows'] = len(expected)
        result['removed_catalog_rows'] = len(captured) - len(expected)
        result['sql'] = {name: dict(text=x.sql, params=x.params, characters=len(x.sql)) for name,x in variants.items()}
        for repeat in range(24):
            names = ['before', 'after'] if repeat % 2 == 0 else ['after', 'before']
            for name in names:
                x = variants[name]
                actual = c.run(x.sql, **x.params)
                if name == 'before':
                    assert actual == captured
                    if app == 'littlex': actual = [r for r in actual if int(r[0]) != -1]
                assert actual == expected, (app, name, 'ordered result mismatch')
                raw = c.run('EXPLAIN (ANALYZE,BUFFERS,FORMAT JSON) ' + x.sql, **x.params)[0][0]
                plan = (json.loads(raw) if isinstance(raw, str) else raw)[0]
                result['samples'].append(dict(variant=name, repeat=repeat, warmup=repeat < 3,
                    planning_ms=plan['Planning Time'], execution_ms=plan['Execution Time'], plan=plan))
        c.run('ROLLBACK')
        result['summary'] = {}
        for name in variants:
            rows = [r for r in result['samples'] if r['variant'] == name and not r['warmup']]
            result['summary'][name] = {k: dict(median=statistics.median(r[k] for r in rows),
                min=min(r[k] for r in rows), max=max(r[k] for r in rows)) for k in ('planning_ms', 'execution_ms')}
        result['passed'] = True
    finally:
        c.close()
        save(app + '.json', result)
    print(json.dumps(dict(app=app, rows=result['returned_rows'], summary=result['summary'])), flush=True)


if __name__ == '__main__':
    import jaclang
    import jaclang.sql as q
    assert not OUT.exists() and not PG.exists()
    OUT.mkdir(parents=True); PG.mkdir(parents=True)
    paths = [ROOT / ('jac-ttg/jac/jaclang/runtime/' + n) for n in
             ('ttg_fusion_sql.jac','ttg_sql.jac','ttg_region_dag.jac','ttg_output_tree.py')]
    hashes = {str(p): sha(p) for p in paths}
    save('source.json', dict(files=hashes, script_sha256=sha(__file__)))
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0)); port = s.getsockname()[1]
    save('owner.json', dict(pid=os.getpid(), port=port, data=str(PG/'data')))
    started = False
    try:
        with (OUT/'init.log').open('w') as log:
            subprocess.run([str(BIN/'initdb'), '-D', str(PG/'data'), '-U', 'ttgperf', '-A', 'trust', '--no-locale', '--encoding=UTF8'], stdout=log, stderr=subprocess.STDOUT, check=True)
        with (PG/'data/postgresql.conf').open('a') as f:
            f.write("\nshared_buffers='64MB'\nmax_connections=10\nmin_wal_size='32MB'\nmax_wal_size='64MB'\nlog_statement='none'\n")
        subprocess.run([str(BIN/'pg_ctl'), '-D', str(PG/'data'), '-l', str(OUT/'postgres.log'), '-o', f'-h127.0.0.1 -p{port} -k/tmp', '-w', 'start'], check=True)
        started = True
        compare('littlex', ROOT/'project-notes/measurements/ttg-portfolio-sql-diagnostics-20261104/run-v2/cases/littlex-thread-sql/captures/littlex-thread-cb1a80fb-pid387335.json', port)
        compare('jdrive', ROOT/'project-notes/measurements/ttg-jdrive-freethreaded-20261103/sql-diagnostic-v2/cases/jdrive-thread-diagnostic/captures/thread-first-tree-pid3245993.json', port)
        assert hashes == {str(p): sha(p) for p in paths}
    finally:
        stop = subprocess.run([str(BIN/'pg_ctl'), '-D', str(PG/'data'), '-m', 'fast', '-w', 'stop'], capture_output=True, text=True) if started else None
        status = subprocess.run([str(BIN/'pg_ctl'), '-D', str(PG/'data'), 'status'], capture_output=True, text=True)
        save('stopped.json', dict(status=status.returncode, pidfile=(PG/'data/postmaster.pid').exists(), stop_code=stop.returncode if stop else None, finished_ns=time.time_ns()))
