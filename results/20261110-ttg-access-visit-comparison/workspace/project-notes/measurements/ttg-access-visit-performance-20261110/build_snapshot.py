import hashlib,json,os,shutil,subprocess
from pathlib import Path
R=Path('/home/baichuan/jaseci');W=R/'jac-ttg';O=R/'reproduction/ttg-access-visit-performance-20261110';E=R/'project-notes/measurements/ttg-access-visit-performance-20261110'
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
ref=lambda p:dict(path=str(p),sha256=sha(p))
previous=json.loads((R/'project-notes/measurements/ttg-standard-access-comparison-20261109/snapshots.json').read_text())
assert previous['passed']
tracked=subprocess.check_output(['git','ls-files'],cwd=W,text=True).splitlines()
new=[p for p in subprocess.check_output(['git','ls-files','--others','--exclude-standard'],cwd=W,text=True).splitlines() if p.startswith(('jac/jaclang/runtime/ttg_access_','jac/tests/runtimelib/test_ttg_access_','jac/tests/runtimelib/fixtures/ttg_access_')) or p=='jac/tests/runtimelib/test_standard_access.jac']
instrumented={'jac/jaclang/data/impl/pgwire.impl.jac','jac/jaclang/runtime/prefetch.jac','jac/jaclang/runtime/ttg_process_reader.jac'}
commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=W,text=True).strip();manifests={}
for kind in ['clean','overlay']:
 old=json.loads(Path(previous[kind]['path']).read_text());src=Path(old['root']);dst=O/f'runtime-{kind}-v1';assert not dst.exists()
 shutil.copytree(src,dst,copy_function=os.link,ignore=shutil.ignore_patterns('__pycache__','.jac-cache','.git'))
 files=old['files'].copy();delta={}
 for p,h in files.items():assert sha(dst/p)==h,p
 for p in tracked+new:
  a=W/p
  if not a.is_file() or kind=='overlay' and p in instrumented:continue
  h=sha(a)
  if files.get(p)!=h:
   target=dst/p;target.parent.mkdir(parents=True,exist_ok=True);temp=target.with_suffix(target.suffix+'.access-tmp');shutil.copyfile(a,temp);os.replace(temp,target)
   delta[p]=dict(before=files.get(p),after=h);files[p]=h
 m=dict(old,root=str(dst),commit=commit,files=files,base=previous[kind],working_tree_delta=delta,source_workspace=str(W),source_state='Exact current working-tree source, not a clean commit claim')
 mp=E/f'{kind}-manifest.json';mp.write_text(json.dumps(m,indent=2)+'\n');manifests[kind]=ref(mp)
print({k:len(json.loads(Path(v['path']).read_text())['working_tree_delta']) for k,v in manifests.items()})
import sys
sys.path.insert(0,str(O));from ia_config import run_config
modes={}
for mode in ['aggressive','conservative']:
 profile=E/(mode+'-profile.json');profile.write_text(json.dumps(dict(run=run_config(mode)),indent=2)+'\n')
 modes[mode]=dict(workspace=str(W),profile=ref(profile),**manifests)
(E/'workspaces.json').write_text(json.dumps(dict(passed=True,runtimes=modes,shared_source_commit=commit,source_state='One matched frozen runtime from jac-ttg; aggressive execution policy unchanged, new Access plans used by conservative.',native_verification=ref(R/'project-notes/measurements/ttg-access-visit-20261110/native-v2/outcome.json')),indent=2)+'\n')
(E/'runtime.patch').write_bytes(subprocess.check_output(['git','diff','--binary'],cwd=W))
