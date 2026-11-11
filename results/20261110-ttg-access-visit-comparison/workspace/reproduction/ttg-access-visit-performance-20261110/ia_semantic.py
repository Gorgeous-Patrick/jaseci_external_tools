"""Scale-aware independent replay using the unchanged accepted native oracles."""
import copy
import importlib.util
import json
from pathlib import Path
import random
from ia_config import APP_SNAPSHOT,digest,OWN
from ia_interop import require,read_json,verify_case,sha256,payload_errors,Applications,reference


def independent_replay(directory,case,expected=None):
    directory=Path(directory);seal=verify_case(directory,required=('plus-proof.json','http-raw.jsonl',
        'summary.json','requests.json','final-graph-raw.json','planner-statistics-before-workflow.json'))
    proof=read_json(directory/'plus-proof.json');summary=read_json(directory/'summary.json')
    statistics=read_json(directory/'planner-statistics-before-workflow.json')
    raw_requests=[json.loads(line) for line in (directory/'http-raw.jsonl').read_text().splitlines() if line]
    first=next(r for r in raw_requests if r['phase']=='workflow')
    require(statistics['passed'] and statistics['database']==proof['database'] and statistics['cluster_owner']==proof['cluster_owner'],'Planner statistics target differs')
    require(statistics['commands']==['ANALYZE anchors','ANALYZE graph_types'] and statistics['primary_excluded'],'Planner statistics regime differs')
    require(statistics['admin_end_ns']<=first['start_ns'],'ANALYZE overlaps first primary HTTP')
    require(proof['passed'] and summary['passed'],'Failed creator/native proof')
    require(all(proof['checks'].get(k) is True for k in ('native','oracle','fresh_session','restart')),
            'Incomplete native correctness')
    require(summary['restart_persistence']=='passed','Restart verification absent')
    if case['app'] in ('linked_list','region_chain'):
        return custom_replay(directory,case,proof,seal,expected)
    root=APP_SNAPSHOT.parent
    spec=importlib.util.spec_from_file_location('plus_independent_native',root/'app_suite/native.py')
    native=importlib.util.module_from_spec(spec);spec.loader.exec_module(native)
    spec=importlib.util.spec_from_file_location('plus_independent_corpus',root/'datasets/ttg/build.py')
    corpus=importlib.util.module_from_spec(spec);spec.loader.exec_module(corpus)
    native.corpus=corpus
    app=case['app'];scale=case['scale']
    if app not in native.SOURCES:
        return domain_replay(directory,case,proof,seal,expected)
    cfg=corpus.SCALES[scale]
    graph=corpus.make_graph(app,cfg,random.Random(42));operations=corpus.session(app,cfg,graph)
    rows=[json.loads(line) for line in (directory/'http-raw.jsonl').read_text().splitlines() if line]
    business=[r for r in rows if r['path'].startswith('/walker/') and r['phase'] in
              ('workflow','steady_warmup','steady_read')]
    class Replay:
        def __init__(self):self.cursor=0
        def walker(self,name,body,token,target=None):
            require(self.cursor<len(business),'Independent oracle requested missing RPC')
            row=business[self.cursor];self.cursor+=1
            path='/walker/'+name+('/'+target if target else '')
            require(row['path']==path and row['input']==body,'Native operation path/input/order differs')
            require(200<=row['http_status']<300,'Business transport error')
            return copy.deepcopy(row['output'].get('data',row['output'])['reports'])
    replay=Replay();mapping=read_json(directory/'mapping-initial.json')
    for op in operations:
        wanted=corpus.result(graph,op);actual=native.replay(app,replay,None,mapping,op)
        require(actual==wanted,'Independent original operation output differs: '+str(op))
    last_read=next(op for op in reversed(operations) if op['op'] in ('traverse','feed','tree','list_folder'))
    while replay.cursor<len(business):
        wanted=corpus.result(graph,last_read)
        require(native.replay(app,replay,None,mapping,last_read)==wanted,'Independent steady reader output differs')
    inspections=[r for r in rows if r['path'].startswith('/walker/SuiteInspect')]
    require(inspections,'No actual final inspection')
    last=inspections[-1];value=last['output'].get('data',last['output'])
    class StoredInspection:
        def walker(self,*args,**kwargs):return value['reports']
    native.verify_snapshot(StoredInspection(),None,last['input']['mapping'],graph,app)
    semantic=Applications().semantic.audit(directory,expected.get('full_response') if expected else None,sealed=True)
    require(semantic['full_semantic_sha256']==proof['output_sha256'],'Full response verifier/hash differs')
    if case['length'] is not None:
        traversals=[r for r in business if r['path'].split('/')[2:3]==['Traverse']]
        require(len(traversals)==1,'One actual Traverse request required in each LinkedList workflow')
        report=traversals[0]['output'].get('data',traversals[0]['output'])
        require(report['reports']==list(range(case['length'])) and
                report['result']['visited']==case['length'],'Native Traverse truncated/repeated/incorrect visited count')
    return dict(passed=True,kind='independent_native_semantic_replay',raw_seal=seal,
        proof_sha256=sha256(directory/'plus-proof.json'),actual_operations_checked=replay.cursor,
        final_logical_state_sha256=digest(dict(nodes=graph.nodes,edges=graph.edges)),
        verifier_sources={str(root/name):sha256(root/name) for name in
            ('app_suite/native.py','datasets/ttg/build.py')},full_response=proof['full_response'])


def domain_replay(directory,case,proof,seal,expected):
    """Unchanged accepted SCENARIOS run independently against stored actual RPCs."""
    import tempfile
    suite=Applications();app=case['app']
    if app=='recipe_pantry':
        from recipe_scenario import recipe_pantry
        suite.evaluate.SCENARIOS[app]=recipe_pantry
    from identity import Identities
    require(app in ('recipe_pantry', 'issue_desk', 'stock_room', 'clinic_queue', 'budget_ledger', 'knowledge_map', 'course_path', 'approval_desk', 'library_loans', 'event_seats', 'help_queue', 'delivery_route', 'volunteer_shift', 'incident_room'),'Unexpected fixed domain application')
    rows=[json.loads(line) for line in (directory/'http-raw.jsonl').read_text().splitlines() if line]
    start=next(i for i,r in enumerate(rows) if r['path']=='/walker/Seed')
    end=max(i for i,r in enumerate(rows) if r['phase']=='workflow')
    class StoredReplay:
        def __init__(self):self.records=rows[start:end+1];self.cursor=0
        def post(self,path,body,token=None):
            require(self.cursor<len(self.records),'Missing actual domain RPC')
            r=self.records[self.cursor];self.cursor+=1
            require(r['path']==path and 200<=r['http_status']<300,'Domain path/order/transport differs')
            if path.startswith('/walker/'):
                require(r['input']==body,'Domain business inputs differ')
                return copy.deepcopy(r['output'].get('data',r['output']))
            require(path in ('/user/register','/user/login'),'Unexpected redacted setup RPC')
            return {'token':'redacted-auth-token'} if path=='/user/login' else {}
        def walker(self,name,body,token,target=None):
            value=self.post('/walker/'+name+('/'+target if target else ''),body,token)
            require(not value.get('diagnostics'),'Domain native diagnostics')
            return value['reports']
    replay=StoredReplay();oracle=suite.evaluate.SCENARIOS[app]
    oracle_path=Path(oracle.__code__.co_filename).resolve()
    require(oracle_path==OWN/'recipe_scenario.py' if app=='recipe_pantry' else oracle_path.is_relative_to(APP_SNAPSHOT.parent),'Domain oracle is not frozen source')
    with tempfile.TemporaryDirectory(prefix='next-domain-oracle-',dir=directory.parent) as scratch:
        result=oracle(replay,'redacted-original-token',42,Path(scratch))
    require(replay.cursor==len(replay.records),'Domain oracle did not consume all business records')
    # Steady/restart readers must still match the independently reconstructed board.
    for r in rows:
        if r['phase'] not in ('steady_warmup','steady_read','verify') or r['path']!='/walker/'+result['read_walker']:continue
        require(r['output'].get('data',r['output'])['reports'][0]==result['expected_board'],'Domain final/steady board differs')
    ids=Identities(set_schema=suite.workloads.SET_SCHEMAS.get(app,{}))
    ids.normalize(read_json(directory/'fixture-raw.json'))
    transcript=[]
    for r in rows:
        parts=r['path'].split('/')
        if parts[1:2]!=['walker'] or not (r['phase']=='workflow' or parts[2]=='Seed'):continue
        transcript.append(dict(walker=parts[2],target=parts[3:],input=r['input'],output=r['output'].get('data',r['output'])))
    actions=ids.normalize([{k:v for k,v in r.items() if k!='output'} for r in transcript])
    outputs=ids.normalize(dict(transcript=transcript,final_graph=read_json(directory/'final-graph-raw.json')))
    require(digest(actions)==proof['actions_sha256'] and digest(outputs)==proof['output_sha256'],
        'Independent typed identity/state transcript differs')
    if expected:
        for key in ('fixture_sha256','actions_sha256','output_sha256'):
            require(proof[key]==expected[key],'Policy domain equivalence differs: '+key)
    return dict(passed=True,kind='independent_frozen_domain_scenario_replay',raw_seal=seal,
        proof_sha256=sha256(directory/'plus-proof.json'),actual_operations_checked=replay.cursor,
        selected_oracle=dict(path=str(oracle_path),sha256=sha256(oracle_path)),
        final_logical_state_sha256=digest(outputs['final_graph']),full_response=proof['full_response'])


def custom_replay(directory,case,proof,seal,expected):
    from ia_fixtures import fixture
    f=fixture(case);suite=Applications();native=suite.native
    rows=[json.loads(line) for line in (directory/'http-raw.jsonl').read_text().splitlines() if line]
    business=[r for r in rows if r['phase']=='workflow' and r['path'].startswith('/walker/')]
    require(len(business)==1,'One full traversal RPC required')
    row=business[0];mapping=read_json(directory/'mapping-initial.json')
    require(row['path']=='/walker/'+f['walker']+'/'+mapping['item:0'] and row['input']=={},'Traversal target/input/order differs')
    require(200<=row['http_status']<300,'Traversal transport failure')
    value=row['output'].get('data',row['output'])
    require(value['reports']==f['reports'] and value['result']['visited']==f['visited'],'Independent full native traversal oracle differs')
    require(read_json(directory/'fixture-shape-proof.json')==f['shape_proof'],'Fixture cardinality/acyclicity proof differs')
    inspections=[r for r in rows if r['path'].startswith('/walker/SuiteInspect')]
    require(inspections,'Missing actual final inspection')
    last=inspections[-1];actual=last['output'].get('data',last['output'])
    class Stored:
        def walker(self,*a,**kw):return actual['reports']
    native.verify_snapshot(Stored(),None,last['input']['mapping'],f['graph'],case['app'])
    semantic=suite.semantic.audit(directory,expected.get('full_response') if expected else None,sealed=True)
    require(semantic['full_semantic_sha256']==proof['output_sha256'],'Independent full-response proof differs')
    if expected:
        for key in ('fixture_sha256','actions_sha256','output_sha256'):require(proof[key]==expected[key],'Paired policy equivalence differs: '+key)
    return dict(passed=True,kind='independent_owned_finite_fixture_replay',raw_seal=seal,
        proof_sha256=sha256(directory/'plus-proof.json'),actual_operations_checked=1,
        source_oracle=reference(Path(__file__).with_name('ia_fixtures.py')),
        graph_state=dict(nodes=f['graph'].nodes,edges=f['graph'].edges),shape_proof=f['shape_proof'],
        native_reports=f['reports'],native_visited=f['visited'],full_response=proof['full_response'])
