"""Synthetic ownership/admin lifecycle checks; no application workloads."""
import json
from pathlib import Path
import subprocess
from owned_postgres import OwnedPostgres

def validate(out):
    own = Path(__file__).resolve().parent
    results = {}
    with OwnedPostgres(out / 'postgres') as postgres:
        db = postgres.create_database()
        assert postgres.sql('SELECT 0') == '0'
        results['zero_scalar_preserved'] = True
        actual = json.loads(postgres.sql("SELECT json_agg(json_build_object('value',i)) FROM generate_series(1,3) g(i)", db))
        assert actual == [{'value': 1}, {'value': 2}, {'value': 3}]
        results['json_census_preserved'] = True
        assert postgres.sql(f"SELECT count(*) FROM pg_stat_activity WHERE datname='{db}'") == '0'
        results['query_target_connection_closed'] = True
        manifest = out / 'synthetic-artifacts.json'
        manifest.write_text(json.dumps({'fixture': actual, 'passed': True}))
        try:
            postgres.drop_completed_database('postgres', manifest, True)
            raise AssertionError('Unowned database drop was allowed')
        except RuntimeError as error:
            assert 'not owned' in str(error)
        try:
            postgres.drop_completed_database(db, out / 'absent.json', True)
            raise AssertionError('Unarchived database drop was allowed')
        except RuntimeError as error:
            assert 'manifest' in str(error)
        with (out / 'lease.log').open('w') as log:
            lease = subprocess.Popen(['bash', str(own / 'runtime.sh'), str(own / 'sql_admin.py'),
                '--port', str(postgres.port), '--lease', db], stdin=subprocess.PIPE,
                stdout=subprocess.PIPE, stderr=log, text=True)
            try:
                while True:
                    line = lease.stdout.readline()
                    assert line, 'Lease helper exited unexpectedly'
                    if line.startswith('TTG_ADMIN_LEASE_READY'):
                        break
                assert postgres.sql(f"SELECT count(*) FROM pg_stat_activity WHERE datname='{db}'") == '1'
                try:
                    postgres.drop_completed_database(db, manifest, True)
                    raise AssertionError('Active database drop was allowed')
                except RuntimeError as error:
                    assert 'active sessions' in str(error)
                results['active_session_drop_refused'] = True
            finally:
                lease.stdin.close()
                lease.wait(timeout=10)
        try:
            postgres.drop_completed_database(db, manifest, False)
            raise AssertionError('Running app service drop was allowed')
        except RuntimeError as error:
            assert 'service not stopped' in str(error)
        postgres.drop_completed_database(db, manifest, True)
        assert postgres.sql(f"SELECT count(*) FROM pg_database WHERE datname='{db}'") == '0'
        results['completed_owned_database_dropped'] = True
        failed = postgres.create_database()
        try:
            postgres.sql('SELECT definitely_missing_column', failed)
            raise AssertionError('Expected synthetic failure')
        except RuntimeError as error:
            assert 'PgWireError' in str(error)
        assert failed in postgres.databases
        assert postgres.sql(f"SELECT count(*) FROM pg_database WHERE datname='{failed}'") == '1'
        postgres.record('synthetic_failure_preserved', database=failed)
        results['failed_database_preserved'] = failed
        results['passed'] = True
    results['services_stopped'] = postgres.started is False and postgres.admin_process.poll() is not None
    (out / 'admin-validation.json').write_text(json.dumps(results, indent=2) + '\n')
    print(json.dumps(results, indent=2))
