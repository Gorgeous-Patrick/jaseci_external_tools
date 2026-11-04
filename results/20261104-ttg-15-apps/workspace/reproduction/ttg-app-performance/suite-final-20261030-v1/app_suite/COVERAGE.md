# Application traversal and dependency coverage

The inventory contains one microbenchmark and 29 full applications. These are
functional research patterns, not measured performance results. The read walker
is a stable integration entry point; mutation scenarios exercise additional paths.
Exact source/oracle locations and target-ID requirements are in [registry.json](registry.json).

| App ID | Read walker | Native graph and workflow | Traversal / dependency pattern |
| --- | --- | --- | --- |
| `linked_list` | `Traverse` | Next chain; bounded ordered traversal | Depth, sequential pointer dependence; microbenchmark |
| `littlex` | `load_feed` | Profile follow edges to author posts; merged feed | Shared fan-out and multi-hop joins |
| `jacord` | `load_channel` | Server membership, channel messages and authors | Target-scoped fan-out; access-dependent traversal |
| `jdrive` | `VisibleFolderTree` | Folder containment and file ownership/permissions | Recursive tree; visibility pruning; byte persistence |
| `issue_desk` | `ProjectBoard` | Projects, issues, blockers, assignees and comments | Dependency DAG; cycle rejection; shared assignee fan-in |
| `approval_desk` | `ExpenseBoard` | Expense, ordered approval steps, employees and decisions | Ordered state-gated progression; threshold branches |
| `stock_room` | `Inventory` | Warehouse, products, bins, reservations and stock movements | Shared product joins; atomic quantity conservation |
| `clinic_queue` | `ClinicSchedule` | Practitioners, patients, appointments and slots | Interval overlap rejection; cancellation and rebooking |
| `course_path` | `LearningDashboard` | Courses, shared lessons, prerequisites and enrollment progress | Prerequisite DAG; shared subgraphs; per-user completion |
| `library_loans` | `LibraryCatalog` | Titles, physical copies, members, holds and loans | FIFO queue; exclusive copy ownership; promotion |
| `event_seats` | `EventCatalog` | Venue, sections, seats, bookings and refunds | Exclusive resource edges; confirmation/cancellation branches |
| `help_queue` | `DeskBoard` | Desk, customer, agent, SLA, ticket and reply | Deadline predicate; escalation; reassignment |
| `recipe_pantry` | `PantryBoard` | Recipes share ingredients; meals, purchases and consumptions | Shared ingredient fan-in; aggregate need; conservation |
| `trip_board` | `Itinerary` | Journey, day-ordered stops and accommodation stays | Ordered adjacency; same-day reorder; bounded intervals |
| `delivery_route` | `RouteBoard` | Depot, route, parcels, ordered stops and scan history | Capacity predicate; sequential stop dependency; retry |
| `hiring_pipeline` | `HiringBoard` | Job, candidate, application, interview and scorecard | Multi-round gating; score thresholds; shared candidate exclusion |
| `sales_pipeline` | `SalesBoard` | Account, contacts, opportunities, activities and quotes | Branching sales state machine; accepted quote dependency |
| `grant_review` | `ReviewBoard` | Proposal, reviewer, assignment, conflict and review | Bipartite assignment; conflict exclusion; weighted fan-in |
| `lab_samples` | `LabBoard` | Sample, aliquot, batch, assay and result history | Volume conservation; latest-result branch; release gating |
| `asset_care` | `AssetBoard` | Asset, inspection, work order, technician, part and use | Fault-triggered work; part-stock join; quantity conservation |
| `utility_meter` | `MeterBoard` | Building, meter, monotone readings, tariff and invoice | Ordered history; interval uniqueness; tiered aggregation |
| `volunteer_shift` | `VolunteerBoard` | Organization, skills, volunteers, shifts and signups | Skill intersection; bounded capacity; FIFO waitlist promotion |
| `poll_assembly` | `AssemblyBoard` | Assembly, motion, options, eligible voters and ballots | Replaceable ballot edge; quorum and majority fan-in |
| `budget_ledger` | `BudgetBoard` | Budget, envelopes, category entries and paired transfers | Ledger aggregation; paired-edge conservation; duplicate refs |
| `build_release` | `ReleaseBoard` | Release, build, artifact, prerequisite checks and deployment | Check dependency chain; descendant invalidation; immutable release |
| `knowledge_map` | `KnowledgeBoard` | Article, revision, review, topic and cyclic links | Version-specific approval; cyclic reachability and backlinks |
| `return_counter` | `ReturnBoard` | Order, line, return request, inspection and refund | Quantity bounded across requests; inspection-gated single refund |
| `garden_plan` | `GardenBoard` | Plot, crop, planting, prerequisite tasks and harvest history | Capacity sum; family rotation; task-gated transition |
| `tournament` | `BracketBoard` | Tournament, rounds, matches, teams and results | Bracket DAG; winner propagation; immutable result |
| `incident_room` | `IncidentBoard` | Service dependencies, incidents, alerts and response actions | Cyclic reverse reachability; visited set; all-child resolution gate |

## Workload boundaries

Every new-app scenario seeds an authenticated owner graph, executes accepted and
rejected business actions, checks explicit invariants, verifies cross-user access
and re-reads persisted state after process restart. The browser then changes the
graph through actual forms/buttons, followed by another restart and native oracle.
Original-four adapters preserve application source provenance and use the original
workload walkers. LinkedList is explicitly exempt from the browser gate.

Fixed seed: 42. Original-four acceptance scale: smoke. Each added application uses
its documented deterministic domain scenario. These workflows test sequential
business correctness; they do not establish concurrent contention, external-service
integration or production-scale performance. The existing 36 logical datasets
remain a separate seed/scale expansion, not an implied native pass.

Formal performance is blocked until all 30 entries pass both none and ttg native,
browser (microbenchmark exempt), restart, English and current-source gates.
Four-policy correctness preflight and review of a final immutable source snapshot
precede timing. DB-call wall time, SQL count, application end-to-end time and
background prefetch attribution must remain separate; unmeasured fields are null.
