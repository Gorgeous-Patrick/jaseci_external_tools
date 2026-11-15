"""One small source/plan version; main releases the same plan after18 correctness."""
import argparse,json
from pathlib import Path
from next_config import OWN,ROOT,EVIDENCE,PLUS,APP_SNAPSHOT,CASES,MODES,run_config,schedule
from next_interop import read_json,reference,sha256,require

def build(output,new_clean=None,new_direct=None,startup_floor=2*1024**3,case_floor=1536*1024**2):
    output=Path(output).resolve();require(output.is_relative_to(EVIDENCE) and not output.exists(),'New owned plan directory required')
    old=ROOT/'project-notes/measurements/ttg-plus-performance-20261031/formal-review-ready-v1/sources.json'
    files=dict(read_json(old)['files'])
    for name,wanted in files.items():require(sha256(name)==wanted,'Borrowed frozen helper changed: '+name)
    app_manifest=read_json(APP_SNAPSHOT)
    for name,wanted in app_manifest['files'].items():
        path=APP_SNAPSHOT.parent/name;require(sha256(path)==wanted,'Borrowed application source changed')
        files[str(path)]=wanted
    for path in OWN.glob('*.py'):
        if not path.name.startswith(('render','cpu_')):files[str(path.resolve())]=sha256(path)
    output.mkdir(parents=True)
    sources=output/'sources.json';sources.write_text(json.dumps(dict(files=files,
        scope='One version of execution, compact observation, native/physical acceptance and exact numeric export; presentation separately versioned'),indent=2)+'\n')
    baseline=dict(clean=reference(PLUS/'runtime-clean-final-v2-manifest/manifest.json'),
        overlay=reference(PLUS/'runtime-direct-final-v2-overlay/manifest.json'))
    plan=dict(kind='ttg-next-six-fixture-v1',version=1,seed=42,prefetch_workers=1,prefetch_limit=2048,max_steps=32768,
        configs={m:run_config(m) for m in MODES},correctness_schedule=schedule(False),formal_schedule=schedule(True),
        runtimes=dict(baseline850=baseline,next=dict(clean=reference(new_clean),overlay=reference(new_direct)) if new_clean and new_direct else None),
        sources=reference(sources),app_snapshot=reference(APP_SNAPSHOT),
        postgres=dict(min_wal_size='32MB',max_wal_size='64MB',
            scope='Uniform across off/baseline850/next; actual SHOW evidence in server-settings.json'),
        storage=dict(startup_floor_bytes=startup_floor,case_floor_bytes=case_floor,in_case_stop_bytes=512*1024**2,
            regime='One owned cluster, one equivalent fresh DB at a time; compact outcome output; sealed successful DB dropped only after independent semantic/physical acceptance; failures retained'),
        cache='Fresh application/session/query cache per existing workflow lifecycle; shared OS/PG buffers warmed by seed/verification, no OS flush; balanced measured policy order',
        learning='Always admission; one profile reset before first business RPC; no cross-trial carry',
        comparison='Declared runtime/version package comparison; template construction isolated by separate CPU/artifact experiment; no queue-only causal claim if SQL or other changes are integrated',
        primary='Business HTTP-origin sendall-to-ReadyForQuery SQL intervals, including late work/controls; setup/auth/seed/verification excluded but retained',
        observer='NEWcompact outcome emission, same reviewed direct SQL boundaries and natural close; native850 suffix memory/construction remains unchanged',
        frozen_runtime_pending=not bool(new_clean and new_direct))
    path=output/'plan.json';path.write_text(json.dumps(plan,indent=2)+'\n')
    (output/'formal-run-authorization-TEMPLATE.json').write_text(json.dumps(dict(accepted=False,
        purpose='ttg_next_72_formal',quiet_window_confirmed=False,plan=reference(path),sources=plan['sources'],
        correctness=dict(path='<complete18 index>',sha256='<sha256>')),indent=2)+'\n')
    print(path)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--new-clean',type=Path);p.add_argument('--new-direct',type=Path)
    p.add_argument('--startup-floor',type=int,default=2*1024**3);p.add_argument('--case-floor',type=int,default=1536*1024**2)
    a=p.parse_args();build(a.output,a.new_clean,a.new_direct,a.startup_floor,a.case_floor)
