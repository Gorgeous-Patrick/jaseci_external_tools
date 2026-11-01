"""Completed-nine metadata/source binding plus pure stored-response LittleX replay.

No service, Jac execution, DB, large event, historical metric, or runtime tree
scan. Frozen original Python oracles are reused without modification.
"""
import copy
import hashlib
import importlib.util
import json
import random
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
RUN = ROOT / 'project-notes/measurements/ttg-plus-performance-20261031/correctness-v5'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def ref(value):
    assert sha(value['path']) == value['sha256'], value['path']
    return read(value['path'])


index = read(RUN / 'index.json')
assert index['status'] == 'complete' and index['passed'] and index['stage'] == 'correctness'
assert index['authorization'] is None and len(index['rows']) == 9
plan = ref(index['plan'])
assert index['plan']['sha256'] == 'dc134d0a10553a2b28427f32aadc46ab0c506702bf4359c71074490f25a81394'
assert [{k: row[k] for k in plan['correctness_schedule'][0]} for row in index['rows']] == plan['correctness_schedule']
sources = ref(plan['sources'])
assert plan['sources']['sha256'] == '47a3ea5c5850c79b23f75502a12fce96f434010290ba2495a7271526253c9a50'
assert len(sources['files']) == 50
for name, wanted in sources['files'].items():
    assert sha(name) == wanted, name  # 50 source files only, no runtime trees
ownership_path = Path(index['cluster']) / 'ownership-and-cleanup.jsonl'
ownership = [json.loads(x) for x in ownership_path.read_text().splitlines()]
assert ownership[-1]['action'] == 'cluster_stopped' and ownership[-1]['retained_databases'] == []
drop_records = [r for r in ownership if r['action'] == 'successful_database_dropped']
assert len(drop_records) == 9
grouped = defaultdict(list)
databases = set()
cases = []
for row in index['rows']:
    refs = row['result']
    proof, acceptance, metric, seal = [ref(refs[k]) for k in ('proof', 'acceptance', 'metrics', 'raw')]
    assert row['passed'] and proof['passed'] and acceptance['passed'] and metric['passed']
    assert proof['case_id'] == metric['case_id'] == row['case_id']
    assert proof['config_id'] == metric['config_id'] == row['config_id']
    assert proof['stage'] == metric['stage'] == row['phase'] == 'correctness'
    assert proof['run'] == plan['configs'][row['config_id']]
    assert proof['runtime'] == plan['runtime'] and proof['overlay'] == plan['overlay']
    assert proof['database'] not in databases
    databases.add(proof['database'])
    assert proof['cluster_owner'] == acceptance['database_state']['cluster_owner'] == index['cluster_owner']
    assert acceptance['semantic']['passed'] and acceptance['database_state']['matches_sealed_final_graph']
    assert acceptance['semantic_proof'] == refs['proof']
    assert metric['independent_acceptance'] == refs['acceptance']
    assert metric['raw_seal']['sha256'] == acceptance['raw_seal']['sha256'] == refs['raw']['sha256']
    assert metric['model_outcome_format'] == 'compact-outcome-v1'
    directory = Path(refs['raw']['path']).parent
    target = ref(acceptance['target'])
    assert target['database'] == proof['database'] and target['cluster_owner'] == index['cluster_owner']
    for event in metric['model_outcomes']:
        raw = event['raw_event']
        assert raw['sha256'] == seal['files'][str(Path(raw['path']).relative_to(directory))]
        assert raw['line'] > 0 and len(raw['record_sha256']) == 64
    drop = next(r for r in drop_records if r['database'] == proof['database'])
    assert drop['owner'] == index['cluster_owner'] and drop['active_sessions'] == 0
    assert drop['validated_acceptance'] == refs['acceptance'] and drop['metrics'] == refs['metrics']
    grouped[row['case_id']].append(proof)
    cases.append(dict(case_id=row['case_id'], config_id=row['config_id'], refs=refs,
        operations=acceptance['semantic']['actual_operations_checked'],
        physical_rows=acceptance['database_state']['actual_row_count']))
for proofs in grouped.values():
    for key in ('fixture_sha256', 'actions_sha256', 'output_sha256'):
        assert len({p[key] for p in proofs}) == 1, key
for case, gate_ref in index['mechanism_checks'].items():
    gate = ref(gate_ref)
    assert gate['passed'] and not gate['failed_checks']
assert index['mechanism_status'] == 'passed'

suite = ROOT / 'reproduction/ttg-app-performance/suite-final-20261030-v1'


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


native = module('review_frozen_native', suite / 'app_suite/native.py')
corpus = module('review_frozen_corpus', suite / 'datasets/ttg/build.py')
native.corpus = corpus
littlex = []
for row in index['rows'][-3:]:
    assert row['case_id'] == 'littlex'
    directory = Path(row['result']['raw']['path']).parent
    assert (directory / 'http-raw.jsonl').stat().st_size < 2 * 1024**2
    requests = [json.loads(x) for x in (directory / 'http-raw.jsonl').read_text().splitlines()]
    business = [r for r in requests if r['path'].startswith('/walker/')
                and r['phase'] in ('workflow', 'steady_warmup', 'steady_read')]
    assert len(business) == 15

    class StoredReplay:
        cursor = 0

        def walker(self, name, body, token, target=None):
            r = business[self.cursor]
            self.cursor += 1
            assert r['path'] == '/walker/' + name + ('/' + target if target else '')
            assert r['input'] == body and r['http_status'] == 200
            return copy.deepcopy(r['output']['data']['reports'])

    graph = corpus.make_graph('littlex', corpus.SCALES['smoke'], random.Random(42))
    operations = corpus.session('littlex', corpus.SCALES['smoke'], graph)
    replay = StoredReplay()
    mapping = read(directory / 'mapping-initial.json')
    for operation in operations:
        expected = corpus.result(graph, operation)
        assert native.replay('littlex', replay, None, mapping, operation) == expected
    feed = next(op for op in reversed(operations) if op['op'] == 'feed')
    while replay.cursor < len(business):
        assert native.replay('littlex', replay, None, mapping, feed) == corpus.result(graph, feed)
    final = [r for r in requests if r['path'].startswith('/walker/SuiteInspect')][-1]

    class StoredInspection:
        def walker(self, name, body, token):
            assert name == 'SuiteInspect' and body == final['input']
            return copy.deepcopy(final['output']['data']['reports'])

    native.verify_snapshot(StoredInspection(), None, mapping, graph, 'littlex')
    littlex.append(dict(config=row['config_id'], stored_RPC_outputs_replayed=replay.cursor,
        original_workflow_RPCs=sum(r['phase'] == 'workflow' for r in business),
        excluded_steady_RPCs=sum(r['phase'] != 'workflow' for r in business), final_graph_checked=True))
output = dict(passed=True, scope='Completed9 correctness binding; pure frozen-oracle replay only, no app/DB execution',
    index=dict(path=str(RUN / 'index.json'), sha256=sha(RUN / 'index.json')),
    plan=index['plan'], source_closure=plan['sources'], verified_source_files=50,
    unique_owned_databases=9, active_zero_owned_drops=9, ownership_log_cluster_stopped_empty=True,
    cases=cases, LittleX_original_replay=littlex, mechanism_refs=index['mechanism_checks'],
    oracle_sources={str(p): sha(p) for p in [suite / 'app_suite/native.py', suite / 'datasets/ttg/build.py']},
    formal_samples_accepted=0, reviewer_DB_jobs=0,
    limits='No large event bodies/full runtime trees parsed; host quiet proof/main formal release are separate')
(HERE / 'correctness-v5-complete-review.json').write_text(json.dumps(output, indent=2) + '\n')
print(json.dumps(dict(passed=True, correctness_cases=9, sources=50, LittleX_RPCs=[15, 15, 15],
    report=str(HERE / 'correctness-v5-complete-review.json'))))
