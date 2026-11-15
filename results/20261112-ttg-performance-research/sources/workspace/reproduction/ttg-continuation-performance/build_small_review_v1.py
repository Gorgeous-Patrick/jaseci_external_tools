"""Build reviewable exact two-app artifacts; NEVER creates main authorization."""
import argparse
import json
from pathlib import Path
import shutil
from evidence import read_json, sha256, verify_case
from gate import CONFIGURATIONS, payload_errors
from app_tier_adapter import OLD_SUITE
from small_runner_v1 import APPS, CASES, sources, schedule, complete_preflight, write
from configuration import run_config, signature, EXPECTED_BENEFIT_DEFAULTS, HISTORY_REGIME
from validate_preparation import OWN, EVIDENCE


def ref(path):
    path=Path(path).resolve()
    return dict(path=str(path),sha256=sha256(path))


def build(output, require_complete=False):
    output=Path(output).resolve()
    if not output.is_relative_to(EVIDENCE):raise ValueError('Owned NEW output required')
    output.mkdir(parents=True,exist_ok=False)
    closure=sources();(output/'execution-sources').mkdir()
    for n,(path,digest) in enumerate(closure.items()):
        target=output/'execution-sources'/f'{n:02d}-{Path(path).name}'
        shutil.copy2(path,target)
        if sha256(target)!=digest:raise ValueError('Source changed during copy')
    index_path=EVIDENCE/'apps-preflight-866222-v2/index.json'
    index=read_json(index_path)
    if require_complete:complete_preflight(index_path)
    suite_root=output/'suite';suite_root.mkdir()
    old=read_json(OLD_SUITE);origins=[]
    for name,digest in old['files'].items():
        source=OLD_SUITE.parent/name;target=suite_root/name;target.parent.mkdir(parents=True,exist_ok=True)
        if sha256(source)!=digest:raise ValueError('Accepted app source changed')
        shutil.copy2(source,target)
        if sha256(source)!=digest or sha256(target)!=digest:raise ValueError('Suite changed during coherent copy')
        origins.append(dict(path=str(source),sha256=digest))
    inventory=suite_root/'case-inventory.json'
    write(inventory,dict(cases=[dict(case_id=c,implemented=True,
        required_checks=['native','oracle','fresh_session','restart']) for c in CASES]))
    write(output/'suite-manifest.json',dict(kind='benchmark_suite_snapshot',final=True,root=str(suite_root),
        files={str(p.relative_to(suite_root)):sha256(p) for p in suite_root.rglob('*') if p.is_file()},
        origins=origins,case_inventory=ref(inventory),accepted_source_suite=ref(OLD_SUITE),
        note='Coherent90-member accepted source copy plus exact two-case inventory; unchanged evaluator imports source-identical accepted originals'))
    selected=[]
    for row in index['cases']:
        if row['app'] not in APPS:continue
        directory=index_path.parent/(row['app']+'-'+row['config_id'])
        verify_case(directory,required=('continuation-proof.json',))
        proof=read_json(directory/'continuation-proof.json')
        if not proof['passed'] or payload_errors(proof):raise ValueError('Failed subset correctness')
        selected.append(dict(**proof,evidence=ref(directory/'continuation-proof.json')))
    selected.sort(key=lambda r:(CASES.index(r['case_id']),[c[0] for c in CONFIGURATIONS].index(r['config_id'])))
    if len(selected)!=12:raise ValueError('All12 selected correctness cases required before review')
    runtime=index['runtime_manifest'];overlay=index['overlay_manifest']
    write(output/'correctness.json',dict(passed=True,runtime_manifest_sha256=runtime['sha256'],
        suite_manifest_sha256=sha256(output/'suite-manifest.json'),cases=selected,
        original_raw_source_suite=ref(OLD_SUITE),full180_complete_at_build=index.get('status')=='complete',
        scope='Actual selected12 native cases, source-identical coherent suite copy; NEWfull180 completion is a separate mandatory launch guard'))
    write(output/'selection.json',dict(accepted=True,case_ids=list(CASES),
        case_inventory_sha256=sha256(inventory),scope='Explicit user-selected partial release; no paper61 dependency'))
    plan=dict(case_ids=list(CASES),configurations=[dict(id=c[0],policy=c[1],executor=c[2],
        run=run_config(c[0]),effective_config_sha256=signature(c[0])) for c in CONFIGURATIONS],
        measured_repeats=3,excluded_warmups=1,seeds=[42],schedule=schedule(),
        quiet_window_confirmed=False,startup_ipc_accounting='included_and_separate',
        cache_regime='Fresh equivalent DB each workflow; deterministic seed/setup warms PG+OS; no cache-flush claim',
        model_regime=HISTORY_REGIME,expected_benefit_defaults=EXPECTED_BENEFIT_DEFAULTS,
        lifecycle='Unchanged accepted30 evaluator: fresh sessions, source-defined workflow/steady warmup/steady read/final restart',
        primary_phase='workflow',steady_reads_are_replicates=False,clean_e2e_cases=0,
        complete_180_preflight=ref(index_path),preflight_complete=index.get('status')=='complete',
        source_suite_manifest=ref(OLD_SUITE),trial_databases=48,warmup_workflows=12,measured_workflows=36,
        timing_logging='off',partial_scope='Only LittleX+IssueDesk, all6 policies; full91 remains future work',
        numerical_export='small_export_v1.py; n3 independent workflows/cell; sums and union separate, controls retained',
        storage='48raw cases approximately150-250MB plus one owned cluster; stop below3GiB; preserve failures',
        planned_output=str(EVIDENCE/'small-formal-v1'),planned_cluster=str(OWN/'pg-small-formal-v1'))
    write(output/'plan.json',plan)
    supplemental=EVIDENCE/'sql-41260-v3-supplement-v1/result.json'
    component=EVIDENCE/'main-component-review-866222-v1/review.json'
    for p in (supplemental,component):
        if read_json(p).get('passed') is not True:raise ValueError('Component evidence not passed')
    write(output/'instrument.json',dict(passed=True,runtime_manifest_sha256=runtime['sha256'],
        overlay_manifest_sha256=overlay['sha256'],sources=closure,
        protocol_validation=ref(supplemental),independent_sql_reconciliation=ref(supplemental),
        overhead_review=ref(component),concurrency_review=ref(supplemental),
        component_binding=ref(EVIDENCE/'component-binding-866222-v2/binding.json'),
        overhead_raw=ref(EVIDENCE/'overhead-41260-v1/artifacts.json'),
        overhead_export=ref(EVIDENCE/'overhead-41260-v1-export/results.json'),
        scope='Component controls transferred by reviewed byte identity; new runner/export require main source/test review',
        interpretation='No fixed subtraction, server-only execution claim, app-CPU claim or synthetic-to-app overlap inference'))
    refs=dict(runtime=runtime,overlay=overlay,suite=ref(output/'suite-manifest.json'),
        selection=ref(output/'selection.json'),correctness=ref(output/'correctness.json'),
        instrument=ref(output/'instrument.json'),plan=ref(output/'plan.json'))
    # Templates are deliberately NOT accepted approval artifacts.
    write(output/'main-review-TEMPLATE.json',dict(accepted=False,purpose='cleanup_gate_v2_review',
        artifact_sha256={k:v['sha256'] for k,v in refs.items()},sources=closure,
        source_manifests=dict(runtime=runtime,overlay=overlay,suite=ref(OLD_SUITE)),
        instructions='MAIN ONLY: after180 complete, review frozen sources/tests, set final plan quiet flag and write main-review.json, then fixed formal authorization'))
    refs['main_review']=dict(path=str(output/'main-review.json'),sha256='MAIN_WRITES_EXACT_HASH')
    write(output/'authorization-TEMPLATE.json',dict(schema_version=1,approved=False,approved_by='main',artifacts=refs))
    write(output/'candidate.json',dict(passed=True,kind='small_exact_subset_REVIEW_ONLY',DB_launch_authorized=False,
        formal_authorized=False,sources=closure,artifact_refs={k:v for k,v in refs.items() if k!='main_review'},
        full180_complete=index.get('status')=='complete',source_suite=ref(OLD_SUITE),
        schedule_counts=dict(total=48,excluded=12,measured=36,cells=12),
        command='python3 -B reproduction/ttg-continuation-performance/small_runner_v1.py formal --output '+
            plan['planned_output']+' --cluster '+plan['planned_cluster'],
        next_step='After180 success, rebuild into NEW final review directory with --require-complete; main reviews/releases exact subset'))
    return output/'candidate.json'


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--require-complete',action='store_true')
    args=parser.parse_args();path=build(args.output,args.require_complete)
    print(json.dumps(dict(candidate=str(path),sha256=sha256(path),formal_authorized=False)))
