"""Portable package/evidence verification; standard library, no Jac or DB."""
import hashlib
import json
import tarfile
from pathlib import Path

P=Path(__file__).resolve().parent
def read(p):return json.loads(p.read_text())
def digest(b):return hashlib.sha256(b).hexdigest()
def sha(p):return digest(p.read_bytes())
integrity=read(P/'package-integrity.json')
assert sha(P/'manifests/files.json')==integrity['files_sha256']
files=read(P/'manifests/files.json')
actual={str(p.relative_to(P)) for p in P.rglob('*') if p.is_file()}
assert actual==set(files)|{'manifests/files.json','package-integrity.json'},(actual-set(files),set(files)-actual)
for n,v in files.items():
 p=P/n; assert p.stat().st_size==v['bytes'] and sha(p)==v['sha256'],n
archives=read(P/'manifests/archives.json'); assert len(archives)==24
members={};sealed=0
for a in archives:
 expected={m['name']:m for m in a['members']};seen=set();hashes={};seal=None
 assert files[a['path']]['sha256']==a['sha256']
 with tarfile.open(P/a['path'],'r:xz') as t:
  for m in t:
   assert m.isfile() and m.name in expected and m.name not in seen,m.name
   seen.add(m.name);b=t.extractfile(m).read();h=digest(b)
   assert m.size==expected[m.name]['bytes'] and h==expected[m.name]['sha256']
   hashes[m.name]=h;members[a['path'],m.name]=h
   if m.name=='artifacts.json':seal=json.loads(b)
 assert seen==set(expected) and seal['passed']
 assert set(seal['files'])==seen-{'artifacts.json'}
 assert all(hashes[n]==h for n,h in seal['files'].items())
 sealed+=len(seal['files'])
mapping=read(P/'manifests/path-mapping.json')
for original,r in mapping.items():
 h=members[r['path'],r['member']] if 'member' in r else files[r['path']]['sha256']
 assert h==r['sha256'],original
d=read(P/'slides/slide-data.json');assert d['passed']
for n,h in d['inputs'].items():assert mapping[n]['sha256']==h,n
for g in d['groups']:
 assert g['coverage']==g['covered']/g['demand']
 assert g['used_fraction']==g['covered']/g['prefetched']
 assert g['unused']==g['prefetched']-g['covered']
 assert g['confirmed_unnecessary_lower_bound']==g['unused']+g['confirmed_filter_only']
 checks=[c for c in d['filter_checks'] if c['app']==g['app']]
 assert len(checks)==3
 if g['mode']=='aggressive':
  assert all(len(c['records'])==c['confirmed_filter_only_prefetch']==g['confirmed_filter_only'] for c in checks)
for r in d['recipe_root_rates']:
 assert r['root_demand']==39 and r['nonroot_demand']==r['all_demand']-39
 assert r['nonroot_coverage']==r['covered']/r['nonroot_demand']
for version in ('report','report-v2'):
 report=read(P/'slides'/version/'report-manifest.json');assert report['pages']==12
 for r in [report['source'],report['data'],*report['outputs']]:
  assert mapping[r['path']]['sha256']==r['sha256'],r
assert sha(P/'slides/derive.py')==d['derive_source_sha256']
print(json.dumps(dict(passed=True,files=len(actual),archives=len(archives),sealed_files=sealed,
 mapped_paths=len(mapping),derivation_inputs=len(d['inputs']),slides=report['pages']),indent=2))
