from pathlib import Path
import hashlib,json,shutil,tarfile,subprocess
R=Path('/home/baichuan/jaseci');P=R/'jaseci_external_tools/results/20261103-jdrive-gil-off';E=R/'project-notes/measurements/ttg-jdrive-freethreaded-20261103';D=R/'project-notes/measurements/ttg-jdrive-access-20261103'
assert not P.exists();(P/'manifests').mkdir(parents=True)
mapping=[];known=set();archives=[];external={};runs=[]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text())
def copy(p,wanted=None):
 p=Path(p);original=str(p.relative_to(R));h=wanted or sha(p);key=(original,h)
 if key in known:return
 source=p
 if sha(p)!=h:
  assert p.is_relative_to(R/'jac-ttg'),p
  relative=p.relative_to(R/'jac-ttg')
  source=next(c for c in [R/'reproduction/ttg-jdrive-access/runtime-clean-v1'/relative,R/'reproduction/ttg-jdrive-access/runtime-clean-v2'/relative] if c.exists() and sha(c)==h)
 destination='workspace/'+original
 if (P/destination).exists() and sha(P/destination)!=h:destination='source-versions/'+h+'/'+p.name
 target=P/destination;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target);assert sha(target)==h
 mapping.append(dict(original=original,package_path=destination,sha256=h));known.add(key)
def external_kind(path):
 parts=Path(path).parts
 if '/ttg-littlex-freethreaded/python/' in path:return 'external_free_threaded_python'
 if any(v.startswith('runtime-') for v in parts):return 'external_runtime_snapshot'
 return None
def archive(case,label,kind):
 seal=read(case/'artifacts.json');assert seal['passed'];names=sorted(set(seal['files'])|{'artifacts.json'})
 assert {str(f.relative_to(case)) for f in case.rglob('*') if f.is_file()}==set(names)
 dest='raw/'+label+'.tar.xz';a=P/dest;a.parent.mkdir(exist_ok=True);members=[]
 with tarfile.open(a,'w:xz',preset=3) as t:
  for n in names:
   f=case/n;h=sha(f)
   if n!='artifacts.json':assert seal['files'][n]==h
   info=t.gettarinfo(str(f),arcname=n);info.uid=info.gid=0;info.uname=info.gname='';info.mtime=0
   with f.open('rb') as data:t.addfile(info,data)
   entry=dict(original=str(f.relative_to(R)),package_path=dest,member=n,sha256=h,bytes=f.stat().st_size);members.append(entry);mapping.append(entry);known.add((entry['original'],h))
 archives.append(dict(path=dest,sha256=sha(a),case=str(case.relative_to(R)),kind=kind,members=members))
for run in ['comparison-access-v2','comparison-access-v3','comparison-small-v1']:
 d=E/run;x=read(d/'index.json');assert x['passed'] and x['status']=='complete' and len(x['rows'])==8
 result=read(d/'results.json');assert result['passed'];runs.append(dict(name=run,prefix=str(d.relative_to(R))+'/',initial_folders=364 if run=='comparison-small-v1' else 40,initial_files=121 if run=='comparison-small-v1' else 13,tree_counts=[116,72,73] if run=='comparison-small-v1' else [19,11,12]))
 for folder in [d,d/'metrics',d/'acceptances']:
  for f in folder.iterdir():
   if f.is_file():copy(f)
 for path,h in read(d/'sources.json')['files'].items():
  kind=external_kind(path)
  if kind:external[(path,h)]=dict(original=path,sha256=h,kind=kind);continue
  copy(path,h)
 for key in ['clean','overlay']:
  m=read(d/'plan.json')[key];copy(m['path'])
 for row in x['rows']:archive(Path(row['result']['raw']['path']).parent,run+'--'+row['trial_id'],'primary_capture')
 cluster=R/'reproduction/ttg-jdrive-freethreaded'/({'comparison-access-v2':'pg-access-v2','comparison-access-v3':'pg-access-v3','comparison-small-v1':'pg-small-v1'}[run])
 for n in ['owner.json','ownership-and-cleanup.jsonl']:copy(cluster/n)
for run in ['sql-diagnostic-v1','sql-diagnostic-v2']:
 d=E/run;assert read(d/'result.json')['passed']
 for folder in [d,d/'metrics',d/'acceptances']:
  for f in folder.iterdir():
   if f.is_file():copy(f)
 for row in read(d/'result.json')['rows']:archive(Path(row['result']['raw']['path']).parent,run+'--'+row['mode'],'diagnostic')
 cluster=R/'reproduction/ttg-jdrive-freethreaded'/('pg-'+run)
 for n in ['owner.json','ownership-and-cleanup.jsonl']:copy(cluster/n)
for f in D.iterdir():
 if f.is_file() and f.suffix in ('.json','.py','.log','.sql'):copy(f)
for name in ['native-final-v2','native-sql-v2']:
 for f in (D/name).iterdir():
  if f.is_file():copy(f)
for f in (R/'reproduction/ttg-jdrive-sql-diagnostic').glob('*.py'):copy(f)
for f in (R/'reproduction/ttg-jdrive-sql-diagnostic').glob('selection*.json'):copy(f)
for name in ['verification.json','verification-sql-v2.json']:
 for path,h in read(D/name)['sources'].items():copy(R/'jac-ttg'/path,h)
for n in ['interpreter-assertions.json']:
 copy(R/'project-notes/measurements/ttg-littlex-freethreaded-20261102'/n)
for path in [R/'reproduction/ttg-jdrive-access/freeze.py',R/'reproduction/ttg-jdrive-access/freeze_sql_v2.py']:copy(path)
(P/'manifests/path-mapping.json').write_text(json.dumps(mapping,indent=2)+'\n')
(P/'manifests/archives.json').write_text(json.dumps(archives,indent=2)+'\n')
(P/'manifests/external-runtime.json').write_text(json.dumps(list(external.values()),indent=2)+'\n')
(P/'manifests/runs.json').write_text(json.dumps(runs,indent=2)+'\n')
shutil.copyfile(__file__,P/'build_package.py')
print(json.dumps(dict(files=len(mapping),archives=len(archives),bytes=sum(f.stat().st_size for f in P.rglob('*') if f.is_file()))))
