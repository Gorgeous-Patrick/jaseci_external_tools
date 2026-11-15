"""Independent semantic replay from sealed responses, not copied passed flags."""
import json
from pathlib import Path
import random
import sys
import tempfile
import importlib.util
import copy
from cleanup_guard_v2 import require,passed,digest,validate_raw_case,verify_source_context,validate_cas
from evidence import sha256,read_json


def create_acceptance(directory,output,context):
    directory=Path(directory).resolve();output=Path(output)
    verify_source_context(context)
    seal,summary,proof,rows=validate_raw_case(directory,context)
    validate_cas(context,proof)
    from app_tier_adapter import Applications,OLD
    suite=Applications();app=context['app']
    frozen=suite.suite_manifest.parent
    imports=((suite.workloads,OLD/'workloads.py'),(suite.semantic,OLD/'semantic_responses.py'),
        (suite.native,frozen/'app_suite/native.py'),(suite.evaluate,frozen/'app_suite/evaluate.py'),
        (suite.native.corpus,frozen/'datasets/ttg/build.py'))
    for module,expected_path in imports:
        require(Path(module.__file__).resolve()==expected_path.resolve(),'Imported oracle/workload path is not the bound source')
        require(str(expected_path) in context['sources'] and sha256(expected_path)==context['sources'][str(expected_path)],
            'Imported oracle source is not in required closure')
    if app in suite.semantic.ORIGINALS:
        semantic=suite.semantic.audit(directory,proof['full_response'],sealed=True)
        require(semantic['full_semantic_sha256']==proof['output_sha256'],'Independent full response hash differs')
        graph=suite.native.corpus.make_graph(app,suite.native.corpus.SCALES['smoke'],random.Random(context['seed']))
        for operation in suite.native.corpus.session(app,suite.native.corpus.SCALES['smoke'],graph):
            suite.native.corpus.result(graph,operation)
        state=dict(nodes=graph.nodes,edges=graph.edges)
        require(digest(state)==proof['state_sha256'],'Independent final graph oracle hash differs')
        inspections=[r for r in rows if '/walker/SuiteInspect' in r['path']]
        require(bool(inspections),'Final actual inspection missing')
        latest=inspections[-1];response=latest['output'].get('data',latest['output'])
        class StoredInspection:
            def walker(self,*args,**kwargs):return response['reports']
        # Existing frozen oracle independently checks actual node membership,
        # types/semantic fields and duplicate-preserving edge topology.
        # Load an independent unwrapped frozen function, rather than the live
        # run's temporarily wrapped Python oracle method.
        native_path=suite.suite_manifest.parent/'app_suite/native.py'
        spec=importlib.util.spec_from_file_location('cleanup_frozen_native',native_path)
        independent=importlib.util.module_from_spec(spec);spec.loader.exec_module(independent)
        logical=independent.corpus.make_graph(app,independent.corpus.SCALES['smoke'],random.Random(context['seed']))
        operations=independent.corpus.session(app,independent.corpus.SCALES['smoke'],logical)
        business=[r for r in rows if r['path'].startswith('/walker/') and r['phase'] in
            ('workflow','steady_warmup','steady_read')]
        class StoredOriginal:
            def __init__(self):self.cursor=0
            def walker(self,name,body,token,target=None):
                require(self.cursor<len(business),'Missing original business RPC')
                row=business[self.cursor];self.cursor+=1
                path='/walker/'+name+('/'+target if target else '')
                require(row['path']==path and row['input']==body,'Original action path/input/order differs')
                require(200<=row['http_status']<300,'Original business transport failed')
                return copy.deepcopy(row['output'].get('data',row['output'])['reports'])
        replay=StoredOriginal();mapping=read_json(directory/'mapping-initial.json')
        for operation in operations:
            expected=independent.corpus.result(logical,operation)
            actual=independent.replay(app,replay,None,mapping,operation)
            require(actual==expected,'Original business/steady response differs from corpus oracle')
        read_op=next(op for op in reversed(operations) if op['op'] in ('traverse','feed','channel','tree','list_folder'))
        while replay.cursor<len(business):
            expected=independent.corpus.result(logical,read_op)
            actual=independent.replay(app,replay,None,mapping,read_op)
            require(actual==expected,'Original business/steady response differs from corpus oracle')
        independent.verify_snapshot(StoredInspection(),None,latest['input']['mapping'],graph,app)
        require(digest(dict(state=state,verified=True))==proof['oracle_sha256'],'Independent original oracle differs')
    else:
        start=next(i for i,row in enumerate(rows) if row['path']=='/walker/Seed')
        end=max(i for i,row in enumerate(rows) if row['phase']=='workflow')
        class StoredReplay:
            def __init__(self):self.records=rows[start:end+1];self.cursor=0
            def post(self,path,body,token=None):
                require(self.cursor<len(self.records),'Domain oracle requested an absent RPC')
                record=self.records[self.cursor];self.cursor+=1
                require(record['path']==path,'Domain action order/path differs')
                require(200<=record['http_status']<300,'Domain transport request failed')
                if path.startswith('/walker/'):
                    require(record['input']==body,'Domain action inputs differ')
                    return copy.deepcopy(record['output'].get('data',record['output']))
                # Authentication payloads are deliberately redacted in this
                # historical capture. Source-controlled actor choices and real
                # private-view/denial responses are re-evaluated by the oracle.
                require(path in ('/user/register','/user/login'),'Unexpected redacted setup RPC')
                return {'token':'redacted-auth-token'} if path=='/user/login' else {}
            def walker(self,name,body,token,target=None):
                path='/walker/'+name+('/'+target if target else '')
                value=self.post(path,body,token)
                require(not value.get('diagnostics'),'Domain native diagnostics')
                return value['reports']
        replay=StoredReplay()
        oracle=suite.evaluate.SCENARIOS[app]
        oracle_path=Path(oracle.__code__.co_filename).resolve()
        require(str(oracle_path) in context['sources'],'Selected domain oracle implementation is not source-bound')
        with tempfile.TemporaryDirectory(prefix='cleanup-domain-oracle-',dir=output.parent) as scratch:
            oracle(replay,'redacted-original-token',context['seed'],Path(scratch))
        require(replay.cursor==len(replay.records),'Actual domain actions were not all checked by frozen oracle')
        from identity import Identities
        identities=Identities(set_schema=suite.workloads.SET_SCHEMAS.get(app,{}))
        identities.normalize(read_json(directory/'fixture-raw.json'))
        transcript=[]
        for row in rows:
            parts=row['path'].split('/')
            if parts[1:2]!=['walker'] or not (row['phase']=='workflow' or parts[2]=='Seed'):continue
            transcript.append(dict(walker=parts[2],target=parts[3:],input=row['input'],
                output=row['output'].get('data',row['output'])))
        actions=identities.normalize([{k:v for k,v in row.items() if k!='output'} for row in transcript])
        outputs=identities.normalize(dict(transcript=transcript,final_graph=read_json(directory/'final-graph-raw.json')))
        require(digest(actions)==proof['actions_sha256'],'Immutable response action reconstruction differs')
        require(digest(outputs)==proof['output_sha256'],'Immutable full response/state reconstruction differs')
        require(digest(outputs['final_graph'])==proof['state_sha256'],'Actual final state digest differs')
    closes={}
    from gate import payload_errors
    for file in directory.glob('server-*.events.jsonl'):
        for line in file.read_text().splitlines():
            if not line:continue
            event=json.loads(line)
            require(not payload_errors(event),'Nested payload_error in complete scope history')
            if event['kind']=='dependency_outcome':require(not event['summary'].get('errors'),'Dependency scope errors')
            if event['kind']=='native_context_close' and event.get('origin_request_id'):
                require(event.get('natural_close_completed') is True,'Native close incomplete')
                closes.setdefault(event['origin_request_id'],set()).add(event['session_nonce'])
    seen={}
    for row in rows:
        if not row['path'].startswith('/walker/'):continue
        nonces=closes.get(row['request'])
        require(bool(nonces),'Missing independent actual session evidence')
        for nonce in nonces:
            require(nonce not in seen or seen[nonce]==row['request'],'Session reused across HTTP requests')
            seen[nonce]=row['request']
    expected=context.get('expected')
    if expected:
        for field in ('fixture_sha256','actions_sha256','output_sha256','state_sha256','oracle_sha256'):
            require(proof[field]==expected[field],'Policy semantic equivalence failed: '+field)
    result=dict(passed=True,kind='independent_semantic_cleanup_acceptance',raw_seal=seal,
        semantic_proof=dict(path=str(directory/'continuation-proof.json'),sha256=sha256(directory/'continuation-proof.json')),
        sources=context['sources'],source_manifests=context['source_manifests'],cas_references=context.get('cas_references',[]),
        target_binding=context['target_binding'],database_state=context['database_state'],
        cleanup_review=context['cleanup_review'],
        verification=dict(independent_semantic_recheck=True,raw_response_count=len(rows),
            independent_session_nonces=len(seen),source_closure_rechecked=True,all_declared_CAS_checked=True))
    output.parent.mkdir(parents=True,exist_ok=True)
    if output.exists():raise ValueError('Independent acceptance path already exists')
    output.write_text(json.dumps(result,indent=2)+'\n')
    return result
