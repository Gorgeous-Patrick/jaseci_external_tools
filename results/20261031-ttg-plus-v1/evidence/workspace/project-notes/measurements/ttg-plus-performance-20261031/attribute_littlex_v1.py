"""Read-only, sealed primary LittleX per-RPC/fingerprint attribution."""
import collections
import hashlib
import json
from pathlib import Path
import statistics
import sys

ROOT=Path('/home/baichuan/jaseci')
sys.path.insert(0,str(ROOT/'reproduction/ttg-plus-performance'))
from interop import load_jsonl,reference,scope_calls,totals
from sql_reconciliation import fingerprint,sql_kind

E=ROOT/'project-notes/measurements/ttg-plus-performance-20261031'
index=E/'formal-v1/index.json'
rows=json.loads(index.read_text())['rows']
trials=[]
def checked_ref(value):
    path=Path(value['path'])
    assert reference(path)==value,'Input reference hash changed'
    return path
for row in rows:
    if row['case_id']!='littlex' or row['phase']!='measured':continue
    directory=checked_ref(row['result']['raw']).parent
    metric=json.loads(checked_ref(row['result']['metrics']).read_text())
    calls=load_jsonl(directory,'server-*.calls.jsonl*')
    requests=load_jsonl(directory,'http-raw.jsonl*')
    assigned,startup=scope_calls(calls,requests)
    primary=[(c,r) for c,r in assigned if r['phase']=='workflow']
    total=totals([c for c,r in primary])
    for k,v in total.items():
        assert metric['primary'][k]==v,(row['trial_id'],k)
    groups=collections.defaultdict(list)
    rpc=collections.defaultdict(list)
    for c,r in primary:
        if c['send_ns'] is None:continue
        key=(fingerprint(c['sql']),sql_kind(c['sql']),c['role'])
        groups[key].append(c)
        rpc[(r['request'],r['path'],*key)].append(c)
    def record(key,calls,request=None,path=None):
        f,k,role=key
        return dict(fingerprint=f,kind=k,role=role,sql=calls[0]['sql'],
            **totals(calls),request=request,path=path,
            observed_calls=[{name:c.get(name) for name in ('origin_request_id','server_generation',
                'client_process_pid','backend_pid','send_ns','ready_ns','data_rows','data_row_bytes')}
                for c in calls])
    trials.append(dict(config=row['config_id'],repeat=row['repeat'],trial=row['trial_id'],
        raw=row['result']['raw'],metric=row['result']['metrics'],primary=total,
        fingerprints=[record(k,v) for k,v in sorted(groups.items())],
        per_RPC=[record(k[2:],v,k[0],k[1]) for k,v in sorted(rpc.items())]))
assert len(trials)==9
targets=[]
for prefix,label in [('3166e116','batched current-ability path region'),('d1067307','recursive certified path region')]:
    groups=[g for t in trials if t['config']=='ttg_plus' for g in t['fingerprints'] if g['fingerprint'].startswith(prefix)]
    assert len(groups)==3 and len({g['sql'] for g in groups})==1
    per_rpc=[dict(trial=t['trial'],repeat=t['repeat'],**g) for t in trials if t['config']=='ttg_plus'
        for g in t['per_RPC'] if g['fingerprint'].startswith(prefix)]
    targets.append(dict(label=label,fingerprint=groups[0]['fingerprint'],sql=groups[0]['sql'],
        calls_per_workflow=[g['sql_dispatches'] for g in groups],
        mean_protocol_ms_per_workflow=statistics.mean(g['protocol_sum_ns']/1e6 for g in groups),
        per_RPC=per_rpc,
        binding_contract='Primary captures SQL/framing, not Bind values. Recapture exact Bind on matched diagnostic fixture; label separately.'))
out=E/'littlex-attribution-v1';out.mkdir(exist_ok=False)
result=dict(passed=True,index=reference(index),source=reference(__file__),trials=trials,diagnostic_targets=targets,
    scope='All three accepted measured LittleX repeats per mode; workflow HTTP-origin SQL incl late drain; sealed readers and generation validation.',
    meaning='Protocol completion wall includes decoding progress. SQL contribution is measured attribution, not CPU/server planning causation.')
(out/'results.json').write_text(json.dumps(result,indent=2)+'\n')
for target in targets:
    (out/(target['fingerprint'][:16]+'.sql')).write_text(target['sql']+'\n')
(out/'artifacts.json').write_text(json.dumps(dict(passed=True,outputs=[reference(p) for p in sorted(out.iterdir())]),indent=2)+'\n')
print(json.dumps(dict(result=reference(out/'results.json'),targets=[dict(fingerprint=t['fingerprint'],
    calls=t['calls_per_workflow'],mean_ms=t['mean_protocol_ms_per_workflow'],
    paths=sorted({r['path'] for r in t['per_RPC']})) for t in targets]),indent=2))
