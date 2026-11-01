#!/usr/bin/env python3
"""Materialize portable sources; invoke their unchanged reviewed entrypoints."""
import argparse,hashlib,importlib.util,json,os,runpy,shutil,subprocess,sys
from pathlib import Path
PACKAGE=Path(__file__).resolve().parents[1]
BASELINE='85026d486de8e16d4b894aa5a5664c7873893e89'
COMMIT='9282e246d708aff69e21cb52b9d0cc4893fc5f0f'
PREFIX='/home/baichuan/jaseci/'

def sha(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def copy_tree(source,target):
    for p in source.rglob('*'):
        if p.is_file():
            q=target/p.relative_to(source);q.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,q);assert sha(p)==sha(q)
def mapped(original):
    rows=json.loads((PACKAGE/'manifests/path-mapping.json').read_text());row=next(r for r in rows if r['original']==original)
    assert 'archive_member' not in row;path=PACKAGE/row['package_path'];assert sha(path)==row['sha256'];return path,row

def materialize(workspace):
    assert not workspace.exists(),'Use a NEW workspace'
    copy_tree(PACKAGE/'sources/workspace',workspace)
    dependency=workspace/'reproduction/ttg-continuation-performance/runtime-clean-866222f90-v1/jac/jaclang/vendor/typeshed/stdlib'
    copy_tree(PACKAGE/'sources/runtime-dependencies/typeshed/stdlib',dependency)
    metadata=('reproduction/ttg-app-performance/suite-final-20261030-v1/snapshot.json',
        'project-notes/measurements/ttg-app-performance-20261030/set-field-schema-v1.json')
    for name in metadata:
        source,row=mapped(name);target=workspace/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target);assert sha(target)==row['sha256']
    relocations=[]
    for name,key in (
        ('project-notes/measurements/ttg-continuation-performance-20261030/small-review-ready-v1/instrument.json','sources'),
        ('project-notes/measurements/ttg-plus-performance-20261031/formal-review-ready-v1/sources.json','files')):
        source,row=mapped(name);value=json.loads(source.read_text());relocated={}
        for original,wanted in value[key].items():
            assert original.startswith(PREFIX);target=workspace/original.removeprefix(PREFIX);assert sha(target)==wanted
            relocated[str(target)]=wanted
        value[key]=relocated
        value['reproduction_relocation']=dict(original_path=name,original_sha256=row['sha256'],workspace=str(workspace),source_bytes_identical=True,scope='Only metadata source locations change; captured originals remain archived verbatim')
        target=workspace/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_text(json.dumps(value,indent=2)+'\n')
        relocations.append(dict(original=name,original_sha256=row['sha256'],relocated_sha256=sha(target)))
    (workspace/'reproduction-relocation.json').write_text(json.dumps(dict(source_bytes_identical=True,metadata=relocations,formal_authorization_copied=False),indent=2)+'\n')
    print('Source153, application snapshot, ignored stdlib typing dependency and explicit metadata relocations materialized. No experiment executed.')

def module(path,name):
    spec=importlib.util.spec_from_file_location(name,path);value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value

def runtimes(workspace,repository):
    assert subprocess.check_output(['git','-C',str(repository),'rev-parse','HEAD'],text=True).strip()==COMMIT,'Checkout the tested9282 commit in the supplied repository'
    assert not subprocess.check_output(['git','-C',str(repository),'status','--porcelain'],text=True),'Use a clean supplied Git repository'
    plus=workspace/'reproduction/ttg-plus-performance';nxt=workspace/'reproduction/ttg-next-performance';previous=workspace/'reproduction/ttg-continuation-performance'
    sys.path[:0]=[str(nxt),str(plus),str(previous)]
    baseline_repo=workspace/'.runtime-repositories/baseline850';baseline_repo.parent.mkdir(parents=True,exist_ok=True)
    subprocess.run(['git','-C',str(repository),'worktree','add','--detach',str(baseline_repo),BASELINE],check=True)
    old=module(plus/'snapshot.py','portable_baseline_snapshot')
    proof,_=mapped('project-notes/measurements/ttg-plus-main-20261031/acl-runtime-main-verification.json')
    clean=old.freeze(baseline_repo,BASELINE,proof,plus/'runtime-clean-final-v2');direct=old.direct(clean,plus/'runtime-direct-final-v2')
    new=module(nxt/'snapshot.py','portable_next_snapshot');proof,_=mapped('project-notes/measurements/ttg-next-20261101/verification.json')
    next_clean=new.freeze(repository,COMMIT,proof,nxt/'runtime-clean-reproduced');next_direct=new.direct(next_clean,nxt/'runtime-direct-reproduced')
    print(json.dumps(dict(baseline_clean=str(clean),baseline_direct=str(direct),next_clean=str(next_clean),next_direct=str(next_direct)),indent=2))

def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='action',required=True)
    m=sub.add_parser('materialize');m.add_argument('workspace',type=Path)
    r=sub.add_parser('runtime');r.add_argument('workspace',type=Path);r.add_argument('--repository',type=Path,required=True)
    c=sub.add_parser('run');c.add_argument('workspace',type=Path);c.add_argument('--postgres-bin',type=Path);c.add_argument('--python',type=Path);c.add_argument('script');c.add_argument('arguments',nargs=argparse.REMAINDER)
    a=p.parse_args();workspace=a.workspace.resolve()
    if a.action=='materialize':materialize(workspace);return
    if a.action=='runtime':runtimes(workspace,a.repository.resolve());return
    nxt=workspace/'reproduction/ttg-next-performance';plus=workspace/'reproduction/ttg-plus-performance';previous=workspace/'reproduction/ttg-continuation-performance'
    assert Path(a.script).name==a.script and a.script.endswith('.py'),'Select a packaged script basename'
    target=nxt/a.script;assert target.is_file(),'Packaged entrypoint absent'
    sys.path[:0]=[str(nxt),str(plus),str(previous)]
    if a.postgres_bin:
        import owned_postgres
        owned_postgres.BIN=a.postgres_bin.resolve();os.environ['JAC_PG_DIST']=str(a.postgres_bin.resolve().parent)
    if a.python:os.environ['TTG_PYTHON']=str(a.python.resolve())
    os.environ['PYTHONDONTWRITEBYTECODE']='1';sys.argv=[str(target),*a.arguments];runpy.run_path(str(target),run_name='__main__')
if __name__=='__main__':main()
