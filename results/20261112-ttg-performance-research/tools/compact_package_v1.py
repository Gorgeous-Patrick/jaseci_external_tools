"""Lossless compaction of NEW unpublished package copies; originals untouched."""
import hashlib,json,lzma,tarfile
from collections import defaultdict
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'jaseci_external_tools/results/20261112-ttg-performance-research'
E=ROOT/'project-notes/measurements/ttg-performance-research-20261112'
def read(p):return json.loads(p.read_text())
def digest(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1024**2),b''):h.update(b)
 return h.hexdigest()
def write(p,v):p.write_text(json.dumps(v,indent=2)+'\n')
def main():
 assert OUT.name=='20261112-ttg-performance-research' and not (OUT/'package-integrity.json').exists()
 mapping=read(OUT/'manifests/path-mapping.json');old=read(OUT/'manifests/large-metadata.json')
 members={r['member']:r for r in old['members']};groups=defaultdict(list)
 for entry in mapping:
  if 'archive_member' not in entry:groups[entry['package_path']].append(entry)
 removals=[]
 for name,entries in groups.items():
  p=OUT/name
  if p.suffix!='.json' or p.stat().st_size<=128*1024:continue
  h=digest(p);assert all(e['sha256']==h for e in entries)
  original=ROOT/entries[0]['original'];assert digest(original)==h
  member='workspace/'+entries[0]['original']
  members[member]=dict(source=str(original),member=member,sha256=h,bytes=p.stat().st_size)
  removals.append(dict(path=name,sha256=h,bytes=p.stat().st_size,entries=entries,member=member))
 name='evidence/large-metadata-v2.tar.xz';target=OUT/name;assert not target.exists()
 with lzma.open(target,'wb',preset=1) as packed:
  with tarfile.open(fileobj=packed,mode='w|',format=tarfile.PAX_FORMAT) as tar:
   for r in members.values():
    source=Path(r['source']);assert source.stat().st_size==r['bytes'] and digest(source)==r['sha256']
    info=tarfile.TarInfo(r['member']);info.size=r['bytes'];info.mode=0o644;info.uid=info.gid=info.mtime=0
    with source.open('rb') as f:tar.addfile(info,f)
 seen=set()
 with tarfile.open(target,'r|xz') as tar:
  for info in tar:
   assert info.isfile() and info.name in members and info.name not in seen
   r=members[info.name];h=hashlib.sha256();stream=tar.extractfile(info)
   for b in iter(lambda:stream.read(1024**2),b''):h.update(b)
   assert info.size==r['bytes'] and h.hexdigest()==r['sha256'];seen.add(info.name)
 assert seen==set(members)
 for entry in mapping:
  if entry['package_path']==old['package_path']:entry['package_path']=name
 for r in removals:
  for entry in r['entries']:entry.update(package_path=name,archive_member=r['member'])
 write(OUT/'manifests/path-mapping.json',mapping)
 write(OUT/'manifests/large-metadata.json',dict(package_path=name,sha256=digest(target),members=list(members.values())))
 for r in removals:
  p=OUT/r['path'];assert p.is_relative_to(OUT) and digest(p)==r['sha256'];p.unlink()
 obsolete=OUT/old['package_path'];assert digest(obsolete)==old['sha256'];obsolete.unlink()
 value=dict(passed=True,scope='Only verified NEW unpublished package copies reclaimed; all original evidence/source/index files unchanged.',
  source=str(Path(__file__).resolve()),new_archive=name,members=len(members),new_bytes=target.stat().st_size,
  removed_new_package_copies=[{k:v for k,v in r.items() if k!='entries'} for r in removals],
  package_bytes=sum(p.stat().st_size for p in OUT.rglob('*') if p.is_file()))
 write(E/'package-compaction-v1.json',value);print(json.dumps({k:v for k,v in value.items() if k!='removed_new_package_copies'}),flush=True)
if __name__=='__main__':main()
