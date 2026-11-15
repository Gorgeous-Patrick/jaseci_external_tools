"""Bounded portable publication, reusing the published lossless archive helper.
No runtime/PG/cache trees, Git operations, experiment execution or source edits.
"""
import argparse,hashlib,importlib.util,json,lzma,shutil,tarfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
E=ROOT/'project-notes/measurements/ttg-performance-research-20261112'
D=ROOT/'project-notes/measurements/ttg-performance-research-diagnostics-20261112'
R=E.with_name(E.name+'-review')
OUT=ROOT/'jaseci_external_tools/results/20261112-ttg-performance-research'
SUPPORT=ROOT/'jaseci_external_tools/results/20261101-ttg-next-v1/package_from_originals.py'
spec=importlib.util.spec_from_file_location('nov12_package_support',SUPPORT)
P=importlib.util.module_from_spec(spec);spec.loader.exec_module(P);P.ROOT=ROOT;P.OUT=OUT
cases=[];large={};original_copy=P.copy_file

def read(p):return json.loads(Path(p).read_text())
def relative(p):return str(Path(p).resolve().relative_to(ROOT))
def write(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,indent=2)+'\n')
def copy(path,expected=None,dest=None,from_path=None):
 path=Path(path).absolute();source=Path(from_path).absolute() if from_path else path
 if source.stat().st_size>2_000_000 and source.suffix=='.json' and dest is None:
  h=P.digest(source);assert expected is None or h==expected
  key=relative(path)
  if key in P.mapping:assert P.mapping[key]['sha256']==h;return
  member='workspace/'+key;large[key]=dict(source=str(source),member=member,sha256=h,bytes=source.stat().st_size)
  P.bind(path,'evidence/large-metadata.tar.xz',h,member=member)
  P.queue.append((path,source));return
 return original_copy(path,expected,dest,from_path)
P.copy_file=copy

def forbidden(path):
 try:rel=Path(path).absolute().relative_to(ROOT)
 except ValueError:return True
 if any(x in rel.parts for x in ('.git','__pycache__','node_modules','.venv','venv')):return True
 if any(x.startswith(('runtime-clean-','runtime-overlay-','runtime-direct-','runtime-reference-','cache-','pg-','owned-state-archive','obsolete-')) for x in rel.parts):return True
 if 'cases' in rel.parts:return True  # required current cases are already sealed archives
 if Path(path).suffix.lower() in ('.pdf','.png'):return True
 return False
P.forbidden=forbidden

def archive_row(row,category,disposition='accepted'):
 result=row['result'];r=result['raw'];P.archive_seal(r['path'],row['trial_id'],r['sha256'],category)
 for key,value in result.items():
  if isinstance(value,dict) and 'path' in value and 'sha256' in value:copy(value['path'],value['sha256'])
 if 'gil_proof' in row:copy(row['gil_proof']['path'],row['gil_proof']['sha256'])
 cases.append(dict(trial_id=row['trial_id'],case_id=row['case_id'],mode=row['config_id'],phase=row['phase'],
  category=category,status=disposition,original_raw=r,archive=P.archives[-1]['package_path']))

def archive_metadata():
 if not large:return
 target=OUT/'evidence/large-metadata.tar.xz';target.parent.mkdir(parents=True,exist_ok=True)
 with lzma.open(target,'wb',preset=1) as packed:
  with tarfile.open(fileobj=packed,mode='w|',format=tarfile.PAX_FORMAT) as tar:
   for item in large.values():
    info=tarfile.TarInfo(item['member']);info.size=item['bytes'];info.mode=0o644;info.uid=info.gid=info.mtime=0
    with open(item['source'],'rb') as f:tar.addfile(info,f)
 expected={i['member']:i for i in large.values()};seen=set()
 with tarfile.open(target,'r|xz') as tar:
  for info in tar:
   assert info.name in expected and info.name not in seen and info.isfile()
   h=hashlib.sha256();stream=tar.extractfile(info)
   for block in iter(lambda:stream.read(1024**2),b''):h.update(block)
   assert h.hexdigest()==expected[info.name]['sha256'];seen.add(info.name)
 assert seen==set(expected)
 write(OUT/'manifests/large-metadata.json',dict(package_path='evidence/large-metadata.tar.xz',sha256=P.digest(target),members=list(large.values())))

def main():
 assert OUT.name=='20261112-ttg-performance-research' and not (OUT/'data-stage-complete.json').exists()
 OUT.mkdir(parents=True,exist_ok=True)
 copy(Path(__file__),dest='package_from_originals.py');copy(SUPPORT,dest='tools/package_support.py')
 plan=read(E/'plan-v2/plan.json');source=read(plan['sources']['path'])['files']
 clean=read(plan['runtimes']['clean']['path']);overlay=read(plan['runtimes']['overlay']['path'])
 runtime_roots=[Path(clean['root']),Path(overlay['root'])];closure=[]
 for path,h in source.items():
  p=Path(path)
  if any(p.is_relative_to(root) for root in runtime_roots):
   closure.append(dict(original=relative(p),sha256=h,provider='Pinned runtime commit plus packaged exact implementation delta; full runtime tree excluded'))
  else:
   copy(p,h,'sources/workspace/'+relative(p));closure.append(dict(original=relative(p),sha256=h,package_path=P.mapping[relative(p)]['package_path']))
 # Full immutable application source/config/oracle snapshot, not a live suite.
 app=Path(plan['app_snapshot']['path']);copy(app,plan['app_snapshot']['sha256'])
 for name,h in read(app)['files'].items():copy(app.parent/name,h,'sources/workspace/'+relative(app.parent/name))
 identity=read(ROOT/'project-notes/measurements/ttg-performance-research-20261112-runtime/runtime-identity-v1.json')
 dirty={r['path']:r['latest_frozen_sha256'] for r in identity['dirty_files']}
 for name,h in dirty.items():copy(Path(clean['root'])/name,h,'sources/runtime-delta/'+name)
 for name,h in overlay['files'].items():
  if clean['files'].get(name)!=h:copy(Path(overlay['root'])/name,h,'sources/runtime-overlay/'+name)
 for row in identity['legacy_selected_closure_comparison']:
  name=row['path'];copy(Path(clean['root'])/name,row['frozen'],'sources/runtime-common/'+name)
 write(OUT/'manifests/runtime-reconstruction.json',dict(base_commit=clean['commit'],clean_manifest=plan['runtimes']['clean'],overlay_manifest=plan['runtimes']['overlay'],
  dirty_sources=dirty,overlay_changes={n:h for n,h in overlay['files'].items() if clean['files'].get(n)!=h},
  instruction='Checkout exact base commit; overlay packaged runtime-delta and runtime-overlay files. Full runtime/interpreter/database/cache trees are excluded. Original complete expected runtime-file hashes are preserved in source manifests.'))
 stages=[('first-v1',45),('small-rest-v1',210),('larger-v1',31),('extend-n5-v2',114),('precision-v2',57)]
 for stage,count in stages:
  index=read(E/stage/'index.json');assert len(index['rows'])==count
  assert (index['passed'] and index['status']=='complete') or (stage=='larger-v1' and index['status']=='failed')
  for number,row in enumerate(index['rows'],1):
   status='correctness_only' if row['case_id']=='linked_list-1000' else 'accepted'
   archive_row(row,stage,status)
   print(stage,str(number)+'/'+str(count)+' byte/member verified',flush=True)
  copy(E/stage/'index.json')
 index=read(D/'cpu-native-v1/index.json');assert index['passed'] and len(index['rows'])==6
 for row in index['rows']:archive_row(row,'CPU-diagnostic')
 copy(D/'cpu-native-v1/index.json')
 failure=read(E/'larger-v1-failure-preservation.json');r=failure['failed_raw_seal']
 P.archive_seal(r['path'],'linked_list-1000-aggressive-correctness-0',r['sha256'],'failed-preserved')
 cases.append(dict(trial_id='linked_list-1000-aggressive-correctness-0',case_id='linked_list-1000',mode='aggressive',phase='correctness',category='failed-preserved',status='failed_isolation_gate',original_raw=r,archive=P.archives[-1]['package_path']))
 assert len(cases)==len({c['trial_id'] for c in cases})==464
 # Source/postprocessor and small evidence files only; never recurse PG/cache trees.
 for directory in (E,R,D,E.with_name(E.name+'-runtime')):
  for p in sorted(directory.iterdir()):
   if p.is_file() and p.suffix in ('.json','.py','.md','.log','.csv'):copy(p)
 for folder in ('export-n5-v2','export-precision-v2','analysis-v1','analysis-v2','report-inputs-v1','report-inputs-v2','plan-v1','plan-v2','candidate-v1'):
  base=E/folder
  for p in sorted(base.rglob('*')):
   if p.is_file() and '__pycache__' not in p.parts:copy(p)
 for base in (R/'matrix-raw-audit-v1',D/'candidate-v2',D/'cpu-native-v1/diagnostic-checks'):
  if base.exists():
   for p in sorted(base.rglob('*')):
    if p.is_file() and '__pycache__' not in p.parts:copy(p)
 for root in (ROOT/'reproduction/ttg-performance-research-20261112',ROOT/'reproduction/ttg-performance-research-diagnostics-20261112'):
  for p in sorted(root.glob('*.py')):copy(p,dest='sources/workspace/'+relative(p))
 # Explicit control evidence, no PostgreSQL DATA directories.
 for name in ('pg-first-v1','pg-small-rest-v1','pg-larger-v1','pg-extend-n5-v2','pg-precision-v2'):
  root=ROOT/'reproduction/ttg-performance-research-20261112'/name
  for filename in ('owner.json','ownership-and-cleanup.jsonl','startup.log'):
   if (root/filename).is_file():copy(root/filename)
 for filename in ('owner.json','ownership-and-cleanup.jsonl','startup.log'):
  root=ROOT/'reproduction/ttg-performance-research-diagnostics-20261112/pg-cpu-v1'
  if (root/filename).is_file():copy(root/filename)
 P.collect_references();archive_metadata()
 write(OUT/'manifests/path-mapping.json',list(P.mapping.values()))
 write(OUT/'manifests/archive-members.json',P.archives)
 write(OUT/'manifests/source-closure.json',closure)
 write(OUT/'manifests/reference-exclusions.json',P.excluded_refs)
 write(OUT/'manifests/historical-references.json',P.superseded_refs)
 write(OUT/'manifests/case-inventory.json',cases)
 write(OUT/'data-stage-complete.json',dict(passed=True,report_pending=True,case_archives=len(cases),comparison_records=399,precision_records=57,diagnostic_records=6,LL_off_correctness_extra=1,failed_aggressive_extra=1,
  source_manifest_entries=len(closure),mapped_paths=len(P.mapping),files=sum(p.is_file() for p in OUT.rglob('*')),bytes=sum(p.stat().st_size for p in OUT.rglob('*') if p.is_file())))
 print(json.dumps(read(OUT/'data-stage-complete.json')),flush=True)
if __name__=='__main__':main()
