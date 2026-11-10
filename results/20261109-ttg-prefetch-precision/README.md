# TTG prefetch precision and the standard-access OFF comparison

Two fixed JDrive/LittleX experiments use the same frozen standard-only-permission runtime and free-threaded CPython. Every actual SQL boundary asserts `Py_GIL_DISABLED == 1` and `sys._is_gil_enabled() is False`. Each experiment has 16 fresh workflows: four excluded warmups and twelve measured workflows, n=3 per app/mode. Native business outputs, final physical state, restart, request sessions and owned cleanup passed for all 32 workflows.

JDrive has 364 folders, 121 files and one Drive. LittleX has 50 profiles and 1,000 tweets. Both retain their original business workflow. Each database receives the same explicit ANALYZE before primary requests. The policy configurations use one thread worker and a prefetch limit of 2048.

## Aggressive versus conservative precision

[CSV](workspace/project-notes/measurements/ttg-overfetch-comparison-20261109/table.csv) · [Vectors, request breakdown and raw references](workspace/project-notes/measurements/ttg-overfetch-comparison-20261109/results.json)

Aggressive is the retained `prefetching="ttg"` policy: predict before the walker, then load payloads in a thread. Conservative is `ttg_dependency` with compiled regions/checkpoints and threaded loading. They run in the same current runtime; this isolates policy behavior rather than comparing different historical Python or permission implementations.

| Application | Policy | Actual prefetched objects | Subsequently demanded | Never demanded | Never-demanded share |
|---|---|---:|---:|---:|---:|
| JDrive | Aggressive | 1,090 | 319 | 771 | 70.7% |
| JDrive | Conservative | 258 | 258 | 0 | 0% |
| LittleX | Aggressive | 357 | 357 | 0 | 0% |
| LittleX | Conservative | 287 | 287 | 0 | 0% |

All three measured repetitions have identical counts. Counts are unique anchor IDs per HTTP request and Session, summed over a workflow. The same object fetched in separate requests counts repeatedly. Actual payload delivery is observed at `store_raw` after the background `load_full` completes, including late rows that the cache would discard. Demand means successful foreground `Session.get`/`batch_get` outside prefetch planning. A separate temporal check finds no prior-only demand in these samples. Late already-materialized deliveries are zero in both modes. Props-byte counters are logical serialized property bytes, not network or PostgreSQL scan bytes.

Native OSP entry is recorded separately. A helper can legitimately read an object without visiting it, so lack of an OSP entry is **not** treated as overfetch. LittleX demonstrates this: conservative prefetches 70 fewer objects, but aggressive's extra objects are actually needed. Both modes make 384 successful demand-object accesses per workflow; the reduction is prefetch coverage, not elimination of unused data.

JDrive has another 61 avoidable candidate reads (29 + 16 + 16 across its three tree requests). The aggressive path materializes those Folder candidates to evaluate `trashed`, then rejects them. Conservative's filtered path avoids loading them. The 771 entirely unused objects and these 61 rejected candidates are distinct categories. Counting both yields 832 avoidable prefetches; calling all 832 "never read" would be incorrect. See [the object-level difference record](workspace/project-notes/measurements/ttg-overfetch-comparison-20261109/demand-difference-explanation.json).

The precision observer is identical in both modes. This is a diagnostic for useful/unused object sets, not an uninstrumented latency benchmark.

## Standard-access runtime: OFF versus conservative thread

[CSV](workspace/project-notes/measurements/ttg-standard-access-comparison-20261109/table.csv) · [Full samples](workspace/project-notes/measurements/ttg-standard-access-comparison-20261109/results.json)

| Application | Mode | HTTP response sum, median ms | DB interval sum, median ms | Data SQL | Control SQL |
|---|---|---:|---:|---:|---:|
| JDrive | OFF | 395.863 | 206.659 | 414 | 49 |
| JDrive | Conservative thread | 261.003 | 51.138 | 53 | 52 |
| LittleX | OFF | 216.487 | 50.181 | 90 | 63 |
| LittleX | Conservative thread | 262.544 | 53.613 | 74 | 69 |

JDrive HTTP response sum falls 34.1%; LittleX rises 21.3%. HTTP is the sum of primary request-to-complete-response-read intervals, before explicit post-response drain. DB is all-role send-to-ReadyForQuery protocol time. Setup, normalization, steady checks and restart are excluded. Every primary sample has equal DB sum and union. These are n=3 samples on these fixed small graphs, not a universal speedup claim. Reducing one SQL statement's cost does not establish an application speedup.

## Evidence and reproduction

`raw/` contains all 32 complete, byte-preserved case archives, including their original seals, SQL/HTTP traces, precision events, fixtures, outputs, GIL proofs and correctness evidence. `workspace/` retains the execution scripts, numeric analyses, per-case acceptance records, source manifests and lifecycle/cleanup proofs at their original relative paths. It also contains the earlier standard-access native regression and SQL-only comparison evidence; those diagnostics are separate from the two n=3 workflow experiments.

`runtime.patch` preserves the exact uncommitted runtime change used in these experiments relative to commit `96868d040` (full commit in `manifests/runtime.json`). Capturing that patch here does not commit the runtime repository. `runtime-instrumentation/` preserves the three effective observer files and pristine counterparts. Full runtime/interpreter binaries, PostgreSQL data directories and caches are external; their identities are recorded in `manifests/external-runtime.json`. Re-running the native harness requires those dependencies and the recorded workspace layout. Original absolute references in evidence are preserved; the portable verifier resolves them through the package mapping.

Verify without the original workspace or a database:

```sh
python3 -B verify_package.py
```

The verifier checks package/member hashes, exact case seals, all SQL/GIL joins and aggregate counts/times, precision set differences from raw events, n=3 vectors/CSV, paired semantic hashes and all 32 active-zero owned drops. Original sources and publications remain unchanged.
