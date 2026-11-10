"""NEW strict cleanup acceptance. Does not edit/relabel the stopped v1 run."""
import hashlib
import json
from pathlib import Path
import re
import tomllib
from configuration import run_config,signature
from evidence import sha256,read_json,verify_case,checked_ref

HERE=Path(__file__).resolve().parent
REQUIRED_CHECKS=('native','oracle','fresh_session','restart')
REQUIRED_FILES=('summary.json','continuation-proof.json','fixture-canonical.json',
    'actions-canonical.json','outputs-canonical.json','final-graph-raw.json','http-raw.jsonl','requests.json','jac.toml')


def require(value,message):
    if not value:raise ValueError(message)


def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()


def passed(value,label):
    require(value.get('passed') is True,label+' is not passed')
    require(value.get('status','passed') in ('passed','complete','accepted'),label+' declares a failed/incomplete status')
    require(not value.get('error') and not value.get('errors'),label+' contains errors')


def verify_source_context(context):
    sources=context.get('sources')
    require(isinstance(sources,dict) and bool(sources),'Nonempty execution/semantic source closure required')
    from gate import CORE_SOURCE_NAMES
    old=HERE.parent/'ttg-app-performance'
    frozen=old/'suite-final-20261030-v1'
    mandatory={str(HERE/name) for name in (*CORE_SOURCE_NAMES,'app_tier_adapter.py',
        'cleanup_guard_v2.py','semantic_cleanup_v2.py','owned_postgres_v2.py','application_matrix_v2.py')}
    mandatory.update(str(old/name) for name in ('workloads.py','semantic_responses.py','identity.py','metrics.py','gate.py'))
    mandatory.update(str(frozen/name) for name in ('app_suite/native.py','app_suite/evaluate.py',
        'app_suite/scenarios.py','app_suite/additional_scenarios.py','datasets/ttg/build.py'))
    require(mandatory<=set(sources),'Imported semantic/workload/oracle source closure is incomplete')
    for path,expected in sources.items():
        require(Path(path).is_absolute() and sha256(path)==expected,'Source closure mutation: '+path)
    review=read_json(checked_ref(context['cleanup_review'],HERE))
    require(review.get('accepted') is True and review.get('purpose')=='cleanup_gate_v2_review','Main cleanup review is not accepted')
    require(review.get('sources')==sources,'Main review source closure mismatch')
    refs=context.get('source_manifests')
    require(isinstance(refs,dict) and set(refs)=={'runtime','overlay','suite'},'Exact runtime/overlay/suite refs required')
    require(review.get('source_manifests')==refs,'Main review runtime/suite references mismatch')
    manifests={}
    for label,reference in refs.items():
        path=checked_ref(reference,HERE);manifest=read_json(path);root=Path(manifest.get('root',path.parent)).resolve()
        require(bool(manifest.get('files')),'Empty source tree: '+label)
        expected_names=set(manifest['files'])
        actual=set()
        for item in root.rglob('*'):
            require(not item.is_symlink(),'Source symlink is not an immutable input')
            if not item.is_file():continue
            relative=str(item.relative_to(root))
            # Historical accepted suite has derived Python caches. They are
            # not source; its90 source/config/oracle files remain mandatory.
            if label=='suite' and '__pycache__' in item.relative_to(root).parts and item.suffix=='.pyc':continue
            if item.resolve()==path.resolve():continue
            actual.add(relative)
        require(actual==expected_names,'Unlisted/missing source tree member: '+label)
        for name,expected in manifest['files'].items():
            item=(root/name).resolve()
            require(item.is_relative_to(root) and item.is_file() and sha256(item)==expected,'Source member mismatch: '+name)
        manifests[label]=manifest
    require(manifests['overlay'].get('base_runtime_manifest_sha256')==refs['runtime']['sha256'],'Overlay source base mismatch')
    return refs


def validate_cas(context,proof):
    expected=context.get('cas_references',[])
    require(proof.get('cas_references',[])==expected,'CAS reference inventory mismatch')
    allowed=[Path(p).resolve() for p in context.get('cas_roots',[])]
    for reference in expected:
        path=checked_ref(reference,HERE)
        require(any(path.is_relative_to(root) for root in allowed),'CAS reference escapes declared owned roots')
    return expected


def validate_raw_case(directory,context):
    directory=Path(directory).resolve()
    raw=read_json(directory/'artifacts.json');passed(raw,'Raw archive')
    require(bool(raw.get('files')),'Empty raw seal')
    seal=verify_case(directory,required=REQUIRED_FILES)
    summary=read_json(directory/'summary.json');proof=read_json(directory/'continuation-proof.json')
    passed(summary,'Native summary');passed(proof,'Semantic proof')
    target=read_json(checked_ref(context['target_binding'],HERE))
    require(context['target_binding']['path']==str(directory/'cleanup-target.json') and
        raw['files'].get('cleanup-target.json')==context['target_binding']['sha256'],'Owned target binding is not sealed in this exact case')
    require(target.get('kind')=='owned_cleanup_target','Wrong target binding kind')
    for key in ('database','cluster_owner','run_directory','case_directory','app','config_id','seed'):
        require(target.get(key)==context.get(key),'Owned DB/run target relationship mismatch: '+key)
    require(target.get('cleanup_review')==context['cleanup_review'],'Target was created under another cleanup review')
    require(str(directory)==context['case_directory'] and directory.is_relative_to(Path(context['run_directory']).resolve()),
        'Case directory is not in the exact bound run')
    require(summary.get('database')==context['database'],'Raw summary belongs to another database')
    require(summary.get('restart_persistence')=='passed','Restart proof missing')
    require(summary.get('app')==context['app'] and summary.get('policy')==context['config_id']
        and summary.get('seed')==context['seed'],'Summary cell identity mismatch')
    require(proof.get('case_id')=='apps/'+context['app'] and proof.get('config_id')==context['config_id']
        and proof.get('seed')==context['seed'],'Semantic cell identity mismatch')
    require(all(proof.get('checks',{}).get(name) is True for name in REQUIRED_CHECKS),'Mandatory semantic checks incomplete')
    require(proof.get('run')==run_config(context['config_id']) and proof.get('effective_config_sha256')==signature(context['config_id']),
        'Actual declared configuration differs')
    require(tomllib.loads((directory/'jac.toml').read_text())['run']==run_config(context['config_id']),'Sealed TOML settings differ')
    for field,label in (('runtime_manifest_sha256','runtime'),('overlay_manifest_sha256','overlay'),('suite_manifest_sha256','suite')):
        require(proof.get(field)==context['source_manifests'][label]['sha256'],'Semantic/source reference mismatch: '+field)
    for name in ('fixture','actions'):
        require(proof[name+'_sha256']==digest(read_json(directory/(name+'-canonical.json'))),'Canonical semantic hash mismatch: '+name)
    dataset=directory/'dataset/manifest.json'
    if dataset.exists():
        require('dataset/manifest.json' in raw['files'],'Dataset manifest unsealed')
        for name,expected in read_json(dataset)['files'].items():
            item=(dataset.parent/name).resolve()
            require(item.is_relative_to(dataset.parent.resolve()) and sha256(item)==expected,'Dataset referenced artifact mismatch')
    rows=[json.loads(line) for line in (directory/'http-raw.jsonl').read_text().splitlines() if line]
    require(any(r['path'].startswith('/walker/') and r['phase']=='workflow' for r in rows),'Empty actual business workload')
    return seal,summary,proof,rows


def validate_acceptance(directory,acceptance_path,context):
    """Mandatory independent semantic artifact + raw/CAS/source revalidation."""
    refs=verify_source_context(context)
    seal,summary,proof,rows=validate_raw_case(directory,context)
    validate_cas(context,proof)
    acceptance=read_json(acceptance_path);passed(acceptance,'Independent cleanup acceptance')
    require(acceptance.get('kind')=='independent_semantic_cleanup_acceptance','Wrong acceptance proof kind')
    require(acceptance.get('raw_seal')==seal,'Independent proof references another raw archive')
    require(acceptance.get('sources')==context['sources'],'Independent verifier source closure mismatch')
    require(acceptance.get('source_manifests')==refs,'Independent proof source manifest mismatch')
    require(acceptance.get('cleanup_review')==context['cleanup_review'],'Independent proof cleanup review mismatch')
    require(acceptance.get('target_binding')==context['target_binding'],'Independent proof belongs to another owned DB/run')
    require(acceptance.get('database_state',{}).get('matches_sealed_final_graph') is True,
        'No independent physical database state check')
    require(acceptance.get('database_state')==context.get('database_state'),'Physical state proof/context mismatch')
    require(acceptance['database_state'].get('database')==context['database'] and
        acceptance['database_state'].get('cluster_owner')==context['cluster_owner'] and
        acceptance['database_state'].get('final_graph_sha256')==sha256(Path(directory)/'final-graph-raw.json'),
        'Physical state proof target/hash mismatch')
    require(acceptance.get('semantic_proof')=={'path':str(Path(directory).resolve()/'continuation-proof.json'),
        'sha256':sha256(Path(directory)/'continuation-proof.json')},'Independent semantic proof reference mismatch')
    require(acceptance.get('verification',{}).get('independent_semantic_recheck') is True,'No independent semantic recheck')
    return dict(raw_seal=seal,acceptance=dict(path=str(Path(acceptance_path).resolve()),sha256=sha256(acceptance_path)),
        sources=dict(context['sources']),cas_references=context.get('cas_references',[]))
