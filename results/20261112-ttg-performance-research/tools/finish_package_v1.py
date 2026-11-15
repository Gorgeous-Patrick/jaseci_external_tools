"""Integrate accepted sole PDF, README and reused portable verifier; seal bytes."""
import hashlib,importlib.util,json,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
OWN=Path(__file__).resolve().parent
E=ROOT/'project-notes/measurements/ttg-performance-research-20261112'
R=E.with_name(E.name+'-review')
OUT=ROOT/'jaseci_external_tools/results/20261112-ttg-performance-research'
spec=importlib.util.spec_from_file_location('nov12_package',OWN/'package_v1.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
P=m.P;P.copy_file=m.original_copy
P.mapping={r['original']:r for r in json.loads((OUT/'manifests/path-mapping.json').read_text())}
P.archives=json.loads((OUT/'manifests/archive-members.json').read_text())
P.excluded_refs=json.loads((OUT/'manifests/reference-exclusions.json').read_text())
P.superseded_refs=json.loads((OUT/'manifests/historical-references.json').read_text())
def read(p):return json.loads(p.read_text())
def ref(p):return dict(path=str(p.resolve()),sha256=P.digest(p))
def write(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,indent=2)+'\n')
def main():
 assert not (OUT/'package-integrity.json').exists()
 candidate=read(E/'final-report-candidate-v1.json');assert candidate['pages']==33
 report=candidate['sole_final_PDF'];assert report['sha256']=='717299c5cad5c6f26c825ffe5cc27252a557d3b528167d9b066ee47a82b6d690'
 for key,name in [('sole_final_PDF','ttg-performance-research.pdf'),('renderer','render_report.py'),('figure_inputs','figure-inputs.json'),('report_manifest','report-manifest.json'),('layout_checks','layout-checks.json'),('primary_CSV','primary-summary.csv'),('precision_counts','precision-counts.json')]:
  r=candidate[key];P.copy_file(r['path'],r['sha256'],'report/'+name)
 # Exact editable accepted input, also retained in the original path mapping.
 r=candidate['input'];assert P.digest(Path(r['path']))==r['sha256']
 shutil.copyfile(r['path'],OUT/'report/report-inputs.json')
 for p in [E/'final-report-candidate-v1.json',E/'main-final-report-visual-review-v1.json',R/'final-pdf-numeric-mapping-v1.json',R/'report-inputs-v2-binding-review.json',R/'diagnostic-actual-v1-review.json',E/'package-compaction-v1.json']:
  P.copy_file(p)
 for p in (Path(__file__),OWN/'compact_package_v1.py',OWN/'verify_package_v1.py'):
  P.copy_file(p,dest=('verify_package.py' if p.name=='verify_package_v1.py' else 'tools/'+p.name))
 P.collect_references()
 write(OUT/'manifests/path-mapping.json',list(P.mapping.values()))
 write(OUT/'manifests/reference-exclusions.json',P.excluded_refs)
 write(OUT/'manifests/historical-references.json',P.superseded_refs)
 required=[v for k,v in candidate.items() if isinstance(v,dict) and isinstance(v.get('path'),str) and 'sha256' in v]
 inputs=read(Path(candidate['input']['path']));required+=list(inputs['evidence'].values())+[inputs['requirements']]
 for row in inputs['cpu_diagnostic']['rows']:required.extend([row['profile'],row['validation']])
 required.extend(ref(p) for p in (E/'main-final-report-visual-review-v1.json',R/'final-pdf-numeric-mapping-v1.json'))
 required=list({(r['path'],r['sha256']):dict(path=r['path'],sha256=r['sha256']) for r in required}.values())
 write(OUT/'manifests/required-references.json',required)
 (OUT/'README.md').write_text('''# TTG performance research — 12 November 2026

[English slides (33 pages)](report/ttg-performance-research.pdf) · [editable renderer](report/render_report.py) · [primary table](report/primary-summary.csv)

This publication compares Off, original aggressive TTG and the latest conservative policy on one frozen Nov11 runtime, with real GIL-disabled Python threads, one prefetch worker and identical policy-independent settings. It retains all17 selected apps and the full20-fixture/60-policy-cell inventory. Nineteen successful fixtures have57 cells with five fresh measured workflows each;57 correctness and57 excluded warmup workflows remain separate. The two successful larger fixtures are JDrive depth5 and LittleX50×20.

LinkedList1000 remains Off correctness-only / Aggressive failed backend-isolation gate / Conservative not run after the first failure. Its failed raw evidence and source-bound disposition are retained. Its database remains local and is not packaged. These three terminal records have no timing or precision values.

The sole PDF reports instrumented HTTP response wall, all-role send-to-ReadyForQuery DB sums/unions, data SQL per business HTTP, and separate control counts. Its n5 vectors show medians and ranges. Precision is a separate n1 capture: returned/demand intersection, promotion-backed service, return-before-call subset, late rows and unused rows stay distinct. All-anchor and node ratios differ. Observed Session demand is policy-dependent and is not a business-necessity oracle; unused nodes are an observational lower bound and filter-only necessity is unmeasured. The six-workflow CPU diagnostic measures only the selected native-spawn thread; delegated/total CPU is unmeasured, observation overhead is retained, and those n1 times are not substituted into n5 latency.

## Verify without running experiments

```sh
python3 verify_package.py
```

The standard-library verifier checks package bytes,464 case archives, original seals and explicit lossless decoded representations, selection/lineage, source mapping, required references and the sole final PDF. It starts no service. `manifests/path-mapping.json` resolves original workspace paths to plain package files or archive members. `manifests/large-metadata.json` describes the compressed exact JSON metadata. Raw archives use tar.xz; original gzip traces are stored as byte-verified decoded JSONL with the original gzip hash/compression record retained. Compressed gzip bytes are not claimed identical; decoded trace bytes are identical.

## Evidence and reproduction

The464 case archives contain399 comparison records,57 precision captures,6 full native CPU-diagnostic workflows,1 extra LL1000 Off correctness record and1 failed aggressive record. Original indexes, accepted n3-prefix lineage, n5 extension, semantic/physical/source/GIL proofs, settings, cleanup and stopped-service records are preserved. `data-stage-complete.json` is the initial pre-compaction checkpoint; `package-integrity.json` and the final file inventory describe this sealed package.

`report/report-inputs.json`, `report/figure-inputs.json` and the editable renderer contain the exact final presentation inputs. Rendering used Python3.12.11 and Matplotlib3.10.5. Original absolute references are deliberately preserved; use the path mapping when materializing dependencies into a new workspace. Only the final accepted PDF is included; historical drafts and previews remain local.

`sources/workspace` preserves the unchanged captured controller/helper/app sources. `manifests/source-closure.json` retains all11640 expected source identities. Full runtime, interpreter, PostgreSQL and cache trees are excluded. `manifests/runtime-reconstruction.json` pins base commit96868d0400a2f91fbfa48112c7ee291c891d2d03 and the exact packaged implementation/observer overlays; frozen manifest hashes retain the complete expected runtime identities. The historical aggressive comparison is a scoped11-file equality proof, not whole-program historical equivalence.

To repeat measurements, reconstruct that runtime, restore the source layout using the path map, provide free-threaded CPython3.14.6 and PostgreSQL18.6, and build a NEW local plan with the captured `plan.py`. Original run configurations, seed42, request order, limits2048/32768, WAL32/64MB, ANALYZE placement and source manifests are included. Use the captured `runner.py` for original stages and `runner_v2.py` for the exact114/57 lineage-filtered continuation, with new owned output/cluster paths. Existing releases and failed observations are provenance; they do not authorize modifying or overwriting this publication. Reference exclusions name historical/runtime/environment-only provenance rather than silently substituting bytes.

No database, compilation, new benchmark or runtime change occurs during packaging. Main reviews and pushes this new result directory separately from unrelated working-tree changes.
''')
 excluded={'manifests/files.json','package-integrity.json','SHA256SUMS'}
 files=[dict(path=str(p.relative_to(OUT)),bytes=p.stat().st_size,sha256=P.digest(p)) for p in sorted(OUT.rglob('*')) if p.is_file() and str(p.relative_to(OUT)) not in excluded]
 assert all(r['bytes']<100_000_000 for r in files)
 write(OUT/'manifests/files.json',files)
 manifests=('files.json','archive-members.json','large-metadata.json','path-mapping.json','case-inventory.json','source-closure.json','required-references.json','runtime-reconstruction.json')
 integrity=dict(passed=True,report_sha256=report['sha256'],pages=33,case_archives=464,manifest_hashes={'manifests/'+n:P.digest(OUT/'manifests'/n) for n in manifests},
  files=len(files)+3,bytes_excluding_self_inventory=sum(r['bytes'] for r in files),source_builder=ref(Path(__file__)),scope='Sealed portable publication; all experiments completed before packaging')
 write(OUT/'package-integrity.json',integrity)
 (OUT/'SHA256SUMS').write_text(''.join(P.digest(p)+'  '+str(p.relative_to(OUT))+'\n' for p in sorted(OUT.rglob('*')) if p.is_file() and p.name!='SHA256SUMS'))
 print(json.dumps(dict(passed=True,integrity=ref(OUT/'package-integrity.json'),files=integrity['files'],bytes=sum(p.stat().st_size for p in OUT.rglob('*') if p.is_file()),PDF=report['sha256'])),flush=True)
if __name__=='__main__':main()
