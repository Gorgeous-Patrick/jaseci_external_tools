"""Small diagnostic aggregation; CPU observations remain separate from app DB metrics."""
import hashlib,json,statistics
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];E=ROOT/'project-notes/measurements/ttg-next-performance-20261101'
def ref(p):return dict(path=str(p.resolve()),sha256=hashlib.sha256(p.read_bytes()).hexdigest())
def stats(v):return dict(n=len(v),median=statistics.median(v),min=min(v),max=max(v),samples=v)
result=dict(passed=True,source=ref(Path(__file__)),driver=ref(ROOT/'reproduction/ttg-next-performance/cpu_driver.py'),modules=[],
 scope='Separate DB-free construction experiment. Same actual emitted module/sites and same declared typed fixture-derived inputs, not primary Bind recapture. Construction CPU cannot establish whole-app CPU causes.',
 regime='100 calls/block,3 repeated blocks;10 excluded priming calls for AST and warm paths. Cold hydration uses fresh serialized bundles, copying excluded. Same-thread clocks and blocking/busy controls passed. Profiled/unprofiled retained without subtraction.',
 compiler_regime_correction='First fresh-program sample includes lazy compiler/dependency/JIT initialization; do not interpret all fresh-program samples as identically warm. Fresh/same-program vectors retained. Same-program measured after one excluded compile; no OS flush. Earlier raw cache wording is qualified here.',
 limitations=['Fixed order, single process per version/module diagnostic; not all-app CPU profile.', 'Hydration allocates descriptors for the whole emitted module bundle. Warm select/bind targets the selected declared region.', 'Compiler profiling counters are separate controls; primary app captures did not enable template clocks.'])
for case in ['linked_list32','littlex']:
 item=dict(case=case,compiler={},runtime={})
 for mode in ['baseline850','next']:
  path=E/('cpu-compile-'+mode+'-'+case+'-v1')/'result.json';d=json.loads(path.read_text());assert d['passed'] and d['clock_controls']['passed']
  rows=d['compiler']['samples'];groups={}
  for regime in dict.fromkeys(r['regime'] for r in rows):
   selected=[r for r in rows if r['regime']==regime]
   groups[regime]=dict(thread_cpu_ms=stats([r['thread_cpu_ns']/1e6 for r in selected]),wall_ms=stats([r['wall_ns']/1e6 for r in selected]),
    generation_counters=[r['template_metrics'] for r in selected])
  item['compiler'][mode]=dict(raw=ref(path),emitted_plans=d['compiler']['emitted_plans'],groups=groups,generated_artifacts=rows[0]['generated_artifacts'])
  path=E/('cpu-runtime-'+mode+'-'+case+'-v1')/'result.json';d=json.loads(path.read_text());assert d['passed'] and d['clock_controls']['passed']
  rows=d['runtime_construction']['samples'];groups={}
  for method in dict.fromkeys(r['method'] for r in rows):
   selected=[r for r in rows if r['method']==method]
   assert len(selected)==3 and all(r['iterations']==100 for r in selected)
   expected=100 if method=='dynamic_AST' else 0
   assert all(r['runtime_AST_build_calls']==expected for r in selected)
   groups[method]=dict(thread_cpu_us_per_call=stats([r['thread_cpu_ns']/100/1000 for r in selected]),wall_us_per_call=stats([r['wall_ns']/100/1000 for r in selected]),
     AST_calls_per_block=expected,template_counters=[r['template_metrics'] for r in selected])
  item['runtime'][mode]=dict(raw=ref(path),groups=groups,input_validation=d['runtime_construction']['input_validation'],spec=d['runtime_construction']['spec'])
 result['modules'].append(item)
path=E/'cpu-summary-v1.json';assert not path.exists();path.write_text(json.dumps(result,indent=2)+'\n');print(ref(path))
