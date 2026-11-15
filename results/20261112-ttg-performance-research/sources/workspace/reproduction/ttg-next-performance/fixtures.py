"""DB-free exact reuse of the accepted corpus generator and operation oracle."""
import argparse
import copy
from collections import Counter
import hashlib
import importlib.util
import json
from pathlib import Path
import random

ROOT=Path(__file__).resolve().parents[2]
SUITE=ROOT/'reproduction/ttg-app-performance/suite-final-20261030-v1'
CORPUS=SUITE/'datasets/ttg/build.py'
CASES=(('linked_list32','linked_list','smoke'),('linked_list1000','linked_list','small'),
       ('littlex_original','littlex','smoke'),('littlex_small','littlex','small'),
       ('jdrive','jdrive','smoke'))

def encoded(value):return (json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False)+'\n').encode()
def sha(data):return hashlib.sha256(data).hexdigest()
def ref(path):return dict(path=str(path.resolve()),sha256=sha(path.read_bytes()))

def build_case(corpus,case,app,scale,seed=42):
    config=copy.deepcopy(corpus.SCALES[scale])
    graph=corpus.make_graph(app,config,random.Random(seed))
    initial=dict(nodes=copy.deepcopy(graph.nodes),edges=copy.deepcopy(graph.edges))
    operations=corpus.session(app,config,graph)
    expected=[]
    for op in operations:
        expected.append(dict(operation=copy.deepcopy(op),result=copy.deepcopy(corpus.result(graph,op))))
    return dict(case_id=case,app=app,scale=scale,seed=seed,config=config,
        initial=initial,operations=operations,expected_logical=expected,
        final=dict(nodes=graph.nodes,edges=graph.edges))

def prepare(out):
    spec=importlib.util.spec_from_file_location('accepted_next_corpus',CORPUS)
    corpus=importlib.util.module_from_spec(spec);spec.loader.exec_module(corpus)
    out=Path(out).resolve();out.mkdir(parents=True,exist_ok=False)
    rows=[]
    for case,app,scale in CASES:
        value=build_case(corpus,case,app,scale)
        # Independent repeat verifies seed/order stability without native execution.
        assert encoded(value)==encoded(build_case(corpus,case,app,scale))
        if app=='linked_list':
            n=value['config']['length'];ids=value['expected_logical'][0]['result']
            assert ids==[f'item:{i}' for i in range(n)]
            assert [value['initial']['nodes'][uid]['fields']['value'] for uid in ids]==list(range(n))
            assert value['expected_logical'][1]['result']==n*(n-1)//2
        data=encoded(value);path=out/(case+'.json');path.write_bytes(data)
        initial=value['initial']
        rows.append(dict(case_id=case,app=app,scale=scale,config=value['config'],
            logical_nodes=len(initial['nodes']),logical_edges=len(initial['edges']),
            node_types=dict(Counter(n['type'] for n in initial['nodes'].values())),
            edge_types=dict(Counter(e['type'] for e in initial['edges'])),
            operation_count=len(value['operations']),JSON_bytes=len(data),fixture=ref(path),
            initial_sha256=sha(encoded(initial)),operations_sha256=sha(encoded(value['operations']))))
    manifest=dict(passed=True,stage='DB-free fixture preparation only',seed=42,
        generator=ref(CORPUS),preparer=ref(Path(__file__)),cases=rows,
        interpretation='Logical graph counts exclude native root/identity/import scaffolding. No native correctness or performance claim.')
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps(dict(manifest=ref(out/'manifest.json'),cases=[{k:r[k] for k in ('case_id','logical_nodes','logical_edges','operation_count','JSON_bytes')} for r in rows]),indent=2))

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    prepare(parser.parse_args().output)
