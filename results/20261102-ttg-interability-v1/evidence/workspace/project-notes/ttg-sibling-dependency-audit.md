# Static analysis of access dependencies across the benchmark portfolio

This source audit covers the 30 registered application readers and the 61 selected paper-benchmark operation identities: TPC-H 22, SNB 29, TPC-C 5, and Wikipedia 5. Additional application walkers are reported separately. The unit of the first group is one registered reader, not every operation in an application. These are source-based feasibility arguments for an analysis with explicit effect summaries, not results from an implemented analyzer or new performance experiments.

## Completed portfolio results

| Inventory | Count | Source-based result under the stated summaries |
|---|---:|---|
| Registered application readers | 30 | 29 admit absence arguments for sibling access interference. LinkedList Traverse exposes total-count/cancellation MAY dependence. Additional application walkers are separate below. |
| TPC-H | 22 | All 22 admit absence arguments within their individual sibling stages. Across the whole operation, 16 have no mutable access feedback after summaries; Q5/Q7/Q15/Q17/Q22 have phase-to-access dependencies; Q20 retains a reduction/value barrier and conditional field-materialization obligation. |
| SNB | 29 | 15 traversal operations admit absence arguments; IS2 selects later nested spawns from top-k results; IC3 gates final Person fields using accumulated counts. The other 12 operations are Root-only procedural queries/updates, with no sibling traversal. |
| TPC-C | 5 | All five use a single Root ability. Sequential lookup, loop, mutation, and transaction dependencies remain; they are not sibling-dispatch examples. |
| Wikipedia | 5 | Two readers use singleton Page/Revision/Text chains; three mutations have no sibling dispatch and retain transactional effects. |

These columns deliberately do not form a pooled SQL-eligibility score. Within-stage sibling independence, cross-stage dependencies, field materialization, and Root-only procedural work answer different questions. In particular, the 29/30 application result applies only to registered readers, not their entire application workflows.

The exact 91 IDs and walker names match the two inventories, with no duplicates or omissions. The aggregation rehashed 46 unique referenced files. Full per-case records are in [ttg-sibling-dependency-audit.json](ttg-sibling-dependency-audit.json); it binds each component report by hash.

| Component | Detailed source arguments |
|---|---|
| Original four applications | [Originals](ttg-sibling-audit-originals.md) |
| First 13 additional applications | [Domain A](ttg-sibling-audit-domain-a.md) |
| Other 13 additional applications | [Domain B](ttg-sibling-audit-domain-b.md) |
| TPC-H 22 | [TPC-H](ttg-sibling-audit-tpch.md) |
| SNB 29 | [SNB](ttg-sibling-audit-snb.md) |
| TPC-C 5 and Wikipedia 5 | [Procedural operations](ttg-sibling-audit-procedural.md) |

## The question the analysis should answer

Can a write by one activation change a later activation's accesses, termination, or the accesses of a shared continuation? Include graph queries in helpers and exit abilities, nested spawns, graph mutations, and cancellation. Checking only `visit` expressions misses important dependencies.

Use two separate decisions:

1. **Dependence:** absent under stated contracts, statically detected MAY, or unknown without further contracts. Ordinary loop and transaction dependencies are marked separately from queued sibling execution.
2. **SQL boundary:** can the dependence be represented by a relational operation, does it require ordered procedural state, or is lowering unsupported/unproved?

A detected dependence is a successful analysis result. It does not automatically require a checkpoint or a benchmark rewrite. For example, a completed sum or average used to select later reads can be represented by an aggregate subquery feeding a join. If lowering supports that operation, its internal dependence stays inside SQL. Otherwise the completed aggregate is a natural external dependency for the next region.

## Proposed static algorithm

For each ability and callable helper, compute summaries of field/heap reads and writes, graph reads and writes, visit targets, cancellation, exceptions, and unknown effects. Build a backward slice from all access targets, access guards, and termination decisions. Ordinary output accumulation is excluded only when it cannot flow back into that slice; output order and values still retain their native semantics.

Compose summaries along dispatch, calls, and exit continuations. Check potentially aliasing writes against later access-relevant reads. A dictionary or set requires key/membership summaries; a field name alone does not establish disjointness. Use proven cardinality, ownership, and graph invariants when available. An opaque callback or unresolved alias produces an unknown result rather than an absence proof.

Then form regions using the SQL backend's supported operators. Find the latest external dependency for each region and place its checkpoint after that dependency becomes available. SQL-computable dependencies remain relational edges within the region. Queue order and total-visit budgets must not silently become depth or unordered sets.

## Program simplification versus compiler work

- Helper summaries, output/access slicing, and lowering comprehensions, reductions, and lookups are compiler work. They do not require changing benchmark semantics.
- Removing LinkedList Traverse's total-visit cutoff is an optional, explicitly different finite acyclic-chain workload. The cutoff counts all entered nodes, not depth. The existing generated chain permits a separate topology/cardinality proof; the generic walker source alone does not.
- First-match cancellation, cycle/identity deduplication, stock allocation order, validation, and rollback express observable behavior. Do not remove them merely to obtain a larger SQL region.
- No audited operation is declared theoretically impossible to analyze or compile. Some need contracts or richer lowering; unrestricted program analysis cannot promise a complete yes/no answer for every program.

## Assumptions and scope

Absence arguments use the inspected closed-world ordinary-field implementations, known builtin/helper effects, and a stable graph during a read region. They do not cover arbitrary descriptors, hidden callbacks, concurrent mutation, or external storage implementations. Exception behavior and valid-data requirements must remain explicit. Absence of sibling access interference does not prove termination, safe reordering of output, a single-successor graph, or a performance benefit.

The following component reports retain exact source hashes, line ranges, witnesses, and per-operation reasoning. The companion aggregate JSON binds those reports and checks inventory coverage. Earlier five-app/selected-walker findings remain historical and are superseded in coverage by this portfolio audit.

## Important distinctions in the inspected programs

| Example | Source dependency | Consequence for the proposed analysis |
|---|---|---|
| LinkedList `Sum` | Shared total is only reported; `Next` access does not read it | Separate reduction/output from the access slice; preserve reports |
| LinkedList `Traverse` | Shared total entered-node count gates `disengage` and later `Next` visits | Detect ordered control dependence; use a chain invariant only when actually proved |
| JDrive `VisibleFolderTree` | Shared path/depth maps affect output, but not the child queries or visits | Access independence does not imply output-order independence |
| IssueDesk `ReachIssue`, KnowledgeMap `ExploreLinks`, IncidentRoom `ImpactTrace` | `seen` membership suppresses later traversal; reachability may also cancel | Detect membership/identity dependence; retain cycle/duplicate/termination semantics |
| ApprovalDesk `SubmitExpense` | Line-item sum selects later approver queries at the common exit | Include exit continuations in the graph; an aggregate-to-selection region is a candidate |
| SNB IS2 | Accumulated messages are sorted and limited before nested `_OriginalPost` spawns | Top-k affects future access, so the list is not output-only |
| SNB IC3 | Shared counts gate final Person name-field reads | Retain the field/materialization dependence. This does not establish a new SQL dispatch: the current runtime may already have loaded those fields |
| TPC-H Q15 / Q22 | Reduction results gate a later helper scan or select nested order checks | Analyze exit helpers and aggregate consumers, not just visits in entry abilities |
| TPC-C NewOrder | Repeated stock IDs may alias across ordered read-modify-write iterations | This is a transaction/loop dependence, not an OSP sibling queue; retain rollback |

There is no justified list of programs that **must be simplified merely to classify them**. A conservative analysis can report the dependence. Simplification is a separate choice if the research intentionally restricts the target language/SQL subset. Conversely, a source absence argument is not a proof that the current SQL generator can lower the whole program.
