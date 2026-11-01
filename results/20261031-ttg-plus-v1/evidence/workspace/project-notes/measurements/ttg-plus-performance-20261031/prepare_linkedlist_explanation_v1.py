"""Small accepted derivative inputs only; no native raw outcome or SQL re-read."""
import hashlib,json,statistics
from pathlib import Path
E=Path(__file__).resolve().parent
R=E.parent/'ttg-plus-review-20261031/formal36-raw-audit'
def ref(p):return dict(path=str(Path(p).resolve()),sha256=hashlib.sha256(Path(p).read_bytes()).hexdigest())
summary=json.loads((R/'summary.json').read_text());assert summary['passed']
inputs=[];groups=[];traverses=[];outcomes=[]
for case in ('linked_list32','linked_list1000'):
    for mode in ('off','prefusion','ttg_plus'):
        trials=[]
        for repeat in range(3):
            p=R/f'{case}-{mode}-measured-{repeat}.json'
            a=json.loads(p.read_text());inputs.append(ref(p))
            assert [r['walker'] for r in a['RPCs']]==['Traverse','Sum','Find','Find','Find','Find']
            metric_ref=a['refs']['metrics'];metric_path=Path(metric_ref['path']);assert ref(metric_path)==metric_ref
            m=json.loads(metric_path.read_text());inputs.append(metric_ref)
            trials.append(a)
            for o in m['model_outcomes']:
                outcomes.append(dict(case=case,config=mode,repeat=repeat,request=o['origin_request_id'],
                    fusion=o['summary']['fusion'],stops=o['summary']['continuation_stop_counts'],
                    raw_event=o['raw_event']))
        for ordinal,label in enumerate(('Traverse','Sum','Find head','Find middle','Find tail','Find missing')):
            rs=[t['RPCs'][ordinal] for t in trials]
            assert all(sum(r['categories'].values())==r['sql_dispatches'] for r in rs)
            groups.append(dict(case=case,config=mode,operation=label,n=3,
                SQL=[r['sql_dispatches'] for r in rs],categories=[r['categories'] for r in rs],
                protocol_ms=[r['protocol_sum_ns']/1e6 for r in rs],
                median_protocol_ms=statistics.median(r['protocol_sum_ns']/1e6 for r in rs),
                request_refs=[dict(trial=t['trial_id'],request=r['request']) for t,r in zip(trials,rs)]))
out=E/'linkedlist-explanation-v1';out.mkdir(exist_ok=False)
d=dict(passed=True,source=ref(__file__),independent_raw_audit=ref(R/'summary.json'),inputs=inputs,
    operations=groups,compact_outcomes=outcomes,
    scope='Accepted P8 per-RPC counts/timing and sealed compact metric counters; no new raw outcome semantic admission.',
    semantics='Unknown scalar stop reasons are observed planner facts, not proof of CPU cost. SQL categories copied from independent audit.')
(out/'results.json').write_text(json.dumps(d,indent=2)+'\n')
(out/'artifacts.json').write_text(json.dumps(dict(passed=True,outputs=[ref(out/'results.json')]),indent=2)+'\n')
print(json.dumps(ref(out/'results.json')))
