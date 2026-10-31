#!/usr/bin/env python3
"""Package immutable pilot artifacts without executing applications or changing originals."""
from pathlib import Path
import argparse
import gzip
import hashlib
import json
import shutil
import tarfile

ROOT = Path('/home/baichuan/jaseci')
M = ROOT / 'project-notes/measurements/ttg-continuation-performance-20261030'
OUT = ROOT / 'jaseci_external_tools/results/20261031-ttg-continuation-small'
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
    rel = Path(path).absolute().relative_to(ROOT)
    if any(x in rel.parts for x in ['.git', '.jac', '__pycache__', 'node_modules', 'pgdata', 'data', 'venv', '.venv']):
        # Fixture data and sealed datasets are included explicitly, never via discovery.
        return True
    if len(rel.parts) > 2 and rel.parts[:2] == ('reproduction', 'ttg-continuation-performance'):
        n = rel.parts[2]
        if n.startswith(('runtime-clean-', 'runtime-direct-')) and not n.endswith(('-manifest', '-overlay')):
            return True
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

def archive_seal(seal_path, archive_name, expected=None, category='raw'):
    seal_path = Path(seal_path).absolute()
    seal_sha = digest(seal_path)
    assert expected is None or seal_sha == expected, str(seal_path)
    seal = json.loads(seal_path.read_text())
    assert category == 'controls' or seal['passed'] is True
    files = dict(seal['files'])
    files['artifacts.json'] = seal_sha
    members = []
    for name, sha in sorted(files.items()):
        assert not Path(name).is_absolute() and '..' not in Path(name).parts
        source = seal_path.parent / name
        assert source.is_file() and not source.is_symlink(), str(source)
        assert digest(source) == sha, str(source)
        members.append({'member': name, 'original': relative(source), 'bytes': source.stat().st_size, 'sha256': sha})
    destination = 'raw/' + category + '/' + archive_name + '.tar.gz'
    target = OUT / destination
    target.parent.mkdir(parents=True, exist_ok=True)
    # Deterministic gzip/tar metadata; raw member bytes remain unchanged.
    if not target.exists():
        with target.open('wb') as raw:
            with gzip.GzipFile(filename='', mode='wb', fileobj=raw, mtime=0, compresslevel=6) as gz:
                with tarfile.open(fileobj=gz, mode='w|', format=tarfile.PAX_FORMAT) as tar:
                    for member in members:
                        info = tarfile.TarInfo(member['member'])
                        info.size = member['bytes']
                        info.mode = 0o644
                        info.uid = info.gid = info.mtime = 0
                        with (ROOT / member['original']).open('rb') as stream:
                            tar.addfile(info, stream)
    # Independently read every compressed member and compare to both seal and original.
    with tarfile.open(target, 'r:gz') as tar:
        actual = tar.getmembers()
        assert [x.name for x in actual] == [x['member'] for x in members]
        for info, member in zip(actual, members):
            assert info.isfile() and info.size == member['bytes']
            stream = tar.extractfile(info)
            h = hashlib.sha256()
            for block in iter(lambda: stream.read(1024 * 1024), b''):
                h.update(block)
            assert h.hexdigest() == member['sha256'] == digest(ROOT / member['original'])
            bind(ROOT / member['original'], destination, member['sha256'], member=member['member'])
    assert target.stat().st_size < LIMIT
    archives.append({'package_path': destination, 'sha256': digest(target), 'compressed_bytes': target.stat().st_size,
                     'original_seal': relative(seal_path), 'original_seal_sha256': seal_sha,
                     'original_seal_passed': seal['passed'], 'sealed_members': len(seal['files']), 'members': members})

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
        original, copied = queue.pop(0)
        if str(original) in processed:
            continue
        processed.add(str(original))
        value = json.loads(copied.read_text())
        for path, sha in refs(value):
            p = Path(path)
            if not p.is_absolute():
                p = ROOT / p if (ROOT / p).is_file() else original.parent / p
            try:
                key = relative(p)
            except ValueError:
                excluded_refs.append({'path': str(p), 'sha256': sha, 'reason': 'Outside original workspace; reference retained verbatim'})
                continue
            if key in mapping:
                if mapping[key]['sha256'] != sha:
                    assert 'small-review-candidate1' in original.parts, (original, key, sha, mapping[key]['sha256'])
                    superseded_refs.append({'referencing_document': relative(original), 'path': key, 'historical_sha256': sha, 'current_packaged_sha256': mapping[key]['sha256'], 'reason': 'Historical review-only candidate predates final complete180; final accepted plan/index retained separately'})
            elif forbidden(p):
                excluded_refs.append({'path': key, 'sha256': sha, 'reason': 'Runtime checkout/cache/database excluded; metadata retained verbatim'})
            else:
                copy_file(p, sha)

def copy_directory_files(path, prefix=None):
    for p in sorted(Path(path).rglob('*')):
        if p.is_file() and not p.is_symlink() and not any(x in ['__pycache__', '.jac', '.git'] for x in p.parts):
            copy_file(p, dest=(prefix + '/' + str(p.relative_to(path))) if prefix else None)

def main():
    OUT.mkdir(parents=True, exist_ok=True)
    small = json.loads((M / 'small-formal-v1/index.json').read_text())
    correctness = json.loads((M / 'apps-preflight-866222-v2/index.json').read_text())
    assert small['passed'] and small['status'] == 'complete' and len(small['cases']) == 48
    assert correctness['passed'] and correctness['status'] == 'complete' and len(correctness['cases']) == 180
    assert len(small['sources']) == 38
    # Preserve the exact archived execution closure under original workspace paths.
    archived = {digest(p): p for p in (M / 'small-formal-v1/execution-sources').iterdir() if p.is_file()}
    for original, sha in small['sources'].items():
        source = archived[sha]
        destination = 'sources/workspace/' + relative(original)
        copy_file(original, sha, destination, source)
        source_closure.append({'original': relative(original), 'sha256': sha, 'package_path': destination, 'archived_source': relative(source)})
    assert correctness['sources_before'] == correctness['sources_after']
    for original, sha in correctness['sources_before'].items():
        assert small['sources'][original] == sha
    # Include each measured/reviewed source snapshot as an alias, without duplicate blobs.
    for directory in ['small-review-ready-v1/execution-sources', 'apps-preflight-866222-v2/execution-sources']:
        for p in (M / directory).iterdir():
            if p.is_file():
                sha = digest(p)
                destination = next(x['package_path'] for x in source_closure if x['sha256'] == sha)
                bind(p, destination, sha)
    old_manifest = ROOT / 'reproduction/ttg-app-performance/suite-final-20261030-v1/snapshot.json'
    old = json.loads(old_manifest.read_text())
    assert len(old['files']) == 90
    suite_manifest = json.loads((M / 'small-review-ready-v1/suite-manifest.json').read_text())
    suite = Path(suite_manifest['root'])
    for name, sha in old['files'].items():
        assert suite_manifest['files'][name] == sha
        original = old_manifest.parent / name
        copy_file(original, sha, 'sources/workspace/' + relative(original), suite / name)
    for name, sha in suite_manifest['files'].items():
        if name not in old['files']:
            copy_file(suite / name, sha)
    copy_file(old_manifest)
    print('Source closure copied: 38 execution + 90 suite members', flush=True)
    for group, index, raw_name in [('small48', small, 'small-formal-v1'), ('correctness180', correctness, 'apps-preflight-866222-v2')]:
        for number, case in enumerate(index['cases'], 1):
            assert case['passed']
            ref = case.get('raw_seal', case.get('evidence'))
            name = Path(ref['path']).parent.name
            archive_seal(ref['path'], name, ref['sha256'], group)
            acceptance = M / raw_name / 'cleanup-acceptance' / (name + '.json')
            assert json.loads(acceptance.read_text())['passed']
            copy_file(acceptance)
            if group == 'small48':
                copy_file(case['metrics']['path'], case['metrics']['sha256'])
            if number % 12 == 0:
                print(f'{group}: {number}/{len(index["cases"])} archives verified', flush=True)
        copy_file(M / raw_name / 'index.json')
    for name in ['sql-41260-v3', 'overhead-41260-v1']:
        archive_seal(M / name / 'artifacts.json', name, category='controls')
    copy_directory_files(M / 'small-export-v1', 'results/small-export-v1')
    copy_directory_files(M / 'small-report-v1', 'report/small-report-v1')
    for name, sha in {
        'audit_small_actual_v1.py': 'ea0e52da7b7ff8f2b81a5b110864850fe3fd60bdb5b38baa7c1b1a1486c72a9b',
        'small_render_v1.py': json.loads((M / 'small-report-v1/report-integrity.json').read_text())['renderer']['sha256'],
    }.items():
        p = ROOT / 'reproduction/ttg-continuation-performance' / name
        copy_file(p, sha, 'sources/supplemental/' + relative(p))
    for name in ['small-review-ready-v1', 'main-small-actual-audit-v1', 'main-complete180-review-v1',
                 'main-small-candidate1-source-review', 'main-component-review-866222-v1',
                 'apps-preflight-866222-v2-final-audit', 'small-unit-v1', 'small-recorded-shape-v1',
                 'sql-41260-v3-supplement-v1', 'component-binding-866222-v2', 'overhead-41260-v1-export']:
        directory = M / name
        for p in sorted(directory.rglob('*')):
            if not p.is_file() or 'TEMPLATE' in p.name or 'execution-sources' in p.parts or 'suite' in p.parts or '__pycache__' in p.parts:
                continue
            copy_file(p)
    for name in ['formal-run-authorization.json', 'cleanup-v2-main-review.json', 'small-performance-plan.md', 'apps-preflight-v2-launch-plan.md']:
        copy_file(M / name)
    copy_directory_files(ROOT / 'project-notes/measurements/ttg-continuation-runtime-20261030/release-v3')
    # Only explicit metadata from stopped owned clusters; never discover or copy PG data.
    for cluster in ['pg-small-formal-v1', 'pg-apps-866222-v2']:
        for name in ['owner.json', 'ownership-and-cleanup.jsonl', 'startup.log', 'init.log', 'admin.log']:
            copy_file(ROOT / 'reproduction/ttg-continuation-performance' / cluster / name)
    collect_references()
    write_json(OUT / 'manifests/execution-source-closure.json', source_closure)
    write_json(OUT / 'manifests/archive-members.json', archives)
    write_json(OUT / 'manifests/path-mapping.json', sorted(mapping.values(), key=lambda x: x['original']))
    write_json(OUT / 'manifests/excluded-references.json', excluded_refs)
    write_json(OUT / 'manifests/superseded-references.json', superseded_refs)
    print(json.dumps({'archives': len(archives), 'small48': 48, 'correctness180': 180, 'controls': 2,
                      'mapped_original_paths': len(mapping), 'excluded_references': len(excluded_refs),
                      'compressed_bytes': sum(x['compressed_bytes'] for x in archives)}, indent=2), flush=True)

if __name__ == '__main__':
    main()
