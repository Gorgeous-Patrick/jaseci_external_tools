"""Reuse unchanged accepted30-app workflows/oracles with NEW runtime/observer.

Importing does not start services. Old application sources and old measurement
files are never edited. Formal callers must first pass the NEW fixed release;
correctness callers produce explicitly excluded evidence. Intended for a
dedicated application-tier worker process, avoiding benchmark module collisions.
"""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.request
from configuration import write as write_config,signature,run_config
from evidence import sha256,read_json
import gate as continuation_gate
from owned_postgres import runtime_env

OWN=Path(__file__).resolve().parent
OLD=OWN.parent/'ttg-app-performance'
OLD_SUITE=OLD/'suite-final-20261030-v1/snapshot.json'


def _module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);sys.modules[name]=module
    spec.loader.exec_module(module);return module


def digest(value):
    import hashlib
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()


class Applications:
    def __init__(self,suite_manifest=OLD_SUITE):
        before_path=sys.path[:];before_gate=sys.modules.get('gate')
        try:
            sys.path.insert(0,str(OLD))
            old_gate=_module('accepted_application_gate',OLD/'gate.py')
            sys.modules['gate']=old_gate
            old_gate.verify_snapshot(Path(suite_manifest),'suite')
            self.workloads=_module('accepted_application_workloads',OLD/'workloads.py')
            self.semantic=_module('accepted_application_semantics',OLD/'semantic_responses.py')
            self.native,self.evaluate,self.readers=self.workloads.configure(Path(suite_manifest))
            self.apps=old_gate.APPS
            self.server_type=self.workloads.Server
        finally:
            sys.path[:]=before_path
            if before_gate is not None:sys.modules['gate']=before_gate
            else:sys.modules.pop('gate',None)
        self.suite_manifest=Path(suite_manifest)

    def run(self,app,cell,directory,postgres,clean_manifest,overlay_manifest,
            expected=None,stage='correctness',seed=42,source_guard=None,release=None):
        if stage=='formal':
            if release is None:raise ValueError('NEW fixed main release required before app formal execution')
            continuation_gate.revalidate(release)
        elif stage!='correctness':raise ValueError('Explicit correctness/formal stage required')
        if app not in self.apps:raise ValueError('Unknown accepted application')
        clean=continuation_gate.check_tree(clean_manifest)
        overlay=continuation_gate.check_tree(overlay_manifest)
        if overlay['base_runtime_manifest_sha256']!=sha256(clean_manifest):raise ValueError('App runtime/overlay mismatch')
        directory=Path(directory);runtime=Path(overlay['root']);adapter=self
        native_verify=self.native.verify_snapshot
        current_oracle={}
        def verify_snapshot(server,token,mapping,graph,name):
            result=native_verify(server,token,mapping,graph,name)
            current_oracle['state']=json.loads(json.dumps(dict(nodes=graph.nodes,edges=graph.edges)))
            return result
        self.native.verify_snapshot=verify_snapshot
        active={}
        class Server(self.server_type):
            def __init__(self,*args,**kwargs):
                super().__init__(*args,**kwargs);active['server']=self
            def start(self):
                self.generation+=1
                self.log=(self.directory/f'server-{self.generation}.log').open('w')
                env=runtime_env(self.runtime,self.runtime.name)
                env.update(TTG_HTTP_PORT=str(self.port),TTG_PERF_CONTROL_PORT=str(self.control_port),
                    TTG_DATASET=str(self.directory/'dataset'),JAC_DB_URL=self.url,DATABASE_URL=self.url,POSTGRES_URL=self.url,
                    TTG_PERF_DIR=str(self.directory),TTG_PERF_CELL_ID='apps/'+app+'/'+cell,
                    TTG_PERF_TRIAL_ID=self.directory.name,TTG_PERF_SERVER_GENERATION=str(self.generation),
                    TTG_PERF_CLOCK_DOMAIN='same-host-perf_counter_ns',TTG_PERF_POSTGRES_INSTANCE_ID=postgres.owner)
                self.process=subprocess.Popen(['bash',str(OWN/'runtime.sh'),str(OWN/'perf_serve.py')],
                    cwd=self.directory,env=env,stdout=self.log,stderr=subprocess.STDOUT)
                postgres.services.append(self.process)
                deadline=time.monotonic()+240
                while time.monotonic()<deadline:
                    if self.process.poll() is not None:raise RuntimeError('Application server exited: '+str(self.log.name))
                    try:
                        with urllib.request.urlopen(f'http://127.0.0.1:{self.port}/openapi.json',timeout=1) as response:
                            if response.status==200:return
                    except OSError:time.sleep(.2)
                raise TimeoutError('Application startup: '+str(self.log.name))
        self.workloads.Server=Server
        self.workloads.config=lambda path,name,policy:write_config(path,'apps/'+name,cell)
        proof={}
        def validate_before_accept():
            if source_guard:source_guard()
            if stage=='formal':continuation_gate.revalidate(release)
            # All inherited native/logical/restart/oracle assertions completed.
            # Scan every scope, including late child records, before accepted flag.
            close_nonces={}
            for path in directory.glob('server-*.events.jsonl'):
                for line in path.read_text().splitlines():
                    if not line:continue
                    event=json.loads(line)
                    if continuation_gate.payload_errors(event):
                        raise ValueError('Application nested plan payload_error')
                    if event['kind']=='native_context_close' and event.get('origin_request_id'):
                        if event.get('natural_close_completed') is not True:raise ValueError('Native context close did not complete')
                        close_nonces.setdefault(event['origin_request_id'],set()).add(event['session_nonce'])
            requests=[r for r in active['server'].requests if r['path'].startswith('/walker/')]
            seen={}
            for request in requests:
                nonces=close_nonces.get(request['request'])
                if not nonces:raise ValueError('Missing actual native Session close/freshness evidence')
                for nonce in nonces:
                    if nonce in seen and seen[nonce]!=request['request']:raise ValueError('Session reused across HTTP requests')
                    seen[nonce]=request['request']
            semantic=None
            if app in self.semantic.ORIGINALS:
                semantic=self.semantic.audit(directory,expected.get('full_response') if expected else None,sealed=False)
                (directory/'full-response-proof.json').write_text(json.dumps(semantic,indent=2)+'\n')
            fixture=read_json(directory/'fixture-canonical.json')
            actions=read_json(directory/'actions-canonical.json')
            outputs=read_json(directory/'outputs-canonical.json')
            if app in self.semantic.ORIGINALS:
                state=current_oracle['state']
                state_representation='Independent final logical graph oracle; actual node fields/topology verified by unchanged native.verify_snapshot; narrow volatile timestamps separately validated and raw final graph retained'
                output_hash=semantic['full_semantic_sha256']
            else:
                state=outputs['final_graph'];state_representation='Full canonical actual final graph, using frozen declared-field identity/set schema'
                output_hash=digest(outputs)
            proof.update(passed=True,case_id='apps/'+app,config_id=cell,seed=seed,stage=stage,
                formal_samples=0 if stage=='correctness' else None,
                runtime_manifest_sha256=sha256(clean_manifest),overlay_manifest_sha256=sha256(overlay_manifest),
                suite_manifest_sha256=sha256(adapter.suite_manifest),effective_config_sha256=signature(cell),run=run_config(cell),
                fixture_sha256=digest(fixture),actions_sha256=digest(actions),output_sha256=output_hash,
                state_sha256=digest(state),oracle_sha256=digest(dict(state=state,verified=True)),
                state_representation=state_representation,
                checks=dict(native=True,oracle=True,fresh_session=True,restart=True),
                full_response={key:semantic[key] for key in ('full_semantic_sha256','full_actions_sha256')} if semantic else None,
                semantic_verifier_sha256=sha256(OLD/'semantic_responses.py') if semantic else None)
            proof['fresh_session_evidence']=dict(walker_requests=len(requests),distinct_session_nonces=len(seen),
                request_nonces={k:sorted(v) for k,v in close_nonces.items()})
            if expected:
                for field in ('fixture_sha256','actions_sha256','output_sha256','state_sha256','oracle_sha256'):
                    if proof[field]!=expected[field]:raise ValueError('Application policy correctness differs: '+field)
            (directory/'continuation-proof.json').write_text(json.dumps(proof,indent=2)+'\n')
        class PostgresProxy:
            def __getattr__(self,name):return getattr(postgres,name)
            def drop_completed_database(self,name,manifest,server_stopped):
                if not server_stopped:raise ValueError('Application still active')
                from evidence import verify_case
                verify_case(Path(manifest).parent,required=('continuation-proof.json',))
                if stage=='formal':continuation_gate.revalidate(release)
                postgres.drop_completed_database(name,manifest)
        try:
            summary=self.workloads.trial(app,cell,directory,PostgresProxy(),self.native,self.evaluate,
                self.readers,runtime,stage,seed=seed,scale='smoke',steady_reads=3,
                validate_after=validate_before_accept)
            return dict(summary=summary,proof=proof)
        finally:
            self.native.verify_snapshot=native_verify
            self.workloads.Server=self.server_type
