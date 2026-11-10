from pathlib import Path
import hashlib,json,shutil,tarfile,io,subprocess
R=Path('/home/baichuan/jaseci');P=R/'jaseci_external_tools/results/20261109-ttg-prefetch-precision'
assert not P.exists();(P/'manifests').mkdir(parents=True)
known=set();mapping=[];archives=[];external={}
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_text())
def copy(p,wanted=None,dest=None):
 p=Path(p);rel=str(p.relative_to(R));h=sha(p);assert wanted is None or wanted==h,(p,wanted,h)
 if (rel,h) in known:return
 dest=dest or 'workspace/'+rel;t=P/dest;t.parent.mkdir(parents=True,exist_ok=True)
 if t.exists():assert sha(t)==h
 else:shutil.copyfile(p,t)
 mapping.append(dict(original=rel,sha256=h,package_path=dest));known.add((rel,h))
def ext(path):return '/ttg-littlex-freethreaded/python/' in path or any(v.startswith('runtime-') for v in Path(path).parts)
def sources(path):
 copy(path)
 for p,h in read(path)['files'].items():
  if ext(p):external[(p,h)]=dict(original=p,sha256=h,kind='installed_runtime_or_interpreter_snapshot');continue
  copy(p,h)
def archive(case,label,kind):
 seal=read(case/'artifacts.json');assert seal['passed'];names=sorted(set(seal['files'])|{'artifacts.json'});assert {str(p.relative_to(case)) for p in case.rglob('*') if p.is_file()}==set(names)
 dest='raw/'+label+'.tar.xz';p=P/dest;p.parent.mkdir(exist_ok=True);members=[];rel=str(case.relative_to(R))
 with tarfile.open(p,'w:xz',preset=3) as tar:
  for n in names:
   b=(case/n).read_bytes();h=hashlib.sha256(b).hexdigest()
   if n!='artifacts.json':assert seal['files'][n]==h
   ti=tarfile.TarInfo(n);ti.size=len(b);ti.mode=0o644;ti.mtime=0;tar.addfile(ti,io.BytesIO(b));m=dict(original=rel+'/'+n,package_path=dest,member=n,sha256=h,bytes=len(b));members.append(m);mapping.append(m);known.add((m['original'],h))
 archives.append(dict(path=dest,sha256=sha(p),case=rel,kind=kind,members=members));print('archive',len(archives),label,flush=True)
runs=[]
for name in ('ttg-standard-access-comparison-20261109','ttg-overfetch-comparison-20261109'):
 E=R/'project-notes/measurements'/name;index=read(E/'run-v1/index.json');assert index['passed'] and len(index['rows'])==16
 sources(E/'sources.json')
 for d in (E,E/'run-v1',E/'run-v1/metrics',E/'run-v1/acceptances'):
  for f in sorted(d.iterdir()):
   if f.is_file():copy(f)
 for row in index['rows']:archive(Path(row['result']['raw']['path']).parent,name+'--'+row['trial_id'],name)
 for n in ('owner.json','ownership-and-cleanup.jsonl'):copy(R/'reproduction'/name/'pg-v1'/n)
 runs.append(dict(name=name,prefix=str(E.relative_to(R)),cases=16))
# Preserve all test/SQL-comparison evidence as small files; no PostgreSQL data/cache/checkouts.
E=R/'project-notes/measurements/ttg-standard-access-20261109'
for f in E.rglob('*'):
 if f.is_file():copy(f)
for f in (R/'reproduction/ttg-standard-access-20261109').glob('*.py'):copy(f)
# Exact dirty core state used for both new snapshots, without committing it to jac-ttg.
repo=R/'jac-ttg';head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=repo,text=True).strip()
patch=subprocess.check_output(['git','diff','--binary','HEAD'],cwd=repo)
extra=subprocess.run(['git','diff','--no-index','--binary','--','/dev/null','jac/tests/runtimelib/test_standard_access.jac'],cwd=repo,capture_output=True);assert extra.returncode==1
(P/'runtime.patch').write_bytes(patch+extra.stdout)
paths=subprocess.check_output(['git','diff','--name-only','HEAD'],cwd=repo,text=True).splitlines()+['jac/tests/runtimelib/test_standard_access.jac']
for n in paths:copy(repo/n)
# Capture effective instrumentation and its pristine counterparts at exact bytes.
snap=read(R/'project-notes/measurements/ttg-standard-access-comparison-20261109/snapshots.json')
for kind in ('clean','overlay'):
 m=read(snap[kind]['path']);copy(snap[kind]['path'],snap[kind]['sha256'])
 for n in ('jac/jaclang/data/impl/pgwire.impl.jac','jac/jaclang/runtime/prefetch.jac','jac/jaclang/runtime/ttg_process_reader.jac'):
  copy(Path(m['root'])/n,m['files'][n],dest='runtime-instrumentation/'+kind+'/'+n)
(P/'manifests/runtime.json').write_text(json.dumps(dict(commit=head,patch='runtime.patch',patch_sha256=sha(P/'runtime.patch'),core_worktree_committed=False,standard_only_permissions=True),indent=2)+'\n')
for n,obj in [('path-mapping',mapping),('archives',archives),('external-runtime',list(external.values())),('scope',dict(runs=runs,captured=32,measured=24,excluded_warmups=8,includes='All 32 accepted raw case seals, 2 complete indexes/results/CSV, execution scripts, independent replay inputs, GIL/lifecycle/cleanup evidence, exact runtime patch and instrumentation, earlier SQL-only diagnostic and tests.',external='Full runtime trees, interpreter binaries, PostgreSQL clusters and caches are excluded. Original absolute paths in evidence remain unchanged and are resolved by the portable verifier. Runtime/interpreter file identities are recorded separately. Re-execution needs those installed dependencies and the recorded workspace layout.'))]:
 (P/'manifests'/f'{n}.json').write_text(json.dumps(obj,indent=2)+'\n')
shutil.copyfile(__file__,P/'build_package.py');print('built',len(mapping),sum(p.stat().st_size for p in P.rglob('*') if p.is_file()),flush=True)
