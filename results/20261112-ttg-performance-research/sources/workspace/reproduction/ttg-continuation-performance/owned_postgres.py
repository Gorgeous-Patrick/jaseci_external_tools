"""One owned cluster, one trial database at a time, sealed-success cleanup only."""
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import time
import uuid
from evidence import verify_case

OWN=Path(__file__).resolve().parent
EVIDENCE=OWN.parent.parent/'project-notes/measurements/ttg-continuation-performance-20261030'
BIN=Path('/home/baichuan/.cache/jac/pg/dist/linux-amd64-18.6.0/bin')


def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0));return sock.getsockname()[1]


def runtime_env(runtime,cache_tag):
    result={**os.environ,'TTG_RUNTIME_SOURCE':str(runtime),
        'TTG_RUNTIME_CACHE':str(OWN/('cache-'+cache_tag+'-runtime')),
        'TTG_CACHE_DIR':str(OWN/('cache-'+cache_tag+'-compiler'))}
    for key in list(result):
        if key.startswith('TTG_PERF_'): result.pop(key)
    return result


class OwnedPostgres:
    def __init__(self,directory,clean_runtime,statement_logging=False,resume_owner=None,resume_database=None):
        self.directory=Path(directory).resolve();self.runtime=Path(clean_runtime).resolve()
        if not self.directory.is_relative_to(OWN): raise ValueError('Only owned cluster directories allowed')
        self.port=free_port();self.owner=resume_owner or str(uuid.uuid4());self.started=False
        self.databases=set();self.services=[];self.admin_process=None
        self.statement_logging=statement_logging
        self.resume_database=resume_database

    def record(self,action,**fields):
        with (self.directory/'ownership-and-cleanup.jsonl').open('a') as file:
            file.write(json.dumps(dict(action=action,owner=self.owner,time_ns=time.time_ns(),**fields))+'\n')

    def verify_owner(self):
        value=json.loads((self.directory/'owner.json').read_text())
        if value['owner']!=self.owner: raise ValueError('Cluster ownership changed')

    def __enter__(self):
        if self.directory.exists():
            if not self.resume_database:raise ValueError('Existing cluster requires explicit validated resume evidence')
            self.verify_owner()
            if not re.fullmatch(r'continuation_[0-9a-f]{32}',self.resume_database):raise ValueError('Invalid resumed owned DB')
            status=subprocess.run([str(BIN/'pg_ctl'),'-D',str(self.directory/'data'),'status'],capture_output=True)
            if status.returncode==0:raise ValueError('Existing owned cluster still running')
            self.databases.add(self.resume_database)
            self.record('existing_owned_database_resumed',database=self.resume_database,
                caller_must_verify_equivalent_state=True)
            self.start();return self
        if shutil.disk_usage(self.directory.parent).free<4*1024**3:
            raise RuntimeError('Need4GiB free before owned cluster initialization')
        self.directory.mkdir(exist_ok=False)
        (self.directory/'owner.json').write_text(json.dumps(dict(owner=self.owner,
            kind='ttg-continuation-performance-only',creator_pid=os.getpid())))
        with (self.directory/'init.log').open('w') as log:
            subprocess.run([str(BIN/'initdb'),'-D',str(self.directory/'data'),'-U','ttgperf',
                '-A','trust','--no-locale','--encoding=UTF8'],stdout=log,stderr=subprocess.STDOUT,check=True)
        with (self.directory/'data/postgresql.conf').open('a') as config:
            config.write("\nlog_destination='csvlog'\nlogging_collector=on\nlog_directory='logs'\nlog_filename='postgresql-%Y%m%d-%H%M%S.log'\n")
            config.write("log_statement='all'\n" if self.statement_logging else "log_statement='none'\n")
            config.write("shared_buffers='64MB'\nmax_connections=30\n")
        self.start();return self

    def start(self):
        self.verify_owner()
        if self.started: raise ValueError('Owned cluster already started')
        self.csv_before_start={str(p):p.stat().st_size for p in (self.directory/'data/logs').glob('*.csv')}
        subprocess.run([str(BIN/'pg_ctl'),'-D',str(self.directory/'data'),'-l',str(self.directory/'startup.log'),
            '-o',f'-h127.0.0.1 -p{self.port} -k/tmp','-w','start'],check=True)
        self.started=True;self.record('cluster_started',port=self.port,statement_logging=self.statement_logging)

    def current_csv(self):
        result=[]
        for path in sorted((self.directory/'data/logs').glob('*.csv')):
            if str(path) in self.csv_before_start:
                if path.stat().st_size!=self.csv_before_start[str(path)]:
                    raise ValueError('CSV log filename reused across owned server generations')
            else:result.append(path)
        return result

    def stop(self):
        self.verify_owner()
        if any(service.poll() is None for service in self.services):
            raise ValueError('Owned workload service still running; refuse cluster stop')
        if self.admin_process is not None:
            self.admin_process.stdin.close();self.admin_process.wait(timeout=20)
            self.admin_log.close();self.admin_process=None
        if self.started:
            subprocess.run([str(BIN/'pg_ctl'),'-D',str(self.directory/'data'),'-m','fast','-w','stop'],check=True)
            self.started=False;self.record('cluster_stopped',retained_databases=sorted(self.databases))

    def sql(self,sql,database='postgres'):
        self.verify_owner()
        if not self.started: raise ValueError('Cluster is stopped')
        if self.admin_process is None:
            self.admin_log=(self.directory/'admin.log').open('a')
            self.admin_process=subprocess.Popen(['bash',str(OWN/'runtime.sh'),str(OWN/'sql_admin.py'),
                '--port',str(self.port)],env=runtime_env(self.runtime,self.runtime.name),stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,stderr=self.admin_log,text=True,bufsize=1)
        self.admin_process.stdin.write(json.dumps(dict(database=database,sql=sql))+'\n');self.admin_process.stdin.flush()
        while True:
            line=self.admin_process.stdout.readline()
            if not line: raise RuntimeError('Owned PgWire admin exited; see admin.log')
            if line.startswith('TTG_ADMIN_RESULT='):
                result=json.loads(line[len('TTG_ADMIN_RESULT='):]);break
            self.admin_log.write(line);self.admin_log.flush()
        if not result['ok']: raise RuntimeError(result['error'])
        rows=result['rows']
        if not rows:return ''
        scalar=rows[0][0]
        if isinstance(scalar,str):return scalar
        return json.dumps(scalar) if scalar is None or isinstance(scalar,(dict,list,bool)) else str(scalar)

    def create_database(self):
        if self.databases:raise ValueError('One owned trial database at a time')
        name='continuation_'+uuid.uuid4().hex
        self.sql('CREATE DATABASE '+name);self.databases.add(name)
        self.record('database_created',database=name);return name

    def drop_completed_database(self,name,artifacts_manifest):
        self.verify_owner()
        if name not in self.databases or not re.fullmatch(r'continuation_[0-9a-f]{32}',name):
            raise ValueError('Unowned database')
        if any(service.poll() is None for service in self.services):raise ValueError('Workload service still active')
        seal=verify_case(Path(artifacts_manifest).parent)
        active=self.sql(f"SELECT count(*) FROM pg_stat_activity WHERE datname='{name}'")
        if active!='0':raise ValueError('Owned database still has active sessions')
        self.sql('DROP DATABASE '+name);self.databases.remove(name)
        self.record('successful_database_dropped',database=name,validated_seal=seal,active_sessions=0)

    def __exit__(self,*args):
        self.stop()
        # Failed databases/files remain intact; no filesystem removal here.
