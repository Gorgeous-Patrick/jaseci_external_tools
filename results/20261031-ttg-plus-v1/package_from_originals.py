#!/usr/bin/env python3
"""Package immutable pilot artifacts without executing applications or changing originals."""
from pathlib import Path
import argparse
import gzip
import lzma
import hashlib
import json
import shutil
import tarfile

ROOT = Path('/home/baichuan/jaseci')
M = ROOT / 'project-notes/measurements/ttg-plus-performance-20261031'
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
    if any(x in rel.parts for x in ['.git','__pycache__','node_modules','pgdata','data','venv','.venv']):return True
    for part in rel.parts:
        if part.startswith(('runtime-clean-','runtime-direct-','runtime-reference-')) and not part.endswith(('-manifest','-overlay')):return True
        if part.startswith(('owned-state-archive','historical-v4-metric-archive','obsolete-')):return True
    if path.suffix.lower()=='.png':return True
    if path.suffix.lower()=='.pdf' and 'report-v2-final' not in path.parts:return True
    if 'cases' in rel.parts and 'formal-v1' not in rel.parts and 'correctness-v5' not in rel.parts and 'recapture-v1' not in rel.parts:return True
    if any(x in rel.parts for x in ('correctness-v1','correctness-v2','correctness-v3','correctness-v4')):return True
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
                excluded_refs.append(dict(path=key,sha256=expected,reason='Historical/runtime checkout/database/cache or optional preview excluded; exact provenance retained and current47 raw cases preserved'))
            elif not p.is_file():
                excluded_refs.append(dict(path=key,sha256=expected,reason='Historical/restorable external workspace path; not a current47 raw input'))
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
    formal=json.loads((M/'formal-v1/index.json').read_text());correctness=json.loads((M/'correctness-v5/index.json').read_text())
    assert formal['passed'] and formal['status']=='complete' and len(formal['rows'])==36
    assert correctness['passed'] and correctness['status']=='complete' and len(correctness['rows'])==9
    sources=json.loads((M/'formal-review-ready-v1/sources.json').read_text())['files'];assert len(sources)==50
    for path,sha in sources.items():
        copy_file(path,sha,'sources/workspace/'+relative(path));source_closure.append(dict(original=relative(path),sha256=sha,package_path=mapping[relative(path)]['package_path']))
    app_manifest=ROOT/'reproduction/ttg-app-performance/suite-final-20261030-v1/snapshot.json';app=json.loads(app_manifest.read_text());assert len(app['files'])==90
    copy_file(app_manifest)
    for name,sha in app['files'].items():copy_file(app_manifest.parent/name,sha,'sources/workspace/'+relative(app_manifest.parent/name))
    for category,index in [('formal36',formal),('correctness9',correctness)]:
        for number,row in enumerate(index['rows'],1):
            assert row['passed'];result=row['result'];archive_seal(result['raw']['path'],row['trial_id'],result['raw']['sha256'],category)
            for key in ('acceptance','metrics'):copy_file(result[key]['path'],result[key]['sha256'])
            print(category,str(number)+'/'+str(len(index['rows']))+' archive/readback verified',flush=True)
        copy_file(M/('formal-v1' if category=='formal36' else 'correctness-v5')/'index.json')
    diagnostic=ROOT/'project-notes/measurements/ttg-plus-diagnostics-20261031'
    for cell in ('off','ttg_plus'):
        archive_seal(diagnostic/'recapture-v1'/('littlex-'+cell)/'artifacts.json','littlex-'+cell,category='diagnostics2')
    for p in sorted(diagnostic.glob('*.json')):copy_file(p)
    for p in sorted(diagnostic.glob('*.md')):copy_file(p)
    for name in ('recapture-v1/result.json','recapture-v1/lifecycle.json','recapture-v1/launch.json','recapture-v1/runtime-overlay.json','recapture-v1/sources.json'):
        copy_file(diagnostic/name)
    for p in sorted((ROOT/'reproduction/ttg-plus-diagnostics').glob('*.py')):copy_file(p,dest='sources/workspace/'+relative(p))
    copy_file(ROOT/'reproduction/ttg-plus-diagnostics/README.md',dest='sources/workspace/reproduction/ttg-plus-diagnostics/README.md')
    for folder in ('export-v1','littlex-attribution-v1','formal-review-ready-v1','runner-candidate-v5','correctness-review-v2','report-v2-final','presentation-data-v1'):
        if (M/folder).is_dir():
            for p in sorted((M/folder).iterdir()):
                if p.is_file() and p.suffix.lower() not in ('.png','.pdf'):
                    copy_file(p)
    for name in ('formal-run-authorization.json','component-binding-final-v2.json','post-primary-diagnostics-plan.md','final-report-candidate-v1.json'):
        if (M/name).is_file():copy_file(M/name)
    report=M/'report-v2-final/ttg-plus-performance.pdf';copy_file(report,'3f3138080d751e6953df74715c10176b22e79627e8d9a27449055fc90430378b','report/ttg-plus-performance.pdf')
    copy_file(ROOT/'reproduction/ttg-plus-performance/render_report_v2_final.py','185cb94da6740bc8f85c9224512f603effc332b863deb58ceeaa5d11e93aaddc','report/render_report_v2_final.py')
    for name in ('figure-inputs.json','report-manifest.json'):
        path=M/'report-v2-final'/name
        copy_file(path,dest='report/'+name) if relative(path) not in mapping else None
    main=ROOT/'project-notes/measurements/ttg-plus-main-20261031'
    for p in sorted(main.glob('*.json')):copy_file(p)
    review=ROOT/'project-notes/measurements/ttg-plus-review-20261031'
    for pattern in ('formal36*','correctness-v5*','ll1000-v5*','acl-final-commit*','runtime-final-commit*','*diagnostic*'):
        for p in sorted(review.glob(pattern)):
            if p.is_file():copy_file(p)
    # Package the exactignored dependency bytes already copied into current850.
    clean=json.loads((ROOT/'reproduction/ttg-plus-performance/runtime-clean-final-v2-manifest/manifest.json').read_text())
    dep=clean['ignored_typeshed_source'];current=Path(clean['root'])/'jac/jaclang/vendor/typeshed/stdlib'
    for name,sha in dep['files'].items():
        source=current/name;dest='sources/runtime-dependencies/typeshed/stdlib/'+name;copy_file(source,sha,dest)
        bind(Path(dep['root'])/name,dest,sha)
    collect_references()
    (OUT/'manifests').mkdir(exist_ok=True)
    write_json(OUT/'manifests/path-mapping.json',list(mapping.values()))
    write_json(OUT/'manifests/archive-members.json',archives)
    write_json(OUT/'manifests/source-closure.json',source_closure)
    write_json(OUT/'manifests/reference-exclusions.json',excluded_refs)
    write_json(OUT/'manifests/historical-references.json',superseded_refs)
    print(json.dumps(dict(stage='data_packaged',archives=len(archives),mapped_paths=len(mapping),source_files=len(source_closure),excluded_refs=len(excluded_refs),historical_refs=len(superseded_refs),bytes=sum(p.stat().st_size for p in OUT.rglob('*') if p.is_file()))),flush=True)

if __name__=='__main__':main()
