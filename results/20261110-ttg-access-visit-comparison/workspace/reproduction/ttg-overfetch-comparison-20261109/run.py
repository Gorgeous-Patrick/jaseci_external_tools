"""Standard-only permissions: two-app OFF versus GIL-off thread comparison."""
import hashlib
import json
import os
from pathlib import Path
import time
from ia_config import OWN, EVIDENCE, run_config
from ia_interop import read_json, reference
from ia_runner import Sources, storage_watch
from ia_trial import Trial
from ia_postgres import OwnedPostgres

ROOT=OWN.parents[1]
CASES=(('jdrive','small'),('littlex','small'))
def write(p,x):Path(p).write_text(json.dumps(x,indent=2)+'\n')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def build():
    snapshot=read_json(ROOT/'project-notes/measurements/ttg-standard-access-comparison-20261109/snapshots.json')
    assert snapshot['passed']
    base=ROOT/'project-notes/measurements/ttg-standard-access-comparison-20261109/sources.json'
    files=read_json(base)['files'].copy()
    assert all(sha(p)==h for p,h in files.items()), 'Source drift from reviewed standard-only comparison'
    files.update({str(p):sha(p) for p in OWN.glob('*.py')})
    for kind in ('clean','overlay'):
        ref=snapshot[kind];assert sha(ref['path'])==ref['sha256']
        m=read_json(ref['path']);files.update({str(Path(m['root'])/p):h for p,h in m['files'].items()})
    source=EVIDENCE/'sources.json';assert not source.exists();write(source,dict(files=files))
    rows=[]
    # Complete four excluded validation workflows before measured workflows.
    for phase,repeats in [('excluded_warmup',[-1]),('measured',[0,1,2])]:
        for app,scale in CASES:
            for repeat in repeats:
                modes=['aggressive','conservative'] if max(repeat,0)%2==0 else ['conservative','aggressive']
                for mode in modes:
                    rows.append(dict(case_id=app,app=app,scale=scale,length=None,guard=True,
                        config_id=mode,phase=phase,repeat=repeat,trial_id=f'{app}-{mode}-{phase}-{repeat}'))
    plan=dict(kind='aggressive-conservative-overfetch-comparison',runtime_commit=read_json(snapshot['clean']['path'])['commit'],
        clean=snapshot['clean'],overlay=snapshot['overlay'],sources=reference(source),
        configs={m:run_config(m) for m in ('aggressive','conservative')},schedule=rows,seed=42,
        statistics='ANALYZE anchors and graph_types once after setup, before primary HTTP/reset',
        storage=dict(startup=768*1024**2,between=640*1024**2,stop=512*1024**2),
        selection='Fixed JDrive small and LittleX small, same standard-only runtime, aggressive ttg and conservative ttg_dependency, both thread. No case removed for poor performance.',
        scope='Precision diagnostic, not uninstrumented latency benchmark. Request-bound payload delivery/demand/OSP entry instrumentation identical in both modes. 16 fresh workflows: four excluded warmups, twelve measured, n3 per four cells. Full native correctness and physical-state replay per case; actual GIL-off at SQL boundaries; setup, steady reads and restart excluded.')
    write(EVIDENCE/'plan.json',plan)
    return plan

def main():
    os.environ['TTG_PYTHON']=str(ROOT/'reproduction/ttg-littlex-freethreaded/python.sh')
    plan=build();guard=Sources(plan['sources']);trial=Trial()
    assert all(app in trial.apps.apps for app,_ in CASES)
    output=EVIDENCE/'run-v1';assert not output.exists();output.mkdir();(output/'cases').mkdir()
    index=dict(status='running',passed=False,creator_pid=os.getpid(),plan=reference(EVIDENCE/'plan.json'),rows=[])
    write(output/'index.json',index);baselines={}
    try:
        with OwnedPostgres(OWN/'pg-v1',Path(read_json(plan['clean']['path'])['root']),output,guard,
             startup_floor=plan['storage']['startup'],case_floor=plan['storage']['between']) as pg:
            index['owner']=pg.owner;index['settings']=pg.settings_ref
            for row in plan['schedule']:
                guard();directory=output/'cases'/row['trial_id'];mode=row['config_id'];app=row['app']
                pg.context=dict(directory=directory,case=row,cell=mode,source_manifest=plan['sources'],prior_metrics={})
                write(output/'active-case.json',row);start=time.monotonic()
                with storage_watch(output,row,plan['storage']['stop']):
                    trial.run(row,mode,directory,pg,Path(plan['clean']['path']),Path(plan['overlay']['path']),baselines.get(app))
                if app not in baselines:baselines[app]=read_json(pg.context['result']['proof']['path'])
                index['rows'].append(dict(**row,passed=True,result=pg.context['result'],gil_proof=reference(directory/'gil-proof.json'),case_wall_s=time.monotonic()-start))
                write(output/'index.json',index)
                print(json.dumps(dict(accepted=len(index['rows']),trial=row['trial_id'])),flush=True)
        guard.verify_hashes();index.update(status='complete',passed=True,source_after_passed=True)
    except BaseException as error:
        index.update(status='failed',error=type(error).__name__+': '+str(error));raise
    finally:write(output/'index.json',index)
if __name__=='__main__':main()
