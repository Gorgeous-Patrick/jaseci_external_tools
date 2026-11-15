"""Separate precision pass: returned overlap, raw-promotion service and late rows.

Authoring only while primary runs. Never turns precision times into primary
latency samples. Session scope is joined to actual native-close nonces.
"""
import argparse,gzip,hashlib,json
from collections import defaultdict
from pathlib import Path
from postprocess_v1 import read,ref,checked

def ratio(n,d):return n/d if d else None
def classify_group(events):
 """One actual HTTP request/Session; no batch-start-as-readiness inference."""
 returned=[e for e in events if e['kind']=='precision_payload_returned']
 demands=[e for e in events if e['kind']=='precision_access' and not e['planning'] and e['role']=='foreground']
 promotions=[e for e in events if e['kind']=='precision_promotion' and not e['planning'] and e['role']=='foreground']
 P={e['uid'] for e in returned};D=set();Dnodes=set();Pnodes=set();by_demand=defaultdict(list)
 for e in returned:
  if e['anchor_kind'] in ('NodeAnchor','RootAnchor'):Pnodes.add(e['uid'])
 for e in demands:
  assert len(e['ids'])==len(e['kinds']) and e['started_ns']<=e['timestamp_ns']
  for uid,kind in zip(e['ids'],e['kinds']):
   D.add(uid);by_demand[uid].append(e)
   if kind in ('NodeAnchor','RootAnchor'):Dnodes.add(uid)
 # A returned row's explicit node kind is also identity evidence when a
 # successful-demand wrapper reports a generic Anchor class name.
 Dnodes.update(D&Pnodes)
 delivered=defaultdict(list)
 for e in returned:delivered[e['uid']].append(e)
 served=set();return_before_call=set();after_return=set();witness=[]
 for uid in P&D:
  for demand in by_demand[uid]:
   if any(r['timestamp_ns']<=demand['timestamp_ns'] for r in delivered[uid]):after_return.add(uid)
 for promotion in promotions:
  uid=promotion['uid'];t=promotion['timestamp_ns']
  prior=[e for e in delivered[uid] if e['timestamp_ns']<=t and not e['already_materialized']]
  calls=[e for e in by_demand[uid] if e['started_ns']<=t<=e['timestamp_ns']]
  if not prior or not calls:continue
  served.add(uid)
  if any(r['timestamp_ns']<=d['started_ns'] for r in prior for d in calls):return_before_call.add(uid)
  witness.append(dict(uid=uid,returned=prior[0]['_ref'],promotion=promotion['_ref'],demand=calls[0]['_ref']))
 return dict(returned_unique=len(P),successful_demand_unique=len(D),returned_demand_intersection=len(P&D),
  post_return_successful_demand_overlap=len(after_return),raw_promotion_served_unique=len(served),
  served_return_before_demand_call_unique=len(return_before_call),unused_returned_unique=len(P-D),
  actual_row_deliveries=len(returned),repeated_row_deliveries=len(returned)-len(P),
  already_materialized_late_deliveries=sum(e['already_materialized'] for e in returned),
  returned_node_unique=len(Pnodes),successful_demand_node_unique=len(Dnodes),
  confirmed_unused_node_prefetch_lower_bound=len(Pnodes-Dnodes),
  overlap_coverage=ratio(len(P&D),len(D)),promotion_service_coverage=ratio(len(served),len(D)),
  returned_demand_fraction=ratio(len(P&D),len(P)),promotion_served_fraction=ratio(len(served),len(P)),
  returned_ids=sorted(P),demanded_ids=sorted(D),promotion_served_ids=sorted(served),unused_ids=sorted(P-D),
  unused_node_ids=sorted(Pnodes-Dnodes),service_witnesses=witness)

def load_events(directory,seal,keys):
 paths=sorted(directory.glob('server-*.events.jsonl*'));bases=set();events=[];inputs=[];installed=False
 for path in paths:
  base=path.name.removesuffix('.gz');assert base not in bases,'Duplicate raw/gzip '+base;bases.add(base)
  assert path.name in seal['files'] and ref(path)['sha256']==seal['files'][path.name],'Unsealed/corrupt event file'
  inputs.append(ref(path));opener=gzip.open if path.suffix=='.gz' else open
  with opener(path,'rb') as f:
   for number,line in enumerate(f,1):
    if not line.strip():continue
    e=json.loads(line)
    if e['kind']=='precision_observer_installed':installed=True
    if (str(e['server_generation']),e.get('origin_request_id')) not in keys:continue
    if e['kind'].startswith('precision_') or e['kind']=='native_context_close':
     e['_ref']=dict(path=str(path),line=number,record_sha256=hashlib.sha256(line).hexdigest());events.append(e)
 assert installed,'Precision observer absent'
 return events,inputs

def export(index_path,output):
 index_path=Path(index_path).resolve();output=Path(output).resolve();assert not output.exists()
 index=read(index_path);assert index['passed'] and index['status']=='complete' and index['stage']=='precision'
 plan=read(checked(index['plan']));assert len(index['rows'])==len(plan['stages']['precision'])
 samples=[];inputs=[ref(index_path),index['plan'],ref(Path(__file__)),ref(Path(__file__).with_name('postprocess_v1.py'))]
 additive=('returned_unique','successful_demand_unique','returned_demand_intersection','post_return_successful_demand_overlap',
  'raw_promotion_served_unique','served_return_before_demand_call_unique','unused_returned_unique',
  'actual_row_deliveries','repeated_row_deliveries','already_materialized_late_deliveries',
  'returned_node_unique','successful_demand_node_unique','confirmed_unused_node_prefetch_lower_bound')
 for row,wanted in zip(index['rows'],plan['stages']['precision']):
  assert row['passed'] and all(row[k]==v for k,v in wanted.items())
  metric=read(checked(row['result']['metrics']));proof=read(checked(row['result']['proof']))
  acceptance=read(checked(row['result']['acceptance']));gil=read(checked(row['gil_proof']))
  assert metric['passed'] and proof['passed'] and acceptance['passed'] and gil['passed']
  assert acceptance['semantic']['passed'] and acceptance['database_state']['matches_sealed_final_graph']
  assert acceptance['semantic_proof']==row['result']['proof'] and metric['independent_acceptance']==row['result']['acceptance']
  assert metric['raw_seal']==acceptance['raw_seal']
  inputs.extend(row['result'].values());inputs.append(row['gil_proof'])
  directory=checked(row['result']['raw']).parent;seal=read(directory/'artifacts.json')
  hp=directory/'requests.json';assert ref(hp)['sha256']==seal['files']['requests.json'];inputs.append(ref(hp))
  requests=[r for r in read(hp) if r['phase']=='workflow'];keys={(str(r['server_generation']),r['request']) for r in requests}
  events,refs=load_events(directory,seal,keys);inputs.extend(refs)
  closes=defaultdict(set)
  for e in events:
   if e['kind']=='native_context_close':
    assert e['natural_close_completed']
    closes[e['client_process_pid'],str(e['server_generation']),e['origin_request_id'],e['session_object_id']].add(e['session_nonce'])
  groups=defaultdict(list);batches={};ends={};entries=defaultdict(set)
  for e in events:
   if e['kind']=='precision_osp_entry':entries[str(e['server_generation']),e['origin_request_id']].add(e['uid'])
   if e['kind']=='precision_prefetch_batch':batches[e['batch']]=e
   if e['kind']=='precision_prefetch_batch_end':ends[e['batch']]=e
   if 'session' not in e:continue
   key=(e['client_process_pid'],str(e['server_generation']),e['origin_request_id'],e['session'])
   assert len(closes[key])==1,'Ambiguous/missing actual Session nonce; preserve and investigate'
   scoped=key[:3]+(next(iter(closes[key])),);groups[scoped].append(e)
  assert batches.keys()==ends.keys()
  for e in events:
   if e['kind']!='precision_payload_returned':continue
   start=batches[e['batch']];end=ends[e['batch']]
   assert e['uid'] in start['ids'] and start['session']==e['session']==end['session']
   assert start['timestamp_ns']<=e['timestamp_ns']<=end['timestamp_ns']
  details=[dict(scope=list(k),**classify_group(v)) for k,v in groups.items()]
  totals={field:sum(g[field] for g in details) for field in additive}
  if row['config_id']=='off':assert totals['returned_unique']==0 and not batches
  totals.update(overlap_coverage=ratio(totals['returned_demand_intersection'],totals['successful_demand_unique']),
   promotion_service_coverage=ratio(totals['raw_promotion_served_unique'],totals['successful_demand_unique']),
   returned_demand_fraction=ratio(totals['returned_demand_intersection'],totals['returned_unique']),
   promotion_served_fraction=ratio(totals['raw_promotion_served_unique'],totals['returned_unique']))
  samples.append(dict(**{k:row[k] for k in ('trial_id','case_id','app','scale','config_id','repeat')},
   n=1,references=row['result'],business_requests=len(requests),Session_scopes=len(details),
   native_OSP_unique_per_request=sum(len(v) for v in entries.values()),groups=details,**totals))
 output.mkdir();p=output/'results.json'
 value=dict(passed=True,source=ref(Path(__file__)),inputs=inputs,samples=samples,
  definitions=dict(unit='Unique IDs per actual HTTP request and native Session nonce, summed over workflow; delivery rows also separate.',
   demand='Successful foreground Session.get/batch_get outside recorded planning scope, including memory hits/root; Access is separate from OSP entry.',
   returned_overlap='P intersection D irrespective of timing; not by itself a timely prefetch hit.',
   service='Successful nonplanning foreground raw promotion inside a successful demand-call interval, after a non-discarded payload return of the same ID/Session.',
   before_call='Payload-return callback precedes demand start, with later promotion-backed service; not an exact cache-insertion/readiness timestamp.',
   late='Already materialized at actual return callback; retained independently from overlap and unused counts.',
   white_reads='Confirmed unused returned NodeAnchor IDs Pnode minus observed successful Dnode; a lower bound. Source-validated disjoint filter-only candidates require a separate audit. _owns/jid ID reads remain valid demand.',
   denominators='Empty denominators are null/N/A. Off returned=0 is a valid cell. Counts have n1 precision capture and are not n5 latency samples.',
   latency='Precision pass wall/DB times are not pooled into the instrumented primary latency dataset.'))
 p.write_text(json.dumps(value,indent=2)+'\n')
 (output/'artifacts.json').write_text(json.dumps(dict(passed=True,source=ref(Path(__file__)),inputs=inputs,output=ref(p)),indent=2)+'\n')
 print(json.dumps(dict(passed=True,result=ref(p),samples=len(samples))))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--index',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
 a=p.parse_args();export(a.index,a.output)
