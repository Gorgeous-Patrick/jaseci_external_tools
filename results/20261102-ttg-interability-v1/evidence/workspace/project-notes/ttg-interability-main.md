# Inter-ability SQL regions: supervised implementation

User authorized implementation, subagent supervision, small native benchmarks,
measured analysis, English slides and completion while away. This round follows
the source audit in `ttg-sibling-dependency-audit.md`.

## Baseline and ownership

- Clean core baseline: `9282e246d708aff69e21cb52b9d0cc4893fc5f0f`.
- New core branch: `feat/ttg-interability-regions` in `jac-ttg`.
- Main: scope/design decisions, supervision, DB/CPU scheduling, final review,
  progress, scoped commits/pushes and publication acceptance.
- P6 `ttg-app-suite`: core/compiler/runtime/SQL and focused native regressions;
  `project-notes/ttg-interability.md` and new implementation evidence.
- P7 `ttg-app-perf`: NEW `reproduction/ttg-interability-performance`, native
  workloads, measurement, analysis and slides; new performance note/evidence.
- P8 `ttg-bench-review`: bounded independent design/source/measurement review;
  new review note/evidence. Existing published artifacts remain immutable.

## First implementation contract

Start with genuinely sibling-free typed finite chains. Static per-ability and
supported-helper summaries separate access-relevant dependencies from output.
Compose visit dispatch into SQL regions, with typed node predicates inside SQL
where supported. Runtime supplies external values and selects/binds emitted SQL;
the original walker still executes native outputs and business behavior.

The first examples are a finite LinkedList traversal to its actual end and
A -> B -> C with B's ordinary scalar field selecting the C visit. The original
counter/disengage walker remains a distinct baseline workload. Total entered
node count is never treated as depth. Unsupported writes, cancellation,
unknown effects and access-relevant sibling state retain native fallback.
Ordered path-cache entries, exact prefixes, empty results, ACL, transaction
epoch and incomplete/budgeted results must retain their existing semantics.

Early integration review found the historical Traverse target is untyped.
The NEW finite-chain variant therefore records two explicit edits: remove its
cutoff and add the Item target type to that Traverse visit. The independently
constructed finite all-Item chain justifies that fixture-specific annotation;
it is not an inference about arbitrary Next edges. All three comparison modes
use the identical variant. Original source, Sum and Find remain unchanged.

After this works, use independent LittleX regions to test per-region activation
and reuse rather than the invocation-wide `frontier_attempted` limiter. This
is a bounded extension, not a generic FIFO interpreter in SQL. No cost-model
rewrite or DB prepared-statement work is included.

## Validation and measurement plan

Proposed primary fixtures: LinkedList32, LinkedList1000, typed guarded A/B/C,
and the unchanged original LittleX workflow. Modes: off, immutable9282, new
implementation; fixed admission/process executor/settings. Twelve native
correctness workflows precede 48 fresh performance workflows (12 excluded
warmups,36 measured, n3 per cell). Predicate true/false, fallback and malformed
or unsupported shapes require focused functional tests as appropriate.

Record total data/control SQL across all roles, send-to-ReadyForQuery DB sums
and unions, per-request path/payload counts, actual child OS and PG backend
identities and observed overlap. Do not infer overlap from process existence or
CPU causes from SQL wall time. Retain negative or unsupported workload results.
Re-use accepted compact observer/semantic replay/owned cleanup primitives;
changes need focused tests rather than a new verification framework.

Before freezing this round's harness, main requires identical explicit
`ANALYZE anchors` and `ANALYZE graph_types` after setup/excluded warm views and
before primary timing/profile reset in every mode. Record the admin commands
and a small statistics witness outside application SQL metrics. The previous
controlled experiment established substantial plan sensitivity to initialized
statistics. This new, disclosed regime avoids that known setup confound;
historical unnormalized timing vectors are not same-regime comparisons.

One owned DB/heavy CPU window at a time. Initial free disk was1,136,238,592B;
use immutable hardlinks with atomic overlays and bounded WAL32/64 settings.
Preserve failed evidence and stop safely on capacity risk. No arbitrary new
approval loops: main can release concrete reviewed correctness/performance
work within the user's standing authorization.

## Required English slides

1. New inter-ability dependency method: real Jac code, local dependency graphs,
   dispatch/composed graph, SQL region and latest external-dependency checkpoint.
2. Existing replaceable cost model, feature/feedback flow and limitations;
   mechanism comparisons keep admission fixed.
3. Entire portfolio:30 registered application readers plus61 paper operations;
   clearly identify the small actually measured subset.
4. Actual correctness/SQL-count/DB-time results, bottlenecks and next steps.
5. Sibling dependence: output-only state, total count/cancellation, seen sets,
   reductions/top-k to later accesses, contracts and the next analysis boundary.

Final delivery includes measured evidence, editable diagrams/slides and PDF,
scoped source/results commits and pushes. Existing unrelated external-tools
working-tree changes must not be included.

## Additional user authorization

The user subsequently authorized continuing with larger datasets after the
slides are complete and then left. Preserve the priority order: small native
validation, small measured comparison and slides/publication first; then a
separate larger-data plan, correctness, measurements and additive report.
Candidate larger inputs are the existing LittleX50-users/20-posts generator
and a finite LL scale selected from measured1000-node capacity. Match budgets
across modes; do not blindly scale the older interpreter's retained suffix
metadata to10000 nodes. Main can choose and release the bounded follow-up
within this standing authorization without waiting for the user.

## Resource and model preparation

Main verified 2,782 files in two redundant old `/tmp` portability-check copies
against the unchanged canonical published packages, then removed only those
copies. Reclamation proof is in
`measurements/ttg-interability-main-20261101/temporary-copy-reclamation-v1.json`;
free space rose to1,285,013,504B. No unique evidence or published file was removed.

The source-bound existing model description is
`measurements/ttg-interability-main-20261101/existing-cost-model-v1.json`.
Its estimated opportunity window is not actual SQL interval overlap, and the
current fused path excludes shared batches from model training. Slides must
describe the replaceable method accurately while mechanism trials use Always.

## Implementation checkpoint

P6 delivered initial nine-file source checkpoint
`ttg-interability-20261101/source-v1/manifest.json` (a1ff3d32...) for independent
review. Initial offline failures were test typing/reserved-name issues and an
SQL spelling assertion; generated region SQL reached execution-free tests.
P6 subsequently restored the compiler hook emitter to9282: existing entry
observation already calls prefetch before the ability body. New static regions
reuse that hook, with no duplicate hook insertion. Native acceptance is pending.

P7's statistics normalization is placed once in the NEW Server.post override,
after setup/restart/views and before the parent starts the first workflow HTTP
clock and sends its profile-reset header. Exact commands, owner/database and
small statistics observations are recorded separately from application timings.

P8's source-v1 review found five narrow issues: internal metadata falsely
blocking activation, output-write descriptor checks, node-exit trigger domain,
remaining payload cap, and output arithmetic that may raise before visit.
The source-v2 repair review passed; focused native validation continued.
Native-v1 stopped before setup; native-v2 stopped after test compile errors;
native-v3 passed two cases then exposed overwritten diagnostic reasons;
native-v4 passed four cases including actual zero-query native cache consumption,
fanout, cycle and overflow, then a malformed-data test used the wrong Store API.
Each failure and naturally stopped PG state is preserved. No performance samples
have been collected. P6 is correcting the test and adding the bounded later-region
LittleX attempt fix, with a pure-visit-prefix certificate and cache reuse.

## 2026-11-02 supervision checkpoint

Main handled the pending native-v5 approval directly. All nine focused native
tests passed in25.67s; outcome exit0. The malformed raw fixture is re-seeded
identically before each mode because deserialization can repair invalid values.
The bounded Stage2 collect-prefix case is included. Final regression/format/type
checks, immutable Stage2 review and scoped clean commit are next; no performance
acceptance follows from these functional counts.

P7 froze20 changed harness/fixture sources under review-candidate-v1, manifest
93ae77c7aac4a0ece262f07ce963624704cc3b2bc7bdf7e17bca0e8076a7fa92.
Eight tiny offline checks passed; P8 is reviewing the changed source while P6
finishes core verification. Runtime metadata remains pending. Main independently
read the statistics boundary and sanity policy: uniform excluded ANALYZE, strict
list total-SQL reduction, tiny heterogeneous chain composition/cache correctness
without imposing a speedup requirement. The DB window remains exclusive to P6.

Focused native review passed at native-pass-v1-review.json
4d30896b38b2d1342d47764736dbf4f3891d20c94f7e475aac82853edf0b6ca8;
Stage2 source delta passed6ac30a03, harness passed85830662. Main requested an
additional read-only presentation of actual instrumented HTTP response wall
from existing sealed request records after capture, distinct from DBsum/union
and post-response drain. No capture change or wall-minus-DB CPU inference.
Final formatter passed9; module-local annotation fixes are undergoing typecheck
before the existing206 plus14 new selected regression tests.

Final regression-v1 preserved173PASS/1FAIL on the preexisting chosen-branch
thread-promotion assertion, with new fusion disabled. Source unchanged; owned
PG stopped. Unavailable is submitted-minus-promoted-minus-unused accounting,
not proof of absent DB rows. Payload callback87ms and early demand are consistent
with the default50ms demand-fallback path, but inherited environment was not
bound and historical causality is not established. The exact unchanged test
passed in isolation5.09s after a first no-tests-selected attempt was preserved.
Main authorized a TEST-ONLY deterministic completion setup for the promotion
assertion, preserving all assertions and production timeout/session behavior.
Any follow-up is source-bound and will be included in the final selected run.
Reviewer observation37200565 preserves the timing qualifications.

Final regression-v2 completed220PASS19.05s/source10 unchanged/PG3. The
reviewed test-only completion wrapper preserves all nine assertions; final
source/regression review7110b9c1 passed. Runtime default wait is unchanged.
The run's retained DB growth exceeded the estimate; actual free briefly fell
to60.8MB and recovered to261.5MB after natural shutdown. Main immediately held
all work, authorized only regenerable JIR cache removal and a lossless archive
of the exact stopped owned regression cluster. P6 verified30,596 members before
removing originals; archive111,890,644B SHA8186c9de3452f2bf4dbd4d5764075d798fc015315828ff98ff22acbb91187a4b
retains failed databases. Free space then1,193,353,216B. No failed data was discarded.
Scoped clean commit/proof follows; application workload capacity must use actual
case observations rather than this test-cluster forecast.

## Formal small matrix complete

Main released exact48 under authorization80d99d17 and review63ca5091 after
15 correctness cells, three mechanism gates, stopped proof7f3ffb95 and capacity
3b7ebe88 passed. Formal48 completed without source/correctness failure:12excluded
warmups and36measured samples. P6/P8/main kept the capture window quiet.
Core branch feat/ttg-interability-regions, commitaddd3a4, was pushed successfully
to Gorgeous-Patrick/jaseci after capture completed.
The original exporter reached output construction then failed on obsolete plan
metadata keys cache/learning. Main authorized a NEW standalone v2 exporter
using actual plan.regime; captured172-source closure/raw/numeric calculations
remain unchanged, and failed export is preserved. Full raw audit and slides
follow successful strict export.

## Audited small results and bounded SQL diagnostic release

Strict export-v2 b9a4f485 and independent formal48 data review e957a5ad
passed. All48 samples retain exact counts, protocol intervals and native
acceptance; actual SQL sum equals union. Recorded HTTP response sums distinguish
the large interpreter-bypass gain from SQL time: LL1000 off/baseline/new medians
1240.857/30841.349/726.128ms, while baseline/new DB medians31.441/59.877ms.
LittleX remains slow at98.207/1586.361/1592.227ms HTTP; six scoped child readiness
intervals sum to about1.145s in the new mode. Readiness includes imports and
handshake, not just Popen or DB connection. No residual CPU or additive critical
path attribution is claimed. Analysis3225413d and startup51e0117e bind evidence.

Main reviewed diagnostic candidate-v3 4f9715e3, all7 own+11 borrowed hashes,
selection30dd4f26 and prior raw target review fccd9621. A prelaunch actor lookup
bug was repaired: item mapping does not contain user:0; actual SuiteRoot report
and SuiteImport roots now establish actor lineage. Main release7ee89067 permits
exactly two LL1000 workflows, two selected recursive queries and four EXPLAIN
plans under unchanged statistics normalization and768/640/512MiB guards.
No variants/later ANALYZE or concurrent rendering/timed work. The source remains
frozen; original completion and full native acceptance precede diagnostic
acceptance. Natural stop/first-failure preservation remain required.
