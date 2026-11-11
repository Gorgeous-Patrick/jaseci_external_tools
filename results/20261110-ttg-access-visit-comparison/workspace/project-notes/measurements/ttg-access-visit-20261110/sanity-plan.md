# Access and Visit: prototype and application sanity checks

The first implementation is an opt-in Jac-AST analysis artifact. It does not yet drive SQL, insert hooks, or change prefetch behavior. Existing runtime edits and benchmark records are preserved.

## Two concepts

Access represents a graph expression, including ordinary method/comprehension queries. Visit represents enqueueing query results or an existing value. Native node entry is a separate runtime observation: enqueueing is not proof that execution reaches the node.

The graph distinguishes value flow, data dependence and control dependence. A query used only as an if-condition must not become a Visit target merely because it controls a Visit. Calls and unsupported effects remain unresolved. A local no-Visit-flow finding is not proof that a result cannot reach Visit through a caller, alias or callback.

## Implemented DB-free checks

15 checks parse real Jac source: ordinary query/report; inline Access -> Visit; aliases; repeated Visit without duplicate Access; guard outside/inside Access; query controlling a different Visit; overwritten local; branch merge; opaque call; predicate external parameter; comprehension; ordinary node method; explicit .impl.jac binding; loop boundary; returned query without a global non-visit claim.

Whole-source inventory checks independently count EdgeRefTrailer and VisitStmt AST nodes, including JDrive's implementation file. LittleX: 31 Access / 17 Visit locations. JDrive: 6 / 1. RecipePantry: 12 / 4. These are static source sites, not runtime executions. All inventory deltas are empty.

The standalone analyzer retains source locations and source hashes. It is intentionally not installed as a runtime admission rule. Method receiver/type resolution, call argument/return summaries, effects, dispatch and queue reasoning must be established before this graph can safely drive prefetch.

## Application acceptance

Use the existing fixed LittleX, JDrive and RecipePantry workflows and business oracles across modes. Business responses, updates, state, queue behavior and exceptions must remain unchanged. Do not require prefetch counts to remain unchanged.

- LittleX: cover the 69 get_profile and 1 follow_user useful Access-only nodes currently covered by aggressive and missed by conservative. On the current fixed workload, 357 useful prefetched nodes is the reference, not a quota. Check exact request-local logical ID coverage rather than equal totals alone.
- JDrive: retain pruning of trashed descendants. Ordinary Access coverage must not reintroduce the 771 genuinely unread prefetched nodes. Separately account for candidate nodes read only to reject predicates; these are not automatically required in an optimized implementation.
- RecipePantry: cover ordinary helper and output accesses as well as Visit targets. Counts may increase from 31. Do not force a target of 112 without checking which demands are still necessary after predicate pushdown. Keep all 100%, 50%, and 0% planned-meal ShoppingList assertions.

## Metrics and denominator

Report per HTTP request and Session, then sum the fixed workflow; repeated IDs within one request count once. Also retain actual row delivery counts and repeated/late deliveries separately.

1. Prefetch usefulness (precision): distinct prefetched payload nodes actually read by foreground user execution / distinct prefetched payload nodes. Planning-only reads do not count. No prefetch means undefined, not 100%.
2. Demand coverage: distinct foreground-demand nodes served by prefetch / distinct foreground-demand nodes. This denominator can change if a predicate is pushed down, so keep exact demand sets and explain changes.
3. Wasted prefetch: distinct prefetched payload nodes never read. Report absolute count and bytes as well as rate.
4. Visit coverage/precision: separate control-flow diagnostics, not a replacement for data usefulness.
5. SQL data/control counts, HTTP wall, and DB intervals: performance evidence separate from the extra precision instrumentation.

The term cache hit rate must identify its unit. Existing unique-object usefulness is not the hit rate of repeated Session.get calls. A successful read after prefetch starts also does not by itself prove zero wait: retain promotion and late/materialized observations.

Before application reruns, require executable call-summary and guard/alias regressions, actual emitted Access metadata, same runtime/config comparison, and source-held-constant capture. The current prototype makes no new application performance claim.
