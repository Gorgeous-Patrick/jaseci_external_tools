"""Independent raw-interval/count audit of the completed two-app study; no DB work."""
import argparse
from collections import Counter, defaultdict
import gzip
import hashlib
import json
from pathlib import Path
import re


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def reference(value):
    path = Path(value['path'])
    assert sha(path) == value['sha256'], path
    return path


def lines(path):
    opener = gzip.open if path.suffix == '.gz' else open
    with opener(path, 'rt') as stream:
        return [json.loads(line) for line in stream if line.strip()]


def union(spans):
    end = None
    total = 0
    for start, stop in sorted(spans):
        assert isinstance(start, int) and isinstance(stop, int) and stop >= start
        if end is None or start > end:
            total += stop - start
            end = stop
        elif stop > end:
            total += stop - end
            end = stop
    return total


def category(sql):
    token = re.match(r'\s*([A-Za-z]+)', sql).group(1).upper()
    if token in {'SELECT', 'WITH', 'INSERT', 'UPDATE', 'DELETE', 'MERGE', 'VALUES', 'FETCH'}:
        return 'data'
    if token in {'BEGIN', 'START', 'SET', 'SAVEPOINT', 'RELEASE', 'DISCARD', 'COMMIT',
                 'END', 'ROLLBACK', 'ABORT', 'RESET', 'SHOW', 'DEALLOCATE', 'CLOSE'}:
        return 'control'
    return 'other'


def audit(run, exported, output):
    run, exported, output = map(lambda p: Path(p).resolve(), (run, exported, output))
    index, result = read(run/'index.json'), read(exported)
    assert index['status'] == 'complete' and index['passed'] and result['passed']
    assert len(index['cases']) == 48
    assert result['warmup_workflows'] == 12 and result['measured_workflows'] == 36
    assert reference(result['index']) == run/'index.json'
    for path, expected in result['source_hashes'].items():
        assert sha(path) == expected, path
    groups, phases, identities, databases = defaultdict(list), Counter(), set(), set()
    total_members = 0
    for row in index['cases']:
        assert row['passed']
        identity = (row['app'], row['config_id'], row['phase'], row['repeat'])
        assert identity not in identities
        identities.add(identity)
        phases[row['phase']] += 1
        case = run/row['trial_id']
        seal = reference(row['raw_seal'])
        assert seal == case/'artifacts.json'
        archive = read(seal)
        assert archive['passed']
        for member, expected in archive['files'].items():
            assert sha(case/member) == expected, (case, member)
            total_members += 1
        metric = read(reference(row['metrics']))
        assert metric['raw_seal'] == row['raw_seal']
        acceptance = read(reference(metric['independent_acceptance']))
        assert acceptance['passed'] and acceptance['verification']['independent_semantic_recheck']
        reference(acceptance['semantic_proof'])
        assert acceptance['database_state']['matches_sealed_final_graph']
        assert acceptance['database_state']['final_graph_sha256'] == sha(case/'final-graph-raw.json')
        database = acceptance['database_state']['database']
        assert database not in databases
        databases.add(database)
        http = lines(case/'http-raw.jsonl')
        request_keys = {(str(r['server_generation']), r['request'])
                        for r in http if r['phase'] == 'workflow'}
        files = sorted(case.glob('server-*.calls.jsonl*'))
        names = [str(p).removesuffix('.gz') for p in files]
        assert len(names) == len(set(names))
        calls = [c for p in files for c in lines(p)
                 if (str(c['server_generation']), c.get('origin_request_id')) in request_keys]
        dispatched = [c for c in calls if c['send_ns'] is not None]
        spans = [(c['send_ns'], c['ready_ns']) for c in dispatched]
        assert all(c['database'] == database and c['ready_messages'] == 1 for c in dispatched)
        kinds = Counter(category(c['sql']) for c in dispatched)
        values = dict(protocol_sum_ns=sum(b-a for a, b in spans), protocol_union_ns=union(spans),
            driver_sum_ns=sum(c['driver_end_ns']-c['driver_start_ns'] for c in calls),
            driver_union_ns=union([(c['driver_start_ns'], c['driver_end_ns']) for c in calls]),
            sql_dispatches=len(dispatched), sql_data=kinds['data'], sql_control=kinds['control'],
            sql_other=kinds['other'], command_complete=sum(c['command_complete'] for c in calls),
            protocol_cycles=sum(c['ready_messages'] for c in calls),
            server_error_messages=sum(c['error_messages'] for c in calls),
            data_rows=sum(c['data_rows'] for c in calls),
            data_row_payload_bytes=sum(c['data_row_payload_bytes'] for c in calls))
        for name, value in values.items():
            assert metric['primary'][name] == value, (row['trial_id'], name)
        if row['phase'] == 'measured':
            groups[row['app'], row['config_id']].append(values)
    assert phases == {'excluded_warmup': 12, 'measured': 36}
    assert len(groups) == len(result['table']) == 12
    for cell in result['table']:
        values = groups[cell['app'], cell['config_id']]
        assert len(values) == cell['n'] == 3
        for name in values[0]:
            ordered = sorted(v[name] for v in values)
            stats = cell['metrics'][name]
            assert stats['n'] == 3
            assert stats['median'] == ordered[1]
            assert stats['minimum'] == ordered[0] and stats['maximum'] == ordered[2]
            assert stats['iqr'] == (ordered[2]-ordered[0])/2
    proof = dict(passed=True, scope='Independent raw workflow interval/count/byte and n3 reaggregation',
        run_index=dict(path=str(run/'index.json'), sha256=sha(run/'index.json')),
        accepted_export=dict(path=str(exported), sha256=sha(exported)),
        audit_source=dict(path=str(Path(__file__).resolve()), sha256=sha(__file__)),
        trials_checked=48, sealed_members_checked=total_members, unique_databases=48,
        excluded_warmups=12, measured_workflows=36, cells_checked=12,
        source_refs_checked=len(result['source_hashes']),
        limits='No new DB/app/runtime execution; overlap-pair interpretation separately audited')
    output.mkdir(parents=True, exist_ok=False)
    (output/'audit.json').write_text(json.dumps(proof, indent=2)+'\n')
    return proof


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', required=True)
    parser.add_argument('--export', dest='exported', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    print(json.dumps(audit(args.run, args.exported, args.output)))
