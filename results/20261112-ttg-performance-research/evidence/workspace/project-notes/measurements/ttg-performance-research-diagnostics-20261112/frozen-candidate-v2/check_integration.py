"""Tiny DB-free actual helper/constructor/equality checks; not native acceptance."""
from pathlib import Path
import hashlib,json,tempfile
import run_cpu,cpu_profile
D=Path(__file__).resolve().parent

def main(output):
    for p in D.glob('*.py'):compile(p.read_text(),str(p),'exec')
    assert Path(run_cpu.diagnostic_storage.__file__).resolve()==D/'storage.py'
    with tempfile.TemporaryDirectory() as temporary:
        d=Path(temporary);mapping={'item:0':'00112233445566778899aabbccddeeff','item:1':'10112233445566778899aabbccddeeff'}
        mp=d/'mapping-initial.json';mp.write_text(json.dumps(mapping))
        targets=[dict(request='2:5',generation='2',walker='Traverse',logical_target='item:0'),
                 dict(request='2:6',generation='2',walker='Sum',logical_target='item:0')]
        requests=[];calls=[];signatures=[];(d/'cpu/generation-2').mkdir(parents=True)
        for t in targets:
            path,witness=cpu_profile.bind_path(t,mp)
            requests.append(dict(request=t['request'],server_generation=2,phase='workflow',path=path,input={}))
            profile=dict(passed=True,request=t['request'],pid=100,thread_id=200,target=dict(t,actual_path=path,fresh_binding=witness))
            (d/'cpu/generation-2'/(t['request'].replace(':','-')+'.json')).write_text(json.dumps(profile))
            calls.append(dict(origin_request_id=t['request'],server_generation='2',send_ns=1,role='foreground',client_process_pid=100,thread_id=200,sql='SELECT 1'))
            signatures.append(dict(request=t['request'],data_SQL=1,control_SQL=0,
                fingerprints=[dict(fingerprint=run_cpu.fingerprint('SELECT 1'),role='foreground',count=1)]))
        (d/'requests.json').write_text(json.dumps(requests))
        old=run_cpu.load_unsealed;events=[]
        run_cpu.load_unsealed=lambda directory,pattern:iter(calls if '.calls.' in pattern else events)
        selection=dict(targets=targets,control_variants=[dict(repeat=0,native=None,targets=signatures)])
        try:
            result=run_cpu.validate_case(d,selection)
            assert result['passed'] and result['actual_native'] is None
            zeros={key:0 for key in run_cpu.COUNT_FIELDS}
            event=dict(kind='dependency_outcome',server_generation='2',origin_request_id='2:5',summary=zeros)
            events.append(event)
            counter_control=dict(targets=targets,control_variants=[dict(repeat=0,
                native=dict(outcome_events=1,summary_events=1,cumulative_counts=zeros.copy()),targets=signatures)])
            assert run_cpu.validate_case(d,counter_control)['passed']
            for fault in ('missing','bool','negative'):
                damaged=zeros.copy()
                if fault=='missing':damaged.pop('plan_count')
                else:damaged['plan_count']=False if fault=='bool' else -1
                event['summary']=damaged
                try:run_cpu.validate_case(d,counter_control)
                except (AssertionError,ValueError):pass
                else:raise AssertionError('Invalid actual zero counter admitted: '+fault)
            events.clear()
            calls.append(dict(calls[0]));assert not run_cpu.validate_case(d,selection)['passed'];calls.pop()
            p=d/'cpu/generation-2/2-5.json';profile=json.loads(p.read_text())
            profile['target']['actual_path']='/walker/Traverse/primary-old-UUID';p.write_text(json.dumps(profile))
            try:run_cpu.validate_case(d,selection)
            except (AssertionError,ValueError):pass
            else:raise AssertionError('Old UUID path admitted')
        finally:run_cpu.load_unsealed=old
        for mapping in [{'item:0':'bad'},{'other':'00112233445566778899aabbccddeeff'},
                        {'item:0':'00112233445566778899aabbccddeeff','item:1':'00112233445566778899aabbccddeeff'}]:
            mp.write_text(json.dumps(mapping))
            try:cpu_profile.bind_path(targets[0],mp)
            except (ValueError,KeyError):pass
            else:raise AssertionError('Invalid native mapping admitted')
    run_cpu.free_port=lambda:55432
    pg=run_cpu.PG(D/'constructor-only-never-started',Path('reproduction/ttg-condition-access-performance-20261111/runtime-clean-v1'),
                 Path('project-notes/measurements/ttg-performance-research-diagnostics-20261112'),lambda:None,{})
    assert not pg.started and not pg.directory.exists()
    result=dict(passed=True,checks=['Current Python syntax','Exact storage module identity after borrowed imports',
        'validate_case off/no-outcome remains null','Changed SQL-count negative rejects','Old UUID path negative rejects',
        'Fresh mapping and malformed/missing/duplicate identity negatives','Native PG constructor only, no socket/DB',
        'Full actual zero-counter positive and missing-zero/bool/negative counter negatives'],
        storage_module=str(run_cpu.diagnostic_storage.__file__),
        source_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in D.glob('*.py')},no_DB=True,no_native_run=True)
    output=Path(output);assert not output.exists();output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(passed=True,checks=len(result['checks']))))

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',required=True)
    main(parser.parse_args().output)
