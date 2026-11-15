"""Summarize only twelve accepted direct-CPU JSON records; no raw replay."""
from collections import defaultdict
import argparse,hashlib,json
from pathlib import Path

def ref(p):return dict(path=str(p.resolve()),sha256=hashlib.sha256(p.read_bytes()).hexdigest())
def main(run,output):
    run=Path(run);output=Path(output);assert not output.exists()
    index=json.loads((run/'index.json').read_text());life=json.loads((run/'lifecycle.json').read_text())
    assert index['passed'] and index['status']=='complete' and len(index['rows'])==6
    assert life['services_stopped'] and life['pg_status']==3 and not life['postmaster_pid_exists'] and not life['retained_databases']
    rows=[]
    for case in index['rows']:
        validation_ref=case['result']['CPU_validation'];validation=json.loads(Path(validation_ref['path']).read_text())
        assert validation['passed'] and validation['matched_unprofiled_control_repeats']
        for source in validation['profiles']:
            path=Path(source['path']);assert ref(path)==source
            p=json.loads(path.read_text());assert p['passed']
            groups=defaultdict(lambda:dict(calls=0,inclusive_thread_CPU_ns=0,exclusive_thread_CPU_ns=0,inclusive_wall_ns=0))
            for e in p['events']:
                assert e['thread_id']==p['thread_id'] and e['native_thread_id']==p['native_thread_id']
                g=groups[e['name']];g['calls']+=1;g['inclusive_thread_CPU_ns']+=e['thread_cpu_ns']
                g['exclusive_thread_CPU_ns']+=e['exclusive_thread_cpu_ns'];g['inclusive_wall_ns']+=e['wall_ns']
            assert sum(x['exclusive_thread_CPU_ns'] for x in groups.values())==p['thread_cpu_ns']
            phases=[dict(name=name,calls=v['calls'],inclusive_thread_CPU_ms=v['inclusive_thread_CPU_ns']/1e6,
                         exclusive_thread_CPU_ms=v['exclusive_thread_CPU_ns']/1e6,inclusive_wall_ms=v['inclusive_wall_ns']/1e6)
                    for name,v in groups.items()]
            phases.sort(key=lambda r:r['exclusive_thread_CPU_ms'],reverse=True)
            rows.append(dict(case_id=case['case_id'],app=case['app'],mode=case['config_id'],request=p['request'],
                walker=p['target']['walker'],ordinal=p['target']['ordinal'],pid=p['pid'],thread_id=p['thread_id'],
                native_thread_id=p['native_thread_id'],native_spawn_thread_CPU_ms=p['thread_cpu_ns']/1e6,
                native_spawn_wall_ms=p['wall_ns']/1e6,phases=phases,profile=source,validation=validation_ref,
                matched_same_mode_controls=validation['matched_unprofiled_control_repeats']))
    assert len(rows)==12
    result=dict(passed=True,primary_measurement=False,diagnostic_n_per_app_mode=1,selected_RPCs=12,
        source=ref(Path(__file__)),index=ref(run/'index.json'),lifecycle=ref(run/'lifecycle.json'),rows=rows,
        definitions=dict(CPU='Direct time.thread_time_ns on selected native-spawn thread, exclusive nested partition; not whole request/process CPU.',
            wall='Direct perf_counter_ns same callable boundary. Inclusive helper wall overlaps; never sum those columns.',
            background='Any delegated aggressive planner/payload or other thread CPU is unmeasured. Low native-thread CPU is not a totalCPU saving.',
            remainder='native_spawn exclusive is all otherwise-uninstrumented work plus retained observation/timer overhead, not an isolated business-code CPU estimate.',
            controls='Complete same-repeat joint selected SQL and available whole-workflow native-plan counters matched an actual n5 control. Unknown counters are not zero.',
            timing='Separate n1 diagnostic, not pooled with primary n5. No HTTP-minus-DB CPU estimate or overhead subtraction.'))
    output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(summary=ref(output),rows=[dict(case=r['case_id'],mode=r['mode'],walker=r['walker'],CPU_ms=r['native_spawn_thread_CPU_ms'],wall_ms=r['native_spawn_wall_ms'],top_exclusive=r['phases'][0]) for r in rows]),indent=2))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',required=True,type=Path);p.add_argument('--output',required=True,type=Path)
    a=p.parse_args();main(a.run,a.output)
