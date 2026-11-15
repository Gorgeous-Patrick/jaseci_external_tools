"""Small source-bound plan; only main writes the NEW fixed formal release."""
import argparse
import json
from pathlib import Path
import shutil
from plus_config import OWN,EVIDENCE,PREVIOUS,APP_SNAPSHOT,APP_CASES,CELLS,COMMON,MAX_STEPS,schedule,run_config
from interop import require,read_json,reference,checked_ref,sha256,check_tree,verify_case


def check_sources(path):
    manifest=read_json(path)
    require(manifest.get('files'),'Empty execution/numeric closure')
    for name,wanted in manifest['files'].items():
        require(Path(name).is_file() and sha256(name)==wanted,'Bound source mutated: '+name)
    return manifest


def check_plan(path,trees=True):
    plan=read_json(path)
    require(plan['schedule']==schedule(True) and plan['correctness_schedule']==schedule(False),
        'Exact predeclared9/36 schedule required')
    require(plan['configs']=={c:run_config(c) for c in CELLS} and plan['max_steps']==MAX_STEPS,'Configuration differs')
    check_sources(checked_ref(plan['sources'],Path(path).parent))
    clean=checked_ref(plan['runtime'],Path(path).parent);overlay=checked_ref(plan['overlay'],Path(path).parent)
    if trees:check_tree(clean);check_tree(overlay)
    require(read_json(overlay)['base_runtime_manifest_sha256']==sha256(clean),'Overlay base mismatch')
    checked_ref(plan['app_snapshot'],Path(path).parent)
    return plan


def check_regime(previous,plan,parent):
    # A NEW metadata-only review directory has a different sources.json path.
    # Both provenance references must validate and bind identical closure bytes.
    old=checked_ref(previous['sources'],parent);new=checked_ref(plan['sources'],parent)
    check_sources(old);check_sources(new)
    require(previous['sources']['sha256']==plan['sources']['sha256'] and
        read_json(old)['files']==read_json(new)['files'],'Correctness source closure differs')
    for key in ('runtime','overlay','configs','app_snapshot','max_steps'):
        require(previous[key]==plan[key],'Correctness source/config regime differs: '+key)


def check_correctness(index_path,plan):
    index=read_json(index_path)
    require(index.get('status')=='complete' and index.get('passed') is True and index['stage']=='correctness',
        'Completed correctness-only index required')
    expected={(r['case_id'],r['config_id']) for r in schedule(False)}
    require(len(index['rows'])==9 and {(r['case_id'],r['config_id']) for r in index['rows']}==expected,
        'All9 correctness cases required')
    previous=read_json(checked_ref(index['plan'],Path(index_path).parent))
    check_regime(previous,plan,Path(index_path).parent)
    for row in index['rows']:
        require(row['passed'] is True and row['phase']=='correctness','Invalid correctness row')
        result=row['result'];proof=read_json(checked_ref(result['proof'],Path(index_path).parent))
        seal=verify_case(Path(result['raw']['path']).parent)
        require(seal['sha256']==result['raw']['sha256'],'Correctness raw seal changed')
        acceptance=read_json(checked_ref(result['acceptance'],Path(index_path).parent))
        require(acceptance['passed'] and acceptance['raw_seal']==seal and acceptance['semantic']['passed'],
            'Independent correctness acceptance absent')
        require(proof['case_id']==row['case_id'] and proof['config_id']==row['config_id'] and
            proof['passed'] and proof['stage']=='correctness','Correctness identity/status mismatch')
        checked_ref(result['metrics'],Path(index_path).parent)
    return index


def release(plan_path):
    plan=check_plan(plan_path)
    path=EVIDENCE/'formal-run-authorization.json'
    require(path.exists(),'Main-only NEW TTG+ formal release is absent')
    value=read_json(path)
    require(value.get('accepted') is True and value.get('purpose')=='ttg_plus_36_formal' and
        value.get('quiet_window_confirmed') is True,'Main exact36 quiet release required')
    require(value['plan']==reference(plan_path),'Release does not bind exact plan')
    for key in ('sources','runtime','overlay','correctness'):
        require(value[key]==plan[key],'Release binding differs: '+key)
        checked_ref(value[key],path.parent)
    require(value['app_snapshot']==plan['app_snapshot'],'Release app source differs')
    review=read_json(checked_ref(value['main_review'],path.parent))
    require(review.get('accepted') is True and review.get('plan')==reference(plan_path),
        'Main review must accept exact plan')
    check_correctness(checked_ref(plan['correctness'],path.parent),plan)
    return reference(path)


def build(output,runtime,overlay,correctness=None):
    output=Path(output).resolve();require(not output.exists(),'NEW review directory required');output.mkdir(parents=True)
    # Old reviewed sources stay unchanged; bind them as imported reusable
    # primitives, not as an authorization for this new experiment.
    previous=read_json(PREVIOUS.parent.parent/'project-notes/measurements/ttg-continuation-performance-20261030/small-review-ready-v1/instrument.json')
    files=dict(previous['sources'])
    for name,wanted in files.items():require(sha256(name)==wanted,'Historical primitive mutated: '+name)
    for path in OWN.glob('*.py'):
        if not path.name.startswith('render'):files[str(path.resolve())]=sha256(path)
    copies=output/'source-copies';copies.mkdir()
    for name in files:
        relative=Path(name).relative_to(OWN.parent.parent)
        destination=copies/relative;destination.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(name,destination)
    sources=output/'sources.json';sources.write_text(json.dumps(dict(files=files,
        scope='Execution, semantic/physical acceptance, metric aggregation and numeric export; renderer separately versioned'),indent=2)+'\n')
    plan=dict(kind='TTG+ bounded same-runtime comparison',version=1,seed=42,configs={c:run_config(c) for c in CELLS},
        max_steps=MAX_STEPS,schedule=schedule(True),correctness_schedule=schedule(False),
        runtime=reference(runtime) if runtime else None,overlay=reference(overlay) if overlay else None,
        app_snapshot=reference(APP_SNAPSHOT),sources=reference(sources),
        correctness=reference(correctness) if correctness else None,
        primary_phase='workflow',per_request='Every actual Traverse plus Sum/Find/full LittleX workflow retained',
        repetition='Fresh equivalent database/server workflow each trial;9 excluded warmups +27 measured; n3/cell',
        learning='Always only; one reset after setup/before first business RPC; no cross-trial cache/history carry',
        cache='Fresh application/query/model state; shared local OS/PG buffers not forcibly evicted; balanced measured policy order',
        SQL_logging='off for primary timing',storage='One owned cluster/DB; verified pre-seal compression; failed DB retained',
        draft_runtime_pending=not bool(runtime and overlay))
    path=output/'plan.json';path.write_text(json.dumps(plan,indent=2)+'\n')
    if runtime and overlay:check_plan(path)
    if correctness:check_correctness(correctness,plan)
    template=dict(accepted=False,purpose='ttg_plus_36_formal',quiet_window_confirmed=False,
        plan=reference(path),**{k:plan[k] for k in ('sources','runtime','overlay','app_snapshot','correctness')},
        main_review=dict(path='<main review>',sha256='<sha256>'))
    (output/'formal-run-authorization-TEMPLATE.json').write_text(json.dumps(template,indent=2)+'\n')
    print(path)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--runtime',type=Path);parser.add_argument('--overlay',type=Path)
    parser.add_argument('--correctness',type=Path);args=parser.parse_args()
    build(args.output,args.runtime,args.overlay,args.correctness)
