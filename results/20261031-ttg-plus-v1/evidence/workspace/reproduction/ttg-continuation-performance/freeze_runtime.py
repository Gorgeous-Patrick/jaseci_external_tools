"""NEW clean git archive plus explicitly hashed ignored typeshed dependency."""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
from boundary_overlay import OWN
from evidence import sha256,read_json,checked_ref
from gate import check_tree


def files(root):
    result={}
    for path in sorted(root.rglob('*')):
        if path.is_symlink(): raise ValueError('Snapshot dependencies must be copied, not symlinked')
        if path.is_file(): result[str(path.relative_to(root))]=sha256(path)
    return result


def git(repo,*args): return subprocess.check_output(['git','-C',str(repo),*args],text=True).strip()


def freeze(repo,commit,test_evidence,target):
    repo=repo.resolve();target=target.resolve();test_evidence=test_evidence.resolve()
    if not re.fullmatch('[0-9a-f]{40}',commit): raise ValueError('Full commit hash required')
    if not target.is_relative_to(OWN) or target==OWN or target.exists(): raise ValueError('NEW owned snapshot required')
    if git(repo,'rev-parse','HEAD')!=commit or git(repo,'status','--porcelain'):
        raise ValueError('Expected exact clean runtime commit')
    tests=read_json(test_evidence)
    if tests.get('passed') is not True: raise ValueError('Passed main runtime evidence required')
    if tests.get('runtime_commit')!=commit: raise ValueError('Main runtime tests refer to another commit')
    for name,expected in tests['source_files'].items():
        if sha256(repo/name)!=expected:raise ValueError('Main tested source differs: '+name)
    for reference in tests.get('evidence',[]):checked_ref(reference,test_evidence.parent)
    metadata=target.parent/(target.name+'-manifest')
    if metadata.exists(): raise ValueError('Metadata path already exists')
    target.mkdir();metadata.mkdir()
    process=subprocess.Popen(['git','-C',str(repo),'archive',commit],stdout=subprocess.PIPE)
    with tarfile.open(fileobj=process.stdout,mode='r|') as archive:
        archive.extractall(target,filter='data')
    if process.wait()!=0: raise RuntimeError('git archive failed')
    relative=Path('jac/jaclang/vendor/typeshed/stdlib')
    before=files(repo/relative)
    shutil.copytree(repo/relative,target/relative)
    after=files(repo/relative)
    if before!=after or files(target/relative)!=before: raise ValueError('Typeshed changed during copy')
    if git(repo,'rev-parse','HEAD')!=commit or git(repo,'status','--porcelain'):
        raise ValueError('Runtime source changed during snapshot')
    all_files=files(target)
    manifest=dict(schema_version=1,kind='runtime_snapshot',immutable=True,root=str(target),commit=commit,
        continuation_dispatch='runtime_hooks',files=all_files,
        test_evidence=dict(path=str(test_evidence),sha256=sha256(test_evidence)),
        supplemental_dependencies={str(relative):dict(before=before,after=after)},
        method='Exact clean git archive plus coherent copied ignored typeshed stdlib; no live symlinks',
        copied_utc=datetime.now(timezone.utc).isoformat(),
        generator=dict(path=str(Path(__file__).resolve()),sha256=sha256(__file__)))
    path=metadata/'manifest.json';path.write_text(json.dumps(manifest,indent=2)+'\n')
    for item in target.rglob('*'):
        if item.is_file(): item.chmod(0o444|(item.stat().st_mode&0o111))
    check_tree(path)
    return path


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repository',type=Path,required=True)
    parser.add_argument('--commit',required=True)
    parser.add_argument('--test-evidence',type=Path,required=True)
    parser.add_argument('--target',type=Path,required=True)
    args=parser.parse_args();print(freeze(args.repository,args.commit,args.test_evidence,args.target))


if __name__=='__main__': main()
