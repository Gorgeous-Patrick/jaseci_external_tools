#!/usr/bin/env python3
"""Inventory source text and flag CJK script content for English review.

A script scan is evidence of inspected coverage, not a language classifier.
English prose and terminology also require a human review.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re

SUITE = Path(__file__).resolve().parent
WORKSPACE = SUITE.parent.parent
CJK = re.compile(r'[\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af]')
EXTENSIONS = {'.py', '.jac', '.md', '.html', '.js', '.mjs', '.css', '.toml', '.sh'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    directories = [SUITE, SUITE.parent / 'datasets' / 'ttg']
    paths = [p for directory in directories for p in directory.rglob('*')
             if p.is_file() and p.suffix in EXTENSIONS and '.jac' not in p.parts]
    for directory in [SUITE.parent / 'linked_list', SUITE.parent / 'littlex5',
                      WORKSPACE / 'Jacord', WORKSPACE / 'JDrive']:
        paths.extend(p for p in directory.iterdir() if p.is_file() and p.suffix in EXTENSIONS)
        for child in ['components', 'tests']:
            if (directory / child).exists():
                paths.extend(p for p in (directory / child).rglob('*')
                             if p.is_file() and p.suffix in EXTENSIONS)
    findings, inventory = [], []
    for path in sorted(set(paths)):
        raw = path.read_bytes()
        relative = str(path.relative_to(WORKSPACE))
        inventory.append({'path': relative, 'sha256': hashlib.sha256(raw).hexdigest()})
        for number, line in enumerate(raw.decode('utf-8').splitlines(), 1):
            if CJK.search(line):
                findings.append({'path': relative, 'line': number, 'text': line})
    result = {'scope': 'Suite, original-four top-level source/docs, components and tests; historical logs/archives excluded',
              'method': 'CJK script scan plus recorded file hashes; English prose needs editorial review',
              'files_scanned': len(inventory), 'findings': findings, 'inventory': inventory}
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n')
    print(f'English source audit: {len(inventory)} files; {len(findings)} CJK findings')
    return bool(findings)


if __name__ == '__main__':
    raise SystemExit(main())
