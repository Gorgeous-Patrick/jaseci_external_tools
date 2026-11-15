# TTG performance research — 12 November 2026

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
