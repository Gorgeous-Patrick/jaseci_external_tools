#!/usr/bin/env python3
"""Verify the additive report supplement and its original-file/base bindings."""
import hashlib
import json
from pathlib import Path


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def local(root, name):
    path = Path(name)
    assert not path.is_absolute() and '..' not in path.parts
    return root / path


def verify():
    root = Path(__file__).resolve().parent
    integrity = json.loads((root / 'package-integrity.json').read_text())
    for name, sha in integrity['manifest_hashes'].items():
        assert digest(local(root, name)) == sha, name
    inventory = json.loads((root / 'manifests/files.json').read_text())
    names = {item['path'] for item in inventory}
    assert len(names) == len(inventory)
    files = {str(p.relative_to(root)) for p in root.rglob('*') if p.is_file()}
    assert files == names | {'manifests/files.json', 'SHA256SUMS', 'package-integrity.json'}
    assert not any(p.is_symlink() for p in root.rglob('*'))
    for item in inventory:
        p = local(root, item['path'])
        assert p.stat().st_size == item['bytes'] < 100_000_000
        assert digest(p) == item['sha256'], item['path']
    origins = json.loads((root / 'manifests/origins.json').read_text())
    by_original = {x['original']: x for x in origins}
    for item in origins:
        assert digest(local(root, item['package_path'])) == item['sha256']
    inputs = json.loads((root / 'manifests/small-supplement-inputs-v1.json').read_text())['files']
    assert len(inputs) == 21
    for original, sha in inputs.items():
        relative = str(Path(original).relative_to('/home/baichuan/jaseci'))
        assert by_original[relative]['sha256'] == sha
    report = json.loads((root / 'report/small-report-v2/report-integrity.json').read_text())
    assert report['passed'] and report['pages'] == 7
    for name, sha in report['files'].items():
        assert digest(local(root / 'report/small-report-v2', name)) == sha
    trace = root / 'analysis/littlex-trace-attribution-v1'
    seal = json.loads((trace / 'artifacts.json').read_text())
    assert seal['passed']
    for name, sha in seal['files'].items():
        assert digest(local(trace, name)) == sha
    attribution = json.loads((trace / 'attribution.json').read_text())
    for ref in [report['renderer'], attribution['source']]:
        original = str(Path(ref['path']).relative_to('/home/baichuan/jaseci'))
        assert by_original[original]['sha256'] == ref['sha256']
    binding = json.loads((root / 'review/small-actual48-final-review-binding.json').read_text())
    for name in ['report', 'actual48_review', 'LittleX_pairs_review']:
        ref = binding[name]
        original = str(Path(ref['path']).relative_to('/home/baichuan/jaseci'))
        assert by_original[original]['sha256'] == ref['sha256']
    base = root.parent / '20261031-ttg-continuation-small'
    external = json.loads((root / 'manifests/base-bindings.json').read_text())
    for item in external:
        assert digest(local(base, item['path'])) == item['sha256'], item['path']
    print(json.dumps({'passed': True, 'files': len(files), 'copied_original_files': len(origins),
                      'base_bindings_checked': len(external), 'report_pages': 7,
                      'scope': 'Supplement bytes, source/seal/reviewer relationships and base hashes'}, indent=2))


if __name__ == '__main__':
    verify()
