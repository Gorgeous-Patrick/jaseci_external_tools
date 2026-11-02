# Interability results publication plan

Status: planning only. Main owns source/results publication. P7 owns the live fifteen-case correctness window and the later formal experiment. This note is outside core and all frozen execution/evidence closures. No packaging, compression, rendering, archival, staging or pushing is authorized by this plan.

## Scope and acceptance

The intended publication covers four fixtures: finite typed LinkedList 32 and 1000, typed Boolean RegionChain A→B→C, and unchanged LittleX. Three policies give twelve primary cells. One excluded warmup plus three measured trials per cell gives **48 formal trial archives**: twelve warmups and thirty-six measured trials. Keep all warmups identifiable and outside measured aggregates.

Include **15 correctness cases** separately: twelve main fixture/policy cases plus three RegionChain guard-false cases. The initial expected portable raw inventory is therefore **63 accepted case archives**, with exact case IDs taken from the final indexes rather than reconstructed from directory names. Formal acceptance and the final indexes remain pending; partial live results are not a release. Historical failed/interrupted attempts remain explicitly identified provenance when required by the final inventory and are never added to accepted counts.

The finite LinkedList variant has two disclosed source changes: remove the Traverse counter cutoff and use an explicit Item target. Preserve original-source hashes and the exact variant patch. Sum/Find and the other application sources retain their declared provenance. A visited count is total activations, not a depth proof. Report SQL totals and activation evidence separately: the accepted LL32 correctness observation is 75/15/15 all-role/control SQL, with one new static-region query and thirty-two cached paths; it establishes no extra query-count reduction over 9282 and is not a formal timing result.

## Portable package contents

Use a new results directory chosen by main at assignment time, following the existing portable-package layout and mapper/verifier. Do not change earlier published packages.

- One final approved English PDF, its editable renderer/source, figure inputs and the exact report integrity/layout records required by the final input manifest. Exclude all draft PDFs and unnecessary preview/cache copies.
- Final accepted export JSON and CSV, cell/trial definitions, units, warmup exclusions, correctness results, per-policy gates and exact raw references. Keep client-observed DB-call wall time, SQL counts and application end-to-end measures distinct. Preserve foreground/background/control attribution.
- Complete sealed raw evidence for all 48 formal trials and all 15 correctness cases, including request/response oracles, state/persistence checks, activation records, SQL/metric/proof/acceptance records and indexes. Include additional diagnostic material only if subsequently assigned and approved.
- Exact required runner/observer/oracle/application source closure, original/variant provenance, runtime commit and component/overlay manifests, policy/config/seed/workload definitions, release gates, main/reviewer acceptances and stopped-service/ownership records. Runtime implementation provenance must identify the final approved commit and its tested scoped patch; no full runtime checkout is required.
- Existing source-bound method inputs and guarded SQL example where referenced by the approved report. Label the actual static single-successor kernel separately from Stage 2 reuse of the existing collector. Preserve model/prepared-plan roadmap distinctions.
- A concise positive English README leading with the results, PDF and reproduction commands, plus path mapping, file manifest, SHA inventory, package integrity record, portable verifier and small relocation/import smoke evidence.

Exclude PostgreSQL data/WAL/cluster trees, compiler caches, complete runtime checkouts, unrelated application corpora, duplicate old result packages and unapproved presentation drafts. The stopped regression-cluster preservation archive remains external unless an exact required provenance reference calls for its small manifest/restore record; avoid copying the database archive into the results package by default.

## Representation and mapping

Reuse the prior mapper/verifier's workspace-relative source paths, original-evidence-to-package path map and explicit current versus historical/external reference declarations. Resolve every required current reference. Preserve original manifests and seals byte-for-byte rather than editing their paths in place.

Prefer a direct copy of the existing accepted compact representation when Git and disk budgets permit. If lossless decoded repacking is needed after the quiet handoff, reuse the existing decoded-event archive pattern: retain the original compression document, original gzip SHA/size and decoded member SHA, then bind new archive SHA/size and a representation map. Verify exact decoded member membership, bytes, order where specified and semantic source references; reject missing, duplicate or unknown members. Do not claim recompressed bytes equal the original gzip. Original raw evidence stays local and unchanged. Choose the representation only after observing the final inventory and a bounded quiet-window feasibility check.

Every Git blob must remain below 100 MB. Use the established archive splitting/member mapping if needed; do not drop large cases, analytical work or unfavourable observations to meet the limit.

## Execution order after assignment

1. Wait for main's explicit post-formal quiet handoff and P7's frozen final input inventory, sole approved PDF and required reviews. Confirm exact source, report, numerical and case-index versions.
2. Check actual retained/transient bytes and reserve before copying or repacking. Agree any capacity work with main; preserve all originals. No experiment or source changes are part of packaging.
3. Assemble only the supplied inventory using the existing mapper. Copy source and small metadata once; avoid duplicate raw or runtime trees. Repack only under the explicit lossless representation contract if required.
4. Run the existing portable verifier against original bindings and a relocated package. Reuse the minimal metadata relocation pattern for immutable application snapshot metadata and previous-source manifests; record a new relocation manifest without rewriting archived originals. Run only a DB-free import/dependency-resolution smoke, not an application or benchmark replay.
5. Include final main/reviewer records, then seal file manifest, hashes and package integrity. Report accepted case counts, file/archive counts, total bytes, largest blobs, verifier outcomes and full final integrity/PDF hashes. Freeze the directory with no late additions.
6. Hand the frozen directory to main. Main owns scoped attributes, Git index/staging, blob-byte review, commit and push. Any later supplement or correction requires an explicitly assigned new version.

## Inputs still pending

Final 15-case correctness completion; formal release and all 48 trial acceptances; final export and attribution; sole approved English PDF and editable inputs; final source closure and review inventory; actual storage/blob forecast; main's package path and execution assignment. No performance conclusion or packaging completion is claimed while these inputs are pending.
