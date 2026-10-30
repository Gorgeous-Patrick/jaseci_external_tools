# TTG application evaluation suite

Target: **30 entries: one LinkedList microbenchmark and 29 complete applications**.
The original full applications are LittleX, Jacord and JDrive; 26 additions are
specified in [the maintained progress report](../../project-notes/ttg-app-suite.md)
(workspace-relative report: `../../project-notes/ttg-app-suite.md`). Candidate
entries and scaffolding are not completed applications.

## Language and review contract

Use English for every UI string, seeded/demo record, validation/error message,
identifier, comment, README, setup instruction, workload description, test log,
evidence report and slide. Apply the same rule to original-four integration
artifacts. Keep domain terms consistent and prose suitable for advisor review.
Audit inherited source content and record required conversions in the progress
report. Conversation with the user may remain Chinese.

## Verification contract

Each full application requires its own domain graph, native Jac walkers,
persistent storage, operational frontend, deterministic seed, startup command,
user workflow and correctness oracle. Native walker validation is mandatory.
Also validate browser interactions and persistence after restart. Shared auth,
HTTP transport, styling and UI primitives are allowed; renamed domain templates
and JSON-only graphs do not satisfy the contract.

The existing logical corpus under `datasets/ttg/` contains 36 generated datasets.
Logical replay success does not imply native import/replay success. Suite results
must state their scale, seed, exact source hashes, runtime revision, policy and
which verification gates actually ran.

Keep HTTP end-to-end time, native walker time, driver DB-call wall time and SQL
count separate. Unmeasured metrics are null. Retain background prefetch
attribution and finish collecting asynchronous work before interpreting it.
Use isolated ports and databases and preserve unrelated uncommitted work.

## Current status

All 30 entries have domain source, native scenarios and user workflows: one
LinkedList microbenchmark and 29 full applications. Historical evidence is retained
separately from final source-fresh two-policy acceptance.
Final coherent acceptance passed all 60 app/policy cases: both none and ttg
for all 30 entries. Each of the 29 full apps passed real browser actions and
native checks after browser-write restart under both policies. [Coverage](COVERAGE.md) maps every app
to its native read walker and traversal/dependency pattern; [registry.json](registry.json)
provides machine-readable integration paths and target-ID requirements.

```sh
python3 app_suite/status.py
```

`complete_acceptance` requires BOTH none and ttg at seed 42, pinned-runtime
integrity, native correctness, browser interaction (microbenchmark exempt), both
restart gates, current backend/UI/oracle hashes and a current English audit.
`verified_any_policy` and historical functional passes are separate fields.
Per-policy rows expose missing cases and failed/stale gates. A passing summary
under one policy cannot complete an entry. See the maintained progress report
for canonical evidence and the separate pending performance lane. Each new app has an individual README.

No app performance experiments may start before this full acceptance gate.
The independent performance worker owns instrumentation outside `app_suite/`;
four-policy correctness preflight on frozen final sources precedes formal timing.
Performance values in functional evidence remain null. Do not push suite changes
until supervisor review.

## Run original-four native validation

Run from the external-tools checkout. The current adapter targets the workspace's
Jac 0.36.1 checkout on `feat/ttg-dependency-graph`; `runtime.sh` selects it without
changing the checkout. Override `TTG_RUNTIME_SOURCE` and `TTG_PYTHON` to relocate
the source or Python 3.14 runtime. `JAC_PG_DIST` selects PostgreSQL binaries.
The default values match the inspected workspace.

```sh
python3 app_suite/native.py --output /tmp/ttg-original-four-seed42 --seed 42
```

This starts its own PostgreSQL cluster and one native server at a time, creates
separate app databases, registers authenticated users, imports real native graph
objects, restarts, checks exact fields and typed topology, replays all logical
operations using the original walkers, and restarts to check final state. JDrive
also provisions and downloads real 64-byte files. Output directories must be new.
`--scale smoke|small|medium`, `--seed`, `--apps` and `--policy none|ttg` select
the case. Do not interpret one passing smoke case as all 36 existing datasets.

Jacord uses legacy permission constants that Jac 0.36.1 does not define. The
adapter replaces them with `AccessLevel.READ/CONNECT/WRITE` in an isolated source
copy; `source-adaptation.json` records original and adapted hashes. Original
checkouts stay unchanged. Test-only SuiteImport/SuiteInspect walkers are appended
to snapshots to provision and inspect native state; workload replay invokes the
actual application walkers.

## Run browser workflows

The browser dependencies are isolated from repository packages:

```sh
npm install --prefix /tmp/ttg-suite-browser playwright@1.61.1 --cache /tmp/ttg-suite-npm-cache
PLAYWRIGHT_BROWSERS_PATH=/tmp/ttg-suite-browsers node /tmp/ttg-suite-browser/node_modules/playwright/cli.js install chromium
python3 app_suite/native.py --output /tmp/ttg-original-four-browser42 --seed 42 --browser
```

`TTG_PLAYWRIGHT_MODULE` and `PLAYWRIGHT_BROWSERS_PATH` override these paths.
Browser checks enter credentials, fill domain forms, click real controls, inspect
rendered results and persist their mutations through another backend restart.
Evidence includes `browser-result.json`, `browser.png`, `browser-trace.zip`, native
`steps.json`, `requests.json`, source hashes, server logs and per-app summaries.
The browser trace may contain local demo credentials; these are isolated fixed
test accounts, never external-service credentials. LinkedList is explicitly
exempt from the full-application UI gate.

To use an adapted original application interactively, run:

```sh
python3 app_suite/native.py --output /tmp/ttg-littlex-demo42 --apps littlex --seed 42 --interactive littlex
```

Replace both `littlex` values with `jacord` or `jdrive` to select that application.
The command prints the assigned frontend URL. Sign in as `user_0000` with
`isolated-suite-seed-password`. Ctrl-C stops that command's owned services.
The database and file bytes remain in its output directory; no existing service
or source application configuration is modified.

## Pin a concurrently changing runtime

The shared `jac-ttg` checkout may be edited by another task. Freeze it before
comparing policies or making any performance claim:

```sh
python3 app_suite/freeze_runtime.py --source ../jac-ttg --output /tmp/ttg-suite-runtime-review
TTG_RUNTIME_SOURCE=/tmp/ttg-suite-runtime-review python3 app_suite/evaluate.py --apps issue_desk --seed 42 --browser --policy none --output /tmp/issue-desk-pinned-none42
```

The snapshot includes uncommitted source changes. It is accepted only if hashes
match before copying, after copying and in the copy. `snapshot.json` records
source HEAD, dirty paths and every Jac/Python source hash. The shared checkout is
read only. Keep the same snapshot for each policy and all server restarts.
Earlier acceptance runs used the live checkout and are semantic evidence, not
fixed-runtime policy performance comparisons. The suite explicitly configures
only `none`/`ttg`; it has not tested the newly added `ttg_dependency` policy.

The correctness pin is `/tmp/ttg-app-suite-runtime-frozen-20261029`, with 1,552
hashed Jac/Python files. It predates the separate performance worker's immutable
runtime commit `5f94eb62d` snapshot; acceptance evidence identifies the exact pin
and does not claim that the two snapshots are identical. See the workspace's
`project-notes/measurements/ttg-app-suite-20261029/SUITE-STATUS.md` for durable
acceptance evidence. Both-policy final reruns use one coherent suite version.
