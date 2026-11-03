"""NEW owned tested git snapshot + reviewed direct boundary; no live edits."""
import argparse
import difflib
import json
from pathlib import Path
import shutil
import subprocess
import tarfile
from plus_config import OWN,PREVIOUS,EVIDENCE
from interop import require,read_json,sha256,reference,check_tree
import boundary_overlay as reviewed


def members(root):
    result={}
    for path in sorted(root.rglob('*')):
        require(not path.is_symlink(),'Immutable snapshot cannot contain symlinks')
        if path.is_file():result[str(path.relative_to(root))]=sha256(path)
    return result


def budget_contract(root):
    # Exact source strings are included so a changed interface fails review;
    # this function does not modify the already repaired/budgeted final source.
    paths=('jac/jaclang/runtime/ttg_continuation.jac',
           'jac/jaclang/runtime/impl/ttg.impl.jac',
           'jac/jaclang/runtime/ttg_dependency_prefetch.jac')
    records={name:dict(sha256=sha256(root/name),has32768='32768' in (root/name).read_text()) for name in paths}
    require(all(v['has32768'] for v in records.values()),'Common32768 planner/wrapper/caller budget missing')
    return records


def freeze(repo,commit,proof_path,target):
    require(target.is_relative_to(OWN) and not target.exists(),'NEW owned runtime target required')
    head=subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip()
    dirty=subprocess.check_output(['git','-C',str(repo),'status','--porcelain'],text=True)
    require(head==commit and not dirty,'Exact final CLEAN tested commit required')
    proof=read_json(proof_path)
    require(proof.get('passed') is True,'Passed final runtime verification required')
    require(proof.get('runtime_commit',proof.get('commit'))==commit,'Final proof commit differs')
    source_hashes=proof.get('source_files',proof.get('sources',{}))
    require(source_hashes and all(sha256(repo/k)==v for k,v in source_hashes.items()),'Tested source hashes differ')
    target.mkdir();archive=subprocess.Popen(['git','-C',str(repo),'archive',commit],stdout=subprocess.PIPE)
    with tarfile.open(fileobj=archive.stdout,mode='r|') as tar:tar.extractall(target,filter='data')
    require(archive.wait()==0,'git archive failed')
    relative=Path('jac/jaclang/vendor/typeshed/stdlib')
    # Previously frozen ignored dependency is immutable and byte-bound.
    dependency=PREVIOUS/'runtime-clean-866222f90-v1'/relative
    shutil.copytree(dependency,target/relative)
    metadata=target.parent/(target.name+'-manifest');metadata.mkdir()
    manifest=dict(kind='runtime_snapshot',immutable=True,root=str(target),commit=commit,
        files=members(target),test_evidence=reference(proof_path),common_budget=budget_contract(target),
        ignored_typeshed_source=dict(root=str(dependency),files=members(dependency)),
        generator=reference(__file__),method='Clean final git archive + byte-bound immutable ignored typeshed copy')
    path=metadata/'manifest.json';path.write_text(json.dumps(manifest,indent=2)+'\n');check_tree(path)
    return path


def direct(base_manifest,target):
    base=check_tree(base_manifest);require(target.is_relative_to(OWN) and not target.exists(),'NEW owned DIRECT target required')
    shutil.copytree(base['root'],target);patches=[]
    transforms={reviewed.PGWIRE:reviewed.pgwire,reviewed.PREFETCH:reviewed.prefetch}
    # Child propagation needs no parent monkeypatch or transfer-method wrapper.
    # The native final reader can add load_query/load_projection methods freely.
    def child(source):
        source=reviewed.imports(source,'import continuation_probe as _perf_sink;\n')
        return reviewed.once(source,'            bufsize=1\n',
            '            bufsize=1,\n            env=_perf_sink.child_environment()\n')
    transforms[reviewed.PROCESS]=child
    bindings=[]
    for relative,transform in transforms.items():
        path=target/relative;before=path.read_text();after=transform(before);path.write_text(after)
        patches.extend(difflib.unified_diff(before.splitlines(True),after.splitlines(True),
            fromfile='a/'+str(relative),tofile='b/'+str(relative)))
        bindings.append(dict(path=str(relative),base_sha256=sha256(Path(base['root'])/relative),effective_sha256=sha256(path)))
    metadata=target.parent/(target.name+'-overlay');metadata.mkdir()
    patch=metadata/'direct.patch';patch.write_text(''.join(patches))
    manifest=dict(kind='experiment_overlay',root=str(target),files=members(target),
        base_runtime_manifest_sha256=sha256(base_manifest),same_for_all_configurations=True,
        patch=reference(patch),bindings=bindings,reviewed_driver_transform=reference(PREVIOUS/'boundary_overlay.py'),
        reviewed_probe=reference(PREVIOUS/'continuation_probe.py'),generator=reference(__file__),
        scope='Identical reviewed PgWire timing/counters; explicit worker inheritance and automatic child SQL sink; no close waits',
        IPC_phase='Native startup metrics retained; additional transfer-phase clocks not inserted')
    path=metadata/'manifest.json';path.write_text(json.dumps(manifest,indent=2)+'\n');check_tree(path)
    return path


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('stage',choices=('freeze','direct'))
    parser.add_argument('--repository',type=Path);parser.add_argument('--commit');parser.add_argument('--proof',type=Path)
    parser.add_argument('--base',type=Path);parser.add_argument('--target',type=Path,required=True)
    args=parser.parse_args();print(freeze(args.repository.resolve(),args.commit,args.proof.resolve(),args.target.resolve())
        if args.stage=='freeze' else direct(args.base.resolve(),args.target.resolve()))
