"""One source version of the four-fixture experiment; tested runtime bound later."""
import argparse,json
from pathlib import Path
from ia_config import OWN,ROOT,EVIDENCE,NEXT,APP_SNAPSHOT,MODES,run_config,schedule,guard_schedule
from ia_interop import read_json,reference,sha256,require

def build(output,clean=None,direct=None):
 output=Path(output).resolve();require(output.is_relative_to(EVIDENCE) and not output.exists(),'New owned plan path required')
 prior=ROOT/'project-notes/measurements/ttg-next-performance-20261101/correctness-plan-v2/sources.json'
 files=dict(read_json(prior)['files'])
 for name,wanted in files.items():require(sha256(name)==wanted,'Borrowed immutable source changed')
 for p in OWN.glob('*.py'):
  if not p.name.startswith('render'):files[str(p.resolve())]=sha256(p)
 for p in (OWN/'apps').rglob('*'):
  if p.is_file():files[str(p.resolve())]=sha256(p)
 output.mkdir(parents=True);sources=output/'sources.json';sources.write_text(json.dumps(dict(files=files,borrowed=reference(prior)),indent=2)+'\n')
 baseline=dict(clean=reference(NEXT/'runtime-clean-9282-v1-manifest/manifest.json'),overlay=reference(NEXT/'runtime-direct-9282-v1-overlay/manifest.json'))
 plan=dict(kind='ttg-interability-four-fixture-v1',seed=42,prefetch_workers=1,prefetch_limit=2048,max_steps=32768,
  configs={m:run_config(m) for m in MODES},correctness_schedule=schedule(False),guard_schedule=guard_schedule(),formal_schedule=schedule(True),
  runtimes=dict(baseline9282=baseline,interability=dict(clean=reference(clean),overlay=reference(direct)) if clean and direct else None),
  sources=reference(sources),app_snapshot=reference(APP_SNAPSHOT),
  postgres=dict(min_wal_size='32MB',max_wal_size='64MB',statistics='ANALYZE anchors; ANALYZE graph_types, once after setup/views before first workflow/reset/HTTP clock; admin excluded'),storage=dict(startup_floor_bytes=768*1024**2,case_floor_bytes=640*1024**2,in_case_stop_bytes=512*1024**2),
  primary='Actual business-origin PgWire sendall to ReadyForQuery, all-role/control/data counts, sum/union/perRPC fingerprints; late callbacks retained.',
  regime='NEW uniform analyzed-statistics regime; historical n3 results are a different regime. FreshDB/server per workflow, same seed42/actions/native oracles, excluded warmup12+n3measured36, balanced mode order. One profile reset after setup, Always/process1, no cross-trial state.',
  observer='Exact borrowed compact observer/direct SQL clocks. Natural close/dispatch order, no added waits/ability wrappers. Added native scalar region counters retained.',
  sanity='LL: actual region activation and TOTAL SQL reduction vsOff; tinyAB: one composed guarded region plus path-cache reuse, true/false native correctness, no requiredSQL/latencywin.',
  runtime_pending=not bool(clean and direct))
 path=output/'plan.json';path.write_text(json.dumps(plan,indent=2)+'\n');print(path)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--clean',type=Path);p.add_argument('--direct',type=Path);a=p.parse_args();build(a.output,a.clean,a.direct)
