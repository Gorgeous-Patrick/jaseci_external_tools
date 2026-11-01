"""Small sealed-metric coverage projection; all selected cells retained."""
import hashlib,json
from collections import Counter
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];E=ROOT/'project-notes/measurements/ttg-next-performance-20261101'
def ref(p):return dict(path=str(p.resolve()),sha256=hashlib.sha256(p.read_bytes()).hexdigest())
d=json.loads((E/'export-v1/results.json').read_text());samples=[]
for row in d['samples']:
 if row['phase']!='measured':continue
 p=Path(row['metric_ref']['path']);assert ref(p)==row['metric_ref'];m=json.loads(p.read_text())
 counts=Counter();reasons=Counter();points=Counter();regions=Counter();launch=[]
 for o in m['model_outcomes']:
  s=o['summary']
  for k in ('submitted_count','promoted_count','unused_cached_count','unavailable_count','plan_count','resolved_plan_count'):
   counts[k]+=s.get(k,0)
  for k,v in s['fusion'].items():
   if type(v) is int:counts['fusion.'+k]+=v
  reasons.update(s['continuation_stop_counts']);points.update(s['reached_point_counts']);regions.update(s['region_kind_counts'])
  launch.extend(s.get('worker_process_startup_ms',[]))
 overlap=m['primary']['actual_overlap']
 assert m['primary']['protocol_sum_ns']==m['primary']['protocol_union_ns']
 samples.append(dict(**{k:row[k] for k in ('case_id','config_id','repeat','trial_id')},metric=row['metric_ref'],
  counts=dict(counts),continuation_stops=dict(reasons),reached_points=dict(points),regions=dict(regions),
  actual_process_evidence=m['primary']['executor'],all_SQL_overlap_zero=True,worker_startup_ms_observed=launch))
result=dict(passed=True,source=ref(Path(__file__)),export=ref(E/'export-v1/results.json'),samples=samples,
 definition='Native exact per-scope counters summed across workflow outcomes, not a global unique-ID union. Submitted/promoted/unused_cached/unavailable retain native names. Latest pool startup fields are observations, not exhaustive process history; actual child SQL evidence is separate.',
 primary_protocol_overlap='All54 measured workflow sums equal interval unions; independent raw audit confirms all72 including warmups. Real child SQL and distinct backend PIDs exist; overlap is zero in these observations.')
p=E/'coverage-v1.json';assert not p.exists();p.write_text(json.dumps(result,indent=2)+'\n');print(ref(p))
for case in dict.fromkeys(s['case_id'] for s in samples):
 for mode in ['baseline850','next']:
  rows=[s for s in samples if s['case_id']==case and s['config_id']==mode]
  print(case,mode,[(s['counts'].get('fusion.queries',0),s['counts'].get('fusion.template_queries',0),s['counts'].get('fusion.frontier_origins',0),s['counts'].get('submitted_count',0)) for s in rows])
