# Required method, cost and sibling figures

These are source-only figure instructions, not a new implementation or an executed renderer.

## General vision: illustrative A→B and A→C

Show three Jac node instances, A above B and C. Each contains a distinct ability-local dependency graph: parameter/field Access → guard → Visit. Graph edges A→B and A→C connect Visit dispatch to child entry; internal dashed edges mean data/control dependence. Add a labelled candidate SQL region crossing ability boxes only in an inset headed **Illustrative general runtime composition / latest-dependency placement — future work**. Region entry must be after all external bindings are defined; an unknown helper or shared control dependency is a boundary. This is a proposed general explanation, not evidence that the current runtime certifies this arbitrary branched example. It does not negate the prior bounded heterogeneous certificate below.

Sibling counterexample inset: pending order B,C; `self.i=0`; B executes `self.i+=1`; C's next visit depends on `self.i`. Connecting B's write to C's guard exposes possible dependence. A single identical entry snapshot for both siblings is unsound. A shared output append alone does not establish access dependence, and a lack of present analyzer support does not establish theoretical impossibility.

## Prior implemented heterogeneous certificate: finite A→B→C

Bind project-notes/measurements/ttg-interability-20261101/method-inputs-v1.json SHA8922f473d720128b7808259ec4e4c536cb30b0741cb2f08dad333393d021b28b (runtime addd3a4). Draw RegionA entry ability → typed RegionAB visit → RegionB entry ability → typed RegionBC visit → RegionC entry ability. Inside B show `here.active` Access → ordinary Boolean SQL guard → Visit C; shade one finite/unrolled SQL region across the distinct ability definitions. This is actual bounded static composition, not an invented example of current broad support.

The artifact records exact local summary fields, dispatch edges and external dependencies (origin, exact dispatch, actor/ACL), actual emitted guard SQL SHA9112d09d205655b73730a5efe4c322fdbbf88f6b420d4368503b423a5c577a9b and accepted native true/false cases. True: one region query, two cached paths, report[17], two native pair calls with zero store.rows; false: one region query, one cached path, no report, one native pair call with zero store.rows. These are prior functional test records, not new portfolio measurements or proof of zero current payload SQL. Preserve the test-only completion/cache-proof scope.

The supported guard stays SQL-internal. Shared thresholds assigned by earlier abilities were rejected; general helper/alias/heap effects and arbitrary latest-definition checkpoint placement remained future work. A false guard does not invent an empty graph path. Keep this scope separate from the current restored-background JDrive certificate and its performance numbers.

## Actual compiled example: JDrive Folder recurrence

Bind frozen originals/jdrive/server.jac lines 103–111 and server.impl.jac lines 44–68. A, B and C are **Folder instances**, not three heterogeneous node classes. All enter `VisibleFolderTree.walk`.

Each Folder box embeds two lanes. Native output lane: `here.name` → entries/depth/path bookkeeping → later native report/sort. Access/Visit lane: typed `[here ->:Contains:->[?:Folder, trashed == False]]` → complete ordered child pairs → `visit` the same predicate. The child loop also reads `child.name` for output paths. Shade the recurring Access/Visit lane across A.walk, B.walk and C.walk as one **implemented output-tree certificate / recursive SQL** region; leave output computation and `done` outside it. Do not claim that output state is absent: explain that its certified effects do not determine this child predicate.

Below the graph, draw the actual execution chain: owner eligibility/effect proof once per attempt after single-flight/coverage → immutable origin/actor/snapshot capture → worker selects/binds emitted tree SQL in a private transaction → complete row/property/order/empty/closure/cycle validation → owner epoch/capacity check and atomic native-cache publication. Native Visit execution remains authoritative. A compact evidence label links final restoration runtime/native review7012, large export38e58fcd and large raw auditf59b. Actual three recursive SQL calls/five jobs are observed workload counts; publication1600 is summed origin paths, not timely hits.

## Cost model page

State **Always admission in every enabled control/new policy in this experiment**, within each policy's actual eligibility, capacity and cancellation rules. This is not unconditional successful scheduling and does not exercise learned ExpectedBenefit. A conceptual roadmap can compare expected avoided blocking reads against snapshot/setup, planning/binding, dispatch/transfer and wasted work, with queue/cancellation/transaction lifetime as constraints. It must be labelled unimplemented adaptive decision logic, with no fitted coefficients or claimed savings from wall-minus-DB subtraction. DB prepared-plan reuse is separate deferred work.

## Sibling page

Three explicit outcomes: (1) proven absence of access-affecting dependence under a bounded certificate; (2) statically exposed MAY dependence; (3) unknown because of unsupported effects or external behavior. Separate output/reduction state, future query/visit selection, early return/disengage, queue order and writes visible to another sibling. Keep old interpreter assumptions distinct from new static pushdown, and do not present visited count as graph depth or a chain proof.
