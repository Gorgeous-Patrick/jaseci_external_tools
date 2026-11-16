"""Three ranked HTTP regressions: accepted derivatives only, no raw scan."""
import argparse,collections,hashlib,json,statistics
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
E=ROOT/'project-notes/measurements/ttg-background-pushdown-portfolio-performance-20261115'
def ref(p):
 p=Path(p).resolve();return dict(path=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest())
def read(p):return json.loads(Path(p).read_text())
def stats(v):return dict(n=len(v),values=v,median=statistics.median(v),min=min(v),max=max(v))
def build(output):
 output=Path(output);assert not output.exists()
 ip=E/'all30-inputs-v1/inputs.json';data=read(ip)
 cells={(c['app'],c['policy']):c for c in data['cells']}
 ranked=sorted((dict(app=a['app'],delta_HTTP_ms=cells[a['app'],'restored']['metrics']['HTTP_response_sum_ms']['median']-cells[a['app'],'off']['metrics']['HTTP_response_sum_ms']['median'])for a in data['apps']),key=lambda x:x['delta_HTTP_ms'],reverse=True)
 chosen=[r for r in ranked if r['delta_HTTP_ms']>0][:3]
 datasets={d['dataset']:d for d in data['datasets']};caches={};examples=[];consumed=[]
 for choice in chosen:
  app=choice['app'];records={};summaries={}
  for policy in ('off','conservative','restored'):
   cell=cells[app,policy];selected=sorted((s for s in data['samples']if s['app']==app and s['config_id']==policy and s['phase']=='measured'),key=lambda x:x['repeat'])
   ds=datasets[cell['dataset']];key=cell['dataset']
   if key not in caches:
    catalog_ref=ds['SQL_catalog'];raw=Path(catalog_ref['path']).read_bytes();assert hashlib.sha256(raw).hexdigest()==catalog_ref['sha256'];caches[key]=json.loads(raw)
   catalog=caches[key];trials=[]
   for sample in selected:
    r=sample['audit_derivative'];raw=Path(r['path']).read_bytes();assert hashlib.sha256(raw).hexdigest()==r['sha256'];d=json.loads(raw);consumed.append(r)
    assert d['trial_id']==sample['trial_id'] and d['config_id']==policy
    cats=collections.Counter();roles=collections.Counter();fp=collections.defaultdict(lambda:dict(count=0,ns=0))
    for rpc in d['RPCs']:
     for name,v in rpc['categories'].items():cats[name]+=v['sql_dispatches']
     for name,v in rpc['roles'].items():roles[name]+=v['sql_dispatches']
     for f in rpc['fingerprints']:
      target=fp[(f['fingerprint'],f['role'],f['category'])];target['count']+=f['sql_dispatches'];target['ns']+=f['protocol_sum_ns']
    assert sum(cats.values())==sum(roles.values())==d['total_SQL']
    cancelled=sum(any(e.get('native_event',{}).get('cancelled') is True for e in j['events']) for j in d['background_jobs'])
    native=collections.Counter();bg=collections.Counter()
    for e in d['native_work']:
     s=e['summary']
     for k in ('continuation_count','continuation_path_count','continuation_execution_count'):native[k]+=s.get(k,0)
     for k,v in s.get('fusion',{}).get('background_sql',{}).items():
      if isinstance(v,int) and not isinstance(v,bool):bg[k]+=v
    trials.append(dict(ref=r,data=d,categories=dict(cats),roles=dict(roles),fingerprints=fp,cancelled=cancelled,native=dict(native),background_counters=dict(bg)))
   records[policy]=trials
   catkeys=sorted({k for t in trials for k in t['categories']});rolekeys=sorted({k for t in trials for k in t['roles']})
   allfp={k for t in trials for k in t['fingerprints']};topfp=sorted(allfp,key=lambda k:sum(t['fingerprints'].get(k,{}).get('ns',0)for t in trials),reverse=True)[:5]
   fps=[dict(fingerprint=k[0],role=k[1],category=k[2],SQL_text=catalog[k[0]],SQL_count=stats([t['fingerprints'].get(k,{}).get('count',0)for t in trials]),protocol_ms=stats([t['fingerprints'].get(k,{}).get('ns',0)/1e6 for t in trials]))for k in topfp]
   rpc_count=len(trials[0]['data']['RPCs']);assert all(len(t['data']['RPCs'])==rpc_count for t in trials)
   rpc_rows=[]
   for i in range(rpc_count):
    rr=[t['data']['RPCs'][i]for t in trials];walkers=[r['path'].split('/')[2]for r in rr];assert len(set(walkers))==1
    rpc_rows.append(dict(ordinal=i+1,walker=walkers[0],request_ids=[r['request']for r in rr],HTTP_ms=stats([(r['end_ns']-r['start_ns'])/1e6 for r in rr]),DB_sum_ms=stats([r['protocol_sum_ns']/1e6 for r in rr]),DB_union_ms=stats([r['protocol_union_ns']/1e6 for r in rr]),data_SQL=stats([r['sql_data']for r in rr]),control_SQL=stats([r['sql_control']for r in rr]),TOTAL_SQL=stats([r['sql_dispatches']for r in rr]),categories={k:stats([r['categories'].get(k,{}).get('sql_dispatches',0)for r in rr])for k in sorted({k for r in rr for k in r['categories']})}))
   summaries[policy]=dict(primary_metrics=cell['metrics'],SQL_by_purpose={k:stats([t['categories'].get(k,0)for t in trials])for k in catkeys},SQL_by_role={k:stats([t['roles'].get(k,0)for t in trials])for k in rolekeys},jobs=stats([t['data']['pool_jobs']for t in trials]),jobs_with_explicit_cancelled_true=stats([t['cancelled']for t in trials]),tree_jobs=cell['metrics']['tree_jobs'],native_tree=cell['metrics']['native_tree'],native_scope_counter_sums={k:stats([t['native'].get(k,0)for t in trials])for k in sorted({k for t in trials for k in t['native']})},background_scope_counter_sums={k:stats([t['background_counters'].get(k,0)for t in trials])for k in sorted({k for t in trials for k in t['background_counters']})},top_protocol_fingerprints=fps,top_HTTP_RPCs=sorted(rpc_rows,key=lambda r:r['HTTP_ms']['median'],reverse=True)[:3],all_RPCs=rpc_rows,trial_derivatives=[t['ref']for t in trials])
  comparisons={}
  for baseline in ('off','conservative'):
   cats=sorted({k for policy in ('restored',baseline)for t in records[policy]for k in t['categories']})
   deltas={k:[records['restored'][i]['categories'].get(k,0)-records[baseline][i]['categories'].get(k,0)for i in range(5)]for k in cats}
   total=[records['restored'][i]['data']['total_SQL']-records[baseline][i]['data']['total_SQL']for i in range(5)]
   assert [sum(v[i]for v in deltas.values())for i in range(5)]==total
   comparisons[baseline]=dict(TOTAL_SQL_delta=stats(total),exact_per_repeat_purpose_deltas={k:stats(v)for k,v in deltas.items()},scope='Differences paired by declared repeat index for count decomposition; no causal CPU subtraction or pooled timing.')
  examples.append(dict(**choice,policies=summaries,restored_minus=comparisons))
 output.mkdir(parents=True)
 result=dict(passed=True,source=ref(Path(__file__)),accepted_inputs=ref(ip),selection='Three largest positive Restored-minus-Off median workflow HTTP differences among all30; examples only, all120 cells retained.',ranking=ranked,examples=examples,scope='Saved independent audit derivatives only. SQL categories are the inherited audit partition. Snapshot/setup remains within lexical data/control/TOTAL. Protocol sums and HTTP are distinct wall clocks; CPU unmeasured. Native counters sum observed outcome scopes; publications are not timely hits. Explicit-cancelled jobs and native stale counters are distinct.',consumed_derivatives=consumed,SQL_catalogs=[d['SQL_catalog']for d in datasets.values()if d['dataset']in caches])
 p=output/'purpose-examples.json';p.write_text(json.dumps(result,indent=2)+'\n')
 (output/'manifest.json').write_text(json.dumps(dict(passed=True,source=ref(Path(__file__)),inputs=ref(ip),output=ref(p)),indent=2)+'\n')
 print(json.dumps(dict(passed=True,output=ref(p),manifest=ref(output/'manifest.json'),apps=[x['app']for x in chosen],derivatives=len(consumed))),flush=True)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args();build(a.output)
