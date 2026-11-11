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
    output=E/'comparison-access-v1'
    assert not output.exists()
    output.mkdir();(output/'cases').mkdir()
    os.environ['TTG_PYTHON']=str(OWN.parent/'ttg-littlex-freethreaded/python.sh')
    snapshot=read_json(ROOT/'project-notes/measurements/ttg-jdrive-access-20261103/snapshots-v1.json')
    assert snapshot['passed']
    overlay=snapshot['overlay'];clean=snapshot['clean']
    files=read_json(ROOT/'project-notes/measurements/ttg-littlex-freethreaded-20261102/comparison-v2/sources.json')['files'].copy()
    files.update({str(p):digest(p) for p in OWN.iterdir() if p.is_file() and p.suffix in ('.py','.sh','.json')})
    python=OWN.parent/'ttg-littlex-freethreaded/python/cpython-3.14.6+freethreaded-linux-x86_64-gnu/bin/python3.14'
    files[str(python)]=digest(python)
    for r in (clean,overlay):
        m=read_json(r['path'])
        files.update({str(Path(m['root'])/p):h for p,h in m['files'].items()})
    files.update({str(ROOT/'reproduction/ttg-jdrive-access/freeze.py'):digest(ROOT/'reproduction/ttg-jdrive-access/freeze.py')})
    write(output/'sources.json',dict(files=files))
    source=reference(output/'sources.json');guard=Sources(source)
    schedule=[]
    modes=['off','thread']
    for repeat in [-1,0,1,2]:
        rotation=max(repeat,0)%2
        for mode in modes[rotation:]+modes[:rotation]:
            phase='excluded_warmup' if repeat<0 else 'measured'
            schedule.append(dict(case_id='jdrive',app='jdrive',scale='smoke',length=None,
                config_id=mode,phase=phase,repeat=repeat,guard=True,
                trial_id=f'jdrive-{mode}-{phase}-{repeat}'))
    plan=dict(kind='jdrive-access-tree-gil-off-off-thread',source_verification=snapshot['proof'],runtime_commit='5ce63eacde69f11817ed791b2d93544d7524be49',
        overlay=overlay,clean=clean,sources=source,interpreter=reference(E.parent/'ttg-littlex-freethreaded-20261102/interpreter-assertions.json'),
        schedule=schedule,configs={m:run_config(m) for m in modes},
        assertion='GIL off at startup, every SQL boundary, native outcome/close and normal Python exit; actual worker thread/PID/backend required if background SQL occurs; inactive prefetch explicitly labelled',
        storage=dict(startup=768*1024**2,between=640*1024**2,stop=512*1024**2),
        note='Unchanged original JDrive smoke depth3: 40 folders,13 files,1 drive. Same repaired runtime and GIL-off Python; off/thread only. Full semantics/restart/physical checks each workflow; both excluded warmups must pass before measured trials. Output-tree activation and strict total SQL reduction required after the two excluded warmups; same original graph/actions/oracles and explicit ANALYZE regime.')
    write(output/'plan.json',plan)
    index=dict(status='running',passed=False,creator_pid=os.getpid(),plan=reference(output/'plan.json'),rows=[])
    write(output/'index.json',index);trial=Trial();baseline=None
    try:
        with OwnedPostgres(OWN/'pg-access-v1',Path(read_json(clean['path'])['root']),output,guard,
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
                    assert warm['thread']['primary']['sql_dispatches'] < warm['off']['primary']['sql_dispatches'], 'No total SQL reduction; preserve diagnostic warmups and stop'
                    assert warm['thread']['primary']['roles']['background_prefetch']['sql_dispatches'] > 0, 'No actual asynchronous SQL'
                    regions=[o['summary']['fusion'] for o in warm['thread']['model_outcomes'] if o['summary'].get('fusion',{}).get('region_queries',0)]
                    assert len(regions)==3 and sorted(r['region_cache_paths'] for r in regions)==[11,12,19], 'Original three trees did not activate complete region caches'
                    assert all(r['region_queries']==1 and r['region_fallbacks']==0 for r in regions), 'Tree did not resolve in one query'
                    write(output/'activation.json',dict(passed=True,off=warm['off']['primary']['sql_dispatches'],thread=warm['thread']['primary']['sql_dispatches']))
                print(json.dumps(dict(accepted=len(index['rows']),trial=row['trial_id'],
                    gil=read_json(directory/'gil-proof.json'))),flush=True)
        guard.verify_hashes();index.update(status='complete',passed=True)
    except BaseException as error:
        index.update(status='failed',error=type(error).__name__+': '+str(error));raise
    finally:write(output/'index.json',index)

if __name__=='__main__':main()
