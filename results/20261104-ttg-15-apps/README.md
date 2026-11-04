# TTG across 15 applications — GIL-off asynchronous threads

[**31-page slides (PDF)**](report/ttg-15-app-performance.pdf) · [Complete CSV](workspace/project-notes/measurements/ttg-portfolio-v2-20261104/table.csv) · [Exact vectors and per-request results](workspace/project-notes/measurements/ttg-portfolio-v2-20261104/results.json)

The fixed selection contains 15 applications and **120 fresh workflows**: 30 excluded validation warmups followed by 90 measured workflows, three repetitions per application/mode. Every workflow passes native business outputs, mutations/rejections, fresh sessions, restart, independent stored semantic replay and physical-state checks before owned active-zero database cleanup. All actual SQL boundaries assert free-threaded CPython 3.14.6 with the GIL disabled.

The comparison uses the same frozen runtime [f9a6d37b2f531d441515b40e02f3b0a9cc998836](https://github.com/Gorgeous-Patrick/jaseci/commit/f9a6d37b2f531d441515b40e02f3b0a9cc998836), off versus AlwaysPrefetch/thread, one worker, limit 2048, seed 42, and uniform pre-workflow ANALYZE. JDrive has 364 folders, 121 files and one Drive; LittleX has 50 profiles and 1,000 tweets. The other 13 applications use their original, small seeded domain scenarios and full business workflows. They are not production-scale datasets.

## Results

Only JDrive has a lower median summed HTTP response time in this fixed experiment. All slower cases remain included. HTTP is the sum of primary request-to-complete-response-read intervals; DB is all-role send-to-ready protocol time. Explicit post-response drain is separate. Setup, normalization, steady checks and restart are excluded. Values below are medians of n=3; all ranges/vectors and reader-only breakdowns are retained in the linked data and slides.

| Application | HTTP off / thread (ms) | DB off / thread (ms) | SQL off / thread |
|---|---:|---:|---:|
| JDrive | 398.90 / 217.76 | 209.92 / 41.07 | 463 / 105 |
| LittleX | 215.72 / 275.59 | 50.11 / 60.40 | 153 / 143 |
| IssueDesk | 278.59 / 370.20 | 145.93 / 180.51 | 557 / 565 |
| StockRoom | 266.49 / 388.27 | 134.97 / 161.90 | 497 / 493 |
| ClinicQueue | 212.75 / 229.43 | 108.60 / 110.82 | 408 / 411 |
| BudgetLedger | 119.69 / 147.65 | 57.04 / 64.36 | 234 / 236 |
| KnowledgeMap | 145.67 / 183.90 | 72.24 / 88.16 | 298 / 301 |
| CoursePath | 291.09 / 328.09 | 154.17 / 175.32 | 521 / 519 |
| ApprovalDesk | 264.75 / 404.40 | 134.81 / 158.94 | 539 / 545 |
| LibraryLoans | 294.88 / 340.67 | 152.60 / 164.82 | 531 / 533 |
| EventSeats | 220.03 / 240.72 | 110.51 / 114.23 | 434 / 438 |
| HelpQueue | 321.17 / 645.30 | 170.57 / 193.29 | 609 / 614 |
| DeliveryRoute | 215.34 / 324.96 | 103.19 / 135.18 | 415 / 423 |
| VolunteerShift | 161.67 / 181.81 | 85.97 / 87.28 | 286 / 292 |
| IncidentRoom | 141.89 / 198.77 | 68.58 / 91.21 | 293 / 290 |

## Why support does not guarantee speed

JDrive's homogeneous typed, boolean-filtered tree permits recursive discovery and ordered cache publication while native `jid`/depth/path bookkeeping remains intact. It eliminates hundreds of small path/payload queries. Other selected apps expose typed root or branch prefixes, but helpers, graph reads inside comprehensions, exit routing and mutations limit how much work can be fused. A supported prefix can still be unprofitable on a small graph. The remaining 15 registry apps are **unmeasured here**, not declared impossible or unsupported.

Matched diagnostics locate two different costs:

- **Runtime prediction:** direct same-native-thread timers measure 173.00 ms exclusive CPU in `plan_continuation` across three HelpQueue `EvaluateSLA` requests, and 77.45 ms across five ApprovalDesk `SubmitExpense` requests. These are separate n=1 diagnostic workflows with nested exclusive-time accounting, not CPU inferred from primary HTTP minus DB. All original workflows and outcomes are retained. The initial cProfile attempt produced invalid cross-thread clock totals and is explicitly rejected; none of those timings is used.
- **SQL complexity:** actual LittleX Bind packets are captured before the original statements in accepted full workflows. In the matched census-warmed EXPLAIN diagnostic, three native paths total 1.188 ms planning / 0.469 ms execution, versus 2.696 / 1.431 ms for the combined query. Immediate repeats are 1.121 / 0.385 versus 1.897 / 1.147 ms. The combined plan adds window/order/CTE machinery and an anchors sequential scan; root shared hits on the repeat are 329 versus 513, with zero physical reads. These are separate server-plan observations, not primary timing samples.
- **Concurrency:** actual threads and distinct PostgreSQL backends are verified, but no same-request foreground/background SQL overlap is observed in any of the 90 measured workflows. An executor label alone does not establish hidden latency.

The slides show dependency slices inside a Jac A→B/C graph, support/coverage distinctions, every measured app, sibling-dependent access limits and next steps: avoid repeated prediction at known unprofitable boundaries, reuse safe analysis facts, specialize SQL work, then evaluate cost-based admission. Proposed improvements and prepared-statement reuse are not counted as measured gains.

## Evidence and portable verification

Run **`python3 -B verify_package.py`** from this directory. It uses only the Python standard library and reads no original workspace, runtime or database. It verifies:

- exact package inventory and 134 sealed archives: 120 primary/warmup workflows, 10 valid CPU diagnostic workflows and four SQL diagnostic workflows;
- every archive member and original seal, all 120 unique primary databases and owned active-zero drops;
- actual SQL/GIL/thread/backend joins, all primary and per-request/fingerprint SQL/DB/HTTP aggregates, every n3 group and the CSV;
- 22 direct CPU request records with same-thread nonnegative nested partitions, eight actual Parse/Bind captures and sixteen server plans;
- exact source/reference identities and the sole final 31-page PDF's input/output hashes.

`raw/` preserves original sealed file bytes, including original compressed traces. `manifests/path-mapping.json` resolves captured absolute paths by exact hash. Valid CPU cases that were previously archived locally are repackaged without changing their bytes. `workspace/` contains the frozen application/harness/oracle sources, analysis and editable renderer, primary/diagnostic manifests, acceptance proofs, source support inventory, and stopped lifecycle evidence. `report/` contains the final PDF, previews, extracted text and report manifest.

Installed runtime checkouts and the Python executable are represented by exact identities in `manifests/external-runtime.json`; rebuild them from the linked commit and captured instrumentation/freeze scripts. PostgreSQL data directories, regenerable caches, rejected profiler traces and unrelated historical dependency trees are excluded. Local preservation manifests remain provenance references; accepted cases are independently present in this package. The standard-library verifier validates data and recorded proof relationships; it does not rerun Jac business code.

For a new benchmark, restore the workspace layout from the mapping, recreate the pinned runtime/interpreter, and use the supplied portfolio controller/configuration in a **new owned output/cluster directory**, recording a new source seal. Do not overwrite this accepted capture. The final renderer and analysis scripts are under `workspace/project-notes/measurements/ttg-portfolio-v2-20261104/`.
