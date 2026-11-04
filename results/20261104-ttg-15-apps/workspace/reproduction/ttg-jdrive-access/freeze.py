"""Freeze the tested worktree as new copies; never modify a baseline hardlink."""
import hashlib,json,os,shutil,subprocess
from pathlib import Path
ROOT=Path('/home/baichuan/jaseci');OWN=Path(__file__).resolve().parent
E=ROOT/'project-notes/measurements/ttg-jdrive-access-20261103';REPO=ROOT/'jac-ttg'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_text())
def ref(p):return dict(path=str(p),sha256=sha(p))
def checked(r):assert sha(r['path'])==r['sha256'];return read(r['path'])
def write(p,d):p.write_text(json.dumps(d,indent=2)+'\n')
def main():
 proof=E/'verification.json';v=read(proof);assert v['passed']
 for p,h in v['sources'].items():assert sha(REPO/p)==h,p
 old=read(ROOT/'project-notes/measurements/ttg-jdrive-freethreaded-20261103/comparison-v1/plan.json')
 bases={k:checked(old[k]) for k in ('clean','overlay')}
 changes=set(subprocess.check_output(['git','diff','--name-only',bases['clean']['commit'],'--','jac'],cwd=REPO,text=True).splitlines())
 changes.update(p for p in v['sources'] if p.startswith('jac/'))
 for path in changes:assert (REPO/path).is_file(),path
 # Instrumented files must be byte-identical to their accepted canonical source.
 direct=checked(bases['overlay']['base']['overlay'])
 for entry in direct['bindings']:assert sha(REPO/entry['path'])==entry['base_sha256'],entry['path']
 outputs={}
 for name in ('clean','overlay'):
  base=bases[name];target=OWN/('runtime-'+name+'-v1');assert not target.exists()
  for path,digest in base['files'].items():assert sha(Path(base['root'])/path)==digest,path
  shutil.copytree(base['root'],target,copy_function=os.link,symlinks=True)
  for path in changes:
   dest=target/path;dest.parent.mkdir(parents=True,exist_ok=True)
   temporary=dest.with_name(dest.name+'.owned-replacement')
   temporary.write_bytes((REPO/path).read_bytes());os.replace(temporary,dest)
  files=dict(base['files']);files.update({p:sha(target/p) for p in changes})
  assert all(sha(target/p)==digest for p,digest in files.items())
  manifest=E/('runtime-'+name+'-v1.json')
  write(manifest,dict(kind='tested_worktree_snapshot' if name=='clean' else 'experiment_overlay',root=str(target),
    commit=v['base_commit'],worktree_patch=True,verification=ref(proof),files=files,
    base=old[name],changes={p:files[p] for p in sorted(changes)},instrumentation=direct['bindings'] if name=='overlay' else [],
    method='Immutable existing snapshot hardlinks; every changed file replaced atomically. Canonical driver bytes unchanged.'))
  outputs[name]=ref(manifest)
 for name,base in bases.items():assert all(sha(Path(base['root'])/p)==h for p,h in base['files'].items())
 write(E/'snapshots-v1.json',dict(passed=True,**outputs,proof=ref(proof),generator=ref(Path(__file__))))
 print(json.dumps(outputs))
if __name__=='__main__':main()
