"""GIL-off assertions plus unchanged JDrive off/thread full workflows."""
import hashlib
import json
import os
from pathlib import Path
import sys
import time

OWN=Path(__file__).resolve().parent
ROOT=OWN.parents[1]
sys.path.insert(0,str(OWN))
from ia_config import run_config
from ia_interop import read_json,reference
from ia_runner import Sources,storage_watch
from ia_trial import Trial
from ia_postgres import OwnedPostgres

E=ROOT/'project-notes/measurements/ttg-jdrive-freethreaded-20261103'
def write(path,value):path.write_text(json.dumps(value,indent=2)+'\n')
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    output=E/'littlex-small-v1'
    assert not output.exists()
    output.mkdir();(output/'cases').mkdir()
    os.environ['TTG_PYTHON']=str(OWN.parent/'ttg-littlex-freethreaded/python.sh')
    snapshot=read_json(ROOT/'project-notes/measurements/ttg-jdrive-access-20261103/snapshots-v2.json')
    assert snapshot['passed']
    binding=read_json(ROOT/'project-notes/measurements/ttg-jdrive-access-20261103/commit-binding.json')
    assert binding['passed'] and binding['pushed']
    shape=read_json(ROOT/'project-notes/measurements/ttg-jdrive-access-20261103/littlex-small-shape-v1.json')
    assert shape['passed']
    overlay=snapshot['overlay'];clean=snapshot['clean']
    files=read_json(ROOT/'project-notes/measurements/ttg-littlex-freethreaded-20261102/comparison-v2/sources.json')['files'].copy()
    files.update({str(p):digest(p) for p in OWN.iterdir() if p.is_file() and p.suffix in ('.py','.sh','.json')})
    python=OWN.parent/'ttg-littlex-freethreaded/python/cpython-3.14.6+freethreaded-linux-x86_64-gnu/bin/python3.14'
    files[str(python)]=digest(python)
    for r in (clean,overlay):
        m=read_json(r['path'])
        files.update({str(Path(m['root'])/p):h for p,h in m['files'].items()})
    files.update({str(ROOT/'reproduction/ttg-jdrive-access/freeze_sql_v2.py'):digest(ROOT/'reproduction/ttg-jdrive-access/freeze_sql_v2.py')})
    proof=read_json(snapshot['proof']['path'])
    assert digest(Path(snapshot['proof']['path']))==snapshot['proof']['sha256'] and proof['passed']
    for relative, wanted in proof['sources'].items():
        current=ROOT/'jac-ttg'/relative
        assert digest(current)==wanted, 'Reviewed runtime source changed: '+relative
        files[str(current)]=wanted
    for extra in ('commit-binding.json','littlex-small-shape-v1.json'):
        f=ROOT/'project-notes/measurements/ttg-jdrive-access-20261103'/extra;files[str(f)]=digest(f)
    write(output/'sources.json',dict(files=files))
    source=reference(output/'sources.json');guard=Sources(source)
    schedule=[]
    modes=['off','thread']
    for repeat in [-1,0,1,2]:
        rotation=max(repeat,0)%2
        for mode in modes[rotation:]+modes[:rotation]:
            phase='excluded_warmup' if repeat<0 else 'measured'
            schedule.append(dict(case_id='littlex',app='littlex',scale='small',length=None,
                config_id=mode,phase=phase,repeat=repeat,guard=True,
                trial_id=f'littlex-{mode}-{phase}-{repeat}'))
    plan=dict(kind='littlex-small-current-runtime-gil-off-off-thread',source_verification=snapshot['proof'],commit_binding=reference(ROOT/'project-notes/measurements/ttg-jdrive-access-20261103/commit-binding.json'),fixture_shape=reference(ROOT/'project-notes/measurements/ttg-jdrive-access-20261103/littlex-small-shape-v1.json'),runtime_commit='f9a6d37b2f531d441515b40e02f3b0a9cc998836',
        overlay=overlay,clean=clean,sources=source,interpreter=reference(E.parent/'ttg-littlex-freethreaded-20261102/interpreter-assertions.json'),
        schedule=schedule,configs={m:run_config(m) for m in modes},
        assertion='GIL off at startup, every SQL boundary, native outcome/close and normal Python exit; actual worker thread/PID/backend required if background SQL occurs; inactive prefetch explicitly labelled',
        storage=dict(startup=768*1024**2,between=640*1024**2,stop=512*1024**2),
        note='Unchanged standard LittleX small: 50 users and 1000 tweets, original eight logical actions plus get_profile helper. Same current committed runtime, GIL-off Python, off/thread; n3 fresh workflows plus one excluded warmup per mode. Complete semantics/restart/physical proof. Four feed regions and actual background SQL required before measured trials; uniform ANALYZE and no primary CPU inference.')
    write(output/'plan.json',plan)
    index=dict(status='running',passed=False,creator_pid=os.getpid(),plan=reference(output/'plan.json'),rows=[])
    write(output/'index.json',index);trial=Trial();baseline=None
    try:
        with OwnedPostgres(OWN/'pg-littlex-small-v1',Path(read_json(clean['path'])['root']),output,guard,
                startup_floor=plan['storage']['startup'],case_floor=plan['storage']['between']) as pg:
            index['owner']=pg.owner;index['settings']=pg.settings_ref
            for row in schedule:
                guard();directory=output/'cases'/row['trial_id'];mode=row['config_id']
                pg.context=dict(directory=directory,case=row,cell=mode,source_manifest=source,prior_metrics={})
                write(output/'active-case.json',row);start=time.monotonic()
                with storage_watch(output,row,plan['storage']['stop']):
                    trial.run(row,mode,directory,pg,Path(clean['path']),Path(overlay['path']),baseline)
                if baseline is None:baseline=read_json(pg.context['result']['proof']['path'])
                index['rows'].append(dict(**row,passed=True,result=pg.context['result'],
                    gil_proof=reference(directory/'gil-proof.json'),case_wall_s=time.monotonic()-start))
                write(output/'index.json',index)
                if len(index['rows'])==2:
                    warm={r['config_id']:read_json(r['result']['metrics']['path']) for r in index['rows']}
                    assert warm['thread']['primary']['roles']['background_prefetch']['sql_dispatches'] > 0, 'No actual asynchronous SQL'
                    feeds=[r for r in read_json(directory/'requests.json') if r['phase']=='workflow' and r['path'].split('/')[2:3]==['load_feed']]
                    assert len(feeds)==4
                    outcomes={(str(o['server_generation']),o['origin_request_id']):o['summary'] for o in warm['thread']['model_outcomes']}
                    regions=[outcomes[(str(r['server_generation']),r['request'])]['fusion'] for r in feeds]
                    assert all(r['region_queries']==1 for r in regions), 'Expected compiled LittleX feed region missing'
                    write(output/'activation.json',dict(passed=True,off=warm['off']['primary']['sql_dispatches'],thread=warm['thread']['primary']['sql_dispatches']))
                print(json.dumps(dict(accepted=len(index['rows']),trial=row['trial_id'],
                    gil=read_json(directory/'gil-proof.json'))),flush=True)
        guard.verify_hashes();index.update(status='complete',passed=True)
    except BaseException as error:
        index.update(status='failed',error=type(error).__name__+': '+str(error));raise
    finally:write(output/'index.json',index)

if __name__=='__main__':main()
