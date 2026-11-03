"""Bounded fresh LittleX repair comparison; original capture/semantic/cleanup code reused."""
import hashlib,json,os,shutil,sys,time
from pathlib import Path
ROOT=Path('/home/baichuan/jaseci')
OWN=ROOT/'reproduction/ttg-interability-performance'
sys.path.insert(0,str(OWN))
from ia_trial import Trial
from ia_postgres import OwnedPostgres
from ia_runner import Sources,storage_watch
from ia_interop import read_json,reference
E=ROOT/'project-notes/measurements/ttg-interability-performance-20261101/littlex-dag-repair-v4'

def write(p,v):p.write_text(json.dumps(v,indent=2)+'\n')
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    assert not E.exists();E.mkdir();(E/'cases').mkdir()
    oldplan=read_json(E.parent/'correctness-plan-v1/plan.json');base=oldplan['runtimes']['interability']
    original=Path(read_json(base['overlay']['path'])['root'])
    target=OWN/'runtime-direct-littlex-dag-v4';assert not target.exists()
    shutil.copytree(original,target,copy_function=os.link)
    paths=['jac/jaclang/runtime/'+name+'.jac' for name in ('ttg_regions','ttg_region_dag','ttg_dependency_prefetch')]
    for path in paths:
        out=target/path;tmp=out.with_name(out.name+'.new');shutil.copyfile(ROOT/'jac-ttg'/path,tmp);os.replace(tmp,out)
    snapshot=dict(kind='source-bound-repair-overlay',root=str(target),base=base,
        changes={p:digest(target/p) for p in paths},files=read_json(base['overlay']['path'])['files'])
    snapshot['files'].update(snapshot['changes'])
    write(E/'runtime-overlay.json',snapshot)
    source=json.loads(Path(oldplan['sources']['path']).read_text())
    source['files'].update({str(ROOT/'jac-ttg'/p):digest(ROOT/'jac-ttg'/p) for p in paths})
    source['files'][str(Path(__file__).resolve())]=digest(Path(__file__).resolve())
    write(E/'sources.json',source);guard=Sources(reference(E/'sources.json'))
    schedule=[]
    for repeat in [-1,0,1,2]:
        order=['before','after'] if repeat%2 else ['after','before']
        for version in order:
            phase='excluded_warmup' if repeat==-1 else 'measured'
            schedule.append(dict(case_id='littlex',app='littlex',scale='smoke',length=None,
                config_id='interability',phase=phase,repeat=repeat,guard=True,version=version,
                trial_id=f'littlex-{version}-{phase}-{repeat}'))
    plan=dict(kind='littlex-dag-repair-only',source=reference(E/'sources.json'),baseline=base,
        changed=reference(E/'runtime-overlay.json'),schedule=schedule,settings='Original uniform ANALYZE, WAL32/64, process1, limit2048; original compact/direct observers unchanged',
        storage=dict(startup=384*1024**2,between=256*1024**2,stop=160*1024**2),
        note='Eight new full workflows; two excluded warmups and six measured. No historical timings reused.')
    write(E/'plan.json',plan)
    index=dict(status='running',passed=False,creator_pid=os.getpid(),plan=reference(E/'plan.json'),rows=[])
    write(E/'index.json',index)
    trial=Trial();baseline=None
    try:
        with OwnedPostgres(OWN/'pg-littlex-dag-repair-v4',Path(read_json(base['clean']['path'])['root']),E,guard,
                           startup_floor=plan['storage']['startup'],case_floor=plan['storage']['between']) as pg:
            index['owner']=pg.owner;index['settings']=pg.settings_ref
            for row in schedule:
                guard();directory=E/'cases'/row['trial_id'];runtime=Path(base['overlay']['path']) if row['version']=='before' else E/'runtime-overlay.json'
                pg.context=dict(directory=directory,case=row,cell='interability',source_manifest=reference(E/'sources.json'),prior_metrics={})
                write(E/'active-case.json',row);start=time.monotonic()
                with storage_watch(E,row,plan['storage']['stop']):
                    trial.run(row,'interability',directory,pg,Path(base['clean']['path']),runtime,baseline)
                if baseline is None:baseline=read_json(pg.context['result']['proof']['path'])
                record=dict(**row,passed=True,result=pg.context['result'],case_wall_s=time.monotonic()-start)
                index['rows'].append(record);write(E/'index.json',index)
                print(json.dumps(dict(accepted=len(index['rows']),trial=row['trial_id'],seconds=record['case_wall_s'])),flush=True)
        guard.verify_hashes();index.update(status='complete',passed=True)
    except BaseException as error:
        index.update(status='failed',error=type(error).__name__+': '+str(error));raise
    finally:write(E/'index.json',index)

if __name__=='__main__':main()
