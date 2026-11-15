"""Scale-aware independent replay using the unchanged accepted native oracles."""
import copy
import importlib.util
import json
from pathlib import Path
import random
from plus_config import APP_SNAPSHOT,digest
from interop import require,read_json,verify_case,sha256,payload_errors,Applications


def independent_replay(directory,case,expected=None):
    directory=Path(directory);seal=verify_case(directory,required=('plus-proof.json','http-raw.jsonl',
        'summary.json','requests.json','final-graph-raw.json'))
    proof=read_json(directory/'plus-proof.json');summary=read_json(directory/'summary.json')
    require(proof['passed'] and summary['passed'],'Failed creator/native proof')
    require(all(proof['checks'].get(k) is True for k in ('native','oracle','fresh_session','restart')),
            'Incomplete native correctness')
    require(summary['restart_persistence']=='passed','Restart verification absent')
    root=APP_SNAPSHOT.parent
    spec=importlib.util.spec_from_file_location('plus_independent_native',root/'app_suite/native.py')
    native=importlib.util.module_from_spec(spec);spec.loader.exec_module(native)
    spec=importlib.util.spec_from_file_location('plus_independent_corpus',root/'datasets/ttg/build.py')
    corpus=importlib.util.module_from_spec(spec);spec.loader.exec_module(corpus)
    native.corpus=corpus
    app=case['app'];scale=case['scale'];cfg=corpus.SCALES[scale]
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
    last_read=next(op for op in reversed(operations) if op['op'] in ('traverse','feed'))
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
