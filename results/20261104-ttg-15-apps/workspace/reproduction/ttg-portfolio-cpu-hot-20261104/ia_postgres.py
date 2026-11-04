"""One NEW owned cluster; independent semantic/physical proof before success DROP."""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import uuid
from ia_config import OWN,PREVIOUS
from ia_interop import BasePostgres,require,read_json,reference,verify_case,sha256
from owned_postgres import BIN,free_port
from ia_semantic import independent_replay


class OwnedPostgres(BasePostgres):
    def __init__(self,directory,runtime,run_directory,source_guard,startup_floor=2*1024**3,case_floor=1536*1024**2):
        # The inherited constructor intentionally restricts its OLD ownership
        # root. Establish a separate NEW root rather than changing that global.
        self.directory=Path(directory).resolve();self.runtime=Path(runtime).resolve()
        require(self.directory.is_relative_to(OWN) and not self.directory.exists(),'NEW owned cluster required')
        self.run_directory=Path(run_directory).resolve();self.source_guard=source_guard
        self.port=free_port();self.owner=str(uuid.uuid4());self.started=False
        self.databases=set();self.services=[];self.admin_process=None
        self.statement_logging=False;self.context=None
        self.startup_floor=startup_floor;self.case_floor=case_floor

    def __enter__(self):
        self.source_guard()
        require(shutil.disk_usage(self.directory.parent).free>=self.startup_floor,'Plan startup free-space floor')
        self.directory.mkdir()
        (self.directory/'owner.json').write_text(json.dumps(dict(owner=self.owner,
            kind='ttg-interability-performance-only',creator_pid=os.getpid(),run_directory=str(self.run_directory))))
        with (self.directory/'init.log').open('w') as log:
            subprocess.run([str(BIN/'initdb'),'-D',str(self.directory/'data'),'-U','ttgperf',
                '-A','trust','--no-locale','--encoding=UTF8'],stdout=log,stderr=subprocess.STDOUT,check=True)
        with (self.directory/'data/postgresql.conf').open('a') as config:
            config.write("\nlog_statement='none'\nshared_buffers='64MB'\nmax_connections=30\nmin_wal_size='32MB'\nmax_wal_size='64MB'\n")
        self.start()
        try:
            settings={name:self.sql('SHOW '+name) for name in
                ('min_wal_size','max_wal_size','wal_segment_size','checkpoint_timeout','shared_buffers','max_connections','log_statement')}
            require(settings['min_wal_size']=='32MB' and settings['max_wal_size']=='64MB','Actual uniform WAL settings differ')
            path=self.run_directory/'server-settings.json'
            path.write_text(json.dumps(dict(passed=True,cluster_owner=self.owner,settings=settings,
                configuration_sha256=sha256(self.directory/'data/postgresql.conf'),
                scope='Same owned PostgreSQL cluster/settings for all three modes; admin SHOW excluded from application metrics'),indent=2)+'\n')
            self.settings_ref=reference(path);self.record('server_settings_verified',evidence=self.settings_ref,settings=settings)
        except BaseException:
            self.stop();raise
        return self

    def sql(self,sql,database='postgres'):
        self.verify_owner();require(self.started,'Owned cluster stopped')
        if self.admin_process is None:
            env={**os.environ,'TTG_RUNTIME_SOURCE':str(self.runtime),
                'TTG_RUNTIME_CACHE':str(OWN.parent/'ttg-portfolio-v2-20261104'/'cache-admin-runtime'),'TTG_CACHE_DIR':str(OWN.parent/'ttg-portfolio-v2-20261104'/'cache-admin-compiler')}
            for key in list(env):
                if key.startswith('TTG_PERF_'):env.pop(key)
            self.admin_log=(self.directory/'admin.log').open('a')
            self.admin_process=subprocess.Popen(['bash',str(PREVIOUS/'runtime.sh'),str(PREVIOUS/'sql_admin.py'),
                '--port',str(self.port)],env=env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,
                stderr=self.admin_log,text=True,bufsize=1)
        self.admin_process.stdin.write(json.dumps(dict(database=database,sql=sql))+'\n');self.admin_process.stdin.flush()
        while True:
            line=self.admin_process.stdout.readline()
            require(line,'Owned PgWire admin exited; see admin.log')
            if line.startswith('TTG_ADMIN_RESULT='):
                result=json.loads(line[len('TTG_ADMIN_RESULT='):]);break
            self.admin_log.write(line);self.admin_log.flush()
        require(result['ok'],result.get('error','Admin SQL failed'))
        rows=result['rows']
        if not rows:return ''
        scalar=rows[0][0]
        return scalar if isinstance(scalar,str) else (json.dumps(scalar) if scalar is None or
            isinstance(scalar,(dict,list,bool)) else str(scalar))

    def create_database(self):
        require(self.context and not self.databases,'Exact case context and no retained DB required')
        require(shutil.disk_usage(self.directory).free>=self.case_floor,'Plan per-case free-space floor')
        self.source_guard();name=super().create_database()
        target=dict(kind='owned_cleanup_target',database=name,cluster_owner=self.owner,
            run_directory=str(self.run_directory),case_directory=str(self.context['directory']),
            case_id=self.context['case']['case_id'],config_id=self.context['cell'],seed=42)
        path=Path(target['case_directory'])/'cleanup-target.json'
        require(not path.exists(),'Target binding already exists')
        path.write_text(json.dumps(target,indent=2)+'\n');self.context['target']=reference(path)
        return name

    def accept_completed(self,case,cell,name,directory,proof,expected):
        from ia_metrics import summarize
        self.verify_owner();self.source_guard();directory=Path(directory).resolve()
        require(name in self.databases and re.fullmatch(r'continuation_[0-9a-f]{32}',name),'Unowned database')
        require(not any(p.poll() is None for p in self.services),'Owned application still active')
        target=read_json(directory/'cleanup-target.json')
        require(target==dict(kind='owned_cleanup_target',database=name,cluster_owner=self.owner,
            run_directory=str(self.run_directory),case_directory=str(directory),case_id=case['case_id'],
            config_id=cell,seed=42),'Cleanup target differs from actual case/owner/database')
        require(self.context['directory']==directory and self.context['case']==case and self.context['cell']==cell,
            'Live cleanup context differs')
        require(proof['database']==name and proof['cluster_owner']==self.owner,'Semantic proof target differs')
        semantic=independent_replay(directory,case,expected)
        # Reuse the independently checked actual anchor-kind census query.
        from ia_interop import Applications
        apps=Applications()
        if case['app']=='region_chain':
            types=['A','B','C','AB','BC']
        elif case['app'] in apps.native.TYPES:
            types=sum((list(group) for group in apps.native.TYPES[case['app']]),[])
        else:
            source=apps.native.SUITE/'apps'/case['app']
            text='\n'.join(p.read_text() for p in source.glob('*.jac'))
            types=re.findall(r'\b(?:node|edge)\s+(\w+)\s*\{',text)
            require(types,'No bound domain types')
        names=','.join("'"+t+"'" for t in types)
        query=("WITH domain AS (SELECT id FROM anchors WHERE arch_type IN ("+names+")) "
            "SELECT coalesce(json_agg(row_to_json(q)), '[]'::json) FROM ("
            "SELECT id,kind,arch_type,root_id,src,dst,undirected,props FROM anchors WHERE id IN (SELECT id FROM domain) "
            "OR (kind='EdgeAnchor' AND (src IN (SELECT id FROM domain) OR dst IN (SELECT id FROM domain))) ORDER BY seq) q")
        actual=json.loads(self.sql(query,name));final=read_json(directory/'final-graph-raw.json')
        require(actual==final,'Independent physical census differs from sealed final state')
        acceptance=dict(passed=True,raw_seal=verify_case(directory),semantic=semantic,
            semantic_proof=reference(directory/'plus-proof.json'),target=reference(directory/'cleanup-target.json'),
            database_state=dict(database=name,cluster_owner=self.owner,matches_sealed_final_graph=True,
                final_graph_sha256=sha256(directory/'final-graph-raw.json'),actual_row_count=len(actual),SQL=query),
            source_manifest=self.context['source_manifest'])
        accept_path=self.run_directory/'acceptances'/(directory.name+'.json');accept_path.parent.mkdir(exist_ok=True)
        accept_path.write_text(json.dumps(acceptance,indent=2)+'\n')
        metrics=summarize(directory,accept_path)
        metric_path=self.run_directory/'metrics'/(directory.name+'.json');metric_path.parent.mkdir(exist_ok=True)
        metric_path.write_text(json.dumps(metrics,indent=2)+'\n')
        # Correctness mechanism failure retains the sealed case AND its DB.
        if case['phase']=='correctness' and cell=='interability' and case['app'] in ('linked_list','region_chain'):
            from ia_sanity import from_metrics
            paired={m:read_json(r['path']) for m,r in self.context['prior_metrics'].items()}
            paired[cell]=metrics;gate=from_metrics(case,paired)
            gate_path=self.run_directory/(case['case_id']+'-mechanism-before-drop.json')
            gate_path.write_text(json.dumps(gate,indent=2)+'\n')
            require(gate['passed'],'Mechanism sanity failed; preserve sealed case and owned database')
        active=self.sql(f"SELECT count(*) FROM pg_stat_activity WHERE datname='{name}'")
        require(active=='0','Owned database still has active sessions')
        self.source_guard()
        require(verify_case(directory)==acceptance['raw_seal'],'Raw seal changed before DROP')
        require(read_json(accept_path)==acceptance,'Independent acceptance changed before DROP')
        require(sha256(directory/'plus-proof.json')==acceptance['semantic_proof']['sha256'],'Proof changed before DROP')
        self.sql('DROP DATABASE '+name);self.databases.remove(name)
        self.record('successful_database_dropped',database=name,validated_acceptance=reference(accept_path),
            metrics=reference(metric_path),target=reference(directory/'cleanup-target.json'),active_sessions=0)
        self.context['result']=dict(acceptance=reference(accept_path),metrics=reference(metric_path),
            raw=reference(directory/'artifacts.json'),proof=reference(directory/'plus-proof.json'))
