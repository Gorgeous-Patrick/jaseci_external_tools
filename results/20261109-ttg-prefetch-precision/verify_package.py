"""Standard-library portable hashes, raw counts, GIL and precision verification. No DB."""
from collections import Counter,defaultdict
import csv,gzip,hashlib,io,json,re,runpy,tarfile
from pathlib import Path
from statistics import median
P=Path(__file__).resolve().parent;BASE='/home/baichuan/jaseci/'
def sha(b):return hashlib.sha256(b).hexdigest()
def load(n):return json.loads((P/n).read_text())
def safe(n):
 p=Path(n);assert not p.is_absolute() and '..' not in p.parts;return P/p
def lines(b,n):return [json.loads(l) for l in (gzip.decompress(b) if n.endswith('.gz') else b).splitlines() if l.strip()]
def union(xs):
 end=-1;total=0
 for a,b in sorted(xs):assert b>=a;total+=max(0,b-max(a,end));end=max(end,b)
 return total
def kind(s):
 k=re.match(r'\s*([A-Za-z]+)',s).group(1).upper()
 if k in {'BEGIN','START','SET','SAVEPOINT','RELEASE','DISCARD','COMMIT','END','ROLLBACK','ABORT','RESET','SHOW','DEALLOCATE','CLOSE'}:return 'control'
 if k in {'SELECT','WITH','INSERT','UPDATE','DELETE','MERGE','VALUES','FETCH'}:return 'data'
 return 'other'
def main():
 inv=load('manifests/files.json');assert {str(p.relative_to(P)) for p in P.rglob('*') if p.is_file()}==set(inv)|{'manifests/files.json','package-integrity.json'}
 assert not any(p.is_symlink() for p in P.rglob('*'))
 for n,x in inv.items():b=safe(n).read_bytes();assert len(b)==x['bytes'] and sha(b)==x['sha256'],n
 assert load('package-integrity.json')['files_sha256']==sha((P/'manifests/files.json').read_bytes())
 blobs={};cases={};desc=load('manifests/archives.json');assert len(desc)==32
 for a in desc:
  assert sha(safe(a['path']).read_bytes())==a['sha256'];wanted={m['member']:m for m in a['members']};seen={}
  with tarfile.open(safe(a['path']),'r:xz') as tar:
   for m in tar:
    assert m.isfile() and m.name in wanted and m.name not in seen;safe(m.name);b=tar.extractfile(m).read();v=wanted[m.name];assert len(b)==v['bytes'] and sha(b)==v['sha256'];seen[m.name]=b;blobs[(v['original'],v['sha256'])]=b
  assert set(seen)==set(wanted);seal=json.loads(seen['artifacts.json']);assert seal['passed'] and set(seen)==set(seal['files'])|{'artifacts.json'}
  for n,h in seal['files'].items():assert sha(seen[n])==h
  cases[a['case']]=seen
 for m in load('manifests/path-mapping.json'):
  key=(m['original'],m['sha256']);b=blobs[key] if 'member' in m else safe(m['package_path']).read_bytes();assert sha(b)==key[1];blobs[key]=b
 def doc(n):
  b=[v for (path,h),v in blobs.items() if path==n];assert len(b)==1,n;return json.loads(b[0])
 def ref(r):return json.loads(blobs[(r['path'].removeprefix(BASE),r['sha256'])])
 external={(r['original'],r['sha256']) for r in load('manifests/external-runtime.json')}
 for path,h in list(blobs):
  if path.endswith('/sources.json'):
   for n,wanted in json.loads(blobs[(path,h)])['files'].items():assert (n.removeprefix(BASE),wanted) in blobs or (n,wanted) in external,(n,wanted)
 precision_path='workspace/project-notes/measurements/ttg-overfetch-comparison-20261109/analyze.py'
 request_result=runpy.run_path(str(P/precision_path))['request_result']
 sql_total=0
 for run in load('manifests/scope.json')['runs']:
  prefix=run['prefix'];idx=doc(prefix+'/run-v1/index.json');plan=ref(idx['plan']);result=doc(prefix+'/results.json');stop=doc(prefix+'/stopped.json');assert idx['passed'] and idx['source_after_passed'] and idx['status']=='complete' and len(idx['rows'])==16
  assert stop['passed'] and stop['live_recorded_pids']==[] and stop['pg_status']==3 and stop['owned_successful_drops']==16
  assert result['index']['sha256']==sha(blobs[(prefix+'/run-v1/index.json',result['index']['sha256'])])
  dbs=set();semantics=defaultdict(set);precision='overfetch' in run['name']
  for row,wanted,sample in zip(idx['rows'],plan['schedule'],result['samples'],strict=True):
   assert row['passed'] and all(row[k]==v for k,v in wanted.items())
   m=ref(row['result']['metrics']);proof=ref(row['result']['proof']);acc=ref(row['result']['acceptance']);gil=ref(row['gil_proof']);assert all(x['passed'] for x in (m,proof,acc,gil))
   assert proof['database'] not in dbs;dbs.add(proof['database']);semantics[row['app']].add(tuple(proof[k] for k in ('fixture_sha256','actions_sha256','output_sha256')))
   case=str(Path(row['result']['raw']['path']).parent).removeprefix(BASE);raw=cases[case];requests=[r for _,r in enumerate(lines(raw['http-raw.jsonl'],'http-raw.jsonl')) if r['phase']=='workflow'];keys={(str(r['server_generation']),r['request']) for r in requests}
   calls=[c for n,b in raw.items() if n.endswith('.calls.jsonl.gz') for c in lines(b,n)];actual=[c for c in calls if (str(c['server_generation']),c.get('origin_request_id')) in keys and c['send_ns'] is not None]
   checks=[r for n,b in raw.items() if n.startswith('gil-proof-') and n.endswith('.jsonl') for r in lines(b,n)]
   assert checks and all(r['gil_enabled'] is False and r['Py_GIL_DISABLED']==1 for r in checks)
   assert Counter((r['pid'],r['thread_id'],r['server_generation'],r['origin_request_id']) for r in checks if r['kind']=='sql_boundary')==Counter((c['client_process_pid'],c['thread_id'],str(c['server_generation']),c.get('origin_request_id')) for c in calls)
   sql_total+=len(calls);assert len(calls)==gil['SQL_assertions']
   times=[(c['send_ns'],c['ready_ns']) for c in actual];counts=Counter(kind(c['sql']) for c in actual);primary=m['primary']
   assert (len(actual),sum(b-a for a,b in times),union(times),counts['data'],counts['control'])==(primary['sql_dispatches'],primary['protocol_sum_ns'],primary['protocol_union_ns'],primary['sql_data'],primary['sql_control'])
   assert all(c['error'] is None and c['database']==proof['database'] for c in actual)
   if not precision:
    assert sample['http_ms']==sum(r['end_ns']-r['start_ns'] for r in requests)/1e6
    for key,n in [('db_sum_ms','protocol_sum_ns'),('db_union_ms','protocol_union_ns')]:assert sample[key]==primary[n]/1e6
    for key,n in [('data_sql','sql_data'),('control_sql','sql_control'),('total_sql','sql_dispatches'),('http_requests','HTTP_requests')]:assert sample[key]==primary[n]
   else:
    mapping={v.replace('-',''):k for k,v in json.loads(raw['mapping-initial.json']).items()};events=defaultdict(list)
    for n,b in raw.items():
     if not n.endswith('.events.jsonl.gz'):continue
     for number,line in enumerate(gzip.decompress(b).splitlines(),1):
      if not line.strip():continue
      e=json.loads(line);key=(str(e['server_generation']),e.get('origin_request_id'))
      if key in keys and e['kind'].startswith('precision_'):
       e['_ref']=dict(path=BASE+case+'/'+n,sha256=sha(b),line=number);events[key].append(e)
    derived=[]
    for r in requests:
     values=request_result(events[(str(r['server_generation']),r['request'])],mapping)
     derived.append(dict(request=r['request'],walker=r['path'].split('/')[2],**values))
    assert derived==sample['requests']
    for key,v in sample.items():
     if key in derived[0] and isinstance(v,(int,float)) and key!='unused_rate':assert v==sum(r[key] for r in derived)
    assert sample['unused_rate']==sample['unused_payload_objects']/sample['payload_objects']
  assert len(dbs)==16 and all(len(s)==1 for s in semantics.values())
  for group in result['groups']:
   ss=[s for s in result['samples'] if s['app']==group['app'] and s['mode']==group['mode'] and s['phase']=='measured'];assert sorted(s['repeat'] for s in ss)==[0,1,2]
   for k,v in group.items():
    if not isinstance(v,dict):continue
    vals=[s[k] for s in ss];assert v['values']==vals and v['median']==median(vals)
    if 'min' in v:assert v['min']==min(vals) and v['max']==max(vals)
  for row in csv.DictReader(io.StringIO(blobs[(prefix+'/table.csv',next(h for (n,h) in blobs if n==prefix+'/table.csv'))].decode())):
   group=next(g for g in result['groups'] if g['app']==row['app'] and g['mode']==row['mode']);assert int(row['n'])==3
   for k,v in row.items():
    if k not in ('app','mode','n'):assert float(v)==group[k]['median']
  log='reproduction/'+run['name']+'/pg-v1/ownership-and-cleanup.jsonl';records=[json.loads(x) for x in next(b for (n,h),b in blobs.items() if n==log).splitlines() if x]
  assert records[-1]['action']=='cluster_stopped' and records[-1]['retained_databases']==[]
  drops=[r for r in records if r['action']=='successful_database_dropped'];assert len(drops)==16 and {r['database'] for r in drops}==dbs and all(r['active_sessions']==0 for r in drops)
 print(json.dumps(dict(passed=True,archives=32,workflows=32,measured=24,warmups=8,SQL_GIL_records=sql_total,raw_precision_recomputed=True,original_workspace_reads=False)))
if __name__=='__main__':main()
