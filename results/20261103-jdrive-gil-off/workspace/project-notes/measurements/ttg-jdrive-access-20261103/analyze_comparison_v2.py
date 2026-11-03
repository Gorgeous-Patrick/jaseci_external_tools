"""Independent raw-count/time/GIL validation for the small executor comparison."""
import gzip
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from statistics import median

ROOT=Path('/home/baichuan/jaseci')
E=ROOT/'project-notes/measurements/ttg-jdrive-freethreaded-20261103/comparison-access-v2'
def read(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def checked(ref):
    assert sha(ref['path'])==ref['sha256'],ref
    return read(ref['path'])
def stats(xs):return dict(n=len(xs),median=median(xs),min=min(xs),max=max(xs),values=xs)
def union(intervals):
    end=-1;total=0
    for a,b in sorted(intervals):
        assert b>=a
        total+=max(0,b-max(a,end));end=max(end,b)
    return total
def lines(p):
    with (gzip.open(p,'rt') if p.suffix=='.gz' else p.open()) as f:
        for line in f:
            if line.strip():yield json.loads(line)

def classify(sql):
    text=' '.join(sql.split());upper=text.upper()
    if upper.startswith(('BEGIN','COMMIT','ROLLBACK','SET ','DISCARD ')):return 'control'
    if upper.startswith('WITH RECURSIVE') and 'origin_id' in text and 'source_props' in text:return 'tree_path'
    if 'identity_users' in text:return 'identity'
    if text.startswith('SELECT n1.id, e1.id FROM unnest('):return 'path'
    if 'FROM anchors a WHERE a.id = ANY(' in text:return 'payload'
    if upper.startswith(('INSERT ','UPDATE ','DELETE ')):return 'write'
    return 'unknown'

def main():
    index=read(E/'index.json');plan=checked(index['plan'])
    assert index['passed'] and index['status']=='complete' and len(index['rows'])==8
    assert [{k:r[k] for k in plan['schedule'][0]} for r in index['rows']]==plan['schedule']
    samples=[];databases=set();semantics=set();files=0;gil_assertions=0
    for row in index['rows']:
        refs=row['result'];m=checked(refs['metrics']);p=checked(refs['proof'])
        a=checked(refs['acceptance']);seal=checked(refs['raw']);gil=checked(row['gil_proof'])
        assert m['passed'] and p['passed'] and a['passed'] and gil['passed']
        assert p['database'] not in databases;databases.add(p['database'])
        semantics.add((p['fixture_sha256'],p['actions_sha256'],p['output_sha256']))
        directory=Path(refs['raw']['path']).parent
        for name,digest in seal['files'].items():assert sha(directory/name)==digest;files+=1
        requests=[r for r in read(directory/'requests.json') if r['phase']=='workflow']
        assert len(requests)==7
        keys={(str(r['server_generation']),r['request']) for r in requests}
        calls=[c for f in directory.glob('server-*.calls.jsonl.gz') for c in lines(f)]
        actual=[c for c in calls if (str(c['server_generation']),c.get('origin_request_id')) in keys and c.get('send_ns') is not None]
        assert all(c['error'] is None and c['database']==p['database'] for c in actual)
        categories=Counter(classify(c['sql']) for c in actual)
        assert categories['control']==m['primary']['sql_control']
        assert len(actual)-categories['control']==m['primary']['sql_data'] and not categories['unknown']
        intervals=[(c['send_ns'],c['ready_ns']) for c in actual]
        total=sum(b-a for a,b in intervals);united=union(intervals)
        assert (len(actual),total,united)==(m['primary']['sql_dispatches'],m['primary']['protocol_sum_ns'],m['primary']['protocol_union_ns'])
        records=[r for f in directory.glob('gil-proof-*.jsonl') for r in lines(f)]
        assert records and all(r['gil_enabled'] is False and r['Py_GIL_DISABLED']==1 for r in records)
        observed={};expected={}
        for r in records:
            if r['kind']=='sql_boundary':
                key=(r['pid'],r['thread_id'],r['server_generation'],r['origin_request_id'])
                observed[key]=observed.get(key,0)+1
        for c in calls:
            key=(c['client_process_pid'],c['thread_id'],str(c['server_generation']),c.get('origin_request_id'))
            expected[key]=expected.get(key,0)+1
        assert observed==expected and len(calls)==gil['SQL_assertions']
        gil_assertions+=len(calls)
        mode=row['config_id'];fg=[c for c in actual if c['role']=='foreground'];bg=[c for c in actual if c['role']=='background_prefetch']
        parents={c['client_process_pid'] for c in fg};assert len(parents)==1
        if mode=='off':assert not bg
        else:
            assert all(c['actual_executor']==mode for c in bg)
            if not bg:assert all(o['summary']['submitted_count']==0 for o in m['model_outcomes'])
            assert all((c['client_process_pid'] in parents)==(mode=='thread') for c in bg)
            if mode=='thread':
                for c in bg:
                    peers=[f for f in fg if f['origin_request_id']==c['origin_request_id']]
                    assert peers and all(f['thread_id']!=c['thread_id'] and f['backend_pid']!=c['backend_pid'] for f in peers)
        overlaps=[]
        for b in bg:
            for f in fg:
                if (b['origin_request_id'],b['server_generation'])!=(f['origin_request_id'],f['server_generation']) or b['backend_pid']==f['backend_pid']:continue
                start=max(b['send_ns'],f['send_ns']);stop=min(b['ready_ns'],f['ready_ns'])
                if stop>start:overlaps.append((start,stop))
        feeds=[]
        outcomes={(str(o['server_generation']),o['origin_request_id']):o['summary'] for o in m['model_outcomes']}
        for r in requests:
            if r['path'].split('/')[2]!='VisibleFolderTree':continue
            key=(str(r['server_generation']),r['request']);selected=[c for c in actual if (str(c['server_generation']),c['origin_request_id'])==key]
            if mode!='off':assert outcomes[key]['executor']==mode
            value=r['output'].get('data',r['output'])
            entries=value['reports'][0]['entries']
            feeds.append(dict(request=r['request'],SQL=len(selected),entries=len(entries),
                HTTP_ms=(r['end_ns']-r['start_ns'])/1e6, outcome=outcomes.get(key),
                categories=dict(Counter(classify(c['sql']) for c in selected)),fingerprints=[dict(sql=c.get('sql'),category=classify(c['sql']),role=c['role'],protocol_ms=(c['ready_ns']-c['send_ns'])/1e6) for c in selected]))
        assert len(feeds)==3 and [t['entries'] for t in feeds]==[19,11,12]
        samples.append(dict(mode=mode,phase=row['phase'],repeat=row['repeat'],trial_id=row['trial_id'],
            categories=dict(categories),SQL=len(actual),DB_sum_ms=total/1e6,DB_union_ms=united/1e6,
            HTTP_sum_ms=sum(r['end_ns']-r['start_ns'] for r in requests)/1e6,
            FG_BG_overlap_ms=union(overlaps)/1e6,background_SQL=len(bg),
            child_PIDs=sorted({c['client_process_pid'] for c in bg}-parents),
            background_thread_ids=sorted({c['thread_id'] for c in bg}),trees=feeds,request_SQL=[dict(walker=r['path'].split('/')[2],request=r['request'],SQL=sum((str(c['server_generation']),c['origin_request_id'])==(str(r['server_generation']),r['request']) for c in actual),HTTP_ms=(r['end_ns']-r['start_ns'])/1e6) for r in requests],data_SQL=m['primary']['sql_data'],control_SQL=m['primary']['sql_control'],model_outcomes=m['model_outcomes'],evidence=refs,gil_proof=row['gil_proof']))
    assert len(databases)==8 and len(semantics)==1
    ownership=ROOT/'reproduction/ttg-jdrive-freethreaded/pg-access-v2/ownership-and-cleanup.jsonl'
    records=[json.loads(l) for l in ownership.read_text().splitlines()]
    drops=[x for x in records if x['action']=='successful_database_dropped']
    assert len(drops)==8 and {x['database'] for x in drops}==databases
    assert all(x['active_sessions']==0 for x in drops)
    assert records[-1]['action']=='cluster_stopped' and not records[-1]['retained_databases']
    groups={}
    for mode in ['off','thread']:
        chosen=[s for s in samples if s['mode']==mode and s['phase']=='measured']
        assert sorted(s['repeat'] for s in chosen)==[0,1,2]
        groups[mode]={k:stats([s[k] for s in chosen]) for k in ['SQL','DB_sum_ms','DB_union_ms','HTTP_sum_ms','FG_BG_overlap_ms','background_SQL','data_SQL','control_SQL']}
    result=dict(passed=True,index_sha256=sha(E/'index.json'),plan=index['plan'],groups=groups,samples=samples,
        sealed_files_verified=files,SQL_GIL_assertions_verified=gil_assertions,
        scope='Unchanged JDrive 40-folder/13-file/1-drive fixture; same runtime and Python 3.14.6 GIL-off; off/thread n3 fresh workflows after one excluded warmup each; seven instrumented HTTP response intervals, all-role send-to-Z DB intervals. No background activity is explicitly inactive, not proof of worker execution.')
    (E/'results.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(passed=True,groups=groups,SQL_GIL_assertions_verified=gil_assertions),indent=2))
if __name__=='__main__':main()
