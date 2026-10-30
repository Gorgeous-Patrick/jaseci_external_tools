#!/usr/bin/env python3
"""Create NEW coherent source snapshots, including JSON registry and typeshed."""
import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parents[2]
OWN = Path(__file__).resolve().parent
COMMIT = '5f94eb62da2857ab991de704935e7333b405cb8e'
EXTENSIONS = {'.py', '.pyi', '.jac', '.js', '.mjs', '.html', '.css', '.sh', '.toml', '.json', '.yaml', '.yml', '.txt', '.md'}
EXCLUDED = {'__pycache__', '.jac', 'node_modules', '.git', '.venv', 'venv', '.cache'}

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def sources(root):
    return {str(p.relative_to(root)): sha(p) for p in sorted(root.rglob('*'))
            if p.is_file() and p.suffix in EXTENSIONS
            and not any(part in EXCLUDED for part in p.relative_to(root).parts)}

def seal(target, manifest):
    (target / 'snapshot.json').write_text(json.dumps(manifest, indent=2) + '\n')
    for p in target.rglob('*'):
        if p.is_file():
            p.chmod(0o444 | (p.stat().st_mode & 0o111))

def freeze_runtime():
    source = ROOT / 'jac-ttg'
    head = subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip()
    if head != COMMIT or subprocess.check_output(['git', '-C', str(source), 'status', '--porcelain']):
        raise RuntimeError('Expected exact clean runtime commit ' + COMMIT)
    target = OWN / 'runtime-5f94eb62d-v2'
    target.mkdir(exist_ok=False)
    archive = subprocess.check_output(['git', '-C', str(source), 'archive', head])
    with tarfile.open(fileobj=io.BytesIO(archive)) as bundle:
        bundle.extractall(target, filter='data')
    relative = Path('jac/jaclang/vendor/typeshed/stdlib')
    before = sources(source / relative)
    shutil.copytree(source / relative, target / relative)
    if before != sources(source / relative) or sources(target / relative) != before:
        raise RuntimeError('Typeshed changed during snapshot')
    files = {str(p.relative_to(target)): sha(p) for p in sorted(target.rglob('*')) if p.is_file()}
    seal(target, dict(schema_version=1, kind='runtime', commit=head,
        method='clean git archive plus explicitly copied ignored typeshed stdlib',
        source=str(source), files=files, supplemental_dependencies={str(relative): before},
        copied_utc=datetime.now(timezone.utc).isoformat()))
    return target

def freeze_suite(name, final=False):
    target = OWN / name
    target.mkdir(exist_ok=False)
    external = ROOT / 'jaseci_external_tools'
    roots = {'app_suite': external / 'app_suite', 'datasets/ttg': external / 'datasets/ttg'}
    singles = {f'originals/{app}/{filename}': ROOT / directory / filename
               for app, directory in [('jacord', 'Jacord'), ('jdrive', 'JDrive')]
               for filename in ['server.jac', 'server.impl.jac']}
    singles.update({'originals/linked_list/main.jac': external / 'linked_list/main.jac',
                    'originals/littlex/server.jac': external / 'littlex5/server.jac'})
    def collect():
        origins = {f'{prefix}/{rel}': str(source / rel)
                   for prefix, source in roots.items() for rel in sources(source)}
        origins.update({name: str(p) for name, p in singles.items()})
        return origins, {name: sha(Path(path)) for name, path in origins.items()}
    origins, before = collect()
    for name, path in origins.items():
        out = target / name
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, out)
    origins_after, after = collect()
    if before != after or origins != origins_after or any(sha(target / n) != h for n, h in before.items()):
        raise RuntimeError('Sources changed during copy; retry into a NEW snapshot directory')
    seal(target, dict(schema_version=1, kind='suite', final=final, files=before, origins=origins,
        before_sha256=hashlib.sha256(json.dumps(before, sort_keys=True).encode()).hexdigest(),
        after_sha256=hashlib.sha256(json.dumps(after, sort_keys=True).encode()).hexdigest(),
        copied_utc=datetime.now(timezone.utc).isoformat()))
    return target

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', action='store_true')
    parser.add_argument('--suite-name')
    parser.add_argument('--final', action='store_true', help='Candidate only; does not authorize formal runs')
    args = parser.parse_args()
    if args.runtime:
        print(freeze_runtime())
    if args.suite_name:
        print(freeze_suite(args.suite_name, args.final))
