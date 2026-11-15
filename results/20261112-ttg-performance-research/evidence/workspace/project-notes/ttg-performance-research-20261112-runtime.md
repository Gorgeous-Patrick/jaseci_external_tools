# TTG runtime and fixture research — November 12, 2026

This is a new source-only study. No database, compiler, import of Jac, benchmark, or production edit was performed. Core t3 owns the database window; Core t4 owns independent review. Existing publications and the aggressive worktree remain unchanged.

## Runtime identity and three modes

Use the latest accepted immutable clean snapshot `reproduction/ttg-condition-access-performance-20261111/runtime-clean-v1`, rather than executing the mutable development checkout. Its manifest is `project-notes/measurements/ttg-condition-access-performance-20261111/clean-manifest.json`, SHA256 `39ab46b843377eb5ecabe077c3b9ea0b40194ff9ef07129233a37af6a0e3d033`. The instrumentation overlay manifest is its sibling `overlay-manifest.json`, SHA256 `4deaf0ea8ec25e7b71e49e75d8bbd9efb29dade1413ab4e6893a54d09f8a2e18`.

Development HEAD is `96868d0400a2f91fbfa48112c7ee291c891d2d03`; the dirty source is intentional and part of the runtime identity. All 30 modified/untracked files match the named immutable clean manifest. Latest unified normal/condition-call Access source is `ttg_access_plan.py` SHA256 `38b6ae55771ab08245c351da50e61282df685b3d649d2676a0e64c37bf6f6f48` and `ttg_access_graph.py` SHA256 `e040ff582f89f698ecf4bcbd52f2aee2ef60b62755f5bddd2a7ef497530981bf`. The Nov11 verification records 61 pure and 89 native regression checks; this research reads their accepted evidence and does not rerun them.

The historical aggressive worktree is clean at `a6aab9a5a68c94b5d173715a2f6441032c5a7570`. Eleven named legacy/shared files, including `prefetch_policy_ttg`, `ttg`, `impl/ttg.impl`, `ttg_sql`, `prefetch`, topology/query planning and Session implementation, are byte-identical to the latest clean snapshot. Exact hashes and scope are in runtime-identity-v1.json. This supports a common-runtime comparison; it is not an assertion of arbitrary whole-module observational equivalence to every historical runtime. Shared standard-access behavior applies uniformly, and each policy still requires actual business/oracle acceptance.

| Mode | prefetching | ttg_fused_sql | Behavior |
|---|---|---|---|
| Off | none | false | Native graph access, no prefetch dispatch |
| Aggressive | ttg | false | Existing JacTTGGenerator.get_ttg_prefetch_list entry planner and legacy payload dispatcher |
| Conservative | ttg_dependency | true | Dependency/Visit regions plus unified ordinary and conditional-call Access, safe runtime bindings and conservative boundaries |

All three use `async_prefetch=thread`, `ttg_prefetch_model=always`, one worker, limit 2048, topology index and cross-root resolution enabled, seed42. `Always` is admission policy; “conservative” describes dependency/path eligibility, not a learned cost model. The new Access path requires exact Always and fused SQL. Resumed native branch/body/join hooks bind live locals after unresolved conditions; they do not evaluate arbitrary user conditions speculatively. `jobj` is LookupById Access, separate from Visit. `_owns` now exposes its actual root-neighbor graph read and short-circuit predicate. Loops, unknown effects, arbitrary heap aliases and unresolved helpers remain boundaries.

Source entry points: `runtime/prefetch.jac:206` selects none/ttg/dependency; `runtime/prefetch_policy.jac:58` dispatches ttg; `runtime/prefetch_policy_ttg.jac:11` calls the existing generator; `runtime/ttg_dependency_prefetch.jac:157` gates the dependency context; `runtime/ttg_access_plan.py:522` resolves Access and `:684` is the native resumed-control hook. Its compiler integration is `:706`. The chosen frozen artifact contains the corresponding exact files.

## Ordinary standard-access contract

The current runtime uses ordinary Jac nodes/fields and standard anchor permissions. `runtime/impl/archetype.impl.jac:244` rejects any MRO-defined custom `__jac_access__` without invoking descriptors; assignment of such a custom hook is rejected at `:305`. `data/ttg_acl.jac:5` invokes this same contract. This is a changed runtime-wide contract, not an inference from a particular node or a silent ACL bypass. Existing compiled guards additionally require safe ordinary storage and standard attribute access. Unsupported-control apps remain in the benchmark; custom-access programs cannot be presented as supported controls under this runtime contract.

## GIL-off thread configuration

Launch through `reproduction/ttg-littlex-freethreaded/python.sh`: CPython3.14.6 free-threaded executable, `TTG_REQUIRE_GIL_OFF=1`, and PYTHON_GIL unset. Fail closed on `Py_GIL_DISABLED != 1` or `sys._is_gil_enabled() != False` at startup, actual SQL boundaries, outcome/close and exit. Every actual background SQL must use the same OS process as foreground, a different actual thread and separate PostgreSQL backend. Zero eligible work is a valid inactive policy result, not proof that a worker ran. All policy names need the thread-specific audit branch; do not inherit old before/after-name assumptions.

## Publication and metric interpretation

Latest published package is `jaseci_external_tools/results/20261110-ttg-access-visit-comparison`; current slides are report-v4. Its RecipePantry Conservative result is118/164 demand coverage,118 used/0 unused,213 data+166 control SQL. JDrive/LittleX and Aggressive captures are Nov10, Recipe latest Conservative Nov11. The package explicitly presents a versioned precision summary, not a simultaneous three-mode timing comparison. Relevant publication commit is `efa26c7b7612f317fc725a8f73c24d5f4993e4b2`.

New results should report all-role DB send-to-ready wall sum and interval union, data/control SQL and all-role total, separately from instrumented HTTP response-read sum/span, drain, setup and restart. Background attribution follows the originating RPC even when work finishes late. No HTTP-minus-DB CPU estimate. Precision demand is successful foreground Session.get/batch_get excluding planning, unique by request/Session then summed. Report payload returned/used/unused/late and foreground served coverage; ordinary Access without Visit is useful demand. Root-neighbor IDs accessed by `_owns` count as valid Access, not white reads. Excluded-query-filter candidates require source/fixture validation and disjointness before adding to unused payload counts. Logical JSON props bytes are not wire bytes or scanned SQL bytes. Off/unsupported zero-prefetch cases must pass observer validation with zero numerator and a retained demand denominator; existing precision_observer.py:135/144 assumes nonempty batches/deliveries and needs a new external-harness path. No production change is required for this issue.

## Fixed application coverage

Preserve all prior15 portfolio apps and add RecipePantry and LinkedList:17 distinct applications. This avoids replacing old slower cases after seeing results. If main requires exactly15, choose exclusions before executing and document them; no source evidence requires dropping any of17. Existing `reproduction/ttg-portfolio-v2-20261104/run.py:19` provides the original15 full workflow selection. Reuse its native scenario/oracle integration, not only registry read walkers. `fixture-feasibility-v1.json` contains exact per-app source hashes and visit/helper/cancellation sites.

| App | Concrete source coverage |
| jdrive | Typed visible Folder recursion, boolean trash pruning, depth/path output; ListFolder Access without Visit; trash/mkdir mutations. |
| littlex | Feed root/profile and two ordered Post/Follow paths; ordinary to_profile_view graph reads; like/follow/create mutations. |
| issue_desk | Root->Project->Engineer/Issue branches; Blocks reachability with seen set and disengage; assign/comment/close/reopen invariants. |
| stock_room | Warehouse->SKU/Lot/Reservation/Dispatch branches; ordered allocation, reserve/release/dispatch writes. |
| clinic_queue | Clinic->Practitioner->Slot; booking availability and cancellation. |
| budget_ledger | Budget->Envelope/Category/Transfer; conserved transfers and spending limits. |
| knowledge_map | Article reader/helper revisions; ExploreLinks uses visited set and LinksTo cycle boundary. |
| course_path | Root->Course and Enrollment; helper graph reads, prerequisites/completion changes. |
| approval_desk | Expense reader/helper; SubmitExpense->LineItem traversal then approval routing; line aggregation and payment writes. |
| library_loans | Library->Patron/Title/Loan; copy/hold graph reads and loan queue writes. |
| event_seats | Venue->Event; helper Seat/Booking graph reads and hold/confirm/cancel state. |
| help_queue | Desk->Customer/Agent/Ticket; EvaluateSLA traverses tickets and _escalate writes. |
| delivery_route | Depot->Route/Parcel; stop/attempt helper reads, load/deliver/retry state. |
| volunteer_shift | Organization->Volunteer/Shift; capacity/waitlist signup/cancellation. |
| incident_room | Root->Service/Incident; ImpactTrace follows reverse DependsOn with shared seen set; acknowledge/resolve state. |
| recipe_pantry | Root Ingredient/Recipe/Meal branches; _requirements joins and _owns root-neighbor Access; shopping reduction and conserved inventory. |
| linked_list | Unmodified Traverse count cutoff10000, Sum reduction, Find early cancellation; single-successor fixture separately proven. |

HelpQueue SLA writes, ApprovalDesk routing, KnowledgeMap/IncidentRoom seen-set traversal, and LinkedList early Find cancellation are deliberate unsupported/partial-support controls. Do not label an entire app unsupported because a particular helper is a boundary. Keep zero activation, slow cases, branch-negative and rollback cases. The shared output accumulator alone does not establish access dependence.

Original-app independent models are frozen `datasets/ttg/build.py` and `app_suite/native.py`; domain scenarios are frozen evaluate/scenarios plus independent transcript replay and exact stored state. Recipe uses the accepted augmented scenario with all-planned/mixed/all-cooked ShoppingList checks and inventory conservation. Scale-specific oracles must derive independently from fixture parameters, not copy native outputs. Every new scale requires exact output/order/duplicate checks, mutations/rejections, fresh sessions, restart and physical graph/state acceptance before timing.

## Scale proposals and concrete gaps

- **JDrive:** existing depth3/5/7 deterministic 3-ary graph generates40/364/3280 Folders and13/121/1093 Files plus one Drive. Hidden root branch has populated descendants; preserve trash pruning, files, ListFolder, trash/mkdir and repeated tree. Existing model independently walks visible folders and verifies final graph. Depth7 is real reachable graph growth; prefetch2048 remains a disclosed bounded budget, not whole-graph coverage. Depth5 has already been measured in the prior15 study.
- **LittleX:** existing smoke6profiles×4posts=24tweets, small50×20=1000tweets, medium500×100=50000tweets; deterministic follow skew remains. Run full feed/search/like-toggle/follow/create/final-feed workflow plus profile helper. A constant small number of followed authors means global population growth and per-request fanout growth are distinct; publish actual reachable authors/posts per RPC, not merely total tweet count. The independent set-based feed model and graph mutation model exist. Do not claim all50000tweets are accessed by a feed.
- **LinkedList:** original graph32/1000/10000 nodes, all-Item/single-Next/acyclic proof from independent logical topology. Original Traverse stops at visited10000, which is a TOTAL counter, not depth. Keep original source for32/1000/10000; do not advertise >10000 as full Traverse. Preserve Sum and Find(first/middle/last/missing). Limit2048 intentionally caps prefetch on10000; show capped submissions and actual10000 native visits, or predeclare a uniform increased budget across both TTG modes. Any finite-to-end typed variant is separately named and is not an undisclosed source adaptation.
- **RecipePantry:** current Seed/scenario is hard-coded to3ingredients/2recipes; repeating ten sessions does not scale its initial graph. A new deterministic graph fixture and parameterized independent business oracle are required. See forthcoming owned larger-fixture proposal; do not time a “large” label until initial node/edge/cardinality and actually reached workload counts are independently proven.

No new native acceptance or performance is claimed. Source/data preparation is executable only after t3 integrates an immutable selection/config/oracle manifest and main coordinates correctness then formal windows. No old publication or harness was edited.

## Implemented pure Recipe graph scale

The authorized independent module is `reproduction/ttg-performance-research-fixtures-20261112/recipe_fixture.py`, with interface and native adapter requirements in its README. It accepts ingredient/recipe/meal/cooked counts and requirement fanout. Small has92 nodes/96 typed edges/44root edges; large has920/960/440, including real cooked Consumption history. Both have14 fixed business operations, so scale changes the initial reachable graph, not session repetition. Parameterized all-cooked fixtures remain read-only controls. Eleven pure tests pass; initial two erroneous handwritten expectations and their correction are preserved. `measurements/ttg-performance-research-20261112-runtime/recipe-preparation-v1.json` binds source, tests, original unchanged application and generated inputs. Native importer/actor mapping, HTTP/report/poststate/rollback/restart correctness and review remain pending. No DB/compiler/timing or old-source edits occurred.
