"""Existing30-app SIX-policy correctness only; never formal timing exports."""
import argparse
from datetime import datetime,timezone
import gzip
import json
from pathlib import Path
import shutil
import subprocess
import time
from app_tier_adapter import Applications,OLD,OLD_SUITE
from evidence import sha256,read_json,verify_case,checked_ref
from gate import CONFIGURATIONS,CORE_SOURCE_NAMES,check_tree
from owned_postgres_v2 import OwnedPostgres
from validate_preparation import EVIDENCE,OWN

EXECUTION_FILES=tuple(dict.fromkeys((*CORE_SOURCE_NAMES,'app_tier_adapter.py','application_matrix.py',
    'application_matrix_v2.py','cleanup_guard_v2.py','semantic_cleanup_v2.py','owned_postgres_v2.py')))


def source_hashes():
    values={str(OWN/name):sha256(OWN/name) for name in EXECUTION_FILES}
    for name in ('workloads.py','semantic_responses.py','identity.py','metrics.py','gate.py'):
        values[str(OLD/name)]=sha256(OLD/name)
    schema=OLD.parent.parent/'project-notes/measurements/ttg-app-performance-20261030/set-field-schema-v1.json'
    values[str(schema)]=sha256(schema)
    for name in ('app_suite/native.py','app_suite/evaluate.py','app_suite/scenarios.py',
                 'app_suite/additional_scenarios.py','datasets/ttg/build.py'):
        path=OLD_SUITE.parent/name;values[str(path)]=sha256(path)
    return values


def write(path,value):path.write_text(json.dumps(value,indent=2)+'\n')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage',choices=('correctness',))
    for name in ('runtime-manifest','overlay-manifest','postcommit-proof','output','cluster'):
        parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--apps',nargs='+')
    parser.add_argument('--cleanup-review',type=Path,required=True)
    parser.add_argument('--pause-request',type=Path,help='Stop after current completed case; no interrupted case or source mutation')
    args=parser.parse_args()
    clean=check_tree(args.runtime_manifest);overlay=check_tree(args.overlay_manifest)
    if overlay['base_runtime_manifest_sha256']!=sha256(args.runtime_manifest):raise ValueError('Overlay base mismatch')
    postcommit=read_json(args.postcommit_proof)
    if postcommit.get('passed') is not True or postcommit.get('runtime_commit')!=clean['commit']:
        raise ValueError('Passed exact-commit main postcommit proof required')
    for name,expected in postcommit['source_files'].items():
        if sha256(Path(clean['root'])/name)!=expected:raise ValueError('Postcommit source proof mismatch')
    for ref in postcommit.get('evidence',[]):checked_ref(ref,args.postcommit_proof.parent)
    review=read_json(args.cleanup_review)
    if review.get('accepted') is not True or review.get('purpose')!='cleanup_gate_v2_review' or review.get('sources')!=source_hashes():
        raise ValueError('Main-reviewed exact NEW cleanup/execution source closure required')
    expected_manifests=dict(runtime=dict(path=str(args.runtime_manifest.resolve()),sha256=sha256(args.runtime_manifest)),
        overlay=dict(path=str(args.overlay_manifest.resolve()),sha256=sha256(args.overlay_manifest)),
        suite=dict(path=str(OLD_SUITE),sha256=sha256(OLD_SUITE)))
    if review.get('source_manifests')!=expected_manifests:raise ValueError('Main-reviewed exact runtime/suite references required')
    suite=Applications();selected=args.apps or list(suite.apps)
    if len(set(selected))!=len(selected) or not set(selected)<=set(suite.apps):raise ValueError('Unknown/duplicate selected app')
    output=args.output.resolve()
    if not output.is_relative_to(EVIDENCE) or output==EVIDENCE:raise ValueError('New owned output required')
    output.mkdir(parents=True,exist_ok=False)
    sources=source_hashes();(output/'execution-sources').mkdir()
    for i,(name,expected) in enumerate(sources.items()):
        target=output/'execution-sources'/f'{i:02d}-{Path(name).name}';shutil.copy2(name,target)
        if sha256(target)!=expected:raise ValueError('Source changed while copying')
    index=dict(kind='30_application_correctness_six_policy_preflight',formal_samples=0,status='running',
        runtime_manifest=dict(path=str(args.runtime_manifest.resolve()),sha256=sha256(args.runtime_manifest)),
        overlay_manifest=dict(path=str(args.overlay_manifest.resolve()),sha256=sha256(args.overlay_manifest)),
        postcommit_proof=dict(path=str(args.postcommit_proof.resolve()),sha256=sha256(args.postcommit_proof)),
        source_suite=dict(path=str(OLD_SUITE),sha256=sha256(OLD_SUITE)),
        cleanup_review=dict(path=str(args.cleanup_review.resolve()),sha256=sha256(args.cleanup_review)),
        selected_apps=selected,configurations=[c[0] for c in CONFIGURATIONS],seed=42,
        scope='Correctness only. Per-case elapsed/storage are capacity observations, excluded from performance results',
        sources_before=sources,cases=[],started_utc=datetime.now(timezone.utc).isoformat())
    write(output/'index.json',index)
    def guard():
        if sources!=source_hashes():raise ValueError('Application correctness execution closure changed')
        check_tree(args.runtime_manifest);check_tree(args.overlay_manifest)
        # Coherent accepted source/oracle tree, including registry and set schema.
        manifest=read_json(OLD_SUITE)
        for name,expected in manifest['files'].items():
            if sha256(OLD_SUITE.parent/name)!=expected:raise ValueError('Accepted application source changed')
    try:
        with OwnedPostgres(args.cluster,Path(clean['root']),statement_logging=False) as postgres:
            for app in selected:
                baseline=None
                for cell,_,_ in CONFIGURATIONS:
                    guard()
                    if args.pause_request and args.pause_request.exists():
                        postgres.stop();index['status']='paused_at_case_boundary';write(output/'index.json',index);return
                    if shutil.disk_usage(output).free<3*1024**3:raise RuntimeError('Capacity guard:<3GiB free; stopped without dropping cells')
                    directory=output/(app+'-'+cell)
                    if app in suite.native.SOURCES:types=sum((list(x) for x in suite.native.TYPES[app]),[])
                    else:
                        import re
                        text='\n'.join(p.read_text() for p in (OLD_SUITE.parent/'app_suite/apps'/app).glob('*.jac'))
                        types=re.findall(r'\b(?:node|edge)\s+(\w+)\s*\{',text)
                    postgres.cleanup_context=dict(app=app,config_id=cell,seed=42,mode='live_cleanup',
                        run_directory=str(output),case_directory=str(directory),
                        acceptance_directory=str(output/'cleanup-acceptance'),sources=sources,
                        cleanup_review=index['cleanup_review'],
                        source_manifests=dict(runtime=index['runtime_manifest'],overlay=index['overlay_manifest'],suite=index['source_suite']),
                        cas_references=[],cas_roots=[],domain_types=types,expected=baseline)
                    started=time.perf_counter_ns()
                    result=suite.run(app,cell,directory,postgres,args.runtime_manifest,args.overlay_manifest,
                        expected=baseline,stage='correctness',seed=42,source_guard=guard)
                    baseline=baseline or result['proof']
                    seal=verify_case(directory,required=('continuation-proof.json',))
                    # A temporary independent compression count forecasts storage;
                    # original accepted raw files/seals are retained unchanged.
                    raw_bytes=sum(p.stat().st_size for p in directory.rglob('*') if p.is_file())
                    compressed_bytes=sum(len(gzip.compress(p.read_bytes(),mtime=0)) for p in directory.rglob('*') if p.is_file())
                    row=dict(app=app,config_id=cell,passed=True,proof=result['proof'],evidence=seal,
                        capacity_elapsed_seconds=(time.perf_counter_ns()-started)/1e9,
                        capacity_raw_bytes=raw_bytes,capacity_individually_gzipped_bytes=compressed_bytes,
                        free_bytes_after=shutil.disk_usage(output).free)
                    index['cases'].append(row)
                    index['capacity_projection']=dict(completed_cases=len(index['cases']),
                        median_case_seconds=__import__('statistics').median(r['capacity_elapsed_seconds'] for r in index['cases']),
                        median_compressed_bytes=__import__('statistics').median(r['capacity_individually_gzipped_bytes'] for r in index['cases']),
                        limitation='Observed completed-case capacity only; workload families differ. Final all91 forecast waits benchmark correctness observations.')
                    write(output/'index.json',index)
                    print(json.dumps(dict(completed=len(index['cases']),total=len(selected)*6,app=app,config_id=cell,
                        capacity_elapsed_seconds=row['capacity_elapsed_seconds'],raw_bytes=raw_bytes,compressed_bytes=compressed_bytes)),flush=True)
        index['status']='complete';index['passed']=len(index['cases'])==len(selected)*6
    except Exception as error:
        index.update(status='failed_or_invalidated',passed=False,error=f'{type(error).__name__}: {error}')
        raise
    finally:
        index['sources_after']=source_hashes();index['completed_utc']=datetime.now(timezone.utc).isoformat()
        write(output/'index.json',index)


if __name__=='__main__':main()
