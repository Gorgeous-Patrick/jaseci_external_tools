"""Build the concrete staged research plan without importing Jac or opening DBs."""
import argparse,hashlib,json,os
from pathlib import Path
from ia_config import OWN,ROOT,EVIDENCE,APP_SNAPSHOT,APPS,MODES,run_config,schedule
def ref(p):
 p=Path(p).resolve();return dict(path=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest())
def build(output):
 output=Path(output).resolve();assert not output.exists() and output.is_relative_to(EVIDENCE)
 base=ROOT/'project-notes/measurements/ttg-condition-access-performance-20261111'
 runtimes=dict(clean=ref(base/'clean-manifest.json'),overlay=ref(base/'overlay-manifest.json'))
 registry=APP_SNAPSHOT.parent/'app_suite/registry.json';reg=json.loads(registry.read_text())['apps']
 selected={v['app']:v for v in reg if v['app'] in APPS};assert len(selected)==17
 inventory=[]
 for app in APPS:
  if app in ('jdrive','littlex','linked_list'):
   paths=[APP_SNAPSHOT.parent/'originals'/app/n for n in
    (('server.jac','server.impl.jac') if app=='jdrive' else ('main.jac',) if app=='linked_list' else ('server.jac',))]
  else:paths=sorted((APP_SNAPSHOT.parent/'app_suite/apps'/app).glob('*.jac'))
  inventory.append(dict(app=app,read_walker=selected[app]['read_walker'],sources=[ref(p) for p in paths]))
 files={str(p.resolve()):ref(p)['sha256'] for p in OWN.glob('*.py')}
 borrowed=[ROOT/'reproduction/ttg-continuation-performance'/n for n in
  ('runtime.sh','continuation_probe.py','http_observer.py','control_server.py','owned_postgres.py','sql_admin.py')]
 borrowed += [ROOT/'reproduction/ttg-littlex-freethreaded'/n for n in ('python.sh','sitecustomize.py')]
 borrowed += [ROOT/'reproduction/ttg-next-performance/next_interop.py']
 files.update({str(p.resolve()):ref(p)['sha256'] for p in borrowed})
 # Reuse the accepted helper/oracle closure, excluding historical runtime/cache
 # copies. Bind only the effective latest CLEAN+overlay trees once per run.
 accepted=json.loads((base/'sources.json').read_text())['files']
 helper_roots=tuple(str(ROOT/'reproduction'/n)+'/' for n in
  ('ttg-next-performance','ttg-plus-performance','ttg-continuation-performance','ttg-app-performance'))
 for name,digest in accepted.items():
  path=Path(name)
  if name.startswith(str(APP_SNAPSHOT.parent)+'/') or (name.startswith(helper_roots) and
      path.parent.as_posix() in [p[:-1] for p in helper_roots] and path.suffix in ('.py','.sh')):
   files[name]=digest
 for kind,value in runtimes.items():
  manifest=json.loads(Path(value['path']).read_text())
  files[value['path']]=value['sha256']
  files.update({str(Path(manifest['root'])/name):digest for name,digest in manifest['files'].items()})
 # Owned versions replace only their own source paths; borrowed old files are
 # preserved and checked, never silently rebound to a mutable current tree.
 files.update({str(p.resolve()):ref(p)['sha256'] for p in OWN.glob('*.py')})
 output.mkdir(parents=True);source=output/'sources.json';source.write_text(json.dumps(dict(files=files),indent=2)+'\n')
 stages={s:schedule(s) for s in ('first','small-rest','larger','extend-n5','precision')}
 plan=dict(kind='ttg-expanded-performance-20261112-v1',seed=42,runtimes=runtimes,sources=ref(source),
  configs={m:run_config(m) for m in MODES},apps=inventory,app_snapshot=ref(APP_SNAPSHOT),
  scenarios=[ref(APP_SNAPSHOT.parent/'app_suite'/n) for n in ('native.py','evaluate.py','scenarios.py','additional_scenarios.py')],
  fixture_generator=ref(APP_SNAPSHOT.parent/'datasets/ttg/build.py'),recipe_scenario=ref(OWN/'recipe_scenario.py'),
  stages=stages,counts=dict(apps=17,ready_fixtures=20,policy_cells=60,correctness=60,
   excluded_warmups=60,pilot_n3=180,primary_n5=300,timing_workflows_including_warmups=360,
   precision_first_pass=60),
  timing='DIRECT sendall-to-Z and instrumented primary HTTP; no Session precision wrappers. Same native outputs/state/session/restart/physical gates. Summed HTTP responses and first-start/last-response span separately; post-response drain separate.',
  precision='Separate fixed pass: actual returned IDs/request+Session; P intersect D is intersection, not timely cache service. Promotions, return-before-demand and discarded-late delivery distinct. Empty denominators null, Off P=0 valid; Access != Visit.',
  regime=dict(executor='thread',GIL='Actual Py_GIL_DISABLED=1 and sys._is_gil_enabled=False assertions in server and SQL threads',
   workers=1,prefetch_limit=2048,compiled_step_budget=32768,HTTP_timeout_seconds=300,
   min_wal_size='32MB',max_wal_size='64MB',log_statement='none',
   statistics='ANALYZE anchors and graph_types after setup/excluded views before first business/reset',
   profiles='Fresh DB/server workflow; one reset before first business; Always admission; no across-trial history',
   repeats='n3 pilot are predeclared first3 of n5 only if plan/runtime/fixture/capture remain unchanged; else separate version, no pooling',
   summaries='Medians, ranges, dispersion, paired vectors. No empirical p95 claim from n5.'),
  provenance='Common latest frozen Nov11 unified Access runtime for all3 policy modes; 11-file legacy/shared equality audit is scoped, not whole-program historical equivalence. Historical publications are context, not new samples.',
  pending_larger=[dict(app='jdrive',candidate='depth7,3280folders+1093files+Drive',status='Resource/fixture preflight before separate additive release;2048cap disclosed'),
    dict(app='recipe_pantry',candidate='One actor, actual larger graph via native APIs; t13 independent oracle proposal pending',status='No repeated-session relabeling; not in ready20 schedule')],
  storage=dict(free_at_build_bytes=os.statvfs(ROOT).f_bavail*os.statvfs(ROOT).f_frsize,startup=3*1024**3,
   between=2560*1024**2,stop=2*1024**3,retained_estimate_bytes=2*1024**3,
   runtime_cache_cluster_reserve_bytes=1024**3,case_transient_reserve_bytes=512*1024**2,
   policy='One owned cluster, fresh DB per trial, verified compression before successful owner/session/semantic guarded DROP. Failed DBs/evidence preserved; no historic deletions.'),
  runtime_review=ref(ROOT/'project-notes/ttg-performance-research-20261112-runtime.md'),
  execution='No DB until main releases exact plan/stage. All long commands hc run --bg; no side jobs during timing.')
 p=output/'plan.json';p.write_text(json.dumps(plan,indent=2)+'\n')
 print(json.dumps(dict(passed=True,plan=ref(p),sources=ref(source),first_stage_workflows=len(stages['first']),counts=plan['counts'])))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args();build(a.output)
