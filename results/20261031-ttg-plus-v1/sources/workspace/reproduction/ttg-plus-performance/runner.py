"""Sequential9 correctness or exact36 authorized fresh-workflow trials."""
import argparse
import json
import os
from pathlib import Path
import time
from plus_config import OWN,EVIDENCE,schedule
from interop import read_json,require,reference,checked_ref,check_tree
from review import check_plan,check_sources,check_correctness,release
from plus_postgres import OwnedPostgres
from trial import Trial


def write(path,value):path.write_text(json.dumps(value,indent=2)+'\n')


def absolute_paths(output,cluster):
    return Path(output).resolve(),Path(cluster).resolve()


def linked_list_mechanism(case_id,metrics):
    """Correctness-only activation sanity using accepted Traverse metrics.

    Native counters are scoped to the actual Traverse request/generation.
    Payload activation also requires observed background SQL, not just a plan.
    TOTAL is the accepted all-role SQL count, including controls and late work.
    """
    require(case_id in ('linked_list32','linked_list1000') and
        set(metrics)=={'off','prefusion','ttg_plus'},'Complete LinkedList comparison required')
    facts={}
    for cell,metric in metrics.items():
        require(metric['passed'] and metric['stage']=='correctness' and
            metric['case_id']==case_id and metric['config_id']==cell,'Mechanism metric identity/status differs')
        requests=[r for r in metric['request_metrics'] if r['phase']=='workflow' and
            r['path'].split('/')[2:3]==['Traverse']]
        require(len(requests)==1,'Mechanism check requires exactly one business Traverse')
        request=requests[0]
        outcomes=[e['summary'] for e in metric['model_outcomes'] if
            e.get('origin_request_id')==request['request'] and
            str(e['server_generation'])==str(request['server_generation'])]
        facts[cell]=dict(request=request['request'],server_generation=request['server_generation'],
            total_SQL=request['sql_dispatches'],
            resolved_path_plans=sum(s['resolved_plan_count'] for s in outcomes),
            resolved_targets_cumulative=sum(s['resolved_targets_cumulative'] for s in outcomes),
            payload_dispatches=sum(s.get('fusion',{}).get('payload_dispatches',0) for s in outcomes),
            submitted_IDs_cumulative=sum(s['submitted_count'] for s in outcomes),
            actual_background_SQL=sum(request['roles'][role]['sql_dispatches'] for role in
                ('background_prefetch','background_continuation')),
            fused_queries=sum(s.get('fusion',{}).get('queries',0) for s in outcomes))
    pre=facts['prefusion'];fused=facts['ttg_plus'];off=facts['off']
    checks=dict(prefusion_resolved_path=pre['resolved_path_plans']>0,
        prefusion_payload_active=pre['payload_dispatches']>0 and pre['submitted_IDs_cumulative']>0 and
            pre['actual_background_SQL']>0,
        Traverse_fused_queries_positive=fused['fused_queries']>0,
        Traverse_TOTAL_SQL_below_off=fused['total_SQL']<off['total_SQL'])
    failed=[name for name,passed in checks.items() if not passed]
    return dict(passed=not failed,status='failed' if failed else 'passed',case_id=case_id,
        kind='correctness_mechanism_sanity',checks=checks,failed_checks=failed,facts=facts,
        scope='Actual business Traverse only; all SQL roles and controls; cumulative IDs/targets are not unique-ID unions')


def mechanism_after_accept(index,output,row):
    if index['stage']!='correctness' or row['case_id'] not in ('linked_list32','linked_list1000') or row['config_id']!='ttg_plus':
        return
    selected=[r for r in index['rows'] if r['case_id']==row['case_id']]
    require(len(selected)==3 and all(r['passed'] for r in selected),'Three accepted native correctness rows required')
    refs={r['config_id']:r['result']['metrics'] for r in selected}
    metrics={cell:read_json(checked_ref(value,output)) for cell,value in refs.items()}
    status=linked_list_mechanism(row['case_id'],metrics);status['accepted_metric_refs']=refs
    directory=output/'mechanism';directory.mkdir(exist_ok=True)
    path=directory/(row['case_id']+'.json');write(path,status)
    index.setdefault('mechanism_checks',{})[row['case_id']]=reference(path)
    index['mechanism_status']='failed' if not status['passed'] else (
        'passed' if len(index['mechanism_checks'])==2 else 'partial')
    write(output/'index.json',index)
    print(json.dumps(dict(mechanism=status['status'],case_id=row['case_id'],
        failed_checks=status['failed_checks'],evidence=str(path))),flush=True)
    require(status['passed'],'LinkedList mechanism sanity failed: '+row['case_id']+': '+', '.join(status['failed_checks']))


def run(stage,plan_path,output,cluster):
    output,cluster=absolute_paths(output,cluster)
    plan_path=plan_path.resolve();plan=check_plan(plan_path)
    require(output.resolve().is_relative_to(EVIDENCE) and not output.exists(),'NEW owned evidence output required')
    authorization=release(plan_path) if stage=='formal' else None
    require(stage in ('correctness','formal'),'Explicit correctness/formal stage required')
    def source_guard():
        check_sources(checked_ref(plan['sources'],plan_path.parent))
        for key in ('runtime','overlay'):
            check_tree(checked_ref(plan[key],plan_path.parent))
        checked_ref(plan['app_snapshot'],plan_path.parent)
        if stage=='formal':
            require(reference(EVIDENCE/'formal-run-authorization.json')==authorization,'Main release changed during run')
    baselines={}
    if stage=='formal':
        index=check_correctness(checked_ref(plan['correctness'],plan_path.parent),plan)
        for row in index['rows']:
            if row['config_id']=='off':baselines[row['case_id']]=read_json(row['result']['proof']['path'])
    output.mkdir(parents=True);(output/'cases').mkdir()
    index=dict(stage=stage,status='running',passed=False,creator_pid=os.getpid(),started_ns=time.time_ns(),
        plan=reference(plan_path),authorization=authorization,rows=[])
    write(output/'index.json',index);trial=Trial()
    try:
        runtime=Path(read_json(plan['runtime']['path'])['root'])
        with OwnedPostgres(cluster,runtime,output,source_guard) as pg:
            index['cluster']=str(cluster.resolve());index['cluster_owner']=pg.owner
            for row in schedule(stage=='formal'):
                # Unchanged native.prepare owns creation of each fresh case
                # directory for BOTH LinkedList and the reused LittleX trial.
                source_guard();started=time.monotonic_ns();directory=output/'cases'/row['trial_id']
                pg.context=dict(directory=directory,case=row,cell=row['config_id'],source_manifest=plan['sources'])
                write(output/'active-case.json',dict(case=row,directory=str(directory),started_ns=time.time_ns()))
                try:
                    trial.run(row,row['config_id'],directory,pg,Path(plan['runtime']['path']),
                        Path(plan['overlay']['path']),baselines.get(row['case_id']))
                    result=pg.context['result']
                    accepted=dict(**row,passed=True,result=result,wall_seconds=(time.monotonic_ns()-started)/1e9,
                        compressed_evidence_bytes=sum(p.stat().st_size for p in directory.rglob('*') if p.is_file()))
                    index['rows'].append(accepted)
                    if stage=='correctness' and row['config_id']=='off':
                        baselines[row['case_id']]=read_json(result['proof']['path'])
                    write(output/'index.json',index)
                    # The accepted semantic/raw evidence stays preserved if
                    # activation fails. Raise before advancing to any next case.
                    mechanism_after_accept(index,output,accepted)
                    print(json.dumps(dict(accepted=len(index['rows']),total=36 if stage=='formal' else 9,
                        trial=row['trial_id'],seconds=accepted['wall_seconds'],bytes=accepted['compressed_evidence_bytes'])),flush=True)
                except BaseException as error:
                    index['failed_case']=row;raise
            require(not pg.databases,'Retained DB at successful end')
        index.update(status='complete',passed=True,finished_ns=time.time_ns());write(output/'index.json',index)
    except BaseException as error:
        index.update(status='failed',passed=False,error=type(error).__name__+': '+str(error),finished_ns=time.time_ns())
        write(output/'index.json',index);raise
    source_guard();return index


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('stage',choices=('correctness','formal'))
    parser.add_argument('--plan',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--cluster',type=Path,required=True);args=parser.parse_args()
    run(args.stage,args.plan,args.output,args.cluster)
