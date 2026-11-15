"""Six diagnostic workflows using the unchanged current Trial/oracles/gates."""
import argparse
from collections import Counter
import hashlib,importlib.util,json,os,shutil,subprocess,sys,time,uuid
from pathlib import Path
OWN=Path(__file__).resolve().parent;ROOT=OWN.parents[1]
PRIMARY=OWN.parent/'ttg-performance-research-20261112'
E=ROOT/'project-notes/measurements/ttg-performance-research-diagnostics-20261112'
sys.path.insert(0,str(PRIMARY))
import ia_trial
from ia_trial import Trial,load_unsealed
from ia_postgres import OwnedPostgres as ParentPG
from ia_runner import Sources,storage_watch
from ia_interop import read_json,reference,require
from owned_postgres import BIN,free_port
from sql_reconciliation import fingerprint,sql_kind
_storage_spec=importlib.util.spec_from_file_location('_ttg_research_CPU_owned_storage',OWN/'storage.py')
diagnostic_storage=importlib.util.module_from_spec(_storage_spec)
_storage_spec.loader.exec_module(diagnostic_storage)
require(Path(diagnostic_storage.__file__).resolve()==OWN/'storage.py','Diagnostic storage import resolved to another module')
compress_closed_traces=diagnostic_storage.compress_closed_traces
MODES=('off','aggressive','conservative')
WORK=(('linked_list-smoke',(0,1)),('recipe_pantry-smoke',(7,11)))
COUNT_FIELDS=('submitted_count','promoted_count','unused_cached_count','unavailable_count','plan_count',
              'continuation_count','continuation_execution_count','continuation_path_count')
def write(p,v):Path(p).write_text(json.dumps(v,indent=2)+'\n')
def checked(r):
    p=Path(r['path']);require(reference(p)==r,'Changed selected input: '+str(p));return p

def prepare(plan_path,analysis_path,export_path,output):
    output=Path(output);require(not output.exists(),'New selection required')
    plan=read_json(plan_path);analysis=read_json(analysis_path);export=read_json(export_path)
    require(analysis['passed'] and export['passed'],'Accepted derivatives required')
    require(len(export['rows'])==57 and all(r['n']==5 for r in export['rows']),'Final n5 required')
    work=[]
    for case_id,ordinals in WORK:
        for mode in MODES:
            baseline=next(s for s in export['samples'] if s['case_id']==case_id and s['config_id']==mode and s['phase']=='measured' and s['repeat']==0)
            row=next(r for r in analysis['rows'] if r['case_id']==case_id and r['config_id']==mode)
            sites=[next(r for r in analysis['RPCs'] if r['case_id']==case_id and r['config_id']==mode and r['ordinal']==ordinal) for ordinal in ordinals]
            targets=[dict(request=s['request_refs'][0]['request'],generation=s['request_refs'][0]['generation'],
                ordinal=s['ordinal'],walker=s['walker'],logical_target='item:0' if case_id.startswith('linked_list') else None) for s in sites]
            variants=[]
            for repeat in range(5):
                native=next((n for n in row['recorded_native_work'] if n['repeat']==repeat),None)
                if mode=='conservative':
                    if native is None or set(native.get('cumulative_counts',{}))!=set(COUNT_FIELDS):
                        continue  # Missing ancillary data is unknown, never zero/no-outcome.
                    require(native['outcome_events']>0 and native['summary_events']==native['outcome_events'],'Incomplete observed dependency counters')
                else:
                    require(native is None,'Unexpected dependency outcome under Off/legacy policy')
                signatures=[]
                for site in sites:
                    signatures.append(dict(request=site['request_refs'][repeat]['request'],
                        data_SQL=site['data_SQL']['values'][repeat],control_SQL=site['control_SQL']['values'][repeat],
                        fingerprints=sorted([dict(fingerprint=f['fingerprint'],role=role,count=counts[repeat])
                            for f in site['fingerprints'] for role,counts in f['role_counts'].items() if counts[repeat]],
                            key=lambda x:(x['fingerprint'],x['role']))))
                variants.append(dict(repeat=repeat,native={k:native[k] for k in ('outcome_events','summary_events','cumulative_counts')} if native is not None else None,targets=signatures))
            work.append(dict(case=dict(case_id=case_id,app=baseline['app'],scale=baseline['scale'],length=None,
                guard=True,config_id=mode,phase='diagnostic',repeat=0,trial_id=f'{case_id}-{mode}-CPU-diagnostic-0'),
                expected_proof=baseline['references']['proof'],targets=targets,control_variants=variants,
                available_control_repeats=[v['repeat'] for v in variants],
                native_counter_basis='Complete recorded dependency outcomes' if mode=='conservative' else 'No dependency context under none/ttg policy; counters unavailable, not zero. Actual SQL activation remains checked.'))
            require(bool(variants),'No complete same-repeat activation control available')
    source=output.with_name(output.stem+'-sources.json')
    require(not source.exists(),'Do not overwrite an earlier diagnostic source manifest')
    files={str(p.resolve()):reference(p)['sha256'] for p in OWN.glob('*.py')}
    write(source,dict(files=files,parent_source_manifest=plan['sources']))
    value=dict(kind='bounded_native_thread_CPU_v1',plan=reference(plan_path),analysis=reference(analysis_path),
        accepted_export=reference(export_path),sources=reference(source),work=work,
        scope='Six full workflows, diagnostic n1, two selected RPCs each. Same-mode whole joint SQL/native-work count signature must match one actual n5 control, never independent ranges. No background CPU/totalCPU inference.',
        source_changes='Diagnostic entry/helper and owned output/compression routing only; no runtime/app/primary source edit')
    write(output,value);print(json.dumps(dict(selection=reference(output),sources=reference(source),workflows=len(work))))

def validate_case(directory,selected):
    directory=Path(directory);requests=read_json(directory/'requests.json')
    primary={(str(r['server_generation']),r['request']) for r in requests if r['phase']=='workflow'}
    calls=list(load_unsealed(directory,'server-*.calls.jsonl*'))
    profiles=[read_json(p) for p in directory.glob('cpu/generation-*/*.json')]
    require(len(profiles)==2 and all(p['passed'] for p in profiles),'Exactly two successful CPU boundaries required')
    expected_ids={t['request'] for t in selected['targets']}
    require({p['request'] for p in profiles}==expected_ids,'Selected CPU RPC coverage differs')
    actual=[];bindings=[]
    for target in selected['targets']:
        matching=[r for r in requests if r['request']==target['request'] and str(r['server_generation'])==str(target['generation'])]
        require(len(matching)==1 and matching[0]['phase']=='workflow','Missing actual business request')
        record=matching[0];profile=next(p for p in profiles if p['request']==target['request'])
        require(profile['target']['actual_path']==record['path'],'Profile/actual path differs')
        if target['logical_target']:
            mapping_path=directory/'mapping-initial.json';mapping=read_json(mapping_path)
            require(record['path']=='/walker/'+target['walker']+'/'+mapping[target['logical_target']],'Fresh path is not the imported logical target')
            require(profile['target']['fresh_binding']['mapping_sha256']==reference(mapping_path)['sha256'],'Mapping witness differs')
        else:require(record['path']=='/walker/'+target['walker'],'Root walker path differs')
        picked=[c for c in calls if c.get('origin_request_id')==target['request'] and str(c['server_generation'])==str(target['generation']) and c.get('send_ns') is not None]
        require(any(c['role']=='foreground' and c['client_process_pid']==profile['pid'] and c['thread_id']==profile['thread_id'] for c in picked),'CPU worker is not the actual native foreground SQL thread')
        counts=Counter((fingerprint(c['sql']),c['role']) for c in picked)
        actual.append(dict(request=target['request'],data_SQL=sum(sql_kind(c['sql'])=='data' for c in picked),
            control_SQL=sum(sql_kind(c['sql'])=='control' for c in picked),fingerprints=[dict(fingerprint=k[0],role=k[1],count=v) for k,v in sorted(counts.items())]))
        bindings.append(dict(request=record['request'],generation=record['server_generation'],actual_path=record['path'],actual_body=record['input'],
                             logical_target=target['logical_target'],profile_pid=profile['pid'],profile_thread=profile['thread_id']))
    summaries=[]
    for event in load_unsealed(directory,'server-*.events.jsonl*'):
        if event['kind']=='dependency_outcome' and (str(event['server_generation']),event.get('origin_request_id')) in primary:
            summaries.append(event['summary'])
    native=(dict(outcome_events=len(summaries),summary_events=len(summaries),
                cumulative_counts={k:sum(s.get(k,0) for s in summaries) for k in COUNT_FIELDS}) if summaries else None)
    matches=[v['repeat'] for v in selected['control_variants'] if v['native']==native and v['targets']==actual]
    return dict(passed=bool(matches),matched_unprofiled_control_repeats=matches,actual_native=native,
        actual_targets=actual,actual_bindings=bindings,profiles=[reference(p) for p in directory.glob('cpu/generation-*/*.json')],
        scope='Same-mode realized joint control equality only; wrappers do not prove whole-process CPU attribution.')

class PG(ParentPG):
    def __init__(self,directory,runtime,run_directory,guard,selected):
        self.directory=Path(directory).resolve();self.runtime=Path(runtime).resolve()
        require(self.directory.is_relative_to(OWN) and not self.directory.exists(),'New diagnostic cluster only')
        self.run_directory=Path(run_directory).resolve();self.source_guard=guard;self.selected=selected
        self.port=free_port();self.owner=str(uuid.uuid4());self.started=False;self.databases=set();self.services=[]
        self.admin_process=None;self.statement_logging=False;self.context=None
        self.startup_floor=3*1024**3;self.case_floor=2560*1024**2
    def accept_completed(self,case,cell,name,directory,proof,expected):
        selected=self.selected[case['trial_id']]
        result=validate_case(directory,selected)
        path=self.run_directory/'diagnostic-checks'/(case['trial_id']+'.json');path.parent.mkdir(exist_ok=True)
        write(path,result)
        require(result['passed'],'CPU instrumentation changed actual query/plan-count activation; preserve case/DB')
        super().accept_completed(case,cell,name,directory,proof,expected)
        self.context['result']['CPU_validation']=reference(path)

def run(selection_path,output,cluster):
    selection_path=Path(selection_path).resolve();selection=read_json(selection_path)
    checked(selection['analysis']);checked(selection['accepted_export']);plan=read_json(checked(selection['plan']))
    source=read_json(checked(selection['sources']))
    parent=Sources(plan['sources'])
    def guard():
        parent()
        for name,wanted in source['files'].items():require(reference(name)['sha256']==wanted,'Diagnostic source changed: '+name)
        require(reference(selection_path)==selection_ref,'Selection changed')
    selection_ref=reference(selection_path)
    output=Path(output).resolve();cluster=Path(cluster).resolve()
    require(output.is_relative_to(E) and not output.exists(),'New diagnostic output required')
    output.mkdir(parents=True);(output/'cases').mkdir()
    os.environ['TTG_PYTHON']=str(ROOT/'reproduction/ttg-littlex-freethreaded/python.sh')
    os.environ['TTG_RESEARCH_CAPTURE']='timing'
    ia_trial.OWN=OWN;ia_trial.compress_closed_traces=compress_closed_traces
    index=dict(passed=False,status='running',creator_pid=os.getpid(),selection=selection_ref,rows=[])
    write(output/'index.json',index)
    selected={s['case']['trial_id']:s for s in selection['work']}
    clean=checked(plan['runtimes']['clean']);overlay=checked(plan['runtimes']['overlay'])
    pg=PG(cluster,Path(read_json(clean)['root']),output,guard,selected)
    try:
        with pg:
            index['owner']=pg.owner;index['settings']=pg.settings_ref
            for selected_case in selection['work']:
                case=selected_case['case'];cell=case['config_id'];directory=output/'cases'/case['trial_id']
                os.environ.update(TTG_CPU_TARGETS=json.dumps(selected_case['targets']),TTG_CPU_OUTPUT=str(directory/'cpu'),
                                  TTG_CPU_MAPPING_FILE=str(directory/'mapping-initial.json'))
                guard();pg.context=dict(directory=directory,case=case,cell=cell,source_manifest=selection['sources'],prior_metrics={})
                write(output/'active-case.json',case)
                with storage_watch(output,case,2*1024**3):
                    Trial().run(case,cell,directory,pg,clean,overlay,read_json(checked(selected_case['expected_proof'])))
                index['rows'].append(dict(**case,passed=True,result=pg.context['result']))
                write(output/'index.json',index);print(json.dumps(dict(accepted=len(index['rows']),total=6,trial=case['trial_id'])),flush=True)
        parent.verify_hashes();guard();index.update(passed=True,status='complete',source_after_passed=True)
    except BaseException as error:
        index.update(status='failed',error=type(error).__name__+': '+str(error));raise
    finally:
        write(output/'index.json',index)
        status=subprocess.run([str(BIN/'pg_ctl'),'-D',str(cluster/'data'),'status'],capture_output=True,text=True)
        write(output/'lifecycle.json',dict(services_stopped=all(p.poll() is not None for p in pg.services),
            services=[dict(pid=p.pid,exit_code=p.poll()) for p in pg.services],pg_status=status.returncode,
            postmaster_pid_exists=(cluster/'data/postmaster.pid').exists(),retained_databases=sorted(pg.databases),
            free_bytes=shutil.disk_usage(ROOT).free))

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);commands=parser.add_subparsers(dest='command',required=True)
    prep=commands.add_parser('prepare')
    for name in ('plan','analysis','export','output'):prep.add_argument('--'+name,required=True,type=Path)
    launch=commands.add_parser('run')
    for name in ('selection','output','cluster'):launch.add_argument('--'+name,required=True,type=Path)
    args=parser.parse_args()
    if args.command=='prepare':prepare(args.plan,args.analysis,args.export,args.output)
    else:run(args.selection,args.output,args.cluster)
