"""Thin accepted-five trace reader. No runtime/DB imports or measurements."""
import argparse
import hashlib
import json
from pathlib import Path
from classify_timeliness import summarize


def ref(path):
    p=Path(path)
    return dict(path=str(p.resolve()),sha256=hashlib.sha256(p.read_bytes()).hexdigest())


def checked(item):
    p=Path(item['path'])
    if ref(p)['sha256']!=item['sha256']:raise ValueError('Evidence drift: '+str(p))
    return p


def analyze(handoff,output):
    hpath=Path(handoff);h=json.loads(hpath.read_text())
    assert h['passed'] and h['source_after_passed'] and len(h['rows'])==5
    out=Path(output);out.mkdir(parents=True,exist_ok=False)
    cases=[]
    for case in h['rows']:
        requests=case['business_requests']
        ids=[r['request']for r in requests]
        assert len(ids)==len(set(ids))==23
        result=None
        if case['timeliness_observer']:
            events=[]
            for item in case['timeliness_traces']:
                events.extend(json.loads(line)for line in checked(item).read_text().splitlines())
            result=summarize(events,ids)
            detail=out/(case['trial_id']+'.json')
            detail.write_text(json.dumps(result,indent=2)+'\n')
            compact={k:v for k,v in result.items()if k not in ('outcomes','timeline')}
            compact['detail']=ref(detail)
            if result['timeline'] is not None:
                timeline=out/(case['trial_id']+'-timeline.json')
                timeline.write_text(json.dumps(result['timeline'],indent=2)+'\n')
                compact['timeline']=ref(timeline)
        else:compact=None
        cases.append(dict(trial_id=case['trial_id'],mode=case['config_id'],repeat=case['repeat'],
            traced=case['timeliness_observer'],business_HTTP=case['business_HTTP'],
            HTTP_response_sum_ms=case['HTTP_response_sum_ms'],data_SQL=case['data_SQL'],
            control_SQL=case['control_SQL'],TOTAL_SQL=case['TOTAL_SQL'],
            classification=compact,acceptance=case['accepted'],trace_refs=case['timeliness_traces']))
    result=dict(passed=True,handoff=ref(hpath),source=ref(__file__),
        classifier=ref(Path(__file__).with_name('classify_timeliness.py')),
        cases=cases,scope='Separate diagnostic: three traced Restored repetitions, one traced Off and one observer-disabled Restored control; not primary n5.',
        limitations=['Instrumentation changes timing/scheduling and counts; n1 control is not isolated per-event overhead.',
                     'Observed late availability in traced executions does not prove moving a hook improves latency.',
                     'Full exact key + PID + Session + epoch used, not SQL fingerprint-only identity.',
                     'Future readiness and local lease flags are distinct; unknown coverage/cancellation is not inferred lateness.'])
    summary=out/'summary.json';summary.write_text(json.dumps(result,indent=2)+'\n')
    for c in cases:print(json.dumps({k:v for k,v in c.items()if k not in ('acceptance','trace_refs','classification')},separators=(',',':')))
    print(json.dumps(ref(summary)))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--handoff',required=True);p.add_argument('--output',required=True)
    a=p.parse_args();analyze(a.handoff,a.output)
