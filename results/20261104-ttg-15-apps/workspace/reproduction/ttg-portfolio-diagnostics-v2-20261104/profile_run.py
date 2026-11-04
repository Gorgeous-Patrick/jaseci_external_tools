"""Selected full-native diagnostic workflows; excluded from primary tables."""
import json,os,subprocess
from pathlib import Path
from ia_config import OWN,EVIDENCE
from ia_interop import read_json,reference,sha256,require
from ia_runner import Sources,storage_watch
from ia_trial import Trial,load_unsealed
from ia_postgres import OwnedPostgres
from owned_postgres import BIN
from cpu_profile import clock_controls
ROOT=OWN.parents[1]
BASE=ROOT/'project-notes/measurements/ttg-portfolio-v2-20261104'
def write(p,x):Path(p).write_text(json.dumps(x,indent=2)+'\n')
def main():
    plan=read_json(BASE/'plan.json');index=read_json(BASE/'run-v1/index.json')
    assert index['passed'] and index['status']=='complete'
    selection=read_json(EVIDENCE/'profile-selection.json');assert selection['primary_results']==reference(BASE/'results.json')
    output=EVIDENCE/'cpu-v2';assert not output.exists();output.mkdir();(output/'cases').mkdir()
    write(output/'clock-controls.json',clock_controls())
    files=read_json(plan['sources']['path'])['files'].copy();files.update({str(f):sha256(f) for f in OWN.glob('*.py')});files[str(EVIDENCE/'profile-selection.json')]=sha256(EVIDENCE/'profile-selection.json')
    write(output/'sources.json',dict(files=files));guard=Sources(reference(output/'sources.json'))
    os.environ['TTG_PYTHON']=str(ROOT/'reproduction/ttg-littlex-freethreaded/python.sh')
    class PG(OwnedPostgres):
        def accept_completed(self,case,cell,name,directory,proof,expected):
            rows=[read_json(f) for f in (directory/'cpu').glob('*.json')]
            assert len(rows)==1 and rows[0]['passed']
            r=rows[0];calls=[c for c in load_unsealed(directory,'server-*.calls.jsonl*') if c.get('origin_request_id')==r['request'] and c.get('send_ns') is not None and c['role']=='foreground']
            assert calls and any(c['client_process_pid']==r['pid'] and c['thread_id']==r['thread_id'] for c in calls),'Profile is not an actual foreground SQL/native-spawn thread'
            return super().accept_completed(case,cell,name,directory,proof,expected)
    pg=PG(OWN/'pg-cpu-v2',Path(read_json(plan['clean']['path'])['root']),output,guard,startup_floor=768*1024**2,case_floor=640*1024**2)
    rows=[];write(output/'launch.json',dict(creator_pid=os.getpid(),selection=reference(EVIDENCE/'profile-selection.json'),plan=reference(BASE/'plan.json')))
    try:
        with pg:
            for target in selection['targets']:
                mode=target['mode'];app=target['app'];original=next(r for r in index['rows'] if r['app']==app and r['config_id']==mode and r['phase']=='measured' and r['repeat']==0)
                case={k:original[k] for k in plan['schedule'][0]};case.update(phase='diagnostic',trial_id=app+'-'+mode+'-cpu')
                d=output/'cases'/case['trial_id'];os.environ.update(TTG_CPU_REQUESTS=json.dumps([target['request']]),TTG_CPU_OUTPUT=str(d/'cpu'))
                pg.context=dict(directory=d,case=case,cell=mode,source_manifest=reference(output/'sources.json'),prior_metrics={})
                with storage_watch(output,case,512*1024**2):
                    Trial().run(case,mode,d,pg,Path(plan['clean']['path']),Path(plan['overlay']['path']),read_json(original['result']['proof']['path']))
                rows.append(dict(app=app,mode=mode,result=pg.context['result'],profiles=[reference(f) for f in (d/'cpu').glob('*.json')]))
                print('ACCEPTED CPU',app,mode,flush=True)
        guard.verify_hashes();write(output/'result.json',dict(passed=True,primary_measurement=False,rows=rows))
    finally:
        p=subprocess.run([str(BIN/'pg_ctl'),'-D',str(pg.directory/'data'),'status'],capture_output=True,text=True)
        write(output/'lifecycle.json',dict(services_stopped=all(p.poll() is not None for p in pg.services),pg_status=p.returncode,pidfile=(pg.directory/'data/postmaster.pid').exists(),retained_databases=sorted(pg.databases)))
if __name__=='__main__':main()
