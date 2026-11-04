"""Build the fixed fifteen-app publication; never modify source evidence."""
from pathlib import Path
import hashlib,json,shutil,tarfile,io
R=Path('/home/baichuan/jaseci');P=R/'jaseci_external_tools/results/20261104-ttg-15-apps';E=R/'project-notes/measurements/ttg-portfolio-v2-20261104'
D=R/'project-notes/measurements/ttg-portfolio-diagnostics-v2-20261104';H=R/'project-notes/measurements/ttg-portfolio-cpu-hot-20261104';S=R/'project-notes/measurements/ttg-portfolio-sql-diagnostics-20261104'
assert not P.exists();(P/'manifests').mkdir(parents=True)
known=set();mapping=[];archives=[];external={};runs=[]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_text())
def copy(p,wanted=None,dest=None):
 p=Path(p);assert p.is_file(),p;rel=str(p.relative_to(R));h=sha(p);assert wanted is None or wanted==h,(p,wanted,h)
 if (rel,h) in known:return
 dest=dest or 'workspace/'+rel;t=P/dest
 if t.exists():assert sha(t)==h
 else:t.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,t)
 assert sha(t)==h;mapping.append(dict(original=rel,sha256=h,package_path=dest));known.add((rel,h))
def ext(path):return '/ttg-littlex-freethreaded/python/' in path or any(v.startswith('runtime-') for v in Path(path).parts)
def sources(path):
 copy(path)
 for p,h in read(path)['files'].items():
  if ext(p):external[(p,h)]=dict(original=p,sha256=h,kind='installed_runtime_or_interpreter_snapshot');continue
  copy(p,h)
def meta(run):
 for d in (run,run/'metrics',run/'acceptances'):
  if d.is_dir():
   for f in sorted(d.iterdir()):
    if f.is_file():copy(f)
 if (run/'sources.json').exists():sources(run/'sources.json')
def archive(case,label,kind,from_tar=None):
 rel=str(case.relative_to(R));prefix='cases/'+case.name+'/'
 def get(n):return from_tar.extractfile(prefix+n).read() if from_tar else (case/n).read_bytes()
 seal=json.loads(get('artifacts.json'));assert seal['passed'];names=sorted(set(seal['files'])|{'artifacts.json'})
 if from_tar:actual={m.name.removeprefix(prefix) for m in from_tar if m.isfile() and m.name.startswith(prefix)}
 else:actual={str(f.relative_to(case)) for f in case.rglob('*') if f.is_file()}
 assert actual==set(names),(case,actual-set(names),set(names)-actual)
 dest='raw/'+label+'.tar.xz';p=P/dest;p.parent.mkdir(exist_ok=True);members=[]
 with tarfile.open(p,'w:xz',preset=3) as tar:
  for n in names:
   b=get(n);h=hashlib.sha256(b).hexdigest()
   if n!='artifacts.json':assert seal['files'][n]==h,(case,n)
   ti=tarfile.TarInfo(n);ti.size=len(b);ti.mode=0o644;ti.mtime=0;tar.addfile(ti,io.BytesIO(b))
   m=dict(original=rel+'/'+n,package_path=dest,member=n,sha256=h,bytes=len(b));members.append(m);mapping.append(m);known.add((m['original'],h))
 archives.append(dict(path=dest,sha256=sha(p),case=rel,kind=kind,members=members))
 if len(archives)%20==0:print('Archived',len(archives),flush=True)
plan=read(E/'plan.json');index=read(E/'run-v1/index.json');assert index['passed'] and len(index['rows'])==120
meta(E/'run-v1');sources(E/'sources.json')
for row in index['rows']:archive(Path(row['result']['raw']['path']).parent,'primary--'+row['trial_id'],'primary')
for f in sorted(E.iterdir()):
 if f.is_file() and f.suffix in ('.json','.py','.csv','.log'):copy(f)
for f in sorted((E/'slides-final').iterdir()):
 if f.is_file():copy(f,dest='report/'+f.name)
for key in ('clean','overlay'):copy(plan[key]['path'],plan[key]['sha256'])
for base,run,kind in [(D,'cpu-v2','cpu_reader'),(H,'run-v1','cpu_hot'),(S,'run-v2','sql_diagnostic')]:
 d=base/run;meta(d);assert read(d/'result.json')['passed']
 if base==D:
  info=next(x for x in read(D/'stopped-preservation-v1/manifest.json')['archives'] if x['original']==str(d/'cases'));assert sha(info['archive'])==info['sha256']
  with tarfile.open(info['archive'],'r:gz') as tar:
   for row in read(d/'result.json')['rows']:archive(Path(row['result']['raw']['path']).parent,kind+'--'+row['app']+'-'+row['mode'],kind,tar)
 else:
  for row in read(d/'result.json')['rows']:archive(Path(row['result']['raw']['path']).parent,kind+'--'+row['app']+'-'+row['mode'],kind)
 for f in sorted(base.iterdir()):
  if f.is_file() and f.suffix in ('.json','.log','.py'):copy(f)
 for f in (R/'reproduction'/base.name).glob('*.py'):copy(f)
# Local preserved-state archive manifests are provenance; PG data archives are not a reproduction dependency.
copy(D/'stopped-preservation-v1/manifest.json')
invalid=R/'project-notes/measurements/ttg-portfolio-diagnostics-20261104/cpu-v1/profile-validity.json';copy(invalid)
for f in ['run.log','iterator-repair-check.json','run-v1/lifecycle.json']:copy(S/f)
copy(R/'project-notes/measurements/ttg-portfolio-20261104/audit.py')
for pg in [R/'reproduction/ttg-portfolio-v2-20261104/pg-v1',R/'reproduction/ttg-portfolio-diagnostics-v2-20261104/pg-cpu-v2',R/'reproduction/ttg-portfolio-cpu-hot-20261104/pg-v1',R/'reproduction/ttg-portfolio-sql-diagnostics-20261104/pg-v2']:
 for n in ['owner.json','ownership-and-cleanup.jsonl']:copy(pg/n)
for p in ['reproduction/ttg-jdrive-access/freeze.py','reproduction/ttg-jdrive-access/freeze_sql_v2.py','reproduction/ttg-app-performance/suite-final-20261030-v1/snapshot.json','project-notes/measurements/ttg-littlex-freethreaded-20261102/interpreter-assertions.json']:
 copy(R/p)
# Source-only audit provenance explicitly referenced by support inventory.
for f in (R/'project-notes').glob('ttg-sibling-audit-*.json'):copy(f)
(P/'manifests/path-mapping.json').write_text(json.dumps(mapping,indent=2)+'\n');(P/'manifests/archives.json').write_text(json.dumps(archives,indent=2)+'\n');(P/'manifests/external-runtime.json').write_text(json.dumps(list(external.values()),indent=2)+'\n')
(P/'manifests/scope.json').write_text(json.dumps(dict(primary_prefix=str(E.relative_to(R)),primary_cases=120,diagnostic_cases=14,sole_pdf='report/ttg-15-app-performance.pdf',runtime_commit=plan['runtime_commit'],external='Installed runtimes/interpreter identities listed separately; reconstruct from commit and instrumentation. PostgreSQL state archives, caches, unused historical provenance trees and rejected cProfile traces are not bundled. Valid CPU archived cases are repackaged with identical sealed bytes; original path/hash mappings retained.'),indent=2)+'\n')
shutil.copyfile(__file__,P/'build_package.py')
print('BUILT',len(archives),len(mapping),'bytes',sum(p.stat().st_size for p in P.rglob('*') if p.is_file()),flush=True)
