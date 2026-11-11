"""Package the accepted comparison and its slides; no runtime or DB changes."""
from pathlib import Path
import hashlib,io,json,shutil,tarfile
R=Path('/home/baichuan/jaseci')
E=R/'project-notes/measurements/ttg-access-visit-performance-20261110'
P=R/'jaseci_external_tools/results/20261110-ttg-access-visit-comparison'
assert not P.exists();(P/'manifests').mkdir(parents=True)
mapping={}; archives=[]; external=[]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_text())
def copy(p,expected=None,dest=None):
 p=Path(p).resolve();h=sha(p)
 assert expected is None or expected==h,(p,expected,h)
 key=str(p)
 if key in mapping:
  assert mapping[key]['sha256']==h
  return
 dest=dest or 'workspace/'+str(p.relative_to(R));q=P/dest;q.parent.mkdir(parents=True,exist_ok=True)
 shutil.copyfile(p,q);mapping[key]=dict(path=dest,sha256=h)
def archive(row):
 case=Path(row['result']['raw']['path']).parent;seal=read(case/'artifacts.json')
 assert seal['passed'] and sha(case/'artifacts.json')==row['result']['raw']['sha256']
 names=sorted(set(seal['files'])|{'artifacts.json'})
 dest='raw/'+row['trial_id']+'.tar.xz';q=P/dest;q.parent.mkdir(exist_ok=True);members=[]
 with tarfile.open(q,'w:xz',preset=3) as tar:
  for name in names:
   b=(case/name).read_bytes();h=hashlib.sha256(b).hexdigest()
   if name!='artifacts.json':assert h==seal['files'][name]
   info=tarfile.TarInfo(name);info.size=len(b);info.mode=0o644;info.mtime=0;tar.addfile(info,io.BytesIO(b))
   mapping[str(case/name)]=dict(path=dest,member=name,sha256=h)
   members.append(dict(name=name,sha256=h,bytes=len(b)))
 archives.append(dict(path=dest,sha256=sha(q),members=members))
 print('archived',len(archives),row['trial_id'],flush=True)
index=read(E/'run-v1/index.json');assert index['passed'] and index['source_after_passed'] and len(index['rows'])==24
for row in index['rows']:archive(row)
for folder in (E,E/'run-v1',E/'run-v1/metrics',E/'run-v1/acceptances'):
 for p in sorted(folder.iterdir()):
  if p.is_file():copy(p)
for p in (E/'slides-v1').iterdir():
 if p.is_file():copy(p,dest='slides/'+p.name)
for p in (E/'slides-v1/report').iterdir():
 if p.is_file():copy(p,dest='slides/report/'+p.name)
# Bind every data-derivation input to either its unchanged copied file or its
# unchanged raw archive member. No compressed-byte representation conversion.
for path,h in read(E/'slides-v1/slide-data.json')['inputs'].items():
 if path in mapping:assert mapping[path]['sha256']==h
 else:copy(path,h)
for path,h in read(E/'sources.json')['files'].items():
 p=Path(path)
 if not p.is_relative_to(R) or any(x.startswith('runtime-') for x in p.parts) or '/ttg-littlex-freethreaded/python/' in path:
  external.append(dict(path=path,sha256=h));continue
 copy(p,h)
clean=read(E/'clean-manifest.json')
for name,h in clean['worktree_patch'].items():
 copy(Path(clean['root'])/name,h,dest='runtime-delta/'+name)
for kind in ('clean','overlay'):
 manifest=read(E/f'{kind}-manifest.json')
 for name in ('jac/jaclang/data/impl/pgwire.impl.jac','jac/jaclang/runtime/prefetch.jac','jac/jaclang/runtime/ttg_process_reader.jac'):
  copy(Path(manifest['root'])/name,manifest['files'][name],dest='instrumentation/'+kind+'/'+name)
core=R/'project-notes/measurements/ttg-access-visit-20261110'
for folder in (core,core/'native-v1',core/'native-v2'):
 for p in folder.iterdir():
  if p.is_file():copy(p)
for p in (R/'reproduction/ttg-access-visit-performance-20261110').glob('*.py'):copy(p)
for name in ('owner.json','ownership-and-cleanup.jsonl'):
 copy(R/'reproduction/ttg-access-visit-performance-20261110/pg-v1'/name)
for name in ('ttg-overfetch-comparison-20261109','ttg-recipe-precision-20261110'):
 copy(E.parent/name/'results.json')
copy(R/'project-notes/ttg-access-visit.md')
for name,obj in [('path-mapping',mapping),('archives',archives),('external-runtime',external)]:
 (P/'manifests'/f'{name}.json').write_text(json.dumps(obj,indent=2)+'\n')
print('package content ready',len(mapping),sum(p.stat().st_size for p in P.rglob('*') if p.is_file()),flush=True)
