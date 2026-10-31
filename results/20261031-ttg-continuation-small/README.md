# TTG continuation: partial two-application publication package

This package preserves the accepted **LittleX and IssueDesk** pilot: six configurations, seed 42, one prefetch worker and limit 256, with three independent measured workflows per application/configuration. The 48 trials comprise **36 measured workflows and 12 excluded warmups**. The separate **NEW180** evidence is a complete correctness matrix for the original 30 entries across six configurations, with one linked-list microbenchmark and 29 full applications. The two-application performance results and 30-entry correctness evidence are presented as separate datasets.

The primary measurements are actual PgWire send-to-ReadyForQuery protocol-completion wall time and SQL dispatch counts. Summed DB-call time and interval-union time are distinct. Foreground and background calls, transaction controls, late work, model outcomes, and phase exclusions remain in the raw evidence. These are client-observed DB intervals. Each independent workflow has a fresh database and process-local profile; learning occurs naturally within that workflow. Warmup state is not transferred across trials. Setup/authentication/seed, auxiliary steady phases, and restart/verification remain separately attributed.

## Accepted outputs

- [Numerical export](results/small-export-v1/results.json), SHA-256 `17922e61bcf4ff4ca6814a1b23cd758d0ac371d979f1537ab95dc802233c2f4b`.
- [CSV table](results/small-export-v1/table.csv), SHA-256 `997efa665c79b609986f7bfd5d9fd5aaa25952a89fb9ad11fed3fb76a416c8ac`.
- [Original five-page PDF, version 1](report/small-report-v1/ttg-small-performance.pdf), SHA-256 `62880819b666a8d85dc2b6421e2ea2271338c81cda2dcd5585a0d1d028661942`.
- [Report text](report/small-report-v1/report.md), figure inputs, rendered pages, and the original report-integrity manifest are preserved together. Any later explanatory revision must use a new version; version 1 remains unchanged.
- [Main's independent actual-data audit](evidence/workspace/project-notes/measurements/ttg-continuation-performance-20261030/main-small-actual-audit-v1/audit.json): 48 trials, 1,544 sealed members, 48 metrics, 12 cells with n=3, and 38 source references. Its [standalone source](sources/supplemental/reproduction/ttg-continuation-performance/audit_small_actual_v1.py) is supplementary to the measured 38-file closure.
- [PRIMARY48 final stopped-state proof](evidence/workspace/project-notes/measurements/ttg-continuation-performance-20261030/main-small-lifecycle-v1/lifecycle.json): all 257 recorded client/creator PIDs dead, PostgreSQL stopped with no PID file, no retained databases, and 48 owned database drops.
- [Performance worker final host proof](evidence/workspace/project-notes/measurements/ttg-continuation-performance-20261030/small-primary48-lifecycle-v1.json) independently binds stopped processes, SQL logging mode, source/index/release and ownership/cleanup hashes.
- [NEW180 independent review](evidence/workspace/project-notes/measurements/ttg-continuation-performance-20261030/main-complete180-review-v1/review.json), [index](evidence/workspace/project-notes/measurements/ttg-continuation-performance-20261030/apps-preflight-866222-v2/index.json), and [final lifecycle proof](evidence/workspace/project-notes/measurements/ttg-continuation-performance-20261030/apps-preflight-866222-v2-final-audit/lifecycle.json).

## Layout and provenance

| Path | Contents |
| --- | --- |
| `results/small-export-v1/` | Exact accepted JSON, CSV, and export seal |
| `report/small-report-v1/` | Exact PDF, report, figure inputs, images, and integrity evidence |
| `sources/workspace/` | All 38 frozen execution inputs and all 90 accepted suite members, retaining original workspace-relative paths |
| `sources/supplemental/` | Report renderer and independent actual-data auditor; additional referenced helpers are preserved under evidence paths |
| `raw/small48/` | 48 separately sealed, compressed trial archives, including excluded warmups |
| `raw/correctness180/` | 180 separately sealed, compressed correctness archives |
| `raw/controls/` | Original sealed synthetic SQL and overhead control records |
| `evidence/workspace/` | Exact release, authorization, plans, reviews, runtime/overlay manifests and patch, indices, metrics, acceptance, ownership, cleanup, lifecycle, and control provenance |
| `manifests/` | File inventory, archive member hashes, original-to-package path mapping, and the execution source closure |

Runtime commit: `866222f9093cb025950a1857e8175d526cc3a6e3`. The clean-runtime and direct-overlay manifests bind the exact runtime bytes and observer patch. Runtime checkouts, PostgreSQL data/clusters, caches, and generated compiler caches are excluded. Only explicit stopped-cluster metadata and cleanup logs are retained. All original workspace files are preserved.

The six cells are off, legacy TTG/thread, continuation always/thread, continuation always/process, continuation expected-benefit/thread, and continuation expected-benefit/process. Exact effective configurations, source hashes, schedule and quiet-window authorization are in the [accepted main-reviewed plan](evidence/workspace/project-notes/measurements/ttg-continuation-performance-20261030/small-review-ready-v1/main-reviewed-plan.json) and [formal release](evidence/workspace/project-notes/measurements/ttg-continuation-performance-20261030/formal-run-authorization.json). The original draft `plan.json` and review-only candidate are retained as provenance; they are not the final authorization. One historical candidate reference predates the final complete180 index; [superseded-references.json](manifests/superseded-references.json) records its historical and final hashes without rewriting either document. The original SQL-control seal retains its failed CSV-parser result alongside the separately accepted supplemental repair proof; it is not relabeled as a successful original run.

Original JSONs retain their absolute paths and hashes. [path-mapping.json](manifests/path-mapping.json) resolves each bundled original workspace-relative path to a copied file or compressed member; archives do not require the original `/home/baichuan/jaseci` prefix. Each tar contains exactly the seal's files plus `artifacts.json`, with unchanged member bytes. [archive-members.json](manifests/archive-members.json) records archive hashes, every member's original path/hash/size, and seal status. Packaging verifies original bytes, seal hashes, archive readback and maps; it does not rerun the experiment or replace main's semantic audit.

## Verification and commands

From this package directory, verify all copied files, compressed members, seals, index case coverage and path mappings without launching services:

```bash
python3 -B verify_package.py
```

When the original workspace is available, additionally compare every mapped original file:

```bash
python3 -B verify_package.py --original-root /home/baichuan/jaseci
```

To inspect one archive in a new directory:

```bash
mkdir -p /tmp/ttg-publication-inspect-littlex
tar -xzf raw/small48/littlex-none-measured-0.tar.gz -C /tmp/ttg-publication-inspect-littlex
```

The following are the recorded experiment/export entry points, provided for provenance rather than executed by packaging. They require the original reconstructed workspace, pinned runtime/dependencies, an explicitly authorized isolated DB window, and new output paths for any future run:

```bash
python3 -B reproduction/ttg-continuation-performance/small_runner_v1.py formal --output project-notes/measurements/ttg-continuation-performance-20261030/small-formal-v1 --cluster reproduction/ttg-continuation-performance/pg-small-formal-v1
python3 -B reproduction/ttg-continuation-performance/small_export_v1.py --run project-notes/measurements/ttg-continuation-performance-20261030/small-formal-v1 --output project-notes/measurements/ttg-continuation-performance-20261030/small-export-v1
```

Do not rerun these commands against the published original directories. `package_from_originals.py` records the file-copy/archive construction procedure; `verify_package.py` is the portable package check. `manifests/files.json`, `SHA256SUMS`, and `package-integrity.json` bind all deliverable files; every file is below 100,000,000 bytes.
