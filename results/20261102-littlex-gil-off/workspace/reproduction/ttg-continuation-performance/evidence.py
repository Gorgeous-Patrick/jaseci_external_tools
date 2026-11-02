"""Seal-aware readers; matching extras and duplicate raw/gzip inputs fail closed."""
import gzip
import hashlib
import json
from pathlib import Path


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text())


def checked_ref(reference, parent):
    path = Path(reference['path'])
    if not path.is_absolute():
        path = Path(parent) / path
    path = path.resolve()
    if not path.is_file() or sha256(path) != reference['sha256']:
        raise ValueError('Artifact hash mismatch: ' + str(path))
    return path


RAW_PATTERNS = ('server-*.calls.jsonl*', 'server-*.events.jsonl*',
                'requests.jsonl*', 'http-raw.jsonl*', 'workers.jsonl*',
                'profiles/*.json', 'postgres-*.csv*')


def verify_case(directory, required=(), allow_failed=False):
    directory = Path(directory).resolve()
    manifest_path = directory / 'artifacts.json'
    manifest = read_json(manifest_path)
    if manifest.get('passed') is not True and not allow_failed:
        raise ValueError('Case is not accepted')
    listed = manifest['files']
    for name in required:
        if name not in listed:
            raise ValueError('Consumed raw artifact is not sealed: ' + name)
    seen = set()
    for pattern in RAW_PATTERNS:
        for path in directory.glob(pattern):
            name = str(path.relative_to(directory))
            canonical = name.removesuffix('.gz')
            if canonical in seen:
                raise ValueError('Duplicate raw/gzip artifact: ' + canonical)
            seen.add(canonical)
            if name not in listed:
                raise ValueError('Unsealed matching raw artifact: ' + name)
    for name, digest in listed.items():
        path = (directory / name).resolve()
        if not path.is_relative_to(directory):
            raise ValueError('Artifact escapes case directory')
        if not path.is_file() or sha256(path) != digest:
            raise ValueError('Corrupt artifact: ' + name)
    return dict(path=str(manifest_path), sha256=sha256(manifest_path),
                files_checked=len(listed))


def load_jsonl(directory, pattern):
    directory = Path(directory)
    paths = sorted(directory.glob(pattern))
    verify_case(directory, required=[str(p.relative_to(directory)) for p in paths])
    result = []
    for path in paths:
        opener = gzip.open if path.suffix == '.gz' else open
        with opener(path, 'rt') as file:
            for line in file:
                if line.strip():
                    result.append(json.loads(line))
    return result
