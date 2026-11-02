"""Build immutable DBGEN fixtures and all22 independent SQLite answers; no Jac DB."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess

ROOT = Path(__file__).resolve().parents[1]
UPSTREAM = ROOT / 'vendor/jac_tpch'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def reference_module():
    spec = importlib.util.spec_from_file_location('pinned_tpch_sql_oracle', UPSTREAM / 'generate_answers.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def prepare(output, scale='0.001'):
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    work, data = output / 'dbgen-build', output / 'tables'
    work.mkdir(); data.mkdir()
    source = UPSTREAM / 'tpch_small'
    for path in source.iterdir():
        if path.is_file() and (path.suffix in {'.c', '.h'} or path.name in {'makefile', 'dists.dss'}):
            shutil.copyfile(path, work / path.name)
    with (output / 'dbgen-build.log').open('w') as log:
        subprocess.run(['make', 'dbgen', 'MACHINE=LINUX', 'DATABASE=ORACLE', 'WORKLOAD=TPCH', 'CC=gcc'],
                       cwd=work, stdout=log, stderr=subprocess.STDOUT, check=True)
    env = {**os.environ, 'DSS_CONFIG': str(work), 'DSS_PATH': str(data)}
    with (output / 'dbgen.log').open('w') as log:
        subprocess.run([str(work / 'dbgen'), '-s', str(scale), '-f'], cwd=work,
                       env=env, stdout=log, stderr=subprocess.STDOUT, check=True)
    oracle = reference_module()
    oracle.DATA_DIR = data
    oracle.ANSWERS_DIR = output / 'answers'
    connection = sqlite3.connect(':memory:')
    try:
        for ddl, _, _ in oracle.SCHEMA.values():
            connection.execute(ddl)
        counts = {}
        for table, (_, filename, columns) in oracle.SCHEMA.items():
            oracle.load_tbl(connection, table, filename, columns)
            counts[table] = connection.execute('SELECT count(*) FROM ' + table).fetchone()[0]
        oracle.create_indexes(connection)
        queries = oracle.build_queries()
        cases = []
        for number in range(1, 23):
            sql, parameters = queries[number]
            rows = connection.execute(sql, parameters).fetchall()
            oracle.write_answer_file(number, rows)
            result = {'columns': oracle.QUERY_COLUMNS[number], 'rows': rows}
            result_path = output / f'q{number}.expected.json'
            result_path.write_text(json.dumps(result, indent=2) + '\n')
            query_path = output / f'q{number}.reference.sql'
            query_path.write_text(sql + '\n')
            cases.append({'case_id': f'tpch/Q{number}', 'parameters': parameters,
                          'sql': str(query_path), 'sql_sha256': sha(query_path),
                          'expected': str(result_path), 'expected_sha256': sha(result_path),
                          'rows': len(rows), 'nonempty': bool(rows)})
        manifest = {'schema_version': 1, 'benchmark': 'tpch', 'upstream_commit':
                    '685318b8105cecc629bca5c745dd08705d5fba7d', 'scale_factor': str(scale),
                    'fixture_seed': 'Pinned DBGEN 2.9 built-in deterministic seed vector; not an invented seed42',
                    'seed_source_sha256': sha(source / 'rnd.h'), 'request_seed': 4242,
                    'counts': counts, 'table_sha256': {p.name: sha(p) for p in sorted(data.glob('*.tbl'))},
                    'oracle_source_sha256': sha(UPSTREAM / 'generate_answers.py'),
                    'cases': cases, 'scope': 'All22 SQL reference queries on DBGEN tables; not native Jac execution or TPC-H qualification',
                    'native': 'pending', 'restart': 'pending', 'refresh_functions': 'excluded',
                    'numeric_contract': 'Inherited ordered comparator: abs <=0.02 or relative <=1e-4; null/scalar/order rules require explicit adapter checks',
                    'performance': 'not_authorized'}
        (output / 'fixture-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
        print(json.dumps({'tables': counts, 'oracle_cases': len(cases), 'empty_queries':
                         [c['case_id'] for c in cases if not c['nonempty']]}))
    finally:
        connection.close()
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--scale', default='0.001')
    args = parser.parse_args()
    prepare(args.output, args.scale)
