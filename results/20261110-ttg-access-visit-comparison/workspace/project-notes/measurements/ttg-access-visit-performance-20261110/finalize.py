"""Small derived-only final binding; the raw audit is analyze.py/results.json."""
import hashlib
import json
from pathlib import Path

E = Path(__file__).resolve().parent
C = E.parent / 'ttg-access-visit-20261110'

def read(p):
    return json.loads(p.read_text())

def ref(p):
    return {'path': str(p), 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()}

d = read(E / 'results.json')
ix = read(E / 'run-v1/index.json')
assert d['passed'] and ix['passed'] and ix['source_after_passed']
assert read(E / 'stopped.json')['passed']
native = []
for name in ('native-v1', 'native-v2'):
    p = C / name
    assert read(p / 'source-start.json') == read(p / 'source-end.json')
    assert read(p / 'outcome.json')['passed']
    life = read(p / 'lifecycle.json')
    assert life['child_exit'] == 0 and life['pg_status'] == 3 and not life['has_pid']
    native.append({k: ref(p / (k + '.json')) for k in
                   ('source-start', 'source-end', 'outcome', 'lifecycle')})

paired = []
for repeat in range(3):
    ss = {s['mode']: s for s in d['samples'] if s['app'] == 'littlex'
          and s['phase'] == 'measured' and s['repeat'] == repeat}
    a, b = ss['aggressive'], ss['conservative']
    assert len(a['requests']) == len(b['requests']) == 9
    for x, y in zip(a['requests'], b['requests']):
        assert x['walker'] == y['walker']
        fixed = lambda r: sorted(v for v in r['prefetched_logical_ids'] if not v.startswith('unmapped:'))
        fresh = lambda r: sum(v.startswith('unmapped:') for v in r['prefetched_logical_ids'])
        assert fixed(x) == fixed(y) and fresh(x) == fresh(y)
        assert x['payload_objects'] == y['payload_objects']
        assert x['unused_payload_objects'] == y['unused_payload_objects'] == 0
        paired.append(dict(repeat=repeat, walker=x['walker'],
                           fixed_logical_ids_equal=True, prefetched=x['payload_objects'],
                           new_unmapped_ids_per_mode=fresh(x)))

groups = []
for g in d['groups']:
    got, used, demand = [g[k]['median'] for k in
                         ('payload_objects', 'demanded_prefetch_objects', 'successful_demand_objects')]
    groups.append(dict(app=g['app'], mode=g['mode'], n=3,
                       prefetched=got, used=used, unused=got-used,
                       usefulness=used/got, demand_coverage=used/demand,
                       actual_demand=demand, data_sql=g['sql_data']['median'],
                       control_sql=g['sql_control']['median']))

out = dict(passed=True, results=ref(E/'results.json'), stopped=ref(E/'stopped.json'),
           native=native, groups=groups, littlex_request_pairs=paired,
           limits=['Request/session-local unique IDs, summed across a workflow.',
                   'LittleX fixed fixture IDs match; the final feed also contains one newly created ID per mode, whose UUIDs differ. No UUID equality is asserted for it.',
                   'Business outputs, final physical state and fresh-session checks passed in all 24 cases.',
                   'Precision-instrumented measurements establish usefulness/coverage, not uninstrumented latency.',
                   'Executable Access projection is a supported prefix; unknown calls, merged state and general loop/heap effects remain boundaries.'])
(E/'final-binding.json').write_text(json.dumps(out, indent=2)+'\n')
print(json.dumps({'passed': True, 'paired_littlex_requests': len(paired), 'groups': groups}, indent=2))
