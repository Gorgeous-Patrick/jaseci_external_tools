"""One explicitly marked owned cluster; SQL-only removal of owned databases."""
import csv
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import time
import uuid

BIN = Path('/home/baichuan/.cache/jac/pg/dist/linux-amd64-18.6.0/bin')

def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]

class OwnedPostgres:
    def __init__(self, directory, statement_logging=False):
        self.directory = Path(directory).resolve()
        self.port = free_port()
        self.owner = str(uuid.uuid4())
        self.started = False
        self.databases = set()
        self.audit = self.directory / 'ownership-and-cleanup.jsonl'
        self.statement_logging = statement_logging
        self.admin_process = None

    def record(self, action, **fields):
        with self.audit.open('a') as file:
            file.write(json.dumps(dict(action=action, owner=self.owner, time_ns=time.time_ns(), **fields)) + '\n')

    def __enter__(self):
        if shutil.disk_usage(self.directory.parent).free < 4 * 1024**3:
            raise RuntimeError('Storage guard: need at least 4 GiB free before cluster start')
        self.directory.mkdir(exist_ok=False)
        (self.directory / 'owner.json').write_text(json.dumps(dict(owner=self.owner, kind='ttg-performance-only', pid=os.getpid())))
        with (self.directory / 'init.log').open('w') as log:
            subprocess.run([str(BIN / 'initdb'), '-D', str(self.directory / 'data'), '-U', 'ttgperf',
                '-A', 'trust', '--no-locale', '--encoding=UTF8'], stdout=log, stderr=subprocess.STDOUT, check=True)
        with (self.directory / 'data/postgresql.conf').open('a') as config:
            config.write("\nlog_destination='csvlog'\nlogging_collector=on\nlog_directory='logs'\nlog_filename='postgresql.log'\n")
            config.write("log_statement='all'\n" if self.statement_logging else "log_statement='none'\n")
        subprocess.run([str(BIN / 'pg_ctl'), '-D', str(self.directory / 'data'),
            '-l', str(self.directory / 'startup.log'), '-o',
            f'-h 127.0.0.1 -p {self.port} -k /tmp', '-w', 'start'], check=True)
        self.started = True
        self.record('cluster_started', port=self.port, statement_logging=self.statement_logging,
            cluster_bytes=sum(p.stat().st_size for p in self.directory.rglob('*') if p.is_file()))
        return self

    def sql(self, sql, database='postgres'):
        self.verify_owner()
        if self.admin_process is None:
            own = Path(__file__).resolve().parent
            self.admin_log = (self.directory / 'admin.log').open('w')
            environment = {**os.environ, 'TTG_RUNTIME_SOURCE': str(own / 'runtime-5f94eb62d-v2')}
            self.admin_process = subprocess.Popen(['bash', str(own / 'runtime.sh'), str(own / 'sql_admin.py'),
                '--port', str(self.port)], env=environment, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=self.admin_log, text=True, bufsize=1)
        self.admin_process.stdin.write(json.dumps({'database': database, 'sql': sql}) + '\n')
        self.admin_process.stdin.flush()
        while True:
            line = self.admin_process.stdout.readline()
            if not line:
                raise RuntimeError(f'Owned SQL admin exited; see {self.directory / "admin.log"}')
            if line.startswith('TTG_ADMIN_RESULT='):
                result = json.loads(line[len('TTG_ADMIN_RESULT='):])
                break
            self.admin_log.write(line)
            self.admin_log.flush()
        if not result['ok']:
            raise RuntimeError(result['error'])
        rows = result['rows']
        if not rows:
            return ''
        value = rows[0][0]
        # Preserve the existing textual scalar contract, including count=0.
        # JSON aggregates may be returned as raw text or decoded Python values.
        if isinstance(value, str):
            return value
        if isinstance(value, (dict, list, bool)) or value is None:
            return json.dumps(value)
        return str(value)

    def verify_owner(self):
        value = json.loads((self.directory / 'owner.json').read_text())
        if value.get('owner') != self.owner:
            raise RuntimeError('Cluster ownership changed; refuse operation')

    def create_database(self):
        name = 'perf_' + uuid.uuid4().hex
        self.sql(f'CREATE DATABASE {name}')
        self.databases.add(name)
        self.record('database_created', database=name)
        return name

    def drop_completed_database(self, name, artifacts_manifest, server_stopped):
        self.verify_owner()
        if name not in self.databases or not name.startswith('perf_') or not server_stopped:
            raise RuntimeError('Database not owned or application service not stopped')
        if not Path(artifacts_manifest).is_file():
            raise RuntimeError('Archive manifest must exist before dropping completed database')
        active = self.sql(f"SELECT count(*) FROM pg_stat_activity WHERE datname='{name}'")
        if active != '0':
            raise RuntimeError('Database still has active sessions; refuse cleanup')
        self.sql(f'DROP DATABASE {name}')
        self.databases.remove(name)
        self.record('completed_database_dropped', database=name, artifacts_manifest=str(artifacts_manifest), active_sessions=0)

    def __exit__(self, *args):
        self.verify_owner()
        if self.admin_process is not None:
            self.admin_process.stdin.close()
            try:
                self.admin_process.wait(timeout=20)
            except subprocess.TimeoutExpired:
                self.admin_process.terminate()
                self.admin_process.wait(timeout=10)
            self.admin_log.close()
            self.record('admin_service_stopped', exit_code=self.admin_process.returncode)
        if self.started:
            subprocess.run([str(BIN / 'pg_ctl'), '-D', str(self.directory / 'data'), '-m', 'fast', '-w', 'stop'], check=True)
            self.started = False
            self.record('cluster_stopped', failed_databases_preserved=sorted(self.databases))
        # No filesystem deletion. At most one retained cluster per experiment.
