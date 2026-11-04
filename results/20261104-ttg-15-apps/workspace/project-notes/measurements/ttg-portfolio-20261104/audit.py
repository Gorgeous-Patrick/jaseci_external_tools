"""Read-only raw audit. Run only after the selected batch is stopped."""
import argparse,gzip,hashlib,json
from pathlib import Path
from collections import Counter,defaultdict
from statistics import median
R=Path('/home/baichuan/jaseci')
def read(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def checked(r):assert sha(r['path'])==r['sha256'],r;return read(r['path'])
def lines(p):
    with (gzip.open(p,'rt') if p.suffix=='.gz' else p.open()) as f:
        for l in f:
            if l.strip():yield json.loads(l)
def union(xs):
    end=-1;total=0
    for a,b in sorted(xs):assert b>=a;total+=max(0,b-max(a,end));end=max(end,b)
    return total
def stats(xs):return dict(n=len(xs),median=median(xs),min=min(xs),max=max(xs),values=xs)
def main(e):
    e=Path(e).resolve();out=e/'run-v1';index=read(out/'index.json');plan=checked(index['plan'])
    assert index['passed'] and index['status']=='complete' and index['source_after_passed']
    assert [{k:r[k] for k in plan['schedule'][0]} for r in index['rows']]==plan['schedule']
    registry=read(R/'reproduction/ttg-app-performance/suite-final-20261030-v1/app_suite/registry.json')['apps']
    readers={x['app']:x['read_walker'] for x in registry}
    samples=[];databases=set();semantics=defaultdict(set);files=0;gil_count=0
    for row in index['rows']:
        refs=row['result'];m=checked(refs['metrics']);p=checked(refs['proof']);a=checked(refs['acceptance']);seal=checked(refs['raw']);gil=checked(row['gil_proof'])
        assert all(x['passed'] for x in (m,p,a,seal,gil));assert p['database'] not in databases;databases.add(p['database'])
        semantics[row['app']].add(tuple(p[k] for k in ('fixture_sha256','actions_sha256','output_sha256')))
        d=Path(refs['raw']['path']).parent
        for name,h in seal['files'].items():assert sha(d/name)==h;files+=1
        requests=[q for q in read(d/'requests.json') if q['phase']=='workflow'];assert requests
        keys={(str(q['server_generation']),q['request']) for q in requests}
        calls=[c for f in d.glob('server-*.calls.jsonl.gz') for c in lines(f)]
        actual=[c for c in calls if (str(c['server_generation']),c.get('origin_request_id')) in keys and c.get('send_ns') is not None]
        assert all(c['error'] is None and c['database']==p['database'] for c in actual)
        intervals=[(c['send_ns'],c['ready_ns']) for c in actual];total=sum(b-a for a,b in intervals);united=union(intervals)
        assert (len(actual),total,united)==(m['primary']['sql_dispatches'],m['primary']['protocol_sum_ns'],m['primary']['protocol_union_ns'])
        records=[z for f in d.glob('gil-proof-*.jsonl') for z in lines(f)]
        assert records and all(z['gil_enabled'] is False and z['Py_GIL_DISABLED']==1 for z in records)
        observed=Counter((z['pid'],z['thread_id'],z['server_generation'],z['origin_request_id']) for z in records if z['kind']=='sql_boundary')
        expected=Counter((c['client_process_pid'],c['thread_id'],str(c['server_generation']),c.get('origin_request_id')) for c in calls)
        assert observed==expected and len(calls)==gil['SQL_assertions'];gil_count+=len(calls)
        fg=[c for c in actual if c['role']=='foreground'];bg=[c for c in actual if c['role']=='background_prefetch'];parent={c['client_process_pid'] for c in fg};assert len(parent)==1
        if row['config_id']=='off':assert not bg
        else:
            for c in bg:
                assert c['actual_executor']=='thread' and c['client_process_pid'] in parent
                peers=[f for f in fg if f['origin_request_id']==c['origin_request_id']]
                assert peers and all(f['thread_id']!=c['thread_id'] and f['backend_pid']!=c['backend_pid'] for f in peers)
        overlaps=[]
        for b in bg:
            for f in fg:
                if (b['origin_request_id'],b['server_generation'])!=(f['origin_request_id'],f['server_generation']) or b['backend_pid']==f['backend_pid']:continue
                start=max(b['send_ns'],f['send_ns']);stop=min(b['ready_ns'],f['ready_ns'])
                if stop>start:overlaps.append((start,stop))
        per=[];fingerprints={}
        for q in requests:
            key=(str(q['server_generation']),q['request']);cs=[c for c in actual if (str(c['server_generation']),c['origin_request_id'])==key]
            fp={}
            for c in cs:
                h=hashlib.sha256(c['sql'].encode()).hexdigest();fingerprints[h]=c['sql'];r=fp.setdefault(h,dict(count=0,ms=0,roles=[]));r['count']+=1;r['ms']+=(c['ready_ns']-c['send_ns'])/1e6
                if c['role'] not in r['roles']:r['roles'].append(c['role'])
            per.append(dict(walker=q['path'].split('/')[2],request=q['request'],generation=q['server_generation'],SQL=len(cs),DB_ms=sum(c['ready_ns']-c['send_ns'] for c in cs)/1e6,HTTP_ms=(q['end_ns']-q['start_ns'])/1e6,fingerprints=fp))
        rs=[q for q in per if q['walker']==readers[row['app']]];assert rs
        samples.append(dict(app=row['app'],mode=row['config_id'],phase=row['phase'],repeat=row['repeat'],trial_id=row['trial_id'],
            SQL=len(actual),data_SQL=m['primary']['sql_data'],control_SQL=m['primary']['sql_control'],DB_sum_ms=total/1e6,DB_union_ms=united/1e6,
            HTTP_sum_ms=sum(q['end_ns']-q['start_ns'] for q in requests)/1e6,requests=len(requests),background_SQL=len(bg),FG_BG_overlap_ms=union(overlaps)/1e6,
            reader=readers[row['app']],reader_SQL=sum(q['SQL'] for q in rs),reader_DB_ms=sum(q['DB_ms'] for q in rs),reader_HTTP_ms=sum(q['HTTP_ms'] for q in rs),reader_requests=len(rs),
            requests_detail=per,fingerprint_SQL=fingerprints,model_outcomes=m['model_outcomes'],refs=refs,gil_proof=row['gil_proof'],physical_rows=a['database_state']['actual_row_count']))
    assert all(len(v)==1 for v in semantics.values())
    records=list(lines(R/'reproduction'/e.name/'pg-v1/ownership-and-cleanup.jsonl'))
    drops=[r for r in records if r['action']=='successful_database_dropped'];assert len(drops)==len(samples) and {r['database'] for r in drops}==databases and all(r['active_sessions']==0 for r in drops)
    assert records[-1]['action']=='cluster_stopped' and not records[-1]['retained_databases']
    keys=['SQL','data_SQL','control_SQL','DB_sum_ms','DB_union_ms','HTTP_sum_ms','requests','background_SQL','FG_BG_overlap_ms','reader_SQL','reader_DB_ms','reader_HTTP_ms','reader_requests']
    groups={}
    for app in semantics:
        groups[app]={}
        for mode in ('off','thread'):
            s=[v for v in samples if v['app']==app and v['mode']==mode and v['phase']=='measured'];assert sorted(v['repeat'] for v in s)==[0,1,2]
            groups[app][mode]={k:stats([v[k] for v in s]) for k in keys}
    result=dict(passed=True,index_sha256=sha(out/'index.json'),plan=index['plan'],groups=groups,samples=samples,sealed_files_verified=files,SQL_GIL_assertions_verified=gil_count,
        definitions='HTTP: sum of primary response-read intervals; DB: all-role send-to-ready sum/union. Setup/ANALYZE/steady/restart excluded; n3 fresh workflows, excluded warmups. GIL-off assertions joined to actual SQL. No CPU attribution from HTTP minus DB.')
    (e/'results.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(passed=True,apps=len(groups),workflows=len(samples),files=files,SQL_records=gil_count,medians={a:{m:{k:v[k]['median'] for k in ('SQL','DB_sum_ms','HTTP_sum_ms')} for m,v in g.items()} for a,g in groups.items()}),indent=2))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('evidence');main(p.parse_args().evidence)
