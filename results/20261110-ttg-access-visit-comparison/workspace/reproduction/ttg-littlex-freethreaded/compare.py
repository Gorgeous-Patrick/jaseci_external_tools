"""GIL-off assertions plus off/thread/process full LittleX comparisons."""
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

E=ROOT/'project-notes/measurements/ttg-littlex-freethreaded-20261102'
def write(path,value):path.write_text(json.dumps(value,indent=2)+'\n')
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    output=E/'comparison-v2'
    assert not output.exists()
    output.mkdir();(output/'cases').mkdir()
    os.environ['TTG_PYTHON']=str(OWN/'python.sh')
    previous=ROOT/'project-notes/measurements/ttg-interability-performance-20261101/littlex-dag-repair-v4'
    old=read_json(previous/'plan.json')
    overlay=reference(previous/'runtime-overlay.json')
    clean=old['baseline']['clean']
    files=read_json(previous/'sources.json')['files'].copy()
    files.update({str(p):digest(p) for p in OWN.iterdir() if p.is_file() and p.suffix in ('.py','.sh','.json')})
    python=OWN/'python/cpython-3.14.6+freethreaded-linux-x86_64-gnu/bin/python3.14'
    files[str(python)]=digest(python)
    write(output/'sources.json',dict(files=files))
    source=reference(output/'sources.json');guard=Sources(source)
    schedule=[]
    modes=['off','thread','process']
    for repeat in [-1,0,1,2]:
        rotation=max(repeat,0)
        for mode in modes[rotation:]+modes[:rotation]:
            phase='excluded_warmup' if repeat<0 else 'measured'
            schedule.append(dict(case_id='littlex',app='littlex',scale='smoke',length=None,
                config_id=mode,phase=phase,repeat=repeat,guard=True,
                trial_id=f'littlex-{mode}-{phase}-{repeat}'))
    plan=dict(kind='littlex-gil-off-executors',runtime_commit='5ce63eacde69f11817ed791b2d93544d7524be49',
        overlay=overlay,clean=clean,sources=source,interpreter=reference(E/'interpreter-assertions.json'),
        schedule=schedule,configs={m:run_config(m) for m in modes},
        assertion='GIL off at startup, every SQL boundary, native outcome/close and normal Python exit; actual worker thread/PID/backend required',
        storage=dict(startup=256*1024**2,between=160*1024**2,stop=128*1024**2),
        note='Same repaired code and free-threaded Python in all modes. Full correctness on every fresh workflow. All three excluded warmups must pass before measured trials. No historical timing reuse.')
    write(output/'plan.json',plan)
    index=dict(status='running',passed=False,creator_pid=os.getpid(),plan=reference(output/'plan.json'),rows=[])
    write(output/'index.json',index);trial=Trial();baseline=None
    try:
        with OwnedPostgres(OWN/'pg-comparison-v2',Path(read_json(clean['path'])['root']),output,guard,
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
                print(json.dumps(dict(accepted=len(index['rows']),trial=row['trial_id'],
                    gil=read_json(directory/'gil-proof.json'))),flush=True)
        guard.verify_hashes();index.update(status='complete',passed=True)
    except BaseException as error:
        index.update(status='failed',error=type(error).__name__+': '+str(error));raise
    finally:write(output/'index.json',index)

if __name__=='__main__':main()
