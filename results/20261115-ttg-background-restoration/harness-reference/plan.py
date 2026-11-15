"""Bind fresh restoration trials to two immutable source versions, once."""
import argparse,json,os
from pathlib import Path
from ia_config import ROOT,OWN,EVIDENCE,MODES,APPS,APP_SNAPSHOT,run_config,schedule,runtime_key
from ia_interop import read_json,reference
OLD=ROOT/'project-notes/measurements/ttg-background-pushdown-performance-20261115'
def build(clean,overlay,verification,disabled_proof,output):
 output=Path(output).resolve();assert output.is_relative_to(EVIDENCE) and not output.exists()
 verification=Path(verification).resolve();disabled_proof=Path(disabled_proof).resolve()
 assert read_json(verification)['passed'] and read_json(disabled_proof)['passed']
 old=read_json(OLD/'plan-v1/plan.json')
 runtimes=dict(previous_background=old['runtimes'],restored=dict(clean=reference(clean),overlay=reference(overlay)))
 # Carry the accepted exact source closure; add fresh own source and runtime
 # bytes. Prior artifacts are references, never rewritten or sample inputs.
 files=dict(read_json(old['sources']['path'])['files'])
 for pair in runtimes.values():
  for ref in pair.values():
   assert reference(ref['path'])==ref
   m=read_json(ref['path']);root=Path(m['root']);assert root.is_dir()
   files[ref['path']]=ref['sha256'];files.update({str(root/n):h for n,h in m['files'].items()})
 for p in OWN.glob('*.py'):files[str(p.resolve())]=reference(p)['sha256']
 for p in (verification,disabled_proof):files[str(p)]=reference(p)['sha256']
 output.mkdir();sources=output/'sources.json';sources.write_text(json.dumps(dict(files=files),indent=2)+'\n')
 plan=dict(kind='ttg-background-pushdown-restoration-performance-20261115-v1',seed=42,
  sources=reference(sources),runtimes=runtimes,runtime_by_policy={m:runtime_key(m) for m in MODES},
  runtime_verification=reference(verification),disabled_branch_proof=reference(disabled_proof),
  previous_tested_source_manifest=reference(ROOT/'project-notes/measurements/ttg-background-pushdown-20261115/final-source-v1/manifest.json'),
  previous_plan=reference(OLD/'plan-v1/plan.json'),app_snapshot=reference(APP_SNAPSHOT),
  configs={m:run_config(m) for m in MODES},apps=list(APPS),stages={s:schedule(s) for s in ('correctness','primary')},
  counts=dict(correctness=16,excluded_warmups=4,measured=20,total=40),storage=old['storage'],regime=old['regime'],
  labels=dict(off='Off, restored runtime disabled',conservative='Old Conservative, frozen711d tested source',background='Previous Background, frozen711d tested source',restored='Restored Background, new tested source'),
  pending_integration=False,formal_release=dict(path=str(EVIDENCE/'formal-run-authorization.json'),contract='Main authorization binds exact plan and complete passed16 correctness; restored recursive activation/count/cache artifact and capacity reviewed before primary.'),
  comparison='Fresh matched state and fresh n5 samples in all four cells; old Conservative and previous Background use frozen711d, Off and restored Background use the new runtime; no historical timing pooling. Old resolver parser was refactored in new source, so oldCS uses original frozen implementation.',
  mechanism='JDrive correctness must show actual recursive SQL execution, complete native cache evidence, and all-role data/control/TOTAL comparison. Publication counters alone are not timely-hit evidence.')
 p=output/'plan.json';p.write_text(json.dumps(plan,indent=2)+'\n');print(json.dumps(dict(passed=True,plan=reference(p),sources=reference(sources),counts=plan['counts'])))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--clean-manifest',required=True,type=Path);p.add_argument('--overlay-manifest',required=True,type=Path);p.add_argument('--verification',required=True,type=Path);p.add_argument('--disabled-proof',required=True,type=Path);p.add_argument('--output',required=True,type=Path)
 a=p.parse_args();build(a.clean_manifest,a.overlay_manifest,a.verification,a.disabled_proof,a.output)
