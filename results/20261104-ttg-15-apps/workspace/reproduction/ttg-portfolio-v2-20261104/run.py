"""Fixed eight-app off/thread study; fresh DB per workflow and no runtime edits."""
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
CASES=(('jdrive', 'small'), ('littlex', 'small'), ('issue_desk', 'smoke'), ('stock_room', 'smoke'), ('clinic_queue', 'smoke'), ('budget_ledger', 'smoke'), ('knowledge_map', 'smoke'), ('course_path', 'smoke'), ('approval_desk', 'smoke'), ('library_loans', 'smoke'), ('event_seats', 'smoke'), ('help_queue', 'smoke'), ('delivery_route', 'smoke'), ('volunteer_shift', 'smoke'), ('incident_room', 'smoke'))
def write(p,x):Path(p).write_text(json.dumps(x,indent=2)+'\n')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def build():
    snapshot=read_json(ROOT/'project-notes/measurements/ttg-jdrive-access-20261103/snapshots-v2.json')
    assert snapshot['passed']
    base=ROOT/'project-notes/measurements/ttg-jdrive-freethreaded-20261103/littlex-small-v1/sources.json'
    files=read_json(base)['files'].copy()
    files.update({str(p):sha(p) for p in OWN.glob('*.py')})
    for kind in ('clean','overlay'):
        ref=snapshot[kind];assert sha(ref['path'])==ref['sha256']
        m=read_json(ref['path']);files.update({str(Path(m['root'])/p):h for p,h in m['files'].items()})
    source=EVIDENCE/'sources.json';assert not source.exists();write(source,dict(files=files))
    rows=[]
    # Complete all30 excluded validation workflows before any measured workflow.
    for phase,repeats in [('excluded_warmup',[-1]),('measured',[0,1,2])]:
        for app,scale in CASES:
            for repeat in repeats:
                modes=['off','thread'] if max(repeat,0)%2==0 else ['thread','off']
                for mode in modes:
                    rows.append(dict(case_id=app,app=app,scale=scale,length=None,guard=True,
                        config_id=mode,phase=phase,repeat=repeat,trial_id=f'{app}-{mode}-{phase}-{repeat}'))
    plan=dict(kind='fixed-fifteen-app-gil-off-portfolio',runtime_commit='f9a6d37b2f531d441515b40e02f3b0a9cc998836',
        clean=snapshot['clean'],overlay=snapshot['overlay'],sources=reference(source),
        configs={m:run_config(m) for m in ('off','thread')},schedule=rows,seed=42,
        statistics='ANALYZE anchors and graph_types once after setup, before primary HTTP/reset',
        storage=dict(startup=768*1024**2,between=640*1024**2,stop=512*1024**2),
        selection='JDrive recursive boolean-filtered output tree; LittleX typed cross-ability region; IssueDesk, StockRoom, ClinicQueue, BudgetLedger typed visit chains/branches; KnowledgeMap and CoursePath nested read/helper boundary cases. Source hypotheses, not promised speedups. No workload removed for poor performance.',
        scope='Original fixed native corpus/scenarios, full workflow measured; steady reads/setup/restart excluded. 30 excluded validation warmups then90 measured, n3 per30cells. Actual GIL-off and background execution checked. No speedup/activation acceptance threshold.')
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
