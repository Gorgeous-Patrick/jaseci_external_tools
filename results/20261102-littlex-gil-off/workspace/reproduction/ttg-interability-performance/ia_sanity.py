"""Mandatory actual execution/count sanity; tiny chain has no forced speedup claim."""
from ia_interop import read_json,reference,require

def check_mechanism(case,rows):
 selected={r['config_id']:r for r in rows if r['case_id']==case['case_id']}
 require(set(selected)=={'off','baseline9282','interability'},'All three paired cases required')
 metrics={m:read_json(r['result']['metrics']['path']) for m,r in selected.items()}
 return from_metrics(case,metrics)

def from_metrics(case,metrics):
 require(set(metrics)=={'off','baseline9282','interability'},'Exact three-mode metric comparison required')
 reader='Traverse' if case['app']=='linked_list' else 'RegionChain'
 rpcs={m:next(r for r in v['request_metrics'] if r['phase']=='workflow' and r['path'].split('/')[2:3]==[reader]) for m,v in metrics.items()}
 current=metrics['interability'];request=rpcs['interability']['request']
 scopes=[o['summary'] for o in current['model_outcomes'] if o['origin_request_id']==request]
 counts={k:sum(s['fusion'].get(k,0) for s in scopes) for k in ('region_queries','region_cache_paths','region_reuses','region_fallbacks')}
 native_region=counts['region_queries']>0
 checks=dict(actual_region_executed=native_region,paired_native_pass=all(m['passed'] for m in metrics.values()))
 if case['app']=='linked_list':checks['TOTAL_SQL_reduced_vs_off']=rpcs['interability']['sql_dispatches']<rpcs['off']['sql_dispatches']
 else:
  checks.update(one_composed_region_query=counts['region_queries']==1,two_cached_stage_paths=counts['region_cache_paths']>=2,native_region_reuse=counts['region_reuses']>=1)
 return dict(passed=all(checks.values()),case=case,checks=checks,actual_counts=counts,
  TOTAL_SQL={m:r['sql_dispatches'] for m,r in rpcs.items()},source=reference(__import__('pathlib').Path(__file__)),
  definition='All-role real SQL including controls; list reduction vsOff mandatory. Tiny3node chain only requires actual composed execution/cache reuse/native oracle; overhead/negative timing retained.')
