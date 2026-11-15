"""DB-free compact-counter equivalence against one accepted native full record."""
import argparse,gzip,hashlib,json,threading
from pathlib import Path
from types import SimpleNamespace as NS
from compact_observer import project_state

def ref(p):return dict(path=str(p.resolve()),sha256=hashlib.sha256(p.read_bytes()).hexdigest())
def validate(metric,output):
    m=json.loads(metric.read_text());record=m['model_outcomes'][0];raw=record['raw_event'];path=Path(raw['path'])
    assert ref(path)['sha256']==raw['sha256']
    with (gzip.open(path,'rb') if path.suffix=='.gz' else path.open('rb')) as f:
        line=next(line for number,line in enumerate(f,1) if number==raw['line'])
    assert hashlib.sha256(line).hexdigest()==raw['record_sha256']
    event=json.loads(line);s=event['summary']
    mem=NS(_raw_lock=threading.RLock(),__raw_mem__={uid:None for uid in s['unused_cached_ids']},
        _prefetch_process_pids=s['worker_process_pids'],_prefetch_process_startup_ms=s['worker_process_startup_ms'])
    state=NS(ctx=NS(mem=mem),submitted=set(s['submitted_ids']),promoted=set(s['promoted_ids']),
        plans=s['plans'],continuations=s['continuations'],fusion=s['fusion'],errors=s['errors'],
        model=type(s['model'],(),{})(),provider=type(s['feature_provider'],(),{})(),
        mode=s['executor'],feedback=s['feedback'])
    compact=project_state(state,NS(records=event.get('checkpoints',[]),hits=event.get('hits',[])))
    expected=record['summary'];shared=sorted(set(expected)&set(compact))
    assert shared and all(compact[k]==expected[k] for k in shared),[(k,compact[k],expected[k]) for k in shared if compact[k]!=expected[k]]
    data=json.dumps(compact,separators=(',',':')).encode()
    result=dict(passed=True,kind='Recorded native-counter equivalence; no runtime or DB execution',
        source=ref(Path(__file__)),observer=ref(Path(__file__).with_name('compact_observer.py')),
        accepted_metric=ref(metric),raw_reference=raw,shared_fields=shared,
        native_record_bytes=len(line),compact_summary_bytes=len(data),summary=compact,
        disclosure='No native structure was changed; this validates projection/output, not elimination of baseline native suffix cost.')
    output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(dict(output=ref(output),
        shared_fields=len(shared),native_record_bytes=len(line),compact_summary_bytes=len(data))))
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--metric',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args();validate(a.metric,a.output)
