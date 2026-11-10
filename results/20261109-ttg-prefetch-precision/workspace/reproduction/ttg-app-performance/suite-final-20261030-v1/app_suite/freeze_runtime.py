#!/usr/bin/env python3
"""Copy an immutable runtime source snapshot without modifying the shared checkout."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess


def inventory(directory):
    return {str(path.relative_to(directory)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in directory.rglob('*') if path.is_file() and path.suffix in ('.jac', '.py')
            and not any(part in ('.git', '.jac', '__pycache__', 'node_modules') for part in path.parts)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    source = args.source.resolve()
    output = args.output.resolve()
    before = inventory(source / 'jac' / 'jaclang')
    output.mkdir(parents=True, exist_ok=False)
    shutil.copytree(source / 'jac' / 'jaclang', output / 'jac' / 'jaclang',
                    ignore=shutil.ignore_patterns('.git', '.jac', '__pycache__', 'node_modules', '*.pyc'))
    for path in (source / 'jac').iterdir():
        if path.is_file():
            shutil.copyfile(path, output / 'jac' / path.name)
    after = inventory(source / 'jac' / 'jaclang')
    copied = inventory(output / 'jac' / 'jaclang')
    if before != after or copied != after:
        raise RuntimeError('Runtime source changed during copying; the incomplete snapshot is retained but must not be used')
    head = subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip()
    status = subprocess.check_output(['git', '-C', str(source), 'status', '--porcelain'], text=True)
    manifest = {'source_checkout': str(source), 'source_head': head, 'source_status': status,
                'snapshot_path': str(output), 'runtime_source_sha256': copied,
                'snapshot_contract': 'Source hashes identical before copy, after copy and in snapshot; no shared source edits'}
    (output / 'snapshot.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(f'Frozen {len(copied)} runtime source files into {output}')


if __name__ == '__main__':
    main()
