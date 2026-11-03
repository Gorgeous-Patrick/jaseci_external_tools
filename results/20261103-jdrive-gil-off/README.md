# JDrive: dependency-sliced tree prefetch on GIL-off Python

The runtime implementation is [f9a6d37b2f531d441515b40e02f3b0a9cc998836](https://github.com/Gorgeous-Patrick/jaseci/commit/f9a6d37b2f531d441515b40e02f3b0a9cc998836) on `feat/ttg-interability-regions`. It compiles typed, boolean-filtered directory traversal into a recursive SQL region while preserving native output construction, path order, permissions, mutation/restart checks and atomic cache publication. Proven private output bookkeeping (`jid`, depth/path maps and result records) can be separated from access dependencies; unknown effects retain conservative fallback.

Every mode uses CPython 3.14.6 free-threaded, one worker, limit 2048, seed 42 and uniform pre-workflow `ANALYZE anchors` / `ANALYZE graph_types`. Each of the three paired runs contains eight fresh workflows: one excluded warmup and three measured repetitions per mode. The original seven requests are list, tree, trash, tree, mkdir, list and tree.

## Measured results

Values are medians of three measured fresh workflows. DB time is the sum of actual send-to-ready protocol intervals across all roles. HTTP time is the sum of seven instrumented request/response intervals, ending after the complete response is read. Each comparison pairs off/thread within the same frozen runtime; the before-fix and optimized runs are distinct captures.

| Fixture / SQL version | Mode | All SQL | DB sum (ms) | HTTP sum (ms) |
|---|---|---:|---:|---:|
| 40 folders, before SQL fix | off | 156 | 53.731 | 110.144 |
| 40 folders, before SQL fix | thread | 105 | 61.962 | 125.656 |
| 40 folders, optimized | off | 156 | 55.448 | 113.204 |
| 40 folders, optimized | thread | 105 | 32.623 | 109.951 |
| 364 folders, optimized | off | 463 | 219.404 | 411.080 |
| 364 folders, optimized | thread | 105 | 37.883 | 212.442 |

The standard `small` fixture has **364 folders, 121 files and one Drive**, with 485 initial domain edges. Three tree requests return 116, 72 and 73 visible directories. Their all-role SQL counts drop from **176 / 113 / 114** to **15 / 15 / 15**. Whole-workflow SQL drops 77.3%, DB median drops 82.7%, and summed HTTP median drops 48.3%. The smaller 40-folder/13-file fixture has only a 2.9% HTTP median improvement after the SQL repair, with overlapping sample ranges. Exact vectors and ranges are retained in each `results.json`.

## The SQL repair and measured plan

The first tree SQL unnecessarily rejoined the target anchor outside a correlated path. PostgreSQL placed 43 eligible targets outside the recursive worktable, producing **817 path scans for 19 reachable origins**. The repair joins worktable → edge → target directly and evaluates the existing type/module/boolean predicates on that target. The final ordered cache assembly retains native multiplicity and empty-path proof.

Matched diagnostics capture exact Parse/Bind bytes in the actual foreground connection and transaction. Both complete original workflows pass native replay, restart, physical-state checks and selected-query completion before plan acceptance. The first and repeated optimized executions return the same 35 cache records:

| Server EXPLAIN observation | Before repair | Optimized |
|---|---:|---:|
| First execution (ms) | 13.938 | 0.784 |
| Repeated execution (ms) | 13.374 | 0.666 |
| Root shared-buffer hits | 9554 | 297 |
| Shared-buffer reads | 0 | 0 |

These EXPLAIN measurements follow a same-transaction census and explicit ANALYZE; they are separate warmed diagnostics, not primary HTTP samples. JIT was absent. The optimized recursive step scans/materializes 54 candidate edges once and uses 32 endpoint primary-key lookups, while 19 ordered final path assemblies remain. No foreground/background SQL interval overlap was observed in these primary runs. The evidence does not attribute remaining HTTP time to CPU or IPC.

## Evidence and reproduction

- [Optimized larger-run results](workspace/project-notes/measurements/ttg-jdrive-freethreaded-20261103/comparison-small-v1/results.json)
- [Optimized original-size results](workspace/project-notes/measurements/ttg-jdrive-freethreaded-20261103/comparison-access-v3/results.json)
- [SQL optimization binding](workspace/project-notes/measurements/ttg-jdrive-access-20261103/sql-optimization-v2.json)
- [Exact tested-code/commit binding](workspace/project-notes/measurements/ttg-jdrive-access-20261103/commit-binding.json)
- [Larger fixture and expected outputs](workspace/project-notes/measurements/ttg-jdrive-access-20261103/larger-shape-v1.json)
- `raw/`: 24 accepted performance workflows and three complete diagnostic workflows, sealed byte-preserving archives including original gzip traces.
- `workspace/` and `source-versions/`: harness, semantic oracles, changed compiler/runtime sources, tests, SQL/capture helpers, manifests, summaries and shutdown proofs.
- `manifests/external-runtime.json`: explicit identities of installed runtime snapshot files and the external Python executable. Runtime checkouts, PostgreSQL clusters and installed interpreters are not bundled; reconstruct the runtime from the linked commit and captured instrumentation manifests.

Run `python3 -B verify_package.py`. The portable standard-library verifier validates exact package inventory, all archive members and original seals, all 24 fresh database identities, business-output equivalence within each paired run, GIL-off assertions joined to actual SQL records, real same-process background threads/different PostgreSQL backends, n3 raw SQL/DB/HTTP reaggregation, clean DROP ownership evidence, and actual diagnostic Parse/Bind/plan records. Original absolute paths are resolved through the versioned path/hash map; historical references outside this study are provenance pointers rather than a claim that their full dependency trees are bundled.

The optimized SQL passes four focused compiler/cache checks and all 15 native region tests, including malformed predicates, cycle/overflow rejection, private-output safety and strict zero-SQL native cache consumption. All study services stopped, every accepted database was dropped only after semantic/physical/source validation, and no failed historical database was removed.
