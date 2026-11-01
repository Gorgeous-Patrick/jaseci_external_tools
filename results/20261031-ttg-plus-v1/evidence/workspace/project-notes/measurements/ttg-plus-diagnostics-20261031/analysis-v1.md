# LittleX matched SQL diagnostic findings

Both separate full LittleX recaptures passed all native logical/full-response,
fresh-session, restart and physical-state oracles. All five selected original
queries completed, with ten accepted EXPLAIN plans. The actual diagnostic Bind
packets and pre-statement state are retained. This is one matched diagnostic
instance per configuration, with first/repeated EXPLAIN observations; it does
not replace or numerically decompose the primary n3 client protocol timings.
The census and EXPLAIN executions warm buffers. The same connection/transaction
is used, isolation is captured and the graph is controlled without concurrent
mutation; READ COMMITTED does not imply a single snapshot across statements.

The bound [summary](explain-summary-v1.json) includes every capture hash, exact
plan JSON pointer, executed node condition, rows/loops and buffer counters.

| Region / observation | Native planning ms | Fused planning ms | Native execution ms | Fused execution ms | Native root shared hits | Fused root shared hits |
|---|---:|---:|---:|---:|---:|---:|
| Root→Profile, first | 0.315 | 0.742 | 0.092 | 0.184 | 12 | 22 |
| Root→Profile, repeated | 0.244 | 0.617 | 0.070 | 0.094 | 9 | 22 |
| Collect, first | 0.943 | 1.203 | 0.278 | 0.535 | 55 | 320 |
| Collect, repeated | 0.964 | 1.181 | 0.180 | 0.423 | 55 | 320 |

Collect native values sum two independent statements (Post→Tweet and
Follow→Profile→Post→Tweet), returning 4+8 rows; the batch returns the same 12
rows. Root→Profile returns one row in each version. All root shared-read and
temporary-read/write counters are zero. Root buffer counters are inclusive;
parent and child plan counters are never added together.

## Observed plan differences

Native `native-post` and `native-follow` target-node lookups use `anchors_pkey`
with `Index Cond: id = CASE WHEN edge.src = origin THEN edge.dst ELSE edge.src END`.
The captured first-plan paths include native-post
`/Plan/Plans/0/Plans/1` (alias `n1`) and native-follow
`/Plan/Plans/0/Plans/0/Plans/1` (`n1`) plus
`/Plan/Plans/0/Plans/1/Plans/1` (`n2`). These paths are relative to the first
plan's `Plan` root; the summary supplies complete pointers into each capture.

The batch uses `idx_anchors_kind_type` with index conditions on
`kind='NodeAnchor'` for `_t4`, `_t12` and `_t17`, followed by filters and join
conditions. Its correlated `graph_types_pkey` subplans `_t5` and `_t18` execute
64 and 128 loops in the first plan. The native equivalent uses hashed type
subplans and endpoint primary-key lookups. These are observed plan/operator
and buffer differences, not a claim that shared hits measure CPU time.

The root fused plan has a `Recursive Union` with one actual CTE row. It evaluates
the path in both the recursion/certification branch and the output branch:
the two executed path branches each show 11 shared hits, while the root shows
22. The selected native root lookup returns the same one row with 12 hits on
first EXPLAIN and nine on repetition. This small certified region therefore
has no demonstrated benefit from recursion in this fixture.

The diagnostic reports higher server planning and execution times for these
two fused shapes despite equal semantic output rows. Combined with the accepted
primary attribution, this supports a concrete explanation for why fewer SQL
calls need not lower LittleX DB wall time: the fused statements have more costly
measured plans in this matched recapture. It does not establish server CPU,
network or whole-workflow causal percentages.

## Untested improvement proposals

Preserve the native compiler's indexable endpoint join shape and reuse its
node/edge type predicate form when constructing fused paths. Investigate whether
that avoids kind-only node scans and repeated correlated type-table probes.
For a single-step certified region, consider a direct batch/path form instead
of recursive machinery. A later implementation may also reuse the resolved path
between certification and output while retaining exact ordering, empty markers,
ACL guards, fanout/activation budgets and FIFO semantics. These are proposals;
no runtime change or improvement benchmark has been run for this publication.

Runtime85026d and the primary50 source closure remain unchanged. The separate
[stopped proof](stopped-proof-v1.json) records the actual creator/server/reader
PIDs dead, PG status3, no PID file and no retained DB. Main and perf received the
explicit quiet handoff for presentation and packaging.
