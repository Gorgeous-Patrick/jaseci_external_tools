#!/usr/bin/env python3
"""Verify publication bytes and archive mappings without launching any experiment."""
import argparse
import hashlib
import json
from pathlib import Path
import tarfile


def sha_file(path):
    with Path(path).open('rb') as stream:
        return sha_stream(stream)


def sha_stream(stream):
    value = hashlib.sha256()
    for block in iter(lambda: stream.read(1024 * 1024), b''):
        value.update(block)
    return value.hexdigest()


def checked_path(root, name):
    path = Path(name)
    assert not path.is_absolute() and '..' not in path.parts, name
    return root / path


def verify(root, original_root=None):
    integrity = json.loads((root / 'package-integrity.json').read_text())
    assert integrity['passed'] is True
    for name, sha in integrity['manifest_hashes'].items():
        assert sha_file(checked_path(root, name)) == sha, name
    inventory = json.loads((root / 'manifests/files.json').read_text())
    expected_names = {item['path'] for item in inventory}
    excluded = {'manifests/files.json', 'SHA256SUMS', 'package-integrity.json'}
    actual_names = {str(p.relative_to(root)) for p in root.rglob('*') if p.is_file()}
    assert actual_names == expected_names | excluded, 'Missing or unexpected package files'
    assert not any(p.is_symlink() for p in root.rglob('*')), 'Symlinks are forbidden'
    for item in inventory:
        path = checked_path(root, item['path'])
        assert path.stat().st_size == item['bytes'] < 100_000_000, item['path']
        assert sha_file(path) == item['sha256'], item['path']
    archives = json.loads((root / 'manifests/archive-members.json').read_text())
    members = {}
    for archive in archives:
        path = checked_path(root, archive['package_path'])
        assert sha_file(path) == archive['sha256']
        declared = {item['member']: item for item in archive['members']}
        assert len(declared) == len(archive['members'])
        with tarfile.open(path, 'r:gz') as tar:
            seen = set()
            for item in tar:
                assert item.isfile() and item.name in declared and item.name not in seen
                expected = declared[item.name]
                assert item.size == expected['bytes']
                assert sha_stream(tar.extractfile(item)) == expected['sha256']
                members[(archive['package_path'], item.name)] = expected
                seen.add(item.name)
            assert seen == set(declared)
            seal = json.load(tar.extractfile('artifacts.json'))
            assert set(seal['files']) == seen - {'artifacts.json'}
            assert seal['passed'] == archive['original_seal_passed']
            for name, sha in seal['files'].items():
                assert declared[name]['sha256'] == sha
            assert declared['artifacts.json']['sha256'] == archive['original_seal_sha256']
    mapping = json.loads((root / 'manifests/path-mapping.json').read_text())
    originals = set()
    for item in mapping:
        assert item['original'] not in originals
        originals.add(item['original'])
        if 'archive_member' in item:
            assert members[(item['package_path'], item['archive_member'])]['sha256'] == item['sha256']
        else:
            assert sha_file(checked_path(root, item['package_path'])) == item['sha256']
        if original_root:
            assert sha_file(checked_path(original_root, item['original'])) == item['sha256'], item['original']
    def mapped_json(original):
        item = next(x for x in mapping if x['original'] == original)
        assert 'archive_member' not in item
        return json.loads(checked_path(root, item['package_path']).read_text())
    measurement = 'project-notes/measurements/ttg-continuation-performance-20261030/'
    for name, count, category in [('small-formal-v1', 48, 'small48'), ('apps-preflight-866222-v2', 180, 'correctness180')]:
        index = mapped_json(measurement + name + '/index.json')
        assert index['status'] == 'complete' and index['passed'] and len(index['cases']) == count
        selected_archives = [a for a in archives if a['package_path'].startswith('raw/' + category + '/')]
        assert len(selected_archives) == count
        seals = {a['original_seal']: a['original_seal_sha256'] for a in selected_archives}
        for case in index['cases']:
            reference = case.get('raw_seal', case.get('evidence'))
            original = measurement + name + '/' + Path(reference['path']).parent.name + '/artifacts.json'
            assert case['passed'] and seals[original] == reference['sha256']
    result = {'passed': True, 'package_files': len(actual_names), 'archives_verified': len(archives),
              'small_cases': 48, 'correctness_cases': 180, 'mapped_paths': len(mapping),
              'original_files_checked': len(mapping) if original_root else 0,
              'scope': 'Byte, seal, index and path mapping verification only; no DB/app/performance execution'}
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--original-root', type=Path)
    args = parser.parse_args()
    verify(Path(__file__).resolve().parent, args.original_root)
