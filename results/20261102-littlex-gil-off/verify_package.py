"""Portable byte, raw-seal, GIL/executor and numeric verifier. No database jobs."""
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path
from statistics import median
import tarfile

ROOT=Path(__file__).resolve().parent
def digest(data):return hashlib.sha256(data).hexdigest()
def load(name):return json.loads((ROOT/name).read_text())
def safe(name):
    p=Path(name)
    assert not p.is_absolute() and '..' not in p.parts,name
    return ROOT/p
def union(intervals):
    end=-1;total=0
    for a,b in sorted(intervals):
        assert b>=a
        total+=max(0,b-max(a,end));end=max(end,b)
    return total
def main():
    inventory=load('manifests/files.json');special={'manifests/files.json','package-integrity.json'}
    assert {str(p.relative_to(ROOT)) for p in ROOT.rglob('*') if p.is_file()}==set(inventory)|special
    assert not any(p.is_symlink() for p in ROOT.rglob('*'))
    for name,row in inventory.items():
        data=safe(name).read_bytes();assert len(data)==row['bytes'] and digest(data)==row['sha256'],name
    integrity=load('package-integrity.json');assert integrity['passed'] and digest((ROOT/'manifests/files.json').read_bytes())==integrity['files_sha256']
    mapping=load('manifests/path-mapping.json');by_original={m['original']:m for m in mapping};assert len(mapping)==len(by_original)
    blobs={};cases={}
    for a in load('manifests/archives.json'):
        assert digest(safe(a['path']).read_bytes())==a['sha256']
        declared={m['member']:m for m in a['members']};seen={}
        with tarfile.open(safe(a['path']),'r:xz') as t:
            for member in t:
                assert member.isfile() and member.name in declared and member.name not in seen
                m=declared[member.name];data=t.extractfile(member).read()
                assert len(data)==m['bytes'] and digest(data)==m['sha256']
                seen[member.name]=data;blobs[m['original']]=data
        assert set(seen)==set(declared)
        seal=json.loads(seen['artifacts.json']);assert seal['passed'] and set(seen)==set(seal['files'])|{'artifacts.json'}
        for name,h in seal['files'].items():assert digest(seen[name])==h
        cases[a['case']]=seen
    for m in mapping:
        data=blobs[m['original']] if 'member' in m else safe(m['package_path']).read_bytes()
        assert digest(data)==m['sha256'];blobs[m['original']]=data
    def ref(r):
        original=r['path'].removeprefix('/home/baichuan/jaseci/')
        data=blobs[original];assert digest(data)==r['sha256'];return json.loads(data)
    prefix='project-notes/measurements/ttg-littlex-freethreaded-20261102/comparison-v2/'
    index=json.loads(blobs[prefix+'index.json']);result=json.loads(blobs[prefix+'results.json'])
    assert index['passed'] and index['status']=='complete' and result['passed']
    assert digest(blobs[prefix+'index.json'])==result['index_sha256']
    plan=ref(index['plan']);sources=ref(plan['sources'])['files']
    external={r['original']:r for r in load('manifests/external-interpreter.json')}
    for path,h in sources.items():
        if path in external:assert h==external[path]['sha256']
        else:assert digest(blobs[path.removeprefix('/home/baichuan/jaseci/')])==h
    assert len(index['rows'])==12 and [{k:r[k] for k in plan['schedule'][0]} for r in index['rows']]==plan['schedule']
    samples=[];sql_assertions=0;dbs=set();semantic=set()
    for row in index['rows']:
        raw=cases[row['trial_id']];m=ref(row['result']['metrics']);p=ref(row['result']['proof']);a=ref(row['result']['acceptance']);g=ref(row['gil_proof'])
        assert all(r['passed'] for r in [m,p,a,g]) and p['database'] not in dbs;dbs.add(p['database'])
        semantic.add((p['fixture_sha256'],p['actions_sha256'],p['output_sha256']))
        calls=[json.loads(l) for n,data in raw.items() if n.endswith('.calls.jsonl.gz') for l in gzip.decompress(data).splitlines() if l]
        checks=[json.loads(l) for n,data in raw.items() if n.startswith('gil-proof-') and n.endswith('.jsonl') for l in data.splitlines() if l]
        assert checks and all(r['gil_enabled'] is False and r['Py_GIL_DISABLED']==1 for r in checks)
        checked=Counter((r['pid'],r['thread_id'],r['server_generation'],r['origin_request_id']) for r in checks if r['kind']=='sql_boundary')
        expected=Counter((c['client_process_pid'],c['thread_id'],str(c['server_generation']),c.get('origin_request_id')) for c in calls)
        assert checked==expected and len(calls)==g['SQL_assertions'];sql_assertions+=len(calls)
        requests=[r for r in json.loads(raw['requests.json']) if r['phase']=='workflow'];assert len(requests)==9
        keys={(str(r['server_generation']),r['request']) for r in requests}
        primary=[c for c in calls if (str(c['server_generation']),c.get('origin_request_id')) in keys and c.get('send_ns') is not None]
        assert all(c['error'] is None and c['database']==p['database'] for c in primary)
        intervals=[(c['send_ns'],c['ready_ns']) for c in primary];total=sum(b-a for a,b in intervals);united=union(intervals)
        assert (len(primary),total,united)==(m['primary']['sql_dispatches'],m['primary']['protocol_sum_ns'],m['primary']['protocol_union_ns'])
        mode=row['config_id'];fg=[c for c in primary if c['role']=='foreground'];bg=[c for c in primary if c['role']=='background_prefetch'];parents={c['client_process_pid'] for c in fg};assert len(parents)==1
        if mode=='off':assert not bg
        else:
            assert bg and all(c['actual_executor']==mode and ((c['client_process_pid'] in parents)==(mode=='thread')) for c in bg)
            if mode=='thread':
                for c in bg:
                    peers=[f for f in fg if f['origin_request_id']==c['origin_request_id']]
                    assert peers and all(f['thread_id']!=c['thread_id'] and f['backend_pid']!=c['backend_pid'] for f in peers)
        if row['phase']=='measured':samples.append(dict(mode=mode,SQL=len(primary),DB_sum_ms=total/1e6,DB_union_ms=united/1e6,HTTP_sum_ms=sum(r['end_ns']-r['start_ns'] for r in requests)/1e6))
    assert len(dbs)==12 and len(semantic)==1 and sql_assertions==7384
    for mode in ['off','thread','process']:
        s=[r for r in samples if r['mode']==mode];assert len(s)==3
        for key in ['SQL','DB_sum_ms','DB_union_ms','HTTP_sum_ms']:
            values=[r[key] for r in s];wanted=result['groups'][mode][key]
            assert values==wanted['values'] and median(values)==wanted['median'] and min(values)==wanted['min'] and max(values)==wanted['max']
    print('PASS: exact package inventory; 12 sealed cases; 7384 SQL/GIL joins; actual thread/process identities; n=3 SQL/HTTP/DB aggregates.')
if __name__=='__main__':main()
