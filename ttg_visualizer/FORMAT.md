# `jac.ttg.visualization` v1

A portable JSON bundle is the boundary between TTG and the viewer. Unknown
extension fields may be added without changing the version. Changing meanings
of existing fields or ID namespaces requires a new major version.

| Field | Meaning |
|---|---|
| `schema`, `version` | `jac.ttg.visualization`, `1` |
| `title`, `walker` | Human label and selected walker identity |
| `sources` | File key → exact text, lines, SHA256 |
| `compiler.plan` | Original serialized TTG plan, preserved verbatim |
| `compiler.events` | Event IDs/kinds/reads/writes/positions plus adapter location |
| `compiler.edges` | Original typed dependency edges; order, data, control remain distinct |
| `compiler.hooks` | Hook symbol, event, placement, bytecode callsite evidence |
| `compiler.regions` | Entry event, original certificate metadata, referenced template IDs |
| `compiler.templates` | Stable descriptor path, exact SQL, constant params, typed dynamic slots |
| `graph.nodes` | Stable logical ID, type, fields; optional captured runtime ID |
| `graph.edges` | Source/target logical node IDs and edge type; preserve duplicates |
| `graph.state` | Snapshot semantics, including mutation limitations |
| `requests` | Request ID, source evidence, observed visited IDs, SQL records |
| `provenance` | Separate compiler artifact and verified capture/source references |
| `limitations` | Capture-specific missing evidence and interpretation boundaries |

SQL records contain exact SQL text/hash, original evidence file/line, role,
executor, thread/backend IDs, rows, send/ready timestamps, relative start/end
milliseconds, duration, and category (`data` or `control`). They optionally link
to `template_ids`; the current adapter and UI accept only exact SQL text matches.
No link is preferable to a guessed causal association. Bind values are absent
in this capture and displayed as unavailable.

Hook placement values are `ability_entry`, `before_statement`, or
`after_statement`. A hook callsite means **inserted by the compiler**, not fired
in every request. A future runtime trace extension should carry invocation IDs,
request IDs, origin node identities, and event IDs before showing per-node firing.

Compiler `output_tree` metadata contains the access proof, native effects,
predicate, visit line, source type, and runtime contracts. Highlight only the
access portion; retain output effects and generic rejected summaries separately.

Current client validation rejects unknown versions, duplicate entity IDs,
dangling graph/dependency/hook/template references, invalid intervals, and false
exact-SQL associations. The export adapter verifies consumed evidence hashes.
Importing JSON into the browser validates structure/relationships, not a digital
signature or trust in its producer.

The default nested view projects one certified homogeneous recursive
`output_tree` region onto a real origin and up to two eligible targets. It
follows outgoing typed edges and constant equality predicates. A single
connected boundary contains the path-discovery slices at these node instances;
target-ID arrows express value dependence, not timing or a new compiler event
sequence. Predicate/type-excluded edges are listed outside the expansion.
Repeated visits share one compiler event ID with distinct rendering keys
`(node ID, ability, event ID)`. Target navigation and pagination expose further visit expansions. Native output/enqueue and the separately observed payload
query are outside the blue region. This projection is not a per-node firing log
or evidence that the conceptual slide's payload-fusion example is implemented.

A full-snapshot overview includes every node exactly once and every graph edge,
including disconnected nodes and non-tree edges. Color distinguishes observed
native visits, initial trashed fields, selection, and other nodes. The overview
and local expansion use the explicit initial snapshot, never an inferred current
state after subsequent mutation requests. Other unsupported certificates fall back to complete dependencies instead of
being portrayed as recursion.

The complete dependency view shows a focus node and up to two outgoing targets, with
pagination and browsing-history Back navigation. No unique parent is inferred
from incoming edges. The current region adapter supports outgoing typed hops;
it does not claim support for an undirected visit certificate. The graph data is not pruned.
Static dependency nodes are repeated for each applicable graph node. They retain
their original event IDs, scoped by the selected walker; rendering copies are
not additional execution events.

The producer sidecar `jac.ttg.compiler` v1 contains `source`, `plans`, and `hooks`.
Capture adapters join it to their own snapshot/request format and emit the
viewer bundle. This keeps framework/compiler serialization separate from any
particular benchmark harness.

A second projection handles the checked three-rule finite-DAG shape: a root
visit and two dependent visit sites (one direct, one two-hop). Rules retain
actual slots, parent-rule dependencies, event IDs and dispatch boundaries. The
adapter enumerates initial graph paths in edge order, preserving multiplicity;
representative node cards bind to these paths. Path counts are initial-snapshot
counts, not inferred SQL rows or observed visit counts. The intermediate node
of a multi-hop visit is labeled as a hop, not an ability invocation. A single
union outline connects access slices; native barrier code stays outside.

For LittleX only, framework Root nodes and root edges omitted from the domain
fixture are recovered from verified SuiteRoot/SuiteImport and physical seed
census records. Their evidence fields state their provenance. `visited` remains
empty because feed outputs do not establish a complete visit trace.
