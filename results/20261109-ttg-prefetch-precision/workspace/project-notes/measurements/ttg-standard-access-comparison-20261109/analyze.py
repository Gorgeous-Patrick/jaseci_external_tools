"""Read-only exact 16-trial comparison, independently recounting sealed SQL/HTTP."""
import csv
import gzip
import hashlib
import json
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def checked(ref):
    assert sha(ref['path']) == ref['sha256'], ref
    return read(ref['path'])


def union(intervals):
    total = 0
    end = None
    for a, b in sorted(intervals):
        assert b >= a
        if end is None or a >= end:
            total += b-a
        elif b > end:
            total += b-end
        end = b if end is None else max(end, b)
    return total


def rows(path):
    opener = gzip.open if path.suffix == '.gz' else open
    with opener(path, 'rt') as stream:
        for line in stream:
            if line.strip():
                yield json.loads(line)


def main():
    index = read(ROOT/'run-v1/index.json')
    assert index['passed'] and index['status'] == 'complete' and index['source_after_passed']
    plan = checked(index['plan'])
    assert len(index['rows']) == len(plan['schedule']) == 16
    samples = []
    databases = set()
    for row, expected in zip(index['rows'], plan['schedule']):
        assert row['passed'] and all(row[k] == v for k, v in expected.items())
        result = {k: checked(ref) for k, ref in row['result'].items()}
        gil = checked(row['gil_proof'])
        assert gil['passed']
        proof = result['proof']
        assert proof['passed'] and proof['database'] not in databases
        databases.add(proof['database'])
        assert result['acceptance']['passed']
        metric = result['metrics']; primary = metric['primary']
        directory = Path(row['result']['raw']['path']).parent
        # Seal hashes include original compressed representation; no mutation.
        for name, digest in result['raw']['files'].items():
            assert sha(directory/name) == digest, name
        http = [r for r in rows(directory/'http-raw.jsonl') if r['phase'] == 'workflow']
        keys = {(str(r['server_generation']), r['request']) for r in http}
        calls = [c for path in sorted(directory.glob('server-*.calls.jsonl*')) for c in rows(path)
                 if (str(c['server_generation']), c.get('origin_request_id')) in keys
                 and c.get('send_ns') is not None]
        intervals = [(c['send_ns'], c['ready_ns']) for c in calls]
        assert len(calls) == primary['sql_dispatches']
        assert sum(b-a for a,b in intervals) == primary['protocol_sum_ns']
        assert union(intervals) == primary['protocol_union_ns']
        assert len(http) == primary['HTTP_requests']
        by_role = {}
        for role in sorted({c['role'] for c in calls}):
            selected = [c for c in calls if c['role'] == role]
            by_role[role] = len(selected)
            assert len(selected) == primary['roles'][role]['sql_dispatches']
        assert gil['primary_background_SQL'] == by_role.get('background_prefetch', 0)
        requests = []
        for request in http:
            key = (str(request['server_generation']), request['request'])
            q = [c for c in calls if (str(c['server_generation']), c.get('origin_request_id')) == key]
            m = next(m for m in metric['request_metrics'] if (str(m['server_generation']),m['request']) == key)
            assert len(q) == m['sql_dispatches']
            assert sum(c['ready_ns']-c['send_ns'] for c in q) == m['protocol_sum_ns']
            requests.append(dict(request=request['request'], walker=request['path'].split('/')[2],
                http_ms=(request['end_ns']-request['start_ns'])/1e6,
                db_ms=m['protocol_sum_ns']/1e6, data_sql=m['sql_data'], control_sql=m['sql_control'],
                total_sql=len(q)))
        samples.append(dict(app=row['app'],mode=row['config_id'],phase=row['phase'],repeat=row['repeat'],
            trial_id=row['trial_id'],database=proof['database'],metric=row['result']['metrics'],gil=row['gil_proof'],
            http_ms=sum(r['end_ns']-r['start_ns'] for r in http)/1e6,
            http_span_ms=(max(r['end_ns'] for r in http)-min(r['start_ns'] for r in http))/1e6,
            db_sum_ms=primary['protocol_sum_ns']/1e6,db_union_ms=primary['protocol_union_ns']/1e6,
            data_sql=primary['sql_data'],control_sql=primary['sql_control'],total_sql=primary['sql_dispatches'],
            http_requests=len(http),roles=by_role,requests=requests,
            late_background_calls=primary['late_background_calls']))
    groups = []
    fields = ('http_ms','db_sum_ms','db_union_ms','data_sql','control_sql','total_sql','http_requests')
    for app in ('jdrive','littlex'):
        for mode in ('off','thread'):
            s = [s for s in samples if s['app']==app and s['mode']==mode and s['phase']=='measured']
            assert sorted(s['repeat'] for s in s) == [0,1,2]
            groups.append(dict(app=app,mode=mode,n=3,**{f:dict(median=median([x[f] for x in s]),
                min=min(x[f] for x in s),max=max(x[f] for x in s),values=[x[f] for x in s]) for f in fields}))
    result=dict(passed=True,index=dict(path=str(ROOT/'run-v1/index.json'),sha256=sha(ROOT/'run-v1/index.json')),
        analysis_source_sha256=sha(__file__),captured=16,excluded_warmups=4,measured=12,groups=groups,samples=samples,
        definitions=dict(http_ms='Sum of instrumented primary HTTP send-to-full-response-read wall, excludes explicit post-response drain',
            db_sum_ms='Sum of actual SQL send-to-ReadyForQuery intervals across foreground and background',
            db_union_ms='Union of those intervals',data_sql='Data SQL only; controls reported separately',
            regime='Same frozen standard-only runtime, GIL-off asserted at every SQL boundary; explicit ANALYZE before primary'))
    (ROOT/'results.json').write_text(json.dumps(result,indent=2)+'\n')
    with (ROOT/'table.csv').open('w') as f:
        writer=csv.writer(f);writer.writerow(['app','mode','n',*fields])
        for g in groups:writer.writerow([g['app'],g['mode'],g['n'],*[g[k]['median'] for k in fields]])
    print(json.dumps(groups,indent=2))


if __name__ == '__main__':
    main()
