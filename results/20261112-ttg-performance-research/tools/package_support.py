#!/usr/bin/env python3
"""Package accepted TTG-next artifacts while preserving source and evidence bytes."""
from pathlib import Path
import argparse
import gzip
import lzma
import hashlib
import json
import shutil
import tarfile

ROOT = Path('/home/baichuan/jaseci')
M = ROOT / 'project-notes/measurements/ttg-next-performance-20261101'
OUT = Path(__file__).resolve().parent
LIMIT = 100_000_000
mapping = {}
archives = []
queue = []
processed = set()
excluded_refs = []
superseded_refs = []
source_closure = []

def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()

def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')

def relative(path):
    return str(Path(path).absolute().relative_to(ROOT))

def forbidden(path):
    rel=Path(path).absolute().relative_to(ROOT)
    if any(x in rel.parts for x in ('.git','__pycache__','node_modules','pgdata','data','venv','.venv')):return True
    for part in rel.parts:
        if part.startswith(('runtime-','cache-','pg-')) and not part.endswith(('-manifest','-overlay')):return True
        if part.startswith(('owned-state-archive','historical-v4-metric-archive','obsolete-')):return True
    if path.suffix.lower() in ('.png','.pdf'):return True
    if 'cases' in rel.parts:return True
    if any(part in rel.parts for part in ('correctness-v1','correctness-v3','correctness-v4','correctness-v5')):return True
    return False

def bind(path, dest, sha, member=None, archived_source=None):
    key = relative(path)
    entry = {'original': key, 'package_path': dest, 'sha256': sha}
    if member is not None:
        entry['archive_member'] = member
    if archived_source is not None:
        entry['copied_from'] = relative(archived_source)
    if key in mapping:
        old = mapping[key]
        assert old['sha256'] == sha, (key, 'conflicting digest')
        return old
    mapping[key] = entry
    return entry

def copy_file(path, expected=None, dest=None, from_path=None):
    path = Path(path).absolute()
    source = Path(from_path).absolute() if from_path else path
    assert source.is_file() and not source.is_symlink(), str(source)
    sha = digest(source)
    assert expected is None or sha == expected, (str(source), sha, expected)
    if relative(path) in mapping:
        assert mapping[relative(path)]['sha256'] == sha
        if source != path:
            bind(source, mapping[relative(path)]['package_path'], sha)
        return
    dest = dest or 'evidence/workspace/' + relative(path)
    target = OUT / dest
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        assert digest(target) == sha, ('existing output mismatch', target)
    else:
        shutil.copyfile(source, target)
    assert digest(target) == sha
    bind(path, dest, sha, archived_source=source if source != path else None)
    if source != path:
        bind(source, dest, sha)
    if path.suffix == '.json':
        queue.append((path, target))

def refs(value):
    if isinstance(value, dict):
        if isinstance(value.get('path'), str) and isinstance(value.get('sha256'), str) and len(value['sha256']) == 64:
            yield value['path'], value['sha256']
        for child in value.values():
            yield from refs(child)
    elif isinstance(value, list):
        for child in value:
            yield from refs(child)

def collect_references():
    while queue:
        original,copied=queue.pop(0)
        if str(original) in processed:continue
        processed.add(str(original));value=json.loads(copied.read_text())
        for path,expected in refs(value):
            p=Path(path)
            if not p.is_absolute():p=ROOT/p if (ROOT/p).is_file() else original.parent/p
            try:key=relative(p)
            except ValueError:
                excluded_refs.append(dict(path=str(p),sha256=expected,reason='External environment provenance; no portable experiment input is substituted'));continue
            if key in mapping:
                if mapping[key]['sha256']!=expected:
                    superseded_refs.append(dict(referencing_document=relative(original),path=key,historical_sha256=expected,current_packaged_sha256=mapping[key]['sha256'],reason='Historical version reference retained verbatim; current exact accepted sources are separately bound'))
            elif forbidden(p):
                excluded_refs.append(dict(path=key,sha256=expected,reason='Historical/runtime checkout/database/cache or optional preview excluded; exact provenance retained and current92 accepted raw cases preserved'))
            elif not p.is_file():
                excluded_refs.append(dict(path=key,sha256=expected,reason='Historical/restorable external workspace path; not a current92 accepted raw input'))
            elif digest(p)!=expected:
                superseded_refs.append(dict(referencing_document=relative(original),path=key,historical_sha256=expected,current_file_sha256=digest(p),reason='Historical mutable path; no unbound bytes substituted'))
            else:copy_file(p,expected)

def copy_directory_files(path, prefix=None):
    for p in sorted(Path(path).rglob('*')):
        if p.is_file() and not p.is_symlink() and not any(x in ['__pycache__', '.jac', '.git'] for x in p.parts):
            copy_file(p, dest=(prefix + '/' + str(p.relative_to(path))) if prefix else None)


def archive_seal(seal_path,archive_name,expected=None,category='raw'):
    seal_path=Path(seal_path).absolute();seal_sha=digest(seal_path)
    assert expected is None or seal_sha==expected
    seal=json.loads(seal_path.read_text());assert seal['passed'] is True
    declared={**seal['files'],'artifacts.json':seal_sha};compression_path=seal_path.parent/'compression.json'
    compression=json.loads(compression_path.read_text()) if compression_path.exists() else []
    compressed={row['sealed_name']:row for row in compression}
    members=[]
    for name,sha in sorted(declared.items()):
        source=seal_path.parent/name;assert source.is_file() and not source.is_symlink();assert digest(source)==sha
        member=dict(member=name,original=relative(source),bytes=source.stat().st_size,sha256=sha,original_sha256=sha)
        if name.endswith('.jsonl.gz'):
            row=compressed[name];assert row['gzip_sha256']==sha
            member.update(member=name[:-3],bytes=row['uncompressed_bytes'],sha256=row['uncompressed_sha256'],
                representation=dict(kind='gzip_to_decoded_tar_xz',original_gzip_sha256=sha,original_gzip_bytes=source.stat().st_size,
                    compression_document=relative(compression_path),compression_document_sha256=digest(compression_path),
                    compression_entry=row,decoded_bytes_identical=True,compressed_bytes_identical=False))
        members.append(member)
    destination='raw/'+category+'/'+archive_name+'.tar.xz';target=OUT/destination;target.parent.mkdir(parents=True,exist_ok=True)
    if not target.exists():
        with lzma.open(target,'wb',format=lzma.FORMAT_XZ,check=lzma.CHECK_CRC64,preset=3) as packed:
            with tarfile.open(fileobj=packed,mode='w|',format=tarfile.PAX_FORMAT) as tar:
                for member in members:
                    info=tarfile.TarInfo(member['member']);info.size=member['bytes'];info.mode=0o644;info.uid=info.gid=info.mtime=0
                    opener=gzip.open if 'representation' in member else open
                    with opener(ROOT/member['original'],'rb') as stream:
                        tar.addfile(info,stream)
                        assert stream.read(1)==b'', 'Extra decoded bytes beyond original compression metadata'
    expected_members={m['member']:m for m in members};seen=set()
    with tarfile.open(target,'r|xz') as tar:
        for info in tar:
            assert info.isfile() and info.name in expected_members and info.name not in seen
            member=expected_members[info.name];assert info.size==member['bytes'];h=hashlib.sha256();stream=tar.extractfile(info)
            for block in iter(lambda:stream.read(1024*1024),b''):h.update(block)
            assert h.hexdigest()==member['sha256'];seen.add(info.name)
    assert seen==set(expected_members) and target.stat().st_size<LIMIT
    for member in members:
        entry=bind(ROOT/member['original'],destination,member['original_sha256'],member=member['member'])
        if 'representation' in member:entry['representation']=member['representation'];entry['decoded_sha256']=member['sha256']
    archives.append(dict(package_path=destination,sha256=digest(target),compressed_bytes=target.stat().st_size,
        original_seal=relative(seal_path),original_seal_sha256=seal_sha,original_seal_passed=True,
        members=members,codec='xz',preset=3,check='CRC64',scope='Decoded trace bytes preserved; originalgzip bytes/seals retained as explicit provenance'))


def main():
    inventory=M/'packaging-inputs-pre-report-v1.json';inputs=json.loads(inventory.read_text());assert inputs['passed'] and inputs['report_pending']
    formal=json.loads((M/'formal-v1/index.json').read_text());correctness=json.loads((M/'correctness-v2/index.json').read_text())
    assert formal['passed'] and formal['status']=='complete' and len(formal['rows'])==72
    assert correctness['passed'] and correctness['status']=='complete' and len(correctness['rows'])==18
    source_manifest=M/'correctness-plan-v2/sources.json';sources=json.loads(source_manifest.read_text())['files'];assert len(sources)==153
    for path,sha in sources.items():
        copy_file(path,sha,'sources/workspace/'+relative(path));source_closure.append(dict(original=relative(path),sha256=sha,package_path=mapping[relative(path)]['package_path']))
    copy_file(source_manifest)
    app_manifest=ROOT/'reproduction/ttg-app-performance/suite-final-20261030-v1/snapshot.json';app=json.loads(app_manifest.read_text());assert len(app['files'])==90
    copy_file(app_manifest)
    for name,sha in app['files'].items():copy_file(app_manifest.parent/name,sha,'sources/workspace/'+relative(app_manifest.parent/name))
    for category,index,folder in [('formal72',formal,'formal-v1'),('correctness18',correctness,'correctness-v2')]:
        for number,row in enumerate(index['rows'],1):
            assert row['passed'];result=row['result'];archive_seal(result['raw']['path'],row['trial_id'],result['raw']['sha256'],category)
            for key in ('acceptance','metrics'):copy_file(result[key]['path'],result[key]['sha256'])
            print(category,str(number)+'/'+str(len(index['rows']))+' archived/member verified',flush=True)
        copy_file(M/folder/'index.json')
    diagnostic=ROOT/'project-notes/measurements/ttg-next-diagnostics-20261101'
    for cell in ('baseline850','next'):
        archive_seal(diagnostic/'recapture-v2/cases'/('linked_list1000-'+cell+'-diagnostic')/'artifacts.json','ll1000-'+cell,category='diagnostics2')
    for p in sorted(diagnostic.rglob('*')):
        if not p.is_file() or p.name.startswith('package-data-') or any(x in p.parts for x in ('__pycache__','source-snapshot')):continue
        # Accepted cases are already complete archives; keep failed-v1 bytes and source copies separately.
        if 'recapture-v2' in p.parts and 'cases' in p.parts:continue
        copy_file(p)
    failed_sources=diagnostic/'recapture-v1/source-snapshot'
    for p in sorted(failed_sources.rglob('*')):
        if p.is_file():copy_file(p)
    for p in sorted((ROOT/'reproduction/ttg-next-diagnostics').glob('*.py')):copy_file(p,dest='sources/workspace/'+relative(p))
    copy_file(inventory)
    for path,wanted in refs(inputs):
        p=Path(path)
        if p.is_file() and not forbidden(p):copy_file(p,wanted)
    # Runtime provenance and scoped committed implementation changes, never full runtime trees.
    owner=ROOT/'project-notes/measurements/ttg-next-20261101'
    for name in ('verification.json','accepted-native-mechanisms-v1.json','regression-final-v1/outcome.json','regression-final-v1/test.log','regression-final-v1/lifecycle.json','format-final-outcome.json','typecheck-v1-outcome.json','typecheck-v2.log'):
        copy_file(owner/name)
    proof=json.loads((owner/'verification.json').read_text())
    for name,wanted in proof['source_files'].items():copy_file(ROOT/'jac-ttg'/name,wanted,'sources/runtime-changes/'+name)
    import subprocess
    patch=OUT/'sources/runtime-850-to-9282.patch';patch.parent.mkdir(exist_ok=True);patch.write_bytes(subprocess.check_output(['git','-C',str(ROOT/'jac-ttg'),'diff','--binary','85026d486de8e16d4b894aa5a5664c7873893e89','9282e246d708aff69e21cb52b9d0cc4893fc5f0f']))
    review=ROOT/'project-notes/measurements/ttg-next-review-20261101'
    for p in sorted(review.iterdir()):
        if p.is_file() and p.suffix in ('.json','.py','.md'):copy_file(p)
    # Existing byte-bound stdlib typing dependency only; no runtime checkout is packaged.
    clean=json.loads((ROOT/'reproduction/ttg-plus-performance/runtime-clean-final-v2-manifest/manifest.json').read_text())
    dep=clean['ignored_typeshed_source'];current=Path(clean['root'])/'jac/jaclang/vendor/typeshed/stdlib'
    for name,sha in dep['files'].items():
        dest='sources/runtime-dependencies/typeshed/stdlib/'+name;copy_file(current/name,sha,dest);bind(Path(dep['root'])/name,dest,sha)
    collect_references()
    (OUT/'manifests').mkdir(exist_ok=True)
    write_json(OUT/'manifests/path-mapping.json',list(mapping.values()))
    write_json(OUT/'manifests/archive-members.json',archives)
    write_json(OUT/'manifests/source-closure.json',source_closure)
    write_json(OUT/'manifests/reference-exclusions.json',excluded_refs)
    write_json(OUT/'manifests/historical-references.json',superseded_refs)
    print(json.dumps(dict(stage='data_packaged_report_pending',archives=len(archives),source153=len(source_closure),mapped_paths=len(mapping),bytes=sum(p.stat().st_size for p in OUT.rglob('*') if p.is_file()))),flush=True)

if __name__=='__main__':main()
