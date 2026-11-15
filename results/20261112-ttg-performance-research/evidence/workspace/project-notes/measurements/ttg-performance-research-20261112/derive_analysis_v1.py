"""Read-only numerical derivation from independently audited data; no raw rescan."""
import csv,hashlib,json,statistics
from collections import defaultdict
from pathlib import Path
E=Path(__file__).resolve().parent
R=E.with_name(E.name+'-review')/'matrix-raw-audit-v1'
def read(p):return json.loads(p.read_text())
def ref(p):return dict(path=str(p.resolve()),sha256=hashlib.sha256(p.read_bytes()).hexdigest())
def stats(v):return dict(n=len(v),values=v,median=statistics.median(v),min=min(v),max=max(v))
def walker(path):return path.split('/walker/',1)[1].split('/')[0]
def main():
 exported=read(E/'export-n5-v2/results.json');derivative=read(R/'timing-derivatives.json')
 groups=defaultdict(list)
 for s in derivative['samples']:
  if s['phase']=='measured':groups[s['case_id'],s['config_id']].append(s)
 rows=[];rpc_rows=[]
 for (case,mode),samples in groups.items():
  samples.sort(key=lambda s:s['repeat']);assert [s['repeat'] for s in samples]==list(range(5))
  row=dict(case_id=case,config_id=mode,n=5,trial_ids=[s['trial_id'] for s in samples])
  for field in ('HTTP_response_sum_ms','DB_sum_ms','DB_union_ms','data_SQL','control_SQL','total_SQL','data_SQL_per_business_request','business_requests'):
   row[field]=stats([s[field] for s in samples])
  row['DB_sum_minus_union_ms']=stats([s['DB_sum_ms']-s['DB_union_ms'] for s in samples])
  official=next(r for r in exported['rows'] if (r['case_id'],r['config_id'])==(case,mode))
  assert row['HTTP_response_sum_ms']=={k:official['HTTP_response_sum_ms'][k] for k in ('n','values','median','min','max')}
  rpc_count=len(samples[0]['RPCs']);assert all(len(s['RPCs'])==rpc_count for s in samples)
  native=[]
  for s in samples:
   events=s.get('native_work',[])
   if not events:continue
   summaries=[e['summary'] for e in events if isinstance(e.get('summary'),dict)]
   counts={}
   for field in ('submitted_count','promoted_count','unused_cached_count','unavailable_count','plan_count','continuation_count','continuation_execution_count','continuation_path_count'):
    values=[v[field] for v in summaries if field in v]
    if values:counts[field]=sum(values)
   native.append(dict(trial_id=s['trial_id'],repeat=s['repeat'],outcome_events=len(events),summary_events=len(summaries),cumulative_counts=counts))
  row['recorded_native_work']=native
  for ordinal in range(rpc_count):
   rpcs=[s['RPCs'][ordinal] for s in samples];name=walker(rpcs[0]['path']);assert all(walker(r['path'])==name for r in rpcs)
   rpc=dict(case_id=case,config_id=mode,ordinal=ordinal,walker=name,n=5,
    request_refs=[dict(trial_id=s['trial_id'],request=r['request'],generation=r['generation']) for s,r in zip(samples,rpcs)])
   rpc['HTTP_response_ms']=stats([(r['end_ns']-r['start_ns'])/1e6 for r in rpcs])
   for label,key,factor in (('DB_sum_ms','protocol_sum_ns',1e6),('DB_union_ms','protocol_union_ns',1e6),('data_SQL','sql_data',1),('control_SQL','sql_control',1)):
    rpc[label]=stats([r[key]/factor for r in rpcs])
   role_names=set().union(*(r.get('roles',{}) for r in rpcs))
   rpc['roles']={role:{field:stats([r.get('roles',{}).get(role,{}).get(field,0) for r in rpcs]) for field in ('sql_data','sql_control','protocol_sum_ns')} for role in role_names}
   fps=set().union(*({f['fingerprint'] for f in r['fingerprints']} for r in rpcs));fprows=[]
   for fp in fps:
    byrepeat=[[f for f in r['fingerprints'] if f['fingerprint']==fp] for r in rpcs]
    fprows.append(dict(fingerprint=fp,role_counts={role:[sum(f['sql_dispatches'] for f in fs if f['role']==role) for fs in byrepeat] for role in set(f['role'] for fs in byrepeat for f in fs)},
     SQL=stats([sum(f['sql_dispatches'] for f in fs) for fs in byrepeat]),
     protocol_ms=stats([sum(f['protocol_sum_ns'] for f in fs)/1e6 for fs in byrepeat]),
     returned_rows=stats([sum(f.get('returned_rows',0) for f in fs) for fs in byrepeat])))
   rpc['fingerprints']=sorted(fprows,key=lambda f:f['protocol_ms']['median'],reverse=True)
   rpc_rows.append(rpc)
  rows.append(row)
 bycase=defaultdict(dict)
 for r in rows:bycase[r['case_id']][r['config_id']]=r
 comparisons=[]
 for case,modes in bycase.items():
  off=modes['off']
  for mode in ('aggressive','conservative'):
   m=modes[mode];comparisons.append(dict(case_id=case,config_id=mode,
    HTTP_median_ratio=m['HTTP_response_sum_ms']['median']/off['HTTP_response_sum_ms']['median'],
    HTTP_paired_delta_ms=stats([a-b for a,b in zip(m['HTTP_response_sum_ms']['values'],off['HTTP_response_sum_ms']['values'])]),
    DB_median_delta_ms=m['DB_sum_ms']['median']-off['DB_sum_ms']['median'],
    data_SQL_delta=m['data_SQL']['median']-off['data_SQL']['median'],control_SQL_delta=m['control_SQL']['median']-off['control_SQL']['median']))
 for r in rpc_rows:
  off=next(x for x in rpc_rows if x['case_id']==r['case_id'] and x['config_id']=='off' and x['ordinal']==r['ordinal'])
  r['HTTP_median_delta_vs_off_ms']=r['HTTP_response_ms']['median']-off['HTTP_response_ms']['median']
  r['DB_median_delta_vs_off_ms']=r['DB_sum_ms']['median']-off['DB_sum_ms']['median']
 source=Path(__file__);out=E/'analysis-v1';assert not out.exists();out.mkdir()
 value=dict(passed=True,source=ref(source),inputs=[ref(E/'export-n5-v2/results.json'),ref(R/'timing-derivatives.json'),ref(R/'sql-catalog.json')],
  rows=rows,comparisons=comparisons,RPCs=rpc_rows,inventory=exported['inventory'],
  definitions=dict(unit='n5 fresh workflow trials; response wall excludes client decoding and explicit drain; all-role protocol sum and union are separate.',
   native_work='Counters from recorded compact outcome events; empty carried first45 native-work arrays are unavailable, not zero. Counts are abstract planner work, not CPU time or native node entries.',
   fingerprints='Exact independently audited fingerprints, counts and protocol intervals; SQL text is bound in the SQL catalog.',
   interpretation='A sum-minus-union gap can include any overlapping SQL roles; this value alone does not identify foreground/background pairs. No wall-minus-DB CPU estimate.'))
 p=out/'results.json';p.write_text(json.dumps(value,indent=2)+'\n')
 fields=('case_id','config_id','n','HTTP_ms','HTTP_min_ms','HTTP_max_ms','DB_sum_ms','DB_union_ms','data_SQL','control_SQL','data_SQL_per_request')
 with (out/'table.csv').open('w') as f:
  w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
  for r in rows:w.writerow(dict(case_id=r['case_id'],config_id=r['config_id'],n=5,HTTP_ms=r['HTTP_response_sum_ms']['median'],HTTP_min_ms=r['HTTP_response_sum_ms']['min'],HTTP_max_ms=r['HTTP_response_sum_ms']['max'],DB_sum_ms=r['DB_sum_ms']['median'],DB_union_ms=r['DB_union_ms']['median'],data_SQL=r['data_SQL']['median'],control_SQL=r['control_SQL']['median'],data_SQL_per_request=r['data_SQL_per_business_request']['median']))
 (out/'manifest.json').write_text(json.dumps(dict(passed=True,source=ref(source),inputs=value['inputs'],outputs=[ref(p),ref(out/'table.csv')]),indent=2)+'\n')
 print(json.dumps(dict(passed=True,results=ref(p),RPCs=len(rpc_rows),rows=len(rows))))
 print('Top conservative RPC HTTP deltas versus Off:')
 for r in sorted((r for r in rpc_rows if r['config_id']=='conservative'),key=lambda r:r['HTTP_median_delta_vs_off_ms'],reverse=True)[:12]:
  print(r['case_id'],r['ordinal'],r['walker'],'HTTPdelta',round(r['HTTP_median_delta_vs_off_ms'],3),'DBdelta',round(r['DB_median_delta_vs_off_ms'],3),'HTTP',r['HTTP_response_ms']['values'],'SQL',r['data_SQL']['values'],r['control_SQL']['values'],'topFP',[(f['fingerprint'][:12],round(f['protocol_ms']['median'],3),f['SQL']['median']) for f in r['fingerprints'][:2]])
if __name__=='__main__':main()
