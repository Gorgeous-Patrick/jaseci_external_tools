"""Post-run saved-metric/sealed-HTTP export; independent raw SQL audit separate."""
import argparse,csv,hashlib,json,statistics
from collections import defaultdict
from pathlib import Path
def read(p):return json.loads(Path(p).read_text())
def ref(p):
 p=Path(p).resolve();return dict(path=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest())
def checked(v):
 p=Path(v['path']);assert ref(p)==v,'Changed input '+str(p);return p
def union(intervals):
 total=0;end=None
 for left,right in sorted(intervals):
  assert left<=right
  total+=max(0,right-max(left,end if end is not None else left));end=max(right,end or right)
 return total
def stats(values):
 return dict(n=len(values),values=values,median=statistics.median(values),min=min(values),max=max(values),
  mean=statistics.mean(values),stdev=statistics.stdev(values) if len(values)>1 else None)
def export(plan_path,index_paths,output):
 plan_path=Path(plan_path).resolve();plan=read(plan_path);output=Path(output).resolve();assert not output.exists()
 inputs=[ref(plan_path),ref(Path(__file__))];samples=[];seen_trials=set();seen_databases=set();baseline={}
 for ip in index_paths:
  ip=Path(ip).resolve();index=read(ip);inputs.append(ref(ip))
  assert index['status']=='complete' and index['passed'] and index['source_after_passed']
  assert index['plan']==ref(plan_path)
  expected=plan['stages'][index['stage']]
  assert len(index['rows'])==len(expected)
  for row,wanted in zip(index['rows'],expected):
   assert all(row[k]==v for k,v in wanted.items()) and row['passed']
   assert row['trial_id'] not in seen_trials;seen_trials.add(row['trial_id'])
   result=row['result'];metric=read(checked(result['metrics']));proof=read(checked(result['proof']))
   acceptance=read(checked(result['acceptance']));gil=read(checked(row['gil_proof']))
   inputs.extend(result.values());inputs.append(row['gil_proof'])
   assert metric['passed'] and proof['passed'] and acceptance['passed'] and gil['passed']
   assert acceptance['semantic']['passed'] and acceptance['database_state']['matches_sealed_final_graph']
   assert acceptance['semantic_proof']==result['proof'] and metric['independent_acceptance']==result['acceptance']
   assert metric['raw_seal']==acceptance['raw_seal']
   assert proof['database'] not in seen_databases;seen_databases.add(proof['database'])
   assert proof['cluster_owner']==index['owner']
   state=tuple(proof[k] for k in ('fixture_sha256','actions_sha256','output_sha256'))
   assert row['case_id'] not in baseline or baseline[row['case_id']]==state
   baseline[row['case_id']]=state
   directory=checked(result['raw']).parent;seal=read(directory/'artifacts.json')
   http_path=directory/'requests.json'
   assert ref(http_path)['sha256']==seal['files']['requests.json']
   inputs.append(ref(http_path));requests=read(http_path)
   primary=[r for r in requests if r['phase']=='workflow']
   assert primary and len({(str(r['server_generation']),r['request']) for r in primary})==len(primary)
   rpc=[];intervals=[]
   for request in primary:
    left,right=request['start_ns'],request['end_ns'];intervals.append((left,right))
    assert abs(request['http_e2e_ms']-(right-left)/1e6)<1e-6
    assert request['post_response_drain']['start_ns']>=right
    selected=[r for r in metric['request_metrics'] if r['phase']=='workflow' and
     r['request']==request['request'] and str(r['server_generation'])==str(request['server_generation'])]
    assert len(selected)==1
    rpc.append(dict(request=request['request'],server_generation=request['server_generation'],path=request['path'],
     HTTP_response_ms=(right-left)/1e6,DB_sum_ms=selected[0]['protocol_sum_ns']/1e6,
     DB_union_ms=selected[0]['protocol_union_ns']/1e6,data_SQL=selected[0]['sql_data'],
     control_SQL=selected[0]['sql_control'],post_response_drain=request['post_response_drain']))
   p=metric['primary']
   samples.append(dict(**{k:row[k] for k in ('trial_id','case_id','app','scale','config_id','phase','repeat')},
    references=result,GIL_proof=row['gil_proof'],business_requests=len(primary),
    HTTP_response_sum_ms=sum(b-a for a,b in intervals)/1e6,HTTP_response_union_ms=union(intervals)/1e6,
    HTTP_response_span_ms=(max(b for a,b in intervals)-min(a for a,b in intervals))/1e6,
    DB_sum_ms=p['protocol_sum_ns']/1e6,DB_union_ms=p['protocol_union_ns']/1e6,
    data_SQL=p['sql_data'],control_SQL=p['sql_control'],total_SQL=p['sql_dispatches'],
    data_SQL_per_business_request=p['sql_data']/len(primary),roles=p['roles'],actual_overlap=p['actual_overlap'],
    RPCs=rpc,precision=None))
 grouped=defaultdict(list)
 for sample in samples:
  if sample['phase']=='measured':grouped[sample['case_id'],sample['config_id']].append(sample)
 rows=[]
 for (case,mode),items in grouped.items():
  items.sort(key=lambda s:s['repeat']);assert [s['repeat'] for s in items] in ([0,1,2],[0,1,2,3,4])
  row=dict(case_id=case,app=items[0]['app'],scale=items[0]['scale'],config_id=mode,n=len(items))
  for field in ('HTTP_response_sum_ms','HTTP_response_union_ms','HTTP_response_span_ms','DB_sum_ms','DB_union_ms',
   'data_SQL','control_SQL','total_SQL','data_SQL_per_business_request','business_requests'):
   row[field]=stats([s[field] for s in items])
  rows.append(row)
 inventory=[dict(case_id=r['case_id'],config_id=r['config_id']) for r in plan['stages']['precision']]
 completed={(r['case_id'],r['config_id']) for r in rows}
 output.mkdir(parents=True)
 value=dict(passed=True,inputs=inputs,source=ref(Path(__file__)),plan=ref(plan_path),rows=rows,samples=samples,
  counts=dict(captured=len(samples),correctness=sum(s['phase']=='correctness' for s in samples),
   excluded_warmups=sum(s['phase']=='excluded_warmup' for s in samples),measured=sum(s['phase']=='measured' for s in samples),
   measured_cells=len(rows)),inventory=[dict(**r,completed=(r['case_id'],r['config_id']) in completed) for r in inventory],
  definitions=dict(HTTP='Instrumented client response read wall; JSON decoding and explicit post-response drain excluded.',
   workflow_span='First business start to last response end includes inter-request client/control gaps.',
   DB='Accepted all-role sendall-to-ReadyForQuery protocol wall; summed and union intervals, late request-origin calls retained.',
   data_SQL='All-role data statements per successful/expected-error business HTTP request; controls reported separately.',
   verification='Metric/proof/GIL/acceptance references and consumed HTTP seals checked; independent driver-level raw reaggregation separate.',
   precision='Not collected in timing pass. Separate returned/intersection/promotion-backed service/late/unused/demand coverage dataset.'))
 p=output/'results.json';p.write_text(json.dumps(value,indent=2)+'\n')
 fields=('case_id','config_id','n','HTTP_ms_median','HTTP_ms_min','HTTP_ms_max','DB_sum_ms_median','DB_union_ms_median',
  'data_SQL_median','control_SQL_median','data_SQL_per_request_median')
 with (output/'table.csv').open('w') as f:
  w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
  for row in rows:
   w.writerow(dict(case_id=row['case_id'],config_id=row['config_id'],n=row['n'],
    HTTP_ms_median=row['HTTP_response_sum_ms']['median'],HTTP_ms_min=row['HTTP_response_sum_ms']['min'],
    HTTP_ms_max=row['HTTP_response_sum_ms']['max'],DB_sum_ms_median=row['DB_sum_ms']['median'],
    DB_union_ms_median=row['DB_union_ms']['median'],data_SQL_median=row['data_SQL']['median'],
    control_SQL_median=row['control_SQL']['median'],data_SQL_per_request_median=row['data_SQL_per_business_request']['median']))
 (output/'artifacts.json').write_text(json.dumps(dict(passed=True,source=ref(Path(__file__)),inputs=inputs,
  outputs=[ref(p),ref(output/'table.csv')]),indent=2)+'\n')
 print(json.dumps(dict(passed=True,results=ref(p),table=ref(output/'table.csv'),counts=value['counts'])))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--plan',type=Path,required=True);p.add_argument('--index',type=Path,nargs='+',required=True)
 p.add_argument('--output',type=Path,required=True);a=p.parse_args();export(a.plan,a.index,a.output)
