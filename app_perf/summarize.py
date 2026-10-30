#!/usr/bin/env python3
"""Require complete measured DB cells before exporting the all30 result tables."""
import argparse
import csv
import json
import hashlib
from pathlib import Path
from gate import APPS, POLICIES
from metrics import aggregate, dispersion, load_calls,verify_artifacts,audit_scope

def summarize(root):
    import gate
    release=gate.validate_formal_release()
    experiment=json.loads((root/'experiment.json').read_text())
    if experiment['authorization_sha256']!=release.authorization_sha256:
        raise ValueError('Experiment does not match the current exact main release')
    plan=gate.read(release.experiment_plan)
    reference_path,_=gate.referenced(plan['original_response_reference'],release.experiment_plan.parent)
    reference=json.loads(reference_path.read_text())
    references={(c['app'],c['policy']):c for c in reference['cases']}
    index = json.loads((root / 'trials.json').read_text())
    if index['status'] != 'complete':
        raise ValueError('Refuse final results from an incomplete or invalidated experiment')
    samples, cells,artifact_seals,scope_audits = [], [],[],[]
    for trial in index['rows']:
        if not trial.get('passed') or not trial.get('measured'):
            continue
        directory = Path(trial['directory'])
        artifact_seals.append(verify_artifacts(directory,required=('requests.json','summary.json')))
        sealed_summary=json.loads((directory/'summary.json').read_text())
        for identity_field in ('app','policy','seed','mode'):
            if sealed_summary[identity_field]!=trial[identity_field]:raise ValueError('Trial index disagrees with sealed case identity')
        if trial['app'] in ('linked_list','littlex','jacord','jdrive'):
            from semantic_responses import audit
            audit(directory,references[(trial['app'],trial['policy'])])
            proof=directory/'response-semantic-audit.json'
            if not proof.is_file():raise ValueError('Missing pre-acceptance original full-response audit')
        requests = json.loads((directory / 'requests.json').read_text())
        if trial['mode'] == 'primary':
            calls = load_calls(directory)
            if not calls:
                raise ValueError(f'Missing actual driver trace: {directory}')
            scope=audit_scope(requests,calls)
            scope.update(app=trial['app'],policy=trial['policy'],repeat=trial['repeat'])
            scope_audits.append(scope)
            for phase in ('workflow', 'first_workflow_request', 'steady_read'):
                metrics = aggregate(requests, calls, phase)
                metrics.update(app=trial['app'], policy=trial['policy'], repeat=trial['repeat'],
                    mode='primary', phase=phase, directory=str(directory))
                samples.append(metrics)
        elif trial['mode'] == 'uninstrumented_e2e':
            for phase in ('workflow', 'steady_read'):
                chosen = [r for r in requests if r['phase'] == phase]
                samples.append(dict(app=trial['app'], policy=trial['policy'], repeat=trial['repeat'],
                    mode='uninstrumented_e2e', phase=phase, requests=len(chosen),
                    http_clean_sum_ms=sum(r['http_e2e_ms'] for r in chosen), directory=str(directory)))
    for app in APPS:
        for policy in POLICIES:
            for phase in ('workflow', 'first_workflow_request', 'steady_read'):
                selected = [s for s in samples if s['app']==app and s['policy']==policy and s['phase']==phase and s['mode']=='primary']
                if len(selected)!=plan['measured_trials'] or len(selected)<3 or len({s['repeat'] for s in selected})!=len(selected):
                    raise ValueError(f'Incomplete/duplicated primary cell {app}/{policy}/{phase}: n={len(selected)}')
                cell = dict(app=app,policy=policy,phase=phase,n=len(selected))
                for field in ('protocol_sum_ms','protocol_union_ms','driver_sum_ms','sql_dispatches',
                    'command_complete_count','protocol_cycles','control_dispatches','foreground_dispatches',
                    'background_dispatches','errors','foreground_protocol_sum_ms','background_protocol_sum_ms',
                    'late_db_calls','http_instrumented_sum_ms'):
                    cell[field]=dispersion(s[field] for s in selected)
                clean = [s for s in samples if s['app']==app and s['policy']==policy and s['phase']==phase and s['mode']=='uninstrumented_e2e']
                cell['clean_http_e2e_ms']=dispersion(s['http_clean_sum_ms'] for s in clean)
                cells.append(cell)
    return dict(complete=True, apps=30, policies=4, primary_cells=120,
        counting='Workflow, first workflow request, and final-state steady-read phases are separate; n counts independent fresh-DB trials, not within-trial HTTP requests',
        samples=samples,cells=cells,artifact_seals=artifact_seals,scope_audits=scope_audits,authorization_sha256=release.authorization_sha256)

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('experiment',type=Path)
    args=parser.parse_args()
    result=summarize(args.experiment)
    (args.experiment/'results.json').write_text(json.dumps(result,indent=2)+'\n')
    headers=['app','policy','phase','n','protocol_sum_ms_median','protocol_sum_ms_q1','protocol_sum_ms_q3',
        'protocol_union_ms_median','driver_sum_ms_median','sql_dispatches_median','command_complete_median',
        'protocol_cycles_median','control_dispatches_median','background_dispatches_median','errors_median',
        'clean_e2e_n','clean_e2e_ms_median']
    with (args.experiment/'per-app-results.csv').open('w',newline='') as file:
        writer=csv.writer(file);writer.writerow(headers)
        for c in result['cells']:
            writer.writerow([c['app'],c['policy'],c['phase'],c['n'],c['protocol_sum_ms']['median'],
                c['protocol_sum_ms']['q1'],c['protocol_sum_ms']['q3'],c['protocol_union_ms']['median'],
                c['driver_sum_ms']['median'],c['sql_dispatches']['median'],c['command_complete_count']['median'],
                c['protocol_cycles']['median'],c['control_dispatches']['median'],c['background_dispatches']['median'],
                c['errors']['median'],c['clean_http_e2e_ms']['n'],c['clean_http_e2e_ms']['median']])
    integrity=dict(authorization_sha256=result['authorization_sha256'],
        results_sha256=hashlib.sha256((args.experiment/'results.json').read_bytes()).hexdigest(),
        csv_sha256=hashlib.sha256((args.experiment/'per-app-results.csv').read_bytes()).hexdigest(),
        trials_index_sha256=hashlib.sha256((args.experiment/'trials.json').read_bytes()).hexdigest(),
        source_sha256={str(Path(__file__).parent/name):hashlib.sha256((Path(__file__).parent/name).read_bytes()).hexdigest()
            for name in ('summarize.py','metrics.py','semantic_responses.py')})
    (args.experiment/'results-integrity.json').write_text(json.dumps(integrity,indent=2)+'\n')
    print(args.experiment/'per-app-results.csv')
