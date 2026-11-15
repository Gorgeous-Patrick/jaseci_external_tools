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
def lineage_indexes(plan_path,index_paths):
 plan=read(plan_path);line=plan['lineage']
 assert plan['kind']=='ttg-expanded-performance-20261112-v2-lineage'
 old=read(checked(line['original_plan']))
 assert plan['sources']==old['sources'] and plan['configs']==old['configs'] and plan['runtimes']==old['runtimes']
 assert plan['stages']['extend-n5']==[r for r in old['stages']['extend-n5'] if r['case_id']!='linked_list-1000']
 assert len(plan['stages']['extend-n5'])==114
 proof=read(checked(line['failed_stage_preservation']))
 assert proof['passed'] and proof['source_postcheck']['passed'] and not proof['source_postcheck']['mismatches']
 assert proof['source_manifest']==plan['sources'] and proof['report_inventory']==line['excluded_cells']
 assert proof['pg_status']==3 and not proof['postmaster_pid_exists'] and len(proof['retained_databases'])==1
 assert line['excluded_cells']==[dict(case_id='linked_list-1000',config_id=m,status=t) for m,t in zip(
  ('off','aggressive','conservative'),('correctness_only','failed_isolation_gate','not_run_after_first_failure'))]
 prefixes=line['accepted_prefixes'];assert len(prefixes)==3
 assert [(p['start'],p['end'],p['status']) for p in prefixes]==[(0,45,'complete'),(0,210,'complete'),(0,30,'accepted_prefix_of_failed_stage')]
 supplied=[Path(p).resolve() for p in index_paths]
 assert len(supplied)==4 and len(set(supplied))==4
 required=[checked(p['index']).resolve() for p in prefixes]
 assert set(required).issubset(supplied)
 remaining=[p for p in supplied if p not in required];assert len(remaining)==1
 selected=[]
 for pos,(entry,ip) in enumerate(zip(prefixes,required)):
  index=read(ip);assert index['plan']==line['original_plan']
  stage=('first','small-rest','larger')[pos];assert index['stage']==stage
  if pos<2:
   assert index['status']=='complete' and index['passed'] and index['source_after_passed']
   assert len(index['rows'])==entry['end']
  else:
   assert entry['index']==line['failed_index']==proof['index']
   assert index['status']=='failed' and not index['passed'] and len(index['rows'])==31
   assert index['rows'][30]['trial_id']==line['correctness_only_extra_row']
   assert all(index['rows'][30][k]==v for k,v in old['stages']['larger'][30].items())
  selected.append((ip,index,index['rows'][:entry['end']],old['stages'][stage][:entry['end']]))
 ip=remaining[0];index=read(ip)
 assert index['plan']==ref(plan_path) and index['stage']=='extend-n5'
 assert index['status']=='complete' and index['passed'] and index['source_after_passed']
 assert len(index['rows'])==114
 selected.append((ip,index,index['rows'],plan['stages']['extend-n5']))
 assert sum(len(rows) for _,_,rows,_ in selected)==399
 return selected

def export(plan_path,index_paths,output):
 plan_path=Path(plan_path).resolve();plan=read(plan_path);output=Path(output).resolve();assert not output.exists()
 inputs=[ref(plan_path),ref(Path(__file__))];samples=[];seen_trials=set();seen_databases=set();baseline={}
 inputs.extend([plan['lineage']['original_plan'],plan['lineage']['failed_stage_preservation'],plan['controller'],plan['lineage_validator']])
 for ip,index,selected_rows,expected in lineage_indexes(plan_path,index_paths):
  inputs.append(ref(ip))
  assert len(selected_rows)==len(expected)
  for row,wanted in zip(selected_rows,expected):
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
 inventory=[dict(case_id=r['case_id'],config_id=r['config_id']) for r in read(checked(plan['lineage']['original_plan']))['stages']['precision']]
 assert len(rows)==57 and all(r['n']==5 for r in rows)
 assert len(samples)==399 and sum(s['phase']=='measured' for s in samples)==285
 terminal={(r['case_id'],r['config_id']):r for r in plan['lineage']['excluded_cells']}
 completed={(r['case_id'],r['config_id']) for r in rows}
 output.mkdir(parents=True)
 value=dict(passed=True,inputs=inputs,source=ref(Path(__file__)),plan=ref(plan_path),rows=rows,samples=samples,
  counts=dict(captured=len(samples),correctness=sum(s['phase']=='correctness' for s in samples),
   excluded_warmups=sum(s['phase']=='excluded_warmup' for s in samples),measured=sum(s['phase']=='measured' for s in samples),
   measured_cells=len(rows)),lineage=plan['lineage'],inventory=[dict(**r,completed=(r['case_id'],r['config_id']) in completed,
   status=terminal.get((r['case_id'],r['config_id']),{}).get('status','completed_n5'),
   terminal_evidence=plan['lineage']['failed_stage_preservation'] if (r['case_id'],r['config_id']) in terminal else None) for r in inventory],
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
