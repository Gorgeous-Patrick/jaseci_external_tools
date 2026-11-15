"""Thin sequential12+guard correctness /48 fresh-workflow runner; no implicit DB jobs."""
import argparse
import hashlib,json,os
from pathlib import Path
import signal,threading,time
from contextlib import contextmanager
from ia_config import OWN,EVIDENCE,MODES,schedule,guard_schedule
from ia_interop import read_json,reference,require
from ia_postgres import OwnedPostgres
from ia_trial import Trial

def checked(value):
    path=Path(value['path']).resolve();require(reference(path)==value,'Input reference changed: '+str(path));return path
def write(path,value):Path(path).write_text(json.dumps(value,indent=2)+'\n')

@contextmanager
def storage_watch(output,case,minimum):
    """Controller-only10s safety check; no app hook/timer modification."""
    done=threading.Event()
    def watch():
        while not done.wait(10):
            stat=os.statvfs(output);free=stat.f_bavail*stat.f_frsize
            if free<=minimum:
                write(output/'storage-stop.json',dict(passed=False,case=case,free_bytes=free,
                    stop_floor_bytes=minimum,time_ns=time.time_ns(),action='Owner controller SIGINT; preserve current case/database'))
                os.kill(os.getpid(),signal.SIGINT);return
    thread=threading.Thread(target=watch,name='owned-controller-storage',daemon=True);thread.start()
    try:yield
    finally:done.set();thread.join()

class Sources:
    """Version once at matrix start/end; cheap mutation checks at case boundaries."""
    def __init__(self,manifest):
        self.path=checked(manifest);self.files=read_json(self.path)['files'];self.stamps={}
        self.verify_hashes()
        for name in self.files:
            st=Path(name).stat();self.stamps[name]=(st.st_size,st.st_mtime_ns)
    def __call__(self):
        for name,stamp in self.stamps.items():
            st=Path(name).stat();require((st.st_size,st.st_mtime_ns)==stamp,'Source mutation: '+name)
    def verify_hashes(self):
        for name,wanted in self.files.items():
            require(hashlib.sha256(Path(name).read_bytes()).hexdigest()==wanted,'Source hash changed: '+name)

def validate_plan(path):
    plan=read_json(path)
    require(plan['kind']=='ttg-interability-four-fixture-v1','Wrong selected experiment')
    require(plan['correctness_schedule']==schedule(False) and plan['formal_schedule']==schedule(True),'Fixed selection/order differs')
    for mode in ('baseline9282','interability'):
        manifest=read_json(checked(plan['runtimes'][mode]['overlay']))
        require(Path(manifest['root']).is_dir(),'Frozen runtime missing')
        checked(plan['runtimes'][mode]['clean'])
    require(read_json(plan['runtimes']['baseline9282']['clean']['path'])['commit']=='9282e246d708aff69e21cb52b9d0cc4893fc5f0f','Wrong baseline commit')
    require(plan['seed']==42 and plan['prefetch_workers']==1 and plan['prefetch_limit']==2048,'Common regime differs')
    return plan

def release(plan_path,plan):
    path=EVIDENCE/'formal-run-authorization.json';value=read_json(path)
    require(value.get('accepted') is True and value.get('purpose')=='ttg_interability_48_formal','Main formal release absent')
    require(value['plan']==reference(plan_path) and value['sources']==plan['sources'],'Release/source version mismatch')
    require(value.get('quiet_window_confirmed') is True,'Formal quiet window absent')
    previous=read_json(checked(value['correctness']))
    require(previous['passed'] and previous['status']=='complete' and len(previous['rows'])==12,'Complete native correctness required')
    require(previous['plan']==reference(plan_path),'Correctness plan/source regime differs')
    require(previous.get('guard_rows') and len(previous['guard_rows'])==3 and all(r['passed'] for r in previous['guard_rows']),'Three guard-false correctness subchecks required')
    require([{k:r[k] for k in guard_schedule()[0]} for r in previous['guard_rows']]==guard_schedule(),'Exact guard schedule differs')
    expected={}
    for row in previous['rows']:
        require(row['passed'],'Invalid correctness cell')
        if row['config_id']=='off':expected[row['case_id']]=read_json(checked(row['result']['proof']))
    require([(r['case_id'],r['config_id']) for r in previous['rows']]==
        [(r['case_id'],r['config_id']) for r in schedule(False)],'Exact12 unique correctness cells required')
    require(len(expected)==4,'All four correctness baselines required')
    return reference(path),expected

def run(stage,plan_path,output,cluster):
    plan_path=Path(plan_path).resolve();output=Path(output).resolve();cluster=Path(cluster).resolve()
    require(output.is_relative_to(EVIDENCE) and not output.exists(),'New owned evidence path required')
    require(cluster.is_relative_to(OWN) and not cluster.exists(),'New owned cluster path required')
    plan=validate_plan(plan_path);guard=Sources(plan['sources'])
    auth,expected=release(plan_path,plan) if stage=='formal' else (None,{})
    require(stage in ('correctness','formal'),'Explicit stage required')
    output.mkdir(parents=True);(output/'cases').mkdir()
    index=dict(kind='ttg-interability-four-fixture-v1',stage=stage,status='running',passed=False,
        creator_pid=os.getpid(),started_ns=time.time_ns(),plan=reference(plan_path),authorization=auth,rows=[],guard_rows=[])
    write(output/'index.json',index);trial=Trial()
    def source_guard():
        guard()
        if auth:require(reference(EVIDENCE/'formal-run-authorization.json')==auth,'Main release changed')
    # Admin uses the existing clean850 driver; its SQL is request-excluded.
    admin=Path(read_json(plan['runtimes']['baseline9282']['clean']['path'])['root'])
    try:
        with OwnedPostgres(cluster,admin,output,source_guard,
            startup_floor=plan['storage']['startup_floor_bytes'],case_floor=plan['storage']['case_floor_bytes']) as pg:
            index.update(cluster=str(cluster),cluster_owner=pg.owner,postgres_settings=pg.settings_ref)
            write(output/'index.json',index)
            work=[('rows',r) for r in schedule(stage=='formal')]
            if stage=='correctness':work += [('guard_rows',r) for r in guard_schedule()]
            for row_group,row in work:
                source_guard();mode=row['config_id'];runtime=plan['runtimes']['baseline9282' if mode=='baseline9282' else 'interability']
                directory=output/'cases'/row['trial_id'];started=time.monotonic_ns()
                pg.context=dict(directory=directory,case=row,cell=mode,source_manifest=plan['sources'],
                    prior_metrics={r['config_id']:r['result']['metrics'] for r in index['rows'] if r['case_id']==row['case_id']})
                write(output/'active-case.json',dict(case=row,directory=str(directory),started_ns=time.time_ns()))
                try:
                    with storage_watch(output,row,plan['storage']['in_case_stop_bytes']):
                        trial.run(row,mode,directory,pg,checked(runtime['clean']),checked(runtime['overlay']),expected.get(row['case_id']))
                    accepted=dict(**row,passed=True,result=pg.context['result'],wall_seconds=(time.monotonic_ns()-started)/1e9,
                        compressed_evidence_bytes=sum(p.stat().st_size for p in directory.rglob('*') if p.is_file()))
                    index[row_group].append(accepted)
                    if stage=='correctness' and mode=='off':expected[row['case_id']]=read_json(accepted['result']['proof']['path'])
                    write(output/'index.json',index)
                    if stage=='correctness' and row['config_id']=='interability' and row_group=='rows' and row['app'] in ('linked_list','region_chain'):
                        from ia_sanity import check_mechanism
                        gate=check_mechanism(row,index['rows']);write(output/(row['case_id']+'-activation.json'),gate)
                        require(gate['passed'],'Required static-region mechanism/sanity absent; preserve and stop')
                    print(json.dumps(dict(accepted=len(index['rows']),total=48 if stage=='formal' else 12,guard_accepted=len(index['guard_rows']),
                        trial=row['trial_id'],seconds=accepted['wall_seconds'],bytes=accepted['compressed_evidence_bytes'])),flush=True)
                except BaseException:
                    index['failed_case']=row;raise
            require(not pg.databases,'Unexpected retained successful database')
        guard.verify_hashes();index.update(status='complete',passed=True,finished_ns=time.time_ns(),source_hashes_after='passed')
        write(output/'index.json',index)
    except BaseException as error:
        index.update(status='failed',passed=False,error=type(error).__name__+': '+str(error),finished_ns=time.time_ns())
        write(output/'index.json',index);raise
    return index

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('stage',choices=('correctness','formal'))
    parser.add_argument('--plan',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--cluster',type=Path,required=True);args=parser.parse_args()
    run(args.stage,args.plan,args.output,args.cluster)
