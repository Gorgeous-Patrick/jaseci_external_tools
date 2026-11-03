"""Portable sealed JDrive evidence, GIL/thread and numeric verifier. No DB/imports."""
import base64,gzip,hashlib,json,struct,tarfile
from collections import Counter
from pathlib import Path
from statistics import median
ROOT=Path(__file__).resolve().parent
BASE='/home/baichuan/jaseci/'
def sha(b):return hashlib.sha256(b).hexdigest()
def load(n):return json.loads((ROOT/n).read_text())
def safe(n):
 p=Path(n);assert not p.is_absolute() and '..' not in p.parts;return ROOT/p
def union(intervals):
 end=-1;total=0
 for a,b in sorted(intervals):assert b>=a;total+=max(0,b-max(a,end));end=max(end,b)
 return total
def main():
 inv=load('manifests/files.json');special={'manifests/files.json','package-integrity.json'}
 assert {str(p.relative_to(ROOT)) for p in ROOT.rglob('*') if p.is_file()}==set(inv)|special
 assert not any(p.is_symlink() for p in ROOT.rglob('*'))
 for n,r in inv.items():b=safe(n).read_bytes();assert len(b)==r['bytes'] and sha(b)==r['sha256'],n
 seal=load('package-integrity.json');assert seal['passed'] and sha((ROOT/'manifests/files.json').read_bytes())==seal['files_sha256']
 blobs={};cases={};archive_count=0
 for a in load('manifests/archives.json'):
  assert sha(safe(a['path']).read_bytes())==a['sha256'];wanted={r['member']:r for r in a['members']};seen={}
  with tarfile.open(safe(a['path']),'r:xz') as t:
   for member in t:
    assert member.isfile() and member.name in wanted and member.name not in seen
    m=wanted[member.name];data=t.extractfile(member).read();assert len(data)==m['bytes'] and sha(data)==m['sha256']
    seen[member.name]=data;blobs[(m['original'],m['sha256'])]=data
  assert set(seen)==set(wanted);s=json.loads(seen['artifacts.json']);assert s['passed'] and set(seen)==set(s['files'])|{'artifacts.json'}
  for n,h in s['files'].items():assert sha(seen[n])==h
  cases[a['case']]=seen;archive_count+=1
 for m in load('manifests/path-mapping.json'):
  key=(m['original'],m['sha256']);b=blobs[key] if 'member' in m else safe(m['package_path']).read_bytes();assert sha(b)==key[1];blobs[key]=b
 by_path={}
 for (p,h),b in blobs.items():by_path.setdefault(p,[]).append(b)
 def document(path):
  values=by_path[path];assert len(values)==1,path;return json.loads(values[0])
 def reference(r):return json.loads(blobs[(r['path'].removeprefix(BASE),r['sha256'])])
 external={(r['original'],r['sha256']):r['kind'] for r in load('manifests/external-runtime.json')}
 all_assertions=0;all_samples=0
 for run in load('manifests/runs.json'):
  prefix=run['prefix'];idx=document(prefix+'index.json');result=document(prefix+'results.json');assert idx['passed'] and idx['status']=='complete' and result['passed']
  assert sha(by_path[prefix+'index.json'][0])==result['index_sha256'];plan=reference(idx['plan']);assert len(idx['rows'])==8
  assert [{k:r[k] for k in plan['schedule'][0]} for r in idx['rows']]==plan['schedule']
  for path,h in reference(plan['sources'])['files'].items():
   key=(path.removeprefix(BASE),h)
   assert key in blobs or (path,h) in external,(path,h)
  samples=[];dbs=set();semantics=set();checks_total=0
  for row in idx['rows']:
   directory=str(Path(row['result']['raw']['path']).parent).removeprefix(BASE);raw=cases[directory]
   m=reference(row['result']['metrics']);p=reference(row['result']['proof']);a=reference(row['result']['acceptance']);g=reference(row['gil_proof'])
   assert all(v['passed'] for v in [m,p,a,g]);assert p['database'] not in dbs;dbs.add(p['database']);semantics.add((p['fixture_sha256'],p['actions_sha256'],p['output_sha256']))
   calls=[json.loads(l) for n,b in raw.items() if n.endswith('.calls.jsonl.gz') for l in gzip.decompress(b).splitlines() if l]
   checks=[json.loads(l) for n,b in raw.items() if n.startswith('gil-proof-') and n.endswith('.jsonl') for l in b.splitlines() if l]
   assert checks and all(c['gil_enabled'] is False and c['Py_GIL_DISABLED']==1 for c in checks)
   observed=Counter((c['pid'],c['thread_id'],c['server_generation'],c['origin_request_id']) for c in checks if c['kind']=='sql_boundary')
   expected=Counter((c['client_process_pid'],c['thread_id'],str(c['server_generation']),c.get('origin_request_id')) for c in calls)
   assert observed==expected and len(calls)==g['SQL_assertions'];checks_total+=len(calls)
   requests=[r for r in json.loads(raw['requests.json']) if r['phase']=='workflow'];assert len(requests)==7
   trees=[r['output'].get('data',r['output'])['reports'][0]['entries'] for r in requests if r['path'].split('/')[2]=='VisibleFolderTree'];assert [len(t) for t in trees]==run['tree_counts']
   keys={(str(r['server_generation']),r['request']) for r in requests};primary=[c for c in calls if (str(c['server_generation']),c.get('origin_request_id')) in keys and c.get('send_ns') is not None]
   assert all(c['error'] is None and c['database']==p['database'] for c in primary)
   intervals=[(c['send_ns'],c['ready_ns']) for c in primary];total=sum(b-a for a,b in intervals);u=union(intervals)
   assert (len(primary),total,u)==(m['primary']['sql_dispatches'],m['primary']['protocol_sum_ns'],m['primary']['protocol_union_ns'])
   fg=[c for c in primary if c['role']=='foreground'];bg=[c for c in primary if c['role']=='background_prefetch'];parents={c['client_process_pid'] for c in fg};assert len(parents)==1
   if row['config_id']=='off':assert not bg
   else:
    assert bg and all(c['actual_executor']=='thread' and c['client_process_pid'] in parents for c in bg)
    for c in bg:
     peers=[f for f in fg if (f['origin_request_id'],f['server_generation'])==(c['origin_request_id'],c['server_generation'])];assert peers and all(f['thread_id']!=c['thread_id'] and f['backend_pid']!=c['backend_pid'] for f in peers)
   if row['phase']=='measured':samples.append(dict(mode=row['config_id'],SQL=len(primary),DB_sum_ms=total/1e6,DB_union_ms=u/1e6,HTTP_sum_ms=sum(r['end_ns']-r['start_ns'] for r in requests)/1e6))
  assert len(dbs)==8 and len(semantics)==1 and checks_total==result['SQL_GIL_assertions_verified']
  life=document(prefix+'lifecycle.json');assert life['passed'] and life['PG_status']==3 and life['postmaster_pid_absent'] and life['retained_databases']==[]
  ownership=blobs[(life['ownership']['path'].removeprefix(BASE),life['ownership']['sha256'])]
  entries=[json.loads(l) for l in ownership.splitlines() if l];drops=[v for v in entries if v['action']=='successful_database_dropped'];assert {v['database'] for v in drops}==dbs and len(drops)==8 and all(v['active_sessions']==0 for v in drops)
  for mode in ['off','thread']:
   chosen=[s for s in samples if s['mode']==mode];assert len(chosen)==3
   for k in ['SQL','DB_sum_ms','DB_union_ms','HTTP_sum_ms']:
    vals=[s[k] for s in chosen];v=result['groups'][mode][k];assert vals==v['values'] and median(vals)==v['median'] and min(vals)==v['min'] and max(vals)==v['max']
  all_assertions+=checks_total;all_samples+=len(samples)
 diagnostics=0
 for a in load('manifests/archives.json'):
  if a['kind']!='diagnostic':continue
  raw=cases[a['case']];captures=[json.loads(b) for n,b in raw.items() if n.startswith('captures/') and n.endswith('.json')];assert len(captures)==1
  c=captures[0];wire=c['wire'];packet=base64.b64decode(wire['packet_base64'],validate=True);assert sha(packet)==wire['packet_sha256']
  pos=0;frames=[]
  while pos<len(packet):
   kind=packet[pos:pos+1];size=struct.unpack('!i',packet[pos+1:pos+5])[0];assert size>=4;frames.append((kind,packet[pos+5:pos+1+size]));pos+=1+size
  assert pos==len(packet) and [k for k,v in frames]==[b'P',b'B',b'D',b'E',b'S']
  assert frames[0][1].split(b'\0',2)[1].decode()==wire['positional_sql']==c['target']['sql']
  b=frames[1][1];assert b[:4]==b'\0\0\0\0';count=struct.unpack('!h',b[4:6])[0];pos=6;values=[]
  for i in range(count):
   size=struct.unpack('!i',b[pos:pos+4])[0];pos+=4;assert size>=-1;values.append(None if size==-1 else base64.b64encode(b[pos:pos+size]).decode());pos+=max(0,size)
  assert values==wire['parameters_base64'] and b[pos:]==b'\0\0'
  accept=json.loads(raw['diagnostic-acceptance.json']);assert accept['passed'] and accept['actual_call']['error'] is None and accept['actual_call']['returned_rows']==c['target']['returned_rows']
  assert c['explain']['actual_parameters_verified'] and len(c['explain']['repetitions'])==2
  for r in c['explain']['repetitions']:
   p=r['full_plan'][0];assert p['Planning Time']==r['planning_ms'] and p['Execution Time']==r['execution_ms'] and p['Plan']['Actual Rows']==c['target']['returned_rows']
  diagnostics+=1
 assert archive_count==27 and diagnostics==3 and all_samples==18
 print(f'PASS: 27 sealed archives; 24 fresh performance workflows (18 measured, 6 excluded); {all_assertions} SQL/GIL joins; all n3 SQL/DB/HTTP aggregates; 3 matched diagnostics/6 EXPLAIN plans; exact source inventory and declared external runtime references.')
if __name__=='__main__':main()
