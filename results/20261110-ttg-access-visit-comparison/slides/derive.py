"""Read-only, source-bound slide data. Never rewrites accepted measurements."""
import collections
import gzip
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
E = HERE.parent
def read(p): return json.loads(p.read_text())
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def uid(x): return x.replace('-', '')
inputs = {}
def bound(p, expected=None):
    h = sha(p)
    if expected is not None: assert h == expected, str(p)
    inputs[str(p)] = h
    return p
results = read(bound(E/'results.json'))
assert results['passed'] and read(bound(E/'stopped.json'))['passed']
samples = []
for sample in results['samples']:
    if sample['phase'] != 'measured': continue
    seal = read(bound(Path(sample['raw']['path']), sample['raw']['sha256']))
    base = Path(sample['raw']['path']).parent
    def get(name):
        p = bound(base/name, seal['files'][name]); return read(p)
    fixture, final = get('fixture-raw.json'), get('final-graph-raw.json')
    identities = get('identity-map.json')
    mapping = {uid(v): k for k, v in get('mapping-initial.json').items()} if 'mapping-initial.json' in seal['files'] else identities
    types = {uid(n['id']): n['arch_type'] for n in fixture+final}
    props = {mapping.get(uid(n['id']), uid(n['id'])): n['props']['archetype'] for n in fixture if n['kind']=='NodeAnchor'}
    final_props = {mapping.get(uid(n['id']), uid(n['id'])): n['props']['archetype'] for n in final if n['kind']=='NodeAnchor'}
    request_map = {r['request']: r for r in sample['requests']}
    events = collections.defaultdict(list)
    for p in sorted(base.glob('server-*.events.jsonl*')):
        bound(p, seal['files'][p.name])
        with (gzip.open(p, 'rt') if p.suffix=='.gz' else p.open()) as f:
            for line in f:
                row = json.loads(line)
                if row.get('origin_request_id') in request_map:
                    events[row['origin_request_id']].append(row)
    requests = []
    for q, original in request_map.items():
        es = events[q]
        demand = {(e['session'],uid(v)) for e in es if e['kind']=='precision_access' and not e['planning'] for v in e['ids']}
        pref = {(e['session'],uid(e['uid'])) for e in es if e['kind']=='precision_payload_returned'}
        submitted = {(e['session'],uid(v)) for e in es if e['kind']=='precision_prefetch_batch' for v in e['ids']}
        assert (len(pref), len(demand), len(pref & demand)) == (original['payload_objects'],original['successful_demand_objects'],original['demanded_prefetch_objects'])
        # Every candidate in the comparisons below is resolved to a source-bound
        # canonical/logical ID. Fresh IDs are kept out of cross-run set claims.
        logical = lambda vals: sorted({mapping[k] for _,k in vals if k in mapping})
        roots = {k for _,k in demand if k=='0'*32 or k not in types}
        requests.append(dict(walker=original['walker'], request=q,
            demanded=logical(demand), prefetched=logical(pref), unused=logical(pref-demand),
            demand_count=len(demand), prefetched_count=len(pref), used=len(pref&demand),
            unused_count=len(pref-demand), root_count=sum(k in roots for _,k in demand),
            roots=[dict(id=k, global_root=k=='0'*32,
                        witnessed_entry=any(e['kind']=='precision_osp_entry' and uid(e['uid'])==k for e in es),
                        witnessed_owner=any(uid(n.get('root_id') or '')==k for n in fixture+final)) for k in sorted(roots)],
            gap_submitted=len((demand-pref)&submitted)))
    # Source anchoring for the filter-only classifications below.
    for filename in ('server.jac','server.impl.jac'):
        if filename in seal['files']: bound(base/filename, seal['files'][filename])
    states = []
    if sample['app']=='recipe_pantry':
        known = {}
        for step in get('native-steps.json'):
            a = step['actual']; w = step['walker']
            if w=='ShoppingList': states.append(dict(known))
            if w=='PantryBoard' and isinstance(a,dict):
                for m in a.get('meals',[]): known[mapping[uid(m['id'])]]=m['status']
            if w=='PlanMeal' and a.get('ok'):
                known[mapping[uid(a['meal_id'])]]='planned'
            if w=='CookMeal' and a.get('ok'):
                known[mapping[uid(step['input']['meal_id'])]]='cooked'
    samples.append(dict(app=sample['app'],mode=sample['mode'],repeat=sample['repeat'],
                        requests=requests,props=props,final_props=final_props,shopping_states=states))

filter_checks = []
root_rates = []
for app in ('jdrive','littlex','recipe_pantry'):
    for repeat in range(3):
        pair={s['mode']:s for s in samples if s['app']==app and s['repeat']==repeat}
        a,b=pair['aggressive'],pair['conservative']
        assert len(a['requests'])==len(b['requests'])
        confirmed=[]; shopping=0
        for i,(x,y) in enumerate(zip(a['requests'],b['requests'])):
            assert x['walker']==y['walker']
            extra=set(x['demanded'])-set(y['demanded'])
            if app=='jdrive' and x['walker']=='VisibleFolderTree':
                for k in sorted(extra):
                    # First tree precedes TrashFolder; the following trees see
                    # final trash flags (NewFolder adds only an untrashed node).
                    state=a['props'] if i==1 else a['final_props']
                    assert state[k]['__type__']=='Folder' and state[k]['trashed'] is True
                    assert k in x['prefetched'] and k not in x['unused']
                    confirmed.append(dict(request_index=i,walker=x['walker'],logical_id=k,
                                          reason='trashed=True candidate; SQL predicate excludes full-node fetch'))
            if app=='recipe_pantry' and x['walker']=='ShoppingList':
                state=a['shopping_states'][shopping]; shopping+=1
                for k in sorted(extra):
                    assert state[k]=='cooked'
                    assert a['final_props'][k]['__type__']=='Meal'
                    assert k in x['prefetched'] and k not in x['unused']
                    confirmed.append(dict(request_index=i,walker=x['walker'],logical_id=k,
                                          reason='status=cooked candidate; SQL predicate excludes full-node fetch'))
        expected={'jdrive':61,'littlex':0,'recipe_pantry':3}[app]
        assert len(confirmed)==expected,(app,len(confirmed))
        filter_checks.append(dict(app=app,repeat=repeat,confirmed_filter_only_prefetch=len(confirmed),records=confirmed))
        if app=='recipe_pantry':
            for mode,s in pair.items():
                roots=sum(r['root_count'] for r in s['requests'])
                for r in s['requests']:
                    assert all(v['global_root'] or v['witnessed_entry'] or v['witnessed_owner'] for v in r['roots'])
                assert roots==39
                got=sum(r['used'] for r in s['requests']); demand=sum(r['demand_count'] for r in s['requests'])
                root_rates.append(dict(mode=mode,repeat=repeat,covered=got,all_demand=demand,
                    root_demand=roots,nonroot_demand=demand-roots,nonroot_coverage=got/(demand-roots)))

groups=[]
for g in results['groups']:
    values=lambda k:g[k]['values']
    assert all(len(set(values(k)))==1 for k in ('payload_objects','successful_demand_objects','demanded_prefetch_objects','unused_payload_objects'))
    p,d,h,u=[g[k]['median'] for k in ('payload_objects','successful_demand_objects','demanded_prefetch_objects','unused_payload_objects')]
    filt={'jdrive':61,'littlex':0,'recipe_pantry':3}[g['app']] if g['mode']=='aggressive' else 0
    groups.append(dict(app=g['app'],mode=g['mode'],n=3,prefetched=p,demand=d,covered=h,
        coverage=h/d,used_fraction=h/p,unused=u,confirmed_filter_only=filt,
        confirmed_unnecessary_lower_bound=u+filt,
        data_sql=g['sql_data']['median'],control_sql=g['sql_control']['median']))
out=dict(passed=True,groups=groups,filter_checks=filter_checks,recipe_root_rates=root_rates,
    samples=samples,inputs=inputs,derive_source_sha256=sha(Path(__file__)),
    semantic_definition='Unnecessary full-node payload: a payload that need not be transferred/materialized to preserve the measured business result. Predicate evaluation inside PostgreSQL is still necessary.',
    bound='Confirmed lower bound = unused prefetch payload + disjoint source-validated filter-only prefetched payload. This is not an exhaustive semantic-minimality oracle. Zero means no confirmed examples in these two audited classes.',
    hit_definition='Observed demand coverage = unique request/session foreground-demand IDs intersect actual prefetch-returned IDs / foreground-demand IDs. Memory hits included; not SQL cache-hit rate, not minimal semantic-demand coverage.',
    unit='Request/session-local unique node IDs summed over the workflow, not globally distinct nodes.')
(HERE/'slide-data.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps({'groups':groups,'recipe_root_rates':root_rates},indent=2))
