"""Actual frozen LinkedList/LittleX workflows with reviewed transport/observation."""
import copy
import json
import os
from pathlib import Path
import random
import subprocess
import time
import urllib.request
from plus_config import OWN,PREVIOUS,APP_SNAPSHOT,write_config,digest,run_config
from interop import Applications,require,read_json,sha256,payload_errors,load_jsonl,verify_case,reference
from storage import compress_closed_traces


class Trial:
    def __init__(self):
        self.apps=Applications();self.native=self.apps.native;self.w=self.apps.workloads
        self.original_server=self.w.Server

    def run(self,case,cell,directory,pg,runtime_manifest,overlay_manifest,expected=None):
        app=case['app'];scale=case['scale'];directory=Path(directory)
        runtime=Path(read_json(overlay_manifest)['root']);active={};trial=self
        class Server(self.original_server):
            def __init__(self,*args,**kwargs):
                super().__init__(*args,**kwargs);active['server']=self
            def start(self):
                self.generation+=1;self.log=(self.directory/f'server-{self.generation}.log').open('w')
                env={**os.environ,'TTG_RUNTIME_SOURCE':str(runtime),
                    'TTG_RUNTIME_CACHE':str(OWN/'cache-runtime'),'TTG_CACHE_DIR':str(OWN/'cache-compiler'),
                    'TTG_HTTP_PORT':str(self.port),'TTG_PERF_CONTROL_PORT':str(self.control_port),
                    'TTG_DATASET':str(directory/'dataset'),'JAC_DB_URL':self.url,'DATABASE_URL':self.url,'POSTGRES_URL':self.url,
                    'TTG_PERF_DIR':str(directory),'TTG_PERF_CELL_ID':case['case_id']+'/'+cell,
                    'TTG_PERF_TRIAL_ID':directory.name,'TTG_PERF_SERVER_GENERATION':str(self.generation),
                    'TTG_PERF_CLOCK_DOMAIN':'same-host-perf_counter_ns','TTG_PERF_POSTGRES_INSTANCE_ID':pg.owner}
                self.process=subprocess.Popen(['bash',str(PREVIOUS/'runtime.sh'),str(PREVIOUS/'perf_serve.py')],
                    cwd=directory,env=env,stdout=self.log,stderr=subprocess.STDOUT)
                pg.services.append(self.process);deadline=time.monotonic()+300
                while time.monotonic()<deadline:
                    if self.process.poll() is not None:raise RuntimeError('Native server exited: '+str(self.log.name))
                    try:
                        with urllib.request.urlopen(f'http://127.0.0.1:{self.port}/openapi.json',timeout=1) as response:
                            if response.status==200:return
                    except OSError:time.sleep(.2)
                raise TimeoutError('Native startup: '+str(self.log.name))
        self.w.Server=Server;old_config=self.w.config
        self.w.config=lambda path,name,policy:write_config(path,cell)
        # Frozen corpus graph/actions/oracles remain unchanged. Provenance is
        # explicitly the accepted immutable source snapshot, not a live Git HEAD.
        old_revision=self.native.corpus.revision
        self.native.corpus.revision=lambda path:dict(source_kind='immutable_accepted_app_snapshot',
            snapshot=reference(APP_SNAPSHOT),requested_path=str(path))
        try:
            if app=='littlex':
                class Proxy:
                    def __getattr__(self,name):return getattr(pg,name)
                    def drop_completed_database(self,name,manifest,server_stopped):
                        require(server_stopped,'Actual LittleX server still running')
                        trial.finalize(case,cell,directory,active['server'],pg,name,runtime_manifest,overlay_manifest,expected)
                return self.w.trial(app,cell,directory,Proxy(),self.native,self.apps.evaluate,self.apps.readers,
                    runtime,case['phase'],seed=42,scale='smoke',steady_reads=3)
            return self.linked_list(case,cell,directory,pg,runtime_manifest,overlay_manifest,expected,Server)
        finally:
            self.w.Server=self.original_server;self.w.config=old_config
            self.native.corpus.revision=old_revision

    def linked_list(self,case,cell,directory,pg,clean,overlay,expected,Server):
        native=self.native;w=self.w;scale=case['scale']
        native.prepare('linked_list',directory,scale,42,'none');write_config(directory,cell)
        database=pg.create_database();runtime=Path(read_json(overlay)['root'])
        server=Server(directory,f'postgresql://ttgperf@127.0.0.1:{pg.port}/{database}',runtime,case['phase'],'Traverse')
        server.capture_fixture=lambda:w.census(pg,database,['Item','Next'])
        summary=dict(app='linked_list',case_id=case['case_id'],policy=cell,scale=scale,seed=42,
            database=database,passed=False,primary_phase='workflow',
            workload='Native Traverse, Sum, Find head/middle/tail/missing; no inner steady-read repetitions')
        passed=False
        try:
            server.start();password='isolated-suite-seed-password'
            server.post('/user/register',dict(identities=[dict(type='username',value='user_0000')],
                credential=dict(type='password',password=password)))
            token=server.post('/user/login',dict(identity=dict(type='username',value='user_0000'),
                credential=dict(type='password',password=password)))['token']
            root=server.walker('SuiteRoot',{},token)[0]
            mapping=server.walker('SuiteImport',dict(roots={'user:0':root}),token)[0]
            w.write(directory/'mapping-initial.json',mapping)
            graph=native.corpus.make_graph('linked_list',native.corpus.SCALES[scale],random.Random(42))
            server.stop();server.start();native.verify_snapshot(server,token,mapping,graph,'linked_list')
            server.phase='workflow';logical=[]
            for operation in native.corpus.session('linked_list',native.corpus.SCALES[scale],graph):
                wanted=native.corpus.result(graph,operation)
                actual=native.replay('linked_list',server,token,mapping,operation)
                require(actual==wanted,'Native LinkedList logical output differs: '+str(operation))
                logical.append(dict(operation=operation,expected=wanted,actual=actual))
            server.phase='verify';server.stop();server.start()
            native.verify_snapshot(server,token,mapping,graph,'linked_list')
            final=w.census(pg,database,['Item','Next'])
            w.write(directory/'fixture-raw.json',server.fixture);w.write(directory/'final-graph-raw.json',final)
            fixture=read_json(directory/'dataset/manifest.json')
            w.write(directory/'fixture-canonical.json',dict(dataset_files=fixture['files'],config=fixture['config']))
            # Full response identity normalization is independently supplied by
            # the unchanged original-app semantic verifier during finalization.
            w.write(directory/'actions-canonical.json',[r['operation'] for r in logical])
            w.write(directory/'outputs-canonical.json',logical);w.write(directory/'logical-steps.json',logical)
            summary.update(passed=True,restart_persistence='passed');passed=True
        except BaseException as error:
            summary['error']=type(error).__name__+': '+str(error);raise
        finally:
            server.stop();w.write(directory/'requests.json',server.requests);w.write(directory/'summary.json',summary)
            if not passed:
                pg.record('failed_database_preserved',database=database,evidence=str(directory))
        self.finalize(case,cell,directory,server,pg,database,clean,overlay,expected)
        return summary

    def finalize(self,case,cell,directory,server,pg,database,clean,overlay,expected):
        require(server.process is None and not any(p.poll() is None for p in pg.services),'Owned services not stopped')
        compression=compress_closed_traces(directory,True)
        self.w.write(directory/'compression.json',compression)
        events=load_unsealed(directory,'server-*.events.jsonl*')
        closes={}
        for e in events:
            require(not payload_errors(e),'Native nested plan payload_error')
            if e['kind']=='native_context_close' and e.get('origin_request_id'):
                require(e.get('natural_close_completed') is True,'Native context close incomplete')
                closes.setdefault(e['origin_request_id'],set()).add(e['session_nonce'])
            del e
        used={}
        for row in server.requests:
            if not row['path'].startswith('/walker/'):continue
            require(closes.get(row['request']),'Actual native session evidence absent')
            for nonce in closes[row['request']]:
                require(nonce not in used or used[nonce]==row['request'],'Session reused across RPCs')
                used[nonce]=row['request']
        traversal=[]
        if case['length'] is not None:
            for row in server.requests:
                if row['path'].split('/')[2:3]!=['Traverse']:continue
                value=row['output'].get('data',row['output']);reports=value['reports']
                require(reports==list(range(case['length'])),'Traverse reports truncated, repeated or out of order')
                require(value.get('result',{}).get('visited')==case['length'],'Native Traverse visited count differs')
                traversal.append(dict(request=row['request'],phase=row['phase'],expected=case['length'],
                    actual=len(reports),native_visited=value['result']['visited']))
            require(bool(traversal),'No actual native Traverse request')
        semantic=self.apps.semantic.audit(directory,expected.get('full_response') if expected else None,sealed=False)
        self.w.write(directory/'full-response-proof.json',semantic)
        proof=dict(passed=True,case_id=case['case_id'],app=case['app'],scale=case['scale'],length=case['length'],
            config_id=cell,seed=42,stage=case['phase'],run=run_config(cell),
            database=database,cluster_owner=pg.owner,
            runtime=reference(clean),overlay=reference(overlay),app_snapshot=reference(APP_SNAPSHOT),
            fixture_sha256=digest(read_json(directory/'fixture-canonical.json')),
            actions_sha256=semantic['full_actions_sha256'],output_sha256=semantic['full_semantic_sha256'],
            full_response={k:semantic[k] for k in ('full_actions_sha256','full_semantic_sha256')},
            checks=dict(native=True,oracle=True,fresh_session=True,restart=True),Traverse_requests=traversal)
        if expected:
            for key in ('fixture_sha256','actions_sha256','output_sha256'):
                require(proof[key]==expected[key],'Policy fixture/action/output equivalence differs: '+key)
        self.w.write(directory/'plus-proof.json',proof)
        seal=dict(passed=True,files={str(p.relative_to(directory)):sha256(p) for p in directory.rglob('*')
            if p.is_file() and p.name!='artifacts.json'})
        self.w.write(directory/'artifacts.json',seal)
        pg.accept_completed(case,cell,database,directory,proof,expected)


def load_unsealed(directory,pattern):
    import gzip
    for path in sorted(Path(directory).glob(pattern)):
        opener=gzip.open if path.suffix=='.gz' else open
        with opener(path,'rt') as file:
            for line in file:
                if line.strip():yield json.loads(line)
