"""Require observed GIL-off SQL execution, not merely a build label."""
import json
from pathlib import Path

def verify_gil_case(directory, cell):
    directory = Path(directory)
    files = sorted(directory.glob('gil-proof-*.jsonl'))
    assert files, 'Missing actual-process GIL proof'
    records = [json.loads(line) for p in files for line in p.read_text().splitlines()]
    assert all(r['gil_enabled'] is False and r['Py_GIL_DISABLED'] == 1 for r in records)
    calls = [json.loads(line) for p in directory.glob('server-*.calls.jsonl')
             for line in p.read_text().splitlines()]
    observed = {}
    for r in records:
        if r['kind'] == 'sql_boundary':
            key = (r['pid'], r['thread_id'], r['server_generation'], r['origin_request_id'])
            observed[key] = observed.get(key, 0) + 1
    expected = {}
    for c in calls:
        key = (c['client_process_pid'], c['thread_id'], str(c['server_generation']), c.get('origin_request_id'))
        expected[key] = expected.get(key, 0) + 1
    assert expected and observed == expected, 'SQL and GIL-assertion record counts must join exactly'
    requests = json.loads((directory/'requests.json').read_text())
    primary = {(str(r['server_generation']), r['request']) for r in requests if r['phase'] == 'workflow'}
    actual = [c for c in calls if (str(c['server_generation']), c.get('origin_request_id')) in primary and c.get('send_ns') is not None]
    fg = [c for c in actual if c['role'] == 'foreground']
    bg = [c for c in actual if c['role'] == 'background_prefetch']
    parent = {c['client_process_pid'] for c in fg}
    assert len(parent) == 1
    if cell == 'off':
        assert not bg
    else:
        if not bg:
            outcomes=[json.loads(line) for f in directory.glob('server-*.events.jsonl') for line in f.read_text().splitlines() if line]
            outcomes=[e for e in outcomes if e.get('kind')=='dependency_outcome']
            assert outcomes and all(e['summary']['submitted_count']==0 for e in outcomes), 'Submitted work lacks actual background SQL evidence'
        # Zero eligible work is retained as an inactive result, not an executor success claim.
        assert all(c['actual_executor'] == cell for c in bg)
        if cell == 'thread':
            assert all(c['client_process_pid'] in parent for c in bg)
            for c in bg:
                peers = [f for f in fg if f['origin_request_id'] == c['origin_request_id']]
                assert peers and all(f['thread_id'] != c['thread_id'] for f in peers)
                assert all(f['backend_pid'] != c['backend_pid'] for f in peers)
        else:
            assert all(c['client_process_pid'] not in parent for c in bg)
    for p in files:
        r = [json.loads(l) for l in p.read_text().splitlines()]
        assert r[0]['kind'] == 'python_startup' and r[-1]['kind'] == 'python_exit'
    result = dict(passed=True,cell=cell,executor_SQL_observed=bool(bg),processes=len(files),SQL_assertions=len(calls),
                  primary_background_SQL=len(bg),parent_PIDs=sorted(parent),
                  background_PIDs=sorted({c['client_process_pid'] for c in bg}),
                  background_thread_ids=sorted({c['thread_id'] for c in bg}),
                  background_native_thread_ids=sorted({r['native_thread_id'] for r in records
                    if r['kind']=='sql_boundary' and r['role']=='background_prefetch'}),
                  assertion='Py_GIL_DISABLED == 1 and sys._is_gil_enabled() is False at every observed SQL boundary and native outcome/close')
    (directory/'gil-proof.json').write_text(json.dumps(result,indent=2)+'\n')
    return result
