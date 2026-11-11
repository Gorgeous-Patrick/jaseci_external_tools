"""Derive the November 11 slide update from copied accepted results; no DB."""
from collections import defaultdict
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
P = HERE.parent
U = HERE / 'update-20261111'

def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def build():
    inventory = json.loads((U / 'inputs.json').read_text())
    for r in inventory['files']:
        assert sha(P / r['packaged']) == r['sha256']
    results = json.loads((U / 'results.json').read_text())
    verification = json.loads((U / 'verification.json').read_text())
    assert results['passed'] and verification['passed']
    assert verification['app_results']['sha256'] == sha(U / 'results.json')
    assert verification['app_index']['sha256'] == sha(U / 'index.json')
    assert verification['app_stopped']['sha256'] == sha(U / 'stopped.json')
    assert results['captured'] == 8 and results['measured'] == 6
    rows = []
    for mode in ('before', 'after'):
        samples = sorted((s for s in results['samples'] if s['mode'] == mode and s['phase'] == 'measured'), key=lambda s:s['repeat'])
        assert [s['repeat'] for s in samples] == [0, 1, 2]
        fields = ('payload_objects', 'demanded_prefetch_objects', 'successful_demand_objects',
                  'unused_payload_objects', 'sql_data', 'sql_control')
        values = {k: [s[k] for s in samples] for k in fields}
        assert all(len(set(v)) == 1 for v in values.values())
        row = dict(mode=mode, n=3, **{k:v[0] for k,v in values.items()}, vectors=values)
        row['coverage'] = row['demanded_prefetch_objects'] / row['successful_demand_objects']
        row['total_sql'] = row['sql_data'] + row['sql_control']
        rows.append(row)
    assert rows[0]['successful_demand_objects'] == rows[1]['successful_demand_objects']
    for field in ('fixture_sha256','actions_sha256','output_sha256'):
        assert len({s[field] for s in results['samples']}) == 1
    request_groups = defaultdict(dict)
    for mode in ('before','after'):
        s = next(s for s in results['samples'] if s['mode'] == mode and s['phase'] == 'measured' and s['repeat'] == 0)
        sums = defaultdict(int)
        for r in s['requests']:
            sums[r['walker']] += r['demanded_prefetch_objects']
        for walker,v in sums.items():
            request_groups[walker][mode] = v
    changes = [dict(walker=w, **v, added=v['after']-v['before']) for w,v in request_groups.items()]
    assert sum(r['added'] for r in changes) == rows[1]['demanded_prefetch_objects']-rows[0]['demanded_prefetch_objects']
    return dict(passed=True, captured=8, excluded_warmups=2, measured=6,
                verified_sealed_files=results['verified_sealed_files'], current=rows[1],
                covered_by_walker={r['walker']:r['after'] for r in changes},
                pure_tests=verification['pure_tests'], native_regressions=verification['native_regressions'],
                inputs=inventory['files'], derive_source_sha256=sha(Path(__file__)),
                scope='November 11 Conservative before/after only. Aggressive, JDrive and LittleX were not rerun. Semantic unnecessary-payload count was not re-audited for this update.')

if __name__ == '__main__':
    d = build()
    (HERE / 'slide-data-v3.json').write_text(json.dumps(d,indent=2)+'\n')
    print(json.dumps({'passed':True,'current':d['current']},indent=2))
