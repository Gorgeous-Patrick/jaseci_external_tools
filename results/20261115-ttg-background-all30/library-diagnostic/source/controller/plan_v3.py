"""Small source/runtime-bound metadata plan; no DB/compiler/native execution."""
import argparse,hashlib,json,shutil
from pathlib import Path
OWN=Path(__file__).resolve().parent;ROOT=OWN.parents[1]
E=ROOT/'project-notes/measurements/ttg-library-prefetch-performance-20261116'
P=ROOT/'project-notes/measurements/ttg-background-pushdown-portfolio-performance-20261115'
def read(p):return json.loads(Path(p).read_text())
def ref(p):
 p=Path(p).resolve();return dict(path=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest())
def write(p,v):Path(p).write_text(json.dumps(v,indent=2)+'\n')
def build(observer,manifest,checks,output):
 output=Path(output).resolve();observer=Path(observer).resolve();manifest=Path(manifest).resolve();checks=Path(checks).resolve()
 assert not output.exists() and output.is_relative_to(E)
 assert read(checks)['passed'] and read(manifest)['passed'],'Immutable observer source/tests pending'
 binding=next(r['copy'] for r in read(manifest)['files'] if Path(r['copy']['path'])==observer)
 assert ref(observer)=={k:binding[k] for k in ('path','sha256')},'Observer is not the immutable tested copy'
 proposal=read(E/'proposal-v1.json');base=read(proposal['parent_plan']['path'])
 assert ref(proposal['parent_plan']['path'])==proposal['parent_plan']
 out=E/'source-v3';assert not out.exists();out.mkdir()
 prior=P/'source-v2/sources.json';files=dict(read(prior)['files']);copies=[]
 for path in sorted(OWN.glob('*.py')):
  r=ref(path);files[r['path']]=r['sha256'];q=out/path.name;shutil.copyfile(path,q);copies.append(dict(live=r,copy=ref(q)))
 for path in (observer,manifest,checks):r=ref(path);files[r['path']]=r['sha256']
 write(out/'sources.json',dict(files=files))
 write(out/'manifest.json',dict(passed=True,original_sources=ref(prior),copies=copies,
  observer=ref(observer),observer_manifest=ref(manifest),observer_checks=ref(checks),sources=ref(out/'sources.json'),
  source_delta='Accepted Trial changes only serve-entry expression; storage changes only allowed output roots. Original semantic-v2, transport, SQL clocks, GIL/backend, statistics and cleanup bodies reused. Observer adds diagnostics, not runtime code edits.'))
 size_source=P/'A2/primary-v1-stopped-capacity.json';observed=read(size_source)['case_storage']
 bounds={mode:max(r['retained_bytes']+r['metric_acceptance_bytes']for r in observed if r['trial'].startswith('library_loans-smoke-'+mode+'-'))for mode in ('off','restored')}
 base_bytes=bounds['off']+4*bounds['restored'];trace_bytes=4*32*1024**2
 retained=base_bytes+trace_bytes;unc=(retained+9)//10
 raw=max(r['trace_expansion_bytes']for r in observed if r['trial'].startswith('library_loans-smoke-'))
 reserve=512*1024**2;free=shutil.disk_usage(E).free
 budget=dict(saved_size_evidence=ref(size_source),common_case_bounds=bounds,common_retained_bound_bytes=base_bytes,
  traced_workflows=4,per_traced_case_extra_allowance_bytes=32*1024**2,trace_allowance_bytes=trace_bytes,
  retained_bound_bytes=retained,explicit_10percent_uncertainty_bytes=unc,raw_expansion_bound_bytes=raw,
  cluster_compiler_reserve_bytes=reserve,actual_free_at_build_bytes=free,residual_bound_bytes=free-retained-unc-raw-reserve,
  qualification='Saved byte metadata only; no old raw read. Uncompressed timeliness trace retained/sealed. Existing compiler/admin caches reused; no new runtime trees, cleanup or parameter changes.')
 storage={k:base['storage'][k]for k in ('startup','between','stop')};storage['actual_free_at_build_bytes']=free
 assert free>=storage['startup'] and budget['residual_bound_bytes']>storage['between'],'Unchanged diagnostic guards do not fit'
 output.mkdir();write(output/'capacity.json',budget)
 regime=dict(base['regime']);regime.update(warmup='No extra warmup workflows. Existing unchanged setup/views,3steady_warmup,3steady_read and final restart remain outside primary23HTTP and are retained.',
  summaries='3 Restored traced diagnostic repeats;1 Off traced and1 Restored timeliness-observer-disabled fresh control. Separate diagnostic vectors; no n5/p95, clean CPU or performance claim.',
  instrumentation='Common SQL/GIL/DIRECT+compact+job capture in all five workflows. Only timeliness observer disabled for the control; instrumented response wall and separate post-HTTP drain.',
  tracing='Actual keys and native decisions only. No key precompute, SQL condition probe, planner tuning, native wait, forced publication or original runtime/source edit.')
 plan=dict(kind='library-prefetch-timeliness-diagnostic-v1',observer_pending=False,proposal=ref(E/'proposal-v1.json'),
  parent_plan=proposal['parent_plan'],sources=ref(out/'sources.json'),source_manifest=ref(out/'manifest.json'),
  observer=ref(observer),observer_manifest=ref(manifest),observer_checks=ref(checks),runtime=base['runtimes']['restored'],
  seed=42,app_snapshot=base['app_snapshot'],configs={k:base['configs'][k]for k in ('off','restored')},schedule=proposal['schedule'],regime=regime,storage=storage,
  capacity=ref(output/'capacity.json'),counts=dict(workflows=5,Off_traced=1,Restored_traced=3,Restored_timeliness_disabled_control=1,business_HTTP_per_workflow=23),
  gates='Same native outputs/final state/restart/independent scenario/physical census/GIL/backend/cleanup. Fresh Off proof pairs all Restored runs. SQL/job/native counts reported; no exact asynchronous historical count gate.',
  preserved_failed_attempt=ref(E/'diagnostic-v1-failed-stopped.json'),
  prior_results='All30 n5 and28pagePDF immutable. These5diagnostic workflows are separate; appendix is additive.',
  SQL='OriginalSQL/text/fingerprints+protocol metadata retained; original Bind values/raw packets not retained.',
  authorization='User authorized this exact bounded LibraryLoans diagnostic; proceed after observational integration checks and no concrete blocker. Reviewer concurrent, not an added approval layer.')
 path=output/'plan.json';write(path,plan)
 print(json.dumps(dict(passed=True,plan=ref(path),source_manifest=ref(out/'manifest.json'),sources=ref(out/'sources.json'),capacity=ref(output/'capacity.json'),free_bytes=free,residual_bound_bytes=budget['residual_bound_bytes'],counts=plan['counts'])),flush=True)
if __name__=='__main__':
 p=argparse.ArgumentParser()
 for name in ('observer','manifest','checks','output'):p.add_argument('--'+name,type=Path,required=True)
 a=p.parse_args();build(a.observer,a.manifest,a.checks,a.output)
