#!/usr/bin/env python3
"""Materialize exact sources/dependencies; reuse original reviewed entrypoints."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import runpy
import shutil
import sys

PACKAGE=Path(__file__).resolve().parents[1]
COMMIT='85026d486de8e16d4b894aa5a5664c7873893e89'
def sha(p):
    with p.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()
def copy_tree(source,target):
    for path in source.rglob('*'):
        if path.is_file():
            destination=target/path.relative_to(source);destination.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(path,destination);assert sha(path)==sha(destination)
def mapped_file(original):
    mapping=json.loads((PACKAGE/'manifests/path-mapping.json').read_text())
    entry=next(x for x in mapping if x['original']==original)
    assert 'archive_member' not in entry
    path=PACKAGE/entry['package_path'];assert sha(path)==entry['sha256']
    return path,entry

def main():
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='action',required=True)
    m=sub.add_parser('materialize');m.add_argument('workspace',type=Path)
    r=sub.add_parser('runtime');r.add_argument('workspace',type=Path);r.add_argument('--repository',type=Path,required=True)
    c=sub.add_parser('run');c.add_argument('workspace',type=Path);c.add_argument('--postgres-bin',type=Path,required=True);c.add_argument('--python',type=Path,required=True);c.add_argument('script',choices=('review.py','runner.py','export.py','render_report.py'));c.add_argument('arguments',nargs=argparse.REMAINDER)
    args=parser.parse_args();workspace=args.workspace.resolve()
    if args.action=='materialize':
        assert not workspace.exists(),'Use a NEW workspace'
        copy_tree(PACKAGE/'sources/workspace',workspace)
        dependency=workspace/'reproduction/ttg-continuation-performance/runtime-clean-866222f90-v1/jac/jaclang/vendor/typeshed/stdlib'
        copy_tree(PACKAGE/'sources/runtime-dependencies/typeshed/stdlib',dependency)
        relative='reproduction/ttg-app-performance/suite-final-20261030-v1/snapshot.json'
        source,entry=mapped_file(relative);target=workspace/relative
        target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target);assert sha(target)==entry['sha256']
        relative='project-notes/measurements/ttg-app-performance-20261030/set-field-schema-v1.json'
        source,entry=mapped_file(relative);target=workspace/relative
        target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target);assert sha(target)==entry['sha256']
        relative='project-notes/measurements/ttg-continuation-performance-20261030/small-review-ready-v1/instrument.json'
        source,entry=mapped_file(relative);metadata=json.loads(source.read_text())
        prefix='/home/baichuan/jaseci/';relocated={}
        for original,value in metadata['sources'].items():
            assert original.startswith(prefix)
            target=workspace/original.removeprefix(prefix);assert sha(target)==value
            relocated[str(target)]=value
        metadata['sources']=relocated
        metadata['reproduction_relocation']=dict(original_path=relative,original_sha256=entry['sha256'],
            workspace=str(workspace),scope='Only source-map absolute locations change; captured source bytes remain identical. Historical measurement references are provenance, not authorization.')
        target=workspace/relative;target.parent.mkdir(parents=True,exist_ok=True)
        target.write_text(json.dumps(metadata,indent=2)+'\n')
        (workspace/'reproduction-relocation.json').write_text(json.dumps(dict(
            original_instrument_sha256=entry['sha256'],relocated_instrument_sha256=sha(target),
            source_bytes_identical=True,formal_authorization_copied=False),indent=2)+'\n')
        print('Exact sources and ignored stdlib dependency materialized. No authorization or experiment copied/run.');return
    plus=workspace/'reproduction/ttg-plus-performance';previous=workspace/'reproduction/ttg-continuation-performance'
    sys.path[:0]=[str(plus),str(previous)]
    if args.action=='runtime':
        import snapshot
        mapping=json.loads((PACKAGE/'manifests/path-mapping.json').read_text())
        original='project-notes/measurements/ttg-plus-main-20261031/acl-runtime-main-verification.json'
        entry=next(x for x in mapping if x['original']==original);proof=PACKAGE/entry['package_path']
        clean=snapshot.freeze(args.repository.resolve(),COMMIT,proof,plus/'runtime-clean-reproduced')
        direct=snapshot.direct(clean,plus/'runtime-direct-reproduced')
        print(json.dumps(dict(runtime=str(clean),overlay=str(direct)),indent=2));return
    import owned_postgres
    owned_postgres.BIN=args.postgres_bin.resolve()
    os.environ['JAC_PG_DIST']=str(args.postgres_bin.resolve().parent)
    os.environ['TTG_PYTHON']=str(args.python.resolve())
    sys.argv=[str(plus/args.script),*args.arguments]
    runpy.run_path(str(plus/args.script),run_name='__main__')
if __name__=='__main__':main()
