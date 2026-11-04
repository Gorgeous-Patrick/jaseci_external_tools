"""Portable evidence, raw numeric, GIL-off and diagnostic verifier. Standard library only; no DB or original workspace reads."""
import base64,csv,gzip,hashlib,io,json,re,struct,tarfile
from collections import Counter,defaultdict
from pathlib import Path
from statistics import median
P=Path(__file__).resolve().parent;BASE='/home/baichuan/jaseci/'
def sha(b):return hashlib.sha256(b).hexdigest()
def load(n):return json.loads((P/n).read_text())
def safe(n):
 p=Path(n);assert not p.is_absolute() and '..' not in p.parts;return P/p
def union(xs):
 end=-1;total=0
 for a,b in sorted(xs):assert b>=a;total+=max(0,b-max(a,end));end=max(end,b)
 return total
def lines(raw,n):return [json.loads(l) for l in (gzip.decompress(raw[n]) if n.endswith('.gz') else raw[n]).splitlines() if l.strip()]
def kind(sql):
 m=re.match(r'\s*([A-Za-z]+)',sql);t=m.group(1).upper() if m else ''
 if t in {'BEGIN','START','SET','SAVEPOINT','RELEASE','DISCARD','COMMIT','END','ROLLBACK','ABORT','RESET','SHOW','DEALLOCATE','CLOSE'}:return 'control'
 if t in {'SELECT','WITH','INSERT','UPDATE','DELETE','MERGE','VALUES','FETCH'}:return 'data'
 return 'other'
def main():
 inv=load('manifests/files.json');assert {str(p.relative_to(P)) for p in P.rglob('*') if p.is_file()}==set(inv)|{'manifests/files.json','package-integrity.json'}
 assert not any(p.is_symlink() for p in P.rglob('*'))
 for n,r in inv.items():b=safe(n).read_bytes();assert len(b)==r['bytes'] and sha(b)==r['sha256'],n
 assert load('package-integrity.json')['files_sha256']==sha((P/'manifests/files.json').read_bytes())
 blobs={};cases={};descriptions=load('manifests/archives.json')
 for a in descriptions:
  assert sha(safe(a['path']).read_bytes())==a['sha256'];wanted={m['member']:m for m in a['members']};seen={}
  with tarfile.open(safe(a['path']),'r:xz') as tar:
   for m in tar:
    assert m.isfile() and m.name in wanted and m.name not in seen;safe(m.name)
    b=tar.extractfile(m).read();v=wanted[m.name];assert len(b)==v['bytes'] and sha(b)==v['sha256'];seen[m.name]=b;blobs[(v['original'],v['sha256'])]=b
  assert set(seen)==set(wanted);seal=json.loads(seen['artifacts.json']);assert seal['passed'] and set(seen)==set(seal['files'])|{'artifacts.json'}
  for n,h in seal['files'].items():assert sha(seen[n])==h
  cases[a['case']]=seen
 for m in load('manifests/path-mapping.json'):
  key=(m['original'],m['sha256']);b=blobs[key] if 'member' in m else safe(m['package_path']).read_bytes();assert sha(b)==key[1];blobs[key]=b
 bypath=defaultdict(list)
 for (n,h),b in blobs.items():bypath[n].append(b)
 def doc(n):assert len(bypath[n])==1,n;return json.loads(bypath[n][0])
 def ref(r):return json.loads(blobs[(r['path'].removeprefix(BASE),r['sha256'])])
 external={(r['original'],r['sha256']) for r in load('manifests/external-runtime.json')}
 # Every bound execution input is either packaged at its exact hash or explicitly an installed runtime/interpreter identity.
 for n in list(bypath):
  if n.endswith('/sources.json'):
   for path,h in doc(n)['files'].items():assert (path.removeprefix(BASE),h) in blobs or (path,h) in external,(path,h)
 scope=load('manifests/scope.json');prefix=scope['primary_prefix']+'/';idx=doc(prefix+'run-v1/index.json');result=doc(prefix+'results.json');plan=ref(idx['plan']);assert idx['passed'] and idx['source_after_passed'] and idx['status']=='complete';assert len(idx['rows'])==120
 assert [{k:r[k] for k in plan['schedule'][0]} for r in idx['rows']]==plan['schedule'];assert result['index_sha256']==sha(bypath[prefix+'run-v1/index.json'][0])
 dbs=set();semantics=defaultdict(set);samples=[];gil_total=0
 for row,sample in zip(idx['rows'],result['samples'],strict=True):
  refs=row['result'];m=ref(refs['metrics']);p=ref(refs['proof']);a=ref(refs['acceptance']);gil=ref(row['gil_proof']);assert all(x['passed'] for x in [m,p,a,gil]);assert p['database'] not in dbs;dbs.add(p['database']);semantics[row['app']].add(tuple(p[k] for k in ['fixture_sha256','actions_sha256','output_sha256']))
  raw=cases[str(Path(refs['raw']['path']).parent).removeprefix(BASE)];requests=[q for q in json.loads(raw['requests.json']) if q['phase']=='workflow'];keys={(str(q['server_generation']),q['request']) for q in requests};assert len(keys)==len(requests)
  calls=[v for n in raw if n.endswith('.calls.jsonl.gz') for v in lines(raw,n)];actual=[c for c in calls if (str(c['server_generation']),c.get('origin_request_id')) in keys and c.get('send_ns') is not None]
  assert all(c['error'] is None and c['database']==p['database'] for c in actual)
  intervals=[(c['send_ns'],c['ready_ns']) for c in actual];total=sum(b-a for a,b in intervals);u=union(intervals);counts=Counter(kind(c['sql']) for c in actual)
  assert (len(actual),total,u,counts['data'],counts['control'],counts['other'])==(m['primary']['sql_dispatches'],m['primary']['protocol_sum_ns'],m['primary']['protocol_union_ns'],m['primary']['sql_data'],m['primary']['sql_control'],m['primary']['sql_other'])
  checks=[v for n in raw if n.startswith('gil-proof-') and n.endswith('.jsonl') for v in lines(raw,n)];assert checks and all(v['gil_enabled'] is False and v['Py_GIL_DISABLED']==1 for v in checks)
  got=Counter((v['pid'],v['thread_id'],v['server_generation'],v['origin_request_id']) for v in checks if v['kind']=='sql_boundary');want=Counter((c['client_process_pid'],c['thread_id'],str(c['server_generation']),c.get('origin_request_id')) for c in calls);assert got==want and len(calls)==gil['SQL_assertions'];gil_total+=len(calls)
  fg=[c for c in actual if c['role']=='foreground'];bg=[c for c in actual if c['role']=='background_prefetch'];parents={c['client_process_pid'] for c in fg};assert len(parents)==1
  if row['config_id']=='off':assert not bg
  for c in bg:
   peers=[f for f in fg if (f['origin_request_id'],f['server_generation'])==(c['origin_request_id'],c['server_generation'])];assert peers and c['actual_executor']=='thread' and c['client_process_pid'] in parents and all(f['thread_id']!=c['thread_id'] and f['backend_pid']!=c['backend_pid'] for f in peers)
  overlaps=[]
  for b in bg:
   for f in fg:
    if (b['origin_request_id'],b['server_generation'])==(f['origin_request_id'],f['server_generation']):
     lo=max(b['send_ns'],f['send_ns']);hi=min(b['ready_ns'],f['ready_ns'])
     if hi>lo:overlaps.append((lo,hi))
  per=[];fingerprints={}
  for q in requests:
   cs=[c for c in actual if (str(c['server_generation']),c['origin_request_id'])==(str(q['server_generation']),q['request'])];fp={}
   assert q['post_response_drain']['pending']==0
   for c in cs:
    assert c['driver_start_ns']>=q['start_ns'] and c['send_ns']<=c['ready_ns']<=c['driver_end_ns']
    assert c['driver_end_ns']<=q['post_response_drain']['end_ns']
    h=sha(c['sql'].encode());fingerprints[h]=c['sql'];v=fp.setdefault(h,dict(count=0,ms=0,roles=[]));v['count']+=1;v['ms']+=(c['ready_ns']-c['send_ns'])/1e6
    if c['role'] not in v['roles']:v['roles'].append(c['role'])
   per.append(dict(walker=q['path'].split('/')[2],request=q['request'],generation=q['server_generation'],SQL=len(cs),DB_ms=sum(c['ready_ns']-c['send_ns'] for c in cs)/1e6,HTTP_ms=(q['end_ns']-q['start_ns'])/1e6,fingerprints=fp))
  assert per==sample['requests_detail'] and fingerprints==sample['fingerprint_SQL']
  rs=[q for q in per if q['walker']==sample['reader']];derived=dict(SQL=len(actual),data_SQL=counts['data'],control_SQL=counts['control'],DB_sum_ms=total/1e6,DB_union_ms=u/1e6,HTTP_sum_ms=sum(q['end_ns']-q['start_ns'] for q in requests)/1e6,requests=len(requests),background_SQL=len(bg),FG_BG_overlap_ms=union(overlaps)/1e6,reader_SQL=sum(q['SQL'] for q in rs),reader_DB_ms=sum(q['DB_ms'] for q in rs),reader_HTTP_ms=sum(q['HTTP_ms'] for q in rs),reader_requests=len(rs))
  assert all(sample[k]==v for k,v in derived.items());assert sample['app']==row['app'] and sample['mode']==row['config_id'] and sample['model_outcomes']==m['model_outcomes'];samples.append(sample)
 assert len(dbs)==120 and all(len(v)==1 for v in semantics.values()) and len(semantics)==15 and gil_total==result['SQL_GIL_assertions_verified']
 for app,modes in result['groups'].items():
  for mode,stats in modes.items():
   xs=[s for s in samples if s['app']==app and s['mode']==mode and s['phase']=='measured'];assert sorted(s['repeat'] for s in xs)==[0,1,2]
   for k,v in stats.items():vals=[s[k] for s in xs];assert v==dict(n=3,values=vals,median=median(vals),min=min(vals),max=max(vals)),(app,mode,k)
 drops=[json.loads(l) for l in bypath['reproduction/ttg-portfolio-v2-20261104/pg-v1/ownership-and-cleanup.jsonl'][0].splitlines() if l];assert drops[-1]['action']=='cluster_stopped' and not drops[-1]['retained_databases'];ds=[r for r in drops if r['action']=='successful_database_dropped'];assert len(ds)==120 and {d['database'] for d in ds}==dbs and all(d['active_sessions']==0 and d['owner']==idx['owner'] for d in ds)
 for row in csv.DictReader(io.StringIO(bypath[prefix+'table.csv'][0].decode())):
  g=result['groups'][row['application']][row['mode']];assert int(row['n'])==3
  for col,key in [('HTTP_median_ms','HTTP_sum_ms'),('DB_median_ms','DB_sum_ms'),('SQL_median','SQL')]:assert float(row[col])==g[key]['median']
 # CPU records: same-thread nonnegative nested partition; native source-bound diagnostics are separate from primary n3.
 cpu=doc(prefix+'cpu-boundaries.json');assert cpu['passed'] and len(cpu['profiles'])==22
 for r in cpu['profiles']:
  raw=ref(r['source']);assert raw['passed'];assert all(e['thread_id']==raw['thread_id'] and e['cpu_ns']>=e['exclusive_cpu_ns']>=0 for e in raw['events']);assert sum(e['exclusive_cpu_ns'] for e in raw['events'])==raw['thread_cpu_ns'];assert r['native_cpu_ms']==raw['thread_cpu_ns']/1e6
 # Exact diagnostic wire Bind and all sixteen full plans.
 captures=0
 for d in descriptions:
  if d['kind']!='sql_diagnostic':continue
  raw=cases[d['case']];accept=json.loads(raw['diagnostic-acceptance.json']);assert accept['passed']
  for entry in accept['selected']:
   c=ref(entry['capture']);packet=base64.b64decode(c['wire']['packet_base64'],validate=True);assert sha(packet)==c['wire']['packet_sha256'];pos=0;frames=[]
   while pos<len(packet):
    k=packet[pos:pos+1];sz=struct.unpack('!i',packet[pos+1:pos+5])[0];assert sz>=4;frames.append((k,packet[pos+5:pos+1+sz]));pos+=1+sz
   assert pos==len(packet) and [k for k,b in frames]==[b'P',b'B',b'D',b'E',b'S'];assert frames[0][1].split(b'\0',2)[1].decode()==c['wire']['positional_sql']==c['target']['sql']
   b=frames[1][1];assert b[:4]==b'\0\0\0\0';n=struct.unpack('!h',b[4:6])[0];pos=6;values=[]
   for i in range(n):
    size=struct.unpack('!i',b[pos:pos+4])[0];pos+=4;assert size>=-1;values.append(None if size==-1 else base64.b64encode(b[pos:pos+size]).decode());pos+=max(size,0)
   assert values==c['wire']['parameters_base64'] and b[pos:]==b'\0\0';assert entry['actual_call']['error'] is None and entry['actual_call']['returned_rows']==c['target']['returned_rows'];assert c['explain']['actual_parameters_verified'] and len(c['explain']['repetitions'])==2
   for x in c['explain']['repetitions']:
    p=x['full_plan'][0];assert p['Planning Time']==x['planning_ms'] and p['Execution Time']==x['execution_ms'] and p['Plan']['Actual Rows']==c['target']['returned_rows']
   captures+=1
 assert captures==8 and len(descriptions)==134
 report=doc(prefix+'slides-final/manifest.json');assert report['pages']==31
 for r in report['inputs'].values():assert (r['path'].removeprefix(BASE),r['sha256']) in blobs
 for r in report['outputs'].values():assert (r['path'].removeprefix(BASE),r['sha256']) in blobs
 print(json.dumps(dict(passed=True,archives=134,primary_workflows=120,measured=90,warmups=30,apps=15,cells_n3=30,SQL_GIL_joins=gil_total,direct_CPU_records=22,SQL_targets=8,EXPLAIN_plans=16,PDF_pages=31,original_workspace_access=False)))
if __name__=='__main__':main()
