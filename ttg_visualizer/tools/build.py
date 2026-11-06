"""Build Jac, then stage a self-contained HTTP-served viewer under dist/."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--stage-only', action='store_true', help='Stage an already successful Jac build')
    a = p.parse_args()
    if not a.stage_only:
        subprocess.run([os.environ.get('JAC', 'jac'), 'build', '--client', 'static'], cwd=ROOT, check=True)
    built = ROOT / '.jac/client/dist/index.html'
    if not built.is_file():
        raise SystemExit('Build missing: run jac build --client static')
    out = ROOT / 'dist'
    out.mkdir(exist_ok=True)
    shutil.copyfile(built, out / 'index.html')
    shutil.copytree(ROOT / 'public', out, dirs_exist_ok=True)
    tracked = ['main.jac', 'model.js', 'style.css', 'jac.toml', 'public/data/jdrive.json', 'public/data/littlex.json']
    files = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in tracked}
    result = dict(schema='jac.ttg.viewer-build', version=1, source_sha256=files,
                  index_sha256=hashlib.sha256((out / 'index.html').read_bytes()).hexdigest())
    (out / 'build-manifest.json').write_text(json.dumps(result, indent=2) + '\n')
    print(f'Ready: {out}\nServe: python3 -m http.server 8765 --bind 127.0.0.1 --directory {out}')


if __name__ == '__main__':
    main()
