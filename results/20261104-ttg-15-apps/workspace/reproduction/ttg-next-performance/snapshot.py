"""Immutable hardlink snapshots; changed bytes always use atomic replacement."""
import argparse,difflib,json,os,subprocess,tempfile
from pathlib import Path
from next_config import OWN,PLUS,PREVIOUS
from next_interop import read_json,require,sha256,reference
import boundary_overlay as reviewed

def atomic(path,data,mode=0o644):
    path.parent.mkdir(parents=True,exist_ok=True)
    fd,temp=tempfile.mkstemp(prefix='.new-',dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as file:file.write(data)
        os.chmod(temp,mode);os.replace(temp,path)
    finally:
        if os.path.exists(temp):os.unlink(temp)

def members(root):
    result={}
    for p in sorted(root.rglob('*')):
        require(not p.is_symlink(),'Snapshot symlink is unsupported')
        if p.is_file():result[str(p.relative_to(root))]=sha256(p)
    return result

def links(manifest,target):
    require(target.is_relative_to(OWN) and not target.exists(),'New owned immutable target required')
    target.mkdir(parents=True)
    for name in manifest['files']:
        source=Path(manifest['root'])/name;dest=target/name
        require(source.is_file() and not source.is_symlink(),'Missing immutable source member')
        dest.parent.mkdir(parents=True,exist_ok=True);os.link(source,dest)

def freeze(repo,commit,proof_path,target):
    repo=repo.resolve();target=target.resolve();proof=read_json(proof_path)
    require(proof.get('passed') is True and proof.get('runtime_commit',proof.get('commit'))==commit,'Tested immutable runtime proof required')
    require(subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip()==commit,'Clean final HEAD differs')
    require(not subprocess.check_output(['git','-C',str(repo),'status','--porcelain'],text=True),'Final source is dirty')
    base_path=PLUS/'runtime-clean-final-v2-manifest/manifest.json';base=read_json(base_path)
    require(base['commit']=='85026d486de8e16d4b894aa5a5664c7873893e89','Wrong immutable850 base')
    links(base,target);expected=dict(base['files'])
    raw=subprocess.check_output(['git','-C',str(repo),'diff','--name-status','--no-renames','-z',base['commit'],commit]).split(b'\0')
    changes=[]
    for index in range(0,len(raw)-1,2):
        status=raw[index].decode();name=raw[index+1].decode();dest=target/name
        require(dest.resolve().is_relative_to(target),'Git path escapes owned snapshot')
        if status=='D':
            if dest.exists():dest.unlink()
            expected.pop(name,None)
        else:
            data=subprocess.check_output(['git','-C',str(repo),'show',commit+':'+name])
            mode=subprocess.check_output(['git','-C',str(repo),'ls-tree',commit,'--',name],text=True).split()[0]
            require(mode in ('100644','100755'),'Unsupported changed Git member kind')
            atomic(dest,data,0o755 if mode=='100755' else 0o644);expected[name]=sha256(dest)
        changes.append(dict(status=status,path=name))
    actual=members(target);require(actual==expected,'Hardlink snapshot differs from immutable base + exact Git changes')
    require(members(Path(base['root']))==base['files'],'Immutable850 base changed during snapshot construction')
    tested=proof.get('source_files',proof.get('sources',{}));require(tested,'Tested source closure absent')
    require(all(actual.get(name)==digest for name,digest in tested.items()),'Tested source does not match snapshot')
    metadata=target.parent/(target.name+'-manifest');metadata.mkdir()
    manifest=dict(kind='runtime_snapshot',immutable=True,root=str(target),commit=commit,files=actual,
        test_evidence=reference(proof_path),generator=reference(Path(__file__)),
        base_snapshot=reference(base_path),Git_changes=changes,base_after_unchanged=True,
        ignored_typeshed_source='Present immutable850 physical stdlib; hardlinked unchanged, no archived866 dependency',
        method='Immutable850 hardlinks + exact committed changed blobs via temp/os.replace; live mutable tree never linked')
    path=metadata/'manifest.json';path.write_text(json.dumps(manifest,indent=2)+'\n');return path

def direct(base_path,target):
    target=target.resolve();base=read_json(base_path);links(base,target);patch=[];bindings=[]
    def child(source):
        source=reviewed.imports(source,'import continuation_probe as _perf_sink;\n')
        return reviewed.once(source,'            bufsize=1\n','            bufsize=1,\n            env=_perf_sink.child_environment()\n')
    for relative,transform in ((reviewed.PGWIRE,reviewed.pgwire),(reviewed.PREFETCH,reviewed.prefetch),(reviewed.PROCESS,child)):
        path=target/relative;before=path.read_text();after=transform(before)
        atomic(path,after.encode())
        patch.extend(difflib.unified_diff(before.splitlines(True),after.splitlines(True),fromfile='a/'+str(relative),tofile='b/'+str(relative)))
        bindings.append(dict(path=str(relative),base_sha256=base['files'][str(relative)],effective_sha256=sha256(path)))
    require(members(Path(base['root']))==base['files'],'Clean immutable base changed during direct overlay')
    metadata=target.parent/(target.name+'-overlay');metadata.mkdir();p=metadata/'direct.patch';p.write_text(''.join(patch))
    manifest=dict(kind='experiment_overlay',root=str(target),files=members(target),base_runtime_manifest_sha256=sha256(base_path),
        patch=reference(p),bindings=bindings,generator=reference(Path(__file__)),clean_after_unchanged=True,
        reviewed_driver_transform=reference(PREVIOUS/'boundary_overlay.py'),reviewed_probe=reference(PREVIOUS/'continuation_probe.py'),
        scope='Unchanged reviewed direct clocks/counters and inherited child identity; compact HTTP outcome observer separately source-bound')
    path=metadata/'manifest.json';path.write_text(json.dumps(manifest,indent=2)+'\n');return path

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('stage',choices=('freeze','direct'))
    p.add_argument('--repository',type=Path);p.add_argument('--commit');p.add_argument('--proof',type=Path)
    p.add_argument('--base',type=Path);p.add_argument('--target',type=Path,required=True);a=p.parse_args()
    print(freeze(a.repository,a.commit,a.proof.resolve(),a.target) if a.stage=='freeze' else direct(a.base.resolve(),a.target))
