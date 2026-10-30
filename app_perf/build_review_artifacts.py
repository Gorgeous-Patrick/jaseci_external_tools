#!/usr/bin/env python3
"""Build concrete plan/instrument artifacts for MAIN review; never authorizes runs."""
import argparse
import json
from pathlib import Path
import statistics
import gate
from runner import harness_sources
from metrics import aggregate, load_calls,verify_artifacts
from dependency_coverage import summarize as dependency_summary

def ref(path):
    return {'path':str(path.resolve()),'sha256':gate.sha(path)}

def write(path,value):
    path.write_text(json.dumps(value,indent=2)+'\n')

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('preflight','runtime','overlay','suite','acceptance','method-review','output'):
        parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args()
    preflight=gate.read(args.preflight)
    gate.require(preflight.get('status')=='complete','Full correctness preflight is not complete')
    gate.verify_preflight(preflight,gate.sha(args.runtime),gate.sha(args.suite),args.preflight.parent,gate.sha(args.overlay))
    before,after=preflight.get('harness_sources_before'),preflight.get('harness_sources_after')
    gate.require(before==after==harness_sources(),'Current execution sources differ from tested preflight closure')
    method=gate.read(args.method_review)
    gate.require(method.get('method_accepted_for_primary_protocol_measurement') is True,'No accepted primary method review')
    for source in method['audited_sources']:
        gate.require(gate.sha(source['path'])==source['sha256'],'Reviewed measurement source changed: '+source['path'])
    calibration_path=Path(method['calibration_summary']['path'])
    gate.require(gate.sha(calibration_path)==method['calibration_summary']['sha256'],'Reviewed raw calibration changed')
    calibration=gate.read(calibration_path)
    gate.require(calibration.get('protocol_validation_passed') is True and calibration.get('independent_server_validation_passed') is True,
        'Protocol/count calibration incomplete')
    out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    from semantic_responses import audit
    semantic_cases=[];semantic_baselines={}
    for case in preflight['cases']:
        if case['app'] not in ('linked_list','littlex','jacord','jdrive'):continue
        semantic=audit(Path(case['evidence']['path']).parent,semantic_baselines.get(case['app']))
        semantic_baselines.setdefault(case['app'],semantic)
        semantic.update(app=case['app'],policy=case['policy'])
        semantic_cases.append(semantic)
    gate.require(len(semantic_cases)==16,'Missing original full-response equivalence supplement')
    semantic_path=out/'original-full-response-reference.json'
    write(semantic_path,{'cases':semantic_cases,'complete_original16':True,'supplements_independent_logical_oracles':True})
    semantic_path.chmod(0o444)
    diagnostics=[];case_metrics={};summaries=[]
    for case in preflight['cases']:
        directory=Path(case['evidence']['path']).parent
        verify_artifacts(directory,required=('requests.json','summary.json'))
        summary=gate.read(Path(case['evidence']['path']));summaries.append(summary)
        requests=json.loads((directory/'requests.json').read_text())
        case_metrics[(case['app'],case['policy'])]=aggregate(requests,load_calls(directory),'workflow')
        if case['policy'].startswith('dependency_'):
            diagnostic=dependency_summary(directory)
            diagnostic.update(app=case['app'],policy=case['policy'])
            diagnostics.append(diagnostic)
    write(out/'preflight-diagnostic-coverage.json',{'cases':diagnostics,'not_formal_samples':True})
    full_apps=[app for app in gate.APPS if app!='linked_list']
    small=min(full_apps,key=lambda app:(case_metrics[(app,'none')]['sql_dispatches'],app))
    heavy=max(gate.APPS,key=lambda app:(case_metrics[(app,'none')]['sql_dispatches'],app))
    candidates={app:max((d['totals']['considered_plans'] for d in diagnostics if d['app']==app),default=0) for app in gate.APPS}
    branch=max(gate.APPS,key=lambda app:(candidates[app],case_metrics[(app,'ttg')]['background_dispatches'],app))
    selected=list(dict.fromkeys([small,heavy,branch]))
    for app in sorted(gate.APPS,key=lambda app:(-case_metrics[(app,'ttg')]['background_dispatches'],app)):
        if len(selected)>=3:break
        if app not in selected:selected.append(app)
    base=sum(s['case_total_wall_ms'] for s in summaries)/1000
    control_base=sum(s['case_total_wall_ms'] for s in summaries if s['app'] in selected)/1000
    trial_bytes=[]
    for case in preflight['cases']:
        directory=Path(case['evidence']['path']).parent
        trial_bytes.append(sum(p.stat().st_size for p in directory.rglob('*') if p.is_file() and '.jac' not in p.relative_to(directory).parts))
    plan=dict(schema_version=1,seed=42,measured_trials=3,excluded_workflow_warmups_per_cell=1,
        apps=list(gate.APPS),policies=list(gate.POLICIES),original_scale='smoke',primary_instrumentation='direct_boundary',
        runtime_manifest_sha256=gate.sha(args.runtime),overlay_manifest_sha256=gate.sha(args.overlay),suite_manifest_sha256=gate.sha(args.suite),
        preflight_manifest=ref(args.preflight),acceptance_manifest=ref(args.acceptance),
        quiet_window_confirmed=False,
        quiet_window_note='Set true only after main coordinates the next quiet formal window; this file is a review candidate',
        primary_cases=480,primary_measured_cases=360,primary_excluded_warmups=120,
        clean_e2e_apps=[],clean_e2e_trials=0,clean_e2e_cases=0,
        clean_e2e_deferred_reason='Main deferred clean HTTP: frozen clean path does not honor cold-profile reset. A future same-regime reset requires outside-timed control and selected correctness preflight. No clean HTTP times in this release.',
        required_formal_entrypoint='formal_supervisor.py',original_response_reference=ref(semantic_path),
        semantic_verifier_sha256=gate.sha(Path(__file__).resolve().parent/'semantic_responses.py'),
        declared_set_schema=ref(gate.EVIDENCE/'set-field-schema-v1.json'),
        diagnostic_selection={'small_query':small,'query_heavy':heavy,'branch_or_prefetch':branch,
            'observed_dependency_plan_counts':candidates,'meaning':'Selection from actual correctness-preflight traces, not formal results; zero supported opportunities remain explicit'},
        diagnostics={'representative_count_validation_apps':selected,'policies':list(gate.POLICIES),
            'server_logging':'enabled only for separate diagnostics','profiles':'foreground thread CPU; independent CALL/WALL option explicitly labeled',
            'post_primary_profile_rule':'Up to five apps: representative subset and largest measured protocol regressions; full source/query/model traces; no primary time substitution'},
        model_state='Cold provider reset on first workflow request; adaptive within workflow. Three warmup final-state reads then three steady reads. Profiles discarded with process; no held-out training.',
        cache_state='Fresh equivalent DB each trial, seeded/verified pages warm; fresh session per request; compiler/OS warm. Module SQL-template caches not forcibly reset beyond process lifecycle; setup may warm them.',
        input_sizes='Original smoke: length32,users6,posts4,channels2,messages8,depth3. Domain apps use exact captured Seed42 graphs and actual node/edge counts in preflight summaries.',
        estimated_primary_hours=4*base/3600,estimated_clean_control_hours=0,
        duration_basis='Four times measured correctness case-wall durations including setup/restarts; diagnostic preflight costs may exceed primary. Not a DB-time performance result.',
        estimated_evidence_bytes=4*sum(trial_bytes),
        storage={'cluster_strategy':'One owned cluster; fresh databases; archived completed cases dropped only after service stop and zero sessions; failed databases preserved',
            'minimum_free_bytes':4*1024**3,'statement_logging_primary':False},
        missing_clean_e2e_cells='Explicitly absent outside selected subset; never filled from instrumented HTTP')
    write(out/'plan.json',plan)
    sources=[{'path':path,'sha256':digest} for path,digest in before.items()]
    for name in ('make_primary_overlay.py','sql_probe.py','metrics.py','summarize.py','dependency_coverage.py',
        'semantic_responses.py','formal_supervisor.py','build_review_artifacts.py',
        'extract_dependency_plans.py','run_diagnostics.py','cpu_profile.py','diagnostic_serve.py','audit_set_fields.py','explain_results.py'):
        path=Path(__file__).resolve().parent/name
        if not any(item['path']==str(path) for item in sources):sources.append(ref(path))
    instrument=dict(schema_version=1,protocol_validation_passed=True,overhead_control_passed=True,
        primary_method='direct_boundary',files=sources,method_review=ref(args.method_review),raw_calibration=ref(calibration_path),
        overlay_manifest=ref(args.overlay),clean_base_manifest=ref(args.runtime),
        native_kind_validation=preflight['kind_validation'],admin_validation=ref(gate.EVIDENCE/'admin-validation-v1/admin-validation.json'),
        acceptance=ref(args.acceptance),preflight=ref(args.preflight),diagnostic_coverage=ref(out/'preflight-diagnostic-coverage.json'),
        calibration_interpretation='Method accepted by separate main review. Raw v8 pending-review flag preserved. Observed deltas and reference dispersion are reported; no exact-overhead estimate or fixed subtraction.',
        calibration_source_provenance='Main reviewed exact core driver/sql_probe/overlay/runtime hashes predating v8 logs. Orchestration validate_protocol.py was edited after v8; future calibrations require before/after source hashes.',
        presentation_versioning='Presentation-only render_report.py is versioned in report-manifest.json at generation, with numeric-figure-data.json input mapping. Layout/font changes do not mutate the raw/numeric execution release.',
        formal_authorization=False)
    write(out/'instrument.json',instrument)
    print(json.dumps({'plan':str(out/'plan.json'),'instrument':str(out/'instrument.json'),'estimated_primary_hours':plan['estimated_primary_hours'],
        'diagnostic_apps':selected,'clean_e2e_apps':plan['clean_e2e_apps'],'formal_authorization_written':False},indent=2))

if __name__=='__main__':main()
