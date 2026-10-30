# TTG application performance preparation and release contract

All artifacts are English. The performance worker owns this directory and
`project-notes/measurements/ttg-app-performance-20261030/`. The suite worker owns
`jaseci_external_tools/app_suite/`. No live runtime, SQL branch or original app
source is edited. Nothing is pushed without main-agent review.

## Hard gate

No application performance testing is allowed until all 30 entries pass native
correctness, operational browser workflows (LinkedList exempt), restart
persistence, English audit and exact source freshness under **both none and ttg**.
Then create a new coherent final suite snapshot and run all-four-policy
correctness preflight. Formal mode additionally requires the exact fixed file:

`project-notes/measurements/ttg-app-performance-20261030/formal-run-authorization.json`

**Only the main agent writes that file.** This directory contains no release
generator, alternate authorization-path CLI, bypass flag or approval environment
variable. Missing approval fails before application modules import, directory
creation, port allocation or service startup. Every formal cell and completed
trial revalidates source and evidence hashes. A mutation stops the experiment;
its output is marked invalidated, and a new reviewed experiment is required.

SQL-only instrumentation fixtures and mock/unit checks are allowed before this
gate. They are never app results. No application timing run has started.

## Snapshots

`freeze.py --runtime` freezes clean commit
`5f94eb62da2857ab991de704935e7333b405cb8e` into a new immutable directory.
The ignored typeshed stdlib is copied and hashed explicitly. It is not linked
to live mutable sources. Runtime bootstrap has passed on the frozen source.

`freeze.py --suite-name <NEW-NAME> --final` copies all source/config/oracle files,
including `registry.json`, original-four walkers, and corpus adapters. It checks
before/after source hashes and never updates an existing snapshot. `--final`
labels a candidate, not permission to run. Old `suite-snapshot` and
`suite-initial-20261030` directories are preparation-only, superseded, and cannot
authorize experiments. Their partial early copy formats are not final inputs.

The primary overlay is built by `make_primary_overlay.py` in an owned snapshot.
Its `primary-boundary.patch` and effective per-file hashes are disclosed in its
manifest. Every primary policy uses that identical overlay. The clean base is
used for separately scoped uninstrumented HTTP controls. The SQL-only
`make_protocol_reference.py` overlay is a measurement reference, not app runtime.

## Measurement definitions

* **Protocol completion wall time:** immediately before real socket `sendall`
  of a prebuilt packet through receiving ReadyForQuery `Z`. This includes
  PostgreSQL work, local transport, driver row decoding and progress between
  reads. It is not server-only execution or pure network RTT. SQL construction,
  compilation, parameter encoding and packet construction are outside it.
* **Driver-call wall time:** entry to the original driver body through completion
  or error, before appending observer metadata. It includes parameter encoding.
* **Dispatches:** actual driver commands with a socket send; **protocol cycles**
  are separately counted actual Sync/ReadyForQuery completions. CommandComplete
  `C` and DataRow `D` counters are incremented in existing protocol branches.
  A failed SQL statement can complete a cycle without a CommandComplete.
* All BEGIN/SET/SAVEPOINT/RELEASE/DISCARD/COMMIT/ROLLBACK controls are retained and
  separately classified. Foreground thread calls and background prefetch worker
  calls are separated. Foreground includes synchronous speculative resolution;
  it must not be mislabeled as demand-only work.
* Summed intervals and their union are separate: background calls can overlap.
  Foreground protocol union is not a pure blocked-thread wait measurement.
  Unmeasured foreground CPU/wait breakdown remains unknown.
* Original app HTTP completion is observed before a separate harness control
  drains late workers and serializes traces. Natural context close never joins
  or repairs workers. Late calls retain the originating request ID. Sequential
  request pacing includes this explicit outside-response drain in both modes.
* Primary mode has no per-recv callback. Received wire bytes and DataRow payload
  bytes are unknown there. Detailed wrapper diagnostics measure these separately.
  Sent packet bytes are actual bytes passed to sendall (unknown after a failed
  send). Consumed payload bytes are never inferred from predictions.
* SQL fingerprints, packet metadata expansion, JSON serialization and file writes
  run in the post-response control channel. A minimal tuple append after the end
  clock still contributes observer CPU between calls. Residual effects on overlap
  and application e2e are controlled and reported, never subtracted as a constant.

Primary source overlay and wrapper diagnostic modes passed dedicated SQL checks
against independent PostgreSQL CSV logging, including expected error `Z`, control
commands, rows, encoding exclusion, and gated late-worker attribution. See raw
`protocol-validation-v6` and `v7`. The earlier v4 reference included packet
framing and is historical only; v5 and later use the corrected prebuilt packet.
Overhead controls retain rotated trial medians and all individual observations.
Repeat quiet-window controls after suite validation stops before release.

`OwnedPostgres(statement_logging=False)` is the primary/clean default. Independent
`log_statement=all` is enabled only for SQL/count diagnostics. Current v6/v7
overhead observations used logging for validation; repeat quiet controls with
query logging off, and keep validation/count runs separately labeled.

## Workloads, identity and volatile fields

The runner uses the actual frozen `native.replay` and full `SCENARIOS` workflows,
including reads, accepted mutations, rejected mutations and permission checks.
Authentication, provisioning, Seed, graph import and inspection are setup or
verification. They never enter primary workload DB totals.

For original apps, retain the original logical-ID oracle, feed ordering,
authorship, node fields, full edge topology and restart/blob checks. Wall-clock
mutation timestamps are retained raw. Only the existing source-oracle exemptions
for new session objects' created_at/updated_at and the specifically trashed
JDrive folder's updated_at are treated as volatile. Parse them, verify bounds and
created-before-updated ordering. Seed timestamps and all other fields remain
semantic. Never freeze global clocks or drop all timestamp fields.

For new apps, the initial persisted domain graph is ordered by creation sequence
and alpha-renamed first. One bijective ID mapping is then reused for the entire
action/output/final-graph transcript. Every ID remains distinct, including edge
endpoints, root ownership, embedded IDs and URLs. The final BuildRelease backend
creates a genuine SHA256 of its build label; that64-hex digest remains semantic
and unchanged. Field values and list/action order are preserved. Tests prove
consistent renaming matches while changed edges, order, amount, status, action
sequence and wrong embedded references fail.

An AST audit of all30 frozen apps identified exactly three declared walker-state
sets: `ReachIssue.seen`, `ExploreLinks.seen`, and `ImpactTrace.seen`, all `set[str]`.
Only those schema-proven serialized fields are parsed with `ast.literal_eval`
and compared as unordered membership. Types, distinct identities and known UUID
membership are validated. Ordinary strings and ordered lists/reports stay strict.
The schema and source declarations join the execution hash guard.

Original logical oracles are supplemented by full actual result/reports/view
response equivalence. `semantic_responses.py` uses immutable `http-raw.jsonl`,
final logical-ID anchors, strict field/order preservation and narrowly validated
mutation timestamp windows. `formal_supervisor.py` requires this check after
requests but BEFORE each original trial is accepted, archived or cleaned up.
The verifier and all16 reference cases are frozen in the main-reviewed plan.
Every original trial is rechecked at export. Raw case artifacts are verified
against `artifacts.json` before analysis; duplicate raw/gzip traces are refused.

Node/edge counts are not inferred from unchecked kind strings. Initial raw kind
counts are recorded. Before final census labels, verify the actual stored
encodings with a dedicated persisted fixture and query the real anchors table.

## Experiment plan and budget

Primary seed is 42. Original `smoke` parameters are length=32, users=6,
posts/user=4, channels=2, messages/channel=8 and folder depth=3. Additional apps
use their actual domain Seed(42) datasets; initial per-type and graph counts and
the exact fixture/graph hashes will be recorded by preflight, not guessed.

Each primary cell has one excluded fresh-state full-workflow warmup followed by
at least three independent measured fresh-DB trials. Policy order rotates by
application and repetition. Profiles reset at the first workflow request, then
adapt naturally within that workflow. Final-state read-only samples have three
explicit warmup reads and three measured reads, with equality checks. They use
the warmed profile and final mutated dataset; they are distinct from initial
state and mutation groups. New session per HTTP request. PostgreSQL/OS pages are
warm from seeding/verification; there is no OS-cache flush and no claim of cold
disk. Report first-request versus steady final-state results separately.

Required primary schedule: **480 full workflow cases** = 30 apps × 4 policies ×
(1 excluded + 3 measured). Correctness preflight adds120. Main deferred clean
HTTP/e2e from this primary release: the frozen clean path does not honor the
primary provider reset, so it cannot be a same-regime overhead control. Plan
fields are `clean_e2e_apps=[]`, `clean_e2e_cases=0`; clean app HTTP cells stay absent.
A future same-regime control needs an approved outside-timed reset and selected
correctness checks. SQL-only overhead controls and separately scoped thread-CPU,
count/model diagnostics remain available.

Planning estimate, not a measured app result: at 6–25 seconds per complete
fresh-state case (provision/seed, three server generations, workflow and reads),
600 preflight+primary cases take approximately1–4.2 hours. Actual preflight wall durations will replace
these assumptions before formal scheduling. Do not confuse setup duration with
DB-call time.

One marked owned cluster is reused within an experiment; fresh DBs isolate
trials. Completed DBs are dropped only after source/oracle checks, artifact
hash manifest creation, application-service stop and zero active DB sessions.
Failed databases remain in that stopped cluster. Cleanup is logged. No filesystem
cluster deletion or unrelated directory cleanup occurs. At least 4 GiB free is
required. Budget ≤1 GiB for the reused cluster plus retained failures, and
approximately 1–3 GiB for compressed/raw traces and evidence; update the estimate
from preflight trace sizes. Disk was ~14 GiB free at the latest preparation check.

## Release artifact schema (main agent only)

Every reference has `path` (absolute or relative to the containing evidence index)
and the actual file `sha256`. The following is documentation, not a real release:

```json
{
  "schema_version": 1,
  "status": "approved",
  "reviewer": "main-agent",
  "runtime_manifest": {"path": "<clean-base>/snapshot.json", "sha256": "<64 hex>"},
  "overlay_manifest": {"path": "<effective-primary>/snapshot.json", "sha256": "<64 hex>"},
  "suite_manifest": {"path": "<coherent-final-suite>/snapshot.json", "sha256": "<64 hex>"},
  "acceptance_manifest": {"path": "acceptance.json", "sha256": "<64 hex>"},
  "preflight_manifest": {"path": "preflight/preflight.json", "sha256": "<64 hex>"},
  "instrument_manifest": {"path": "instrument.json", "sha256": "<64 hex>"},
  "experiment_plan": {"path": "plan.json", "sha256": "<64 hex>"}
}
```

Acceptance index: schema_version=1, suite_manifest_sha256, and exactly 30
`entries`, each with `app` and `policies.none`/`policies.ttg`. Each policy has true
`native`, `restart_persistence`, `source_freshness`, `english_audit`, and (except
LinkedList) `browser` and `browser_restart`. `summary` references the real suite
summary with matching app/policy/seed42 and passing native/restart/browser fields.
`english_audit_evidence` references a JSON object with passed=true and the exact
suite_manifest_sha256. Flags alone cannot replace referenced summary evidence.

Preflight index: schema_version=1, clean runtime_manifest_sha256,
overlay_manifest_sha256, suite_manifest_sha256 and exactly 120 `cases` covering
all30 × all4 policy labels. Each case has app, policy, seed=42, passed=true,
fixture_sha256, actions_sha256, outputs_sha256 and an `evidence` reference to its
real trial summary containing the same hashes. Each app's three hashes must
match across policies. Failure stops that preflight; failed cells are not passes.

Instrument index: protocol_validation_passed=true, overhead_control_passed=true
after reviewed quiet-window controls, exact source `files` references (including
driver_probe.py, overlay builder, runner, workload engine, gate, runtime wrapper
and control server), raw protocol/count/overhead evidence references, and an
English explanation of residual perturbation. Until main review, the overhead
flag remains false. The overlay manifest binds the clean base, exact patch and
all effective runtime files. Any mutation invalidates the release.

Plan index: seed=42, measured_trials≥3, all30 `apps`, all4 `policies` (none, ttg,
dependency_always, dependency_expected_benefit), original_scale="smoke",
primary_instrumentation="direct_boundary", runtime_manifest_sha256,
overlay_manifest_sha256, suite_manifest_sha256, quiet_window_confirmed=true,
clean_e2e_apps=[], clean_e2e_cases=0 and the explicit deferred-reset reason.
The plan binds required_formal_entrypoint="formal_supervisor.py",
original_response_reference (path/SHA256) and semantic_verifier_sha256.
Numeric aggregation/export/selection/semantic-verification sources join the
instrument manifest. Presentation layout/render code has a separate report-version
manifest with exact input hashes and numeric-figure mapping, so a font fix does
not invalidate the immutable raw experiment.
The main agent releases the exact plan, not an open-ended timing task.

## Commands

```bash
python3 -m unittest discover -s reproduction/ttg-app-performance -p 'test_*.py' -v
python3 reproduction/ttg-app-performance/runner.py check-release
# After all30 acceptance only:
python3 reproduction/ttg-app-performance/runner.py preflight \
  --runtime <base>/snapshot.json --overlay <primary>/snapshot.json \
  --suite <final>/snapshot.json --acceptance <acceptance.json> --output <NEW-preflight>
# Only after the main agent creates the fixed release file:
python3 reproduction/ttg-app-performance/formal_supervisor.py formal --output <NEW-experiment>
```

The formal command currently refuses because no authorization exists. Unit tests
create synthetic approvals only inside temporary unit-fixture directories and
never write the fixed authorization path.
