#!/usr/bin/env python3
"""Copy bounded suite evidence into a durable review directory with integrity hashes."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

ARTIFACTS = ['summary.json', 'steps.json', 'native-steps.json', 'requests.json',
             'browser-result.json', 'browser.png', 'browser-trace.zip', 'browser.log',
             'browser-download.txt', 'source-adaptation.json', 'expected-state.json']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cases', type=Path, nargs='+', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    index = []
    for case in args.cases:
        summary = json.loads((case / 'summary.json').read_text())
        destination = args.output / summary['app']
        destination.mkdir()
        for name in ARTIFACTS:
            if (case / name).exists():
                shutil.copyfile(case / name, destination / name)
        # Keep native startup/restart and database diagnostics, including failures.
        for path in case.glob('*.log'):
            shutil.copyfile(path, destination / path.name)
        snapshot = destination / 'source-snapshot'
        snapshot.mkdir()
        for name in ['server.jac', 'server.impl.jac', 'native_seed.py', 'jac.toml']:
            if (case / name).exists():
                shutil.copyfile(case / name, snapshot / name)
        for name in ['manifest.json', 'run-manifest.json']:
            if (case.parent / name).exists():
                shutil.copyfile(case.parent / name, destination / ('run-' + name))
        index.append({'app': summary['app'], 'status': summary['status'],
                      'original_evidence_directory': str(case.resolve()),
                      'files': {str(path.relative_to(destination)): hashlib.sha256(path.read_bytes()).hexdigest()
                                for path in destination.rglob('*') if path.is_file()}})
    (args.output / 'index.json').write_text(json.dumps(index, indent=2) + '\n')
    print(f'Collected {len(index)} application cases into {args.output}')


if __name__ == '__main__':
    main()
