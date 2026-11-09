# TTG Explorer

A Jac client for inspecting **real compiler hooks, ability dependency graphs,
SQL access regions, and captured queries**. Rendering/state is in `main.jac`;
`model.js` provides data validation and graph layout. The viewer needs no database.

## Run

Use the TTG Jac compiler checkout (`jac-ttg`, tested at `f9a6d37b`):

```bash
cd jaseci_external_tools/ttg_visualizer
JAC=/tmp/jac-ttg-cli python3 tools/build.py
python3 -m http.server 8765 --bind 127.0.0.1 --directory dist
```

With a normal Jac installation, omit `JAC=...`. This project uses the Jac client
static target; no application walkers or database services are launched.

From your laptop, forward the server port:

```bash
ssh -N -o ExitOnForwardFailure=yes \
  -L 127.0.0.1:8765:127.0.0.1:8765 baichuan@clarity3
```

Open <http://127.0.0.1:8765> on that laptop.
Use the **Example app** selector for JDrive / LittleX, or open
<http://127.0.0.1:8765/?app=littlex> directly. Replace `clarity3` with your SSH host.
The generated HTML contains the compiled Jac client; `dist/data` contains the
data bundle. Serve the whole `dist` directory, not only the HTML file.

## Explore

1. **Graph & hooks** defaults to **Multi-level SQL region**, using the nested
   layout of slide 7, “One SQL compilation region across Jac abilities.” A real
   origin sits above up to two eligible visit targets. Each node contains a compact
   dependency slice; a **single connected blue boundary** follows target-ID
   dependencies across the ability instances. Native output/depth/path/enqueue
   code remains outside it. In this capture, payload loading is a separate SQL
   query and is not included in the blue path-discovery region.
   Click a visit to inspect its compiler event/source or **View shared SQL** for
   the exact template. **Explore from here** selects a target; **Back** returns to the previously
   viewed node using browsing history, never an inferred parent;
   pagination covers additional eligible targets. Excluded target types and
   unsatisfied initial-snapshot predicates are listed separately.
   The overview includes **every initial graph node and edge**, with observed
   visits distinguished from static applicability. Click any overview node to
   focus it. The enlarged diagram is an explicit local view, not the entire tree.
   **Complete dependencies** preserves all original compiler event nodes and
   typed dependency edges, including generic barriers. Purple markers are
   bytecode hook callsites. All UI text is English.
2. **SQL & timeline**: select a compiler template or a real query. Links require
   exact original SQL text. Foreground and background queries keep their actual
   send-to-ready coordinates. Control queries can be shown separately.
3. **SQL walkthrough**: both LittleX and JDrive have a logical SQL dataflow graph.
   Select a block to read its Jac source, exact SQL fragments, alias roles and
   constant/runtime parameters. Click an alias or parameter to highlight its
   exact occurrences. See the output-column contract below the graph.
4. **Evidence**: source/capture hashes, compiler-cache provenance, and scope.
5. **Open bundle**: replace the dataset with another version-1 JSON bundle.

The default is the accepted JDrive `thread / measured-0` capture from
`ttg-portfolio-v2-20261104`. It includes 486 initial graph nodes, 19 compiler
events, 2 hook callsites, 1 output-tree region, 6 SQL descriptors, and 3 actual
`VisibleFolderTree` requests. Request `2:6` contains **7 data SQL + 8 controls**;
one recursive SQL exactly matches the emitted gated template, and the final
background payload query returns 115 rows.

The blue region denotes the **access computation**, not arbitrary conversion
of every statement into SQL. JDrive's specialized `output_tree` certificate
accepts this region while the generic effect summary contains barriers. Both
are preserved. Output/depth/path calculations continue in native Jac. The
recursive template spans repeated ability instances on reachable nodes; this
example does not claim distinct heterogeneous abilities are fused.

## Export TTG information

`tools/export_compiler.py` is the reusable producer interface. It reads an
existing trusted local compiler cache or compiles new Jac source without running
the module body or a walker:

```bash
# Run in the Jac compiler's Python environment (Python 3.14 here).
python3.14 tools/export_compiler.py --source /path/to/app/server.jac \
  --output /path/to/compiler.json

python3.14 tools/export_compiler.py --jir /path/to/server.cpython-314.jir \
  --output /path/to/compiler.json
```

The producer exports all walker plans and actual emitted hook callsites. It
does not insert new runtime instrumentation or change production semantics.

`tools/export_bundle.py` is the current **sealed benchmark-capture adapter**:

```bash
python3.14 tools/export_bundle.py \
  --case /path/to/jdrive-thread-measured-0 \
  --jir /path/to/the/same/case/.jac/cache/HASH/server.HASH.cpython-314.jir \
  --walker VisibleFolderTree --output public/data/jdrive.json
```

It checks every consumed sealed source/HTTP/SQL file and the fixture's own
dataset digests. JIR bytecode is inspected, never executed. Only use trusted
local JIRs; the browser accepts JSON, never marshal/bytecode files.

## Extend

See [FORMAT.md](FORMAT.md). The interface separates:

- compiler facts (`events`, `edges`, `hooks`, `regions`, `templates`);
- graph snapshots (`nodes`, `edges`, explicit snapshot semantics);
- recorded requests and SQL intervals;
- source/evidence provenance.

For apps using the existing graph/event/SQL shapes, adding an app means writing
an adapter that produces the same contract. The source, hook, complete-dependency,
SQL and timeline panels can then be reused. Node IDs and event IDs remain different namespaces.
The current JDrive adapter extracts observed visits from native `depths` output;
another app should supply its own observation rule or an empty `visited` list.
An offline compiler-only bundle may contain no requests.

The nested blue-region renderer supports two explicitly checked shapes:

- Homogeneous `output_tree` certificates with one outgoing typed hop and constant
  equality predicates (JDrive).
- `finite_dag` certificates with an origin visit followed by two composed visit
  sites, one direct and one two-hop path (LittleX `load_feed`). Both sites consume
  the origin rule's target IDs, not each other's Tweet results. Unsupported DAG
  shapes retain the complete-dependency / SQL panels.

LittleX uses the accepted `littlex-thread-measured-0` capture from the same
portfolio run: 50 Profiles, 1,000 Tweets, plus 50 witnessed framework Roots.
The adapter adds Root identities from sealed SuiteRoot/SuiteImport reports and
Root→Profile edges from the sealed initial physical census. They are not
fabricated edges in the domain fixture. Four workflow `load_feed` requests each
contain 14 total SQL records and one exact-matched finite-DAG template. Its rows
are 64, 64, 84 and 85 respectively; these include path records and are not a
count of distinct visited nodes. The figure projects representative initial
paths (1 Profile, 20 direct Tweet paths and 40 Follow/Post paths at user:0).
Later workflow mutations are not replayed into the initial graph picture.

The region crosses `run` and `collect`, stopping before native
`gather: self.feed.append(here.to_view())`. Payload loading is separate.
The intermediate Profile in a Follow/Post path is not another collect call.
No complete LittleX visit trace is present, so feed outputs are not labeled as
visited-node evidence. This viewer addition replays existing sealed evidence;
it does not claim a new benchmark or app execution.

Recommended integration sequence:

1. Export the app's exact TTG compiler plans and hook callsites.
2. Adapt its real graph snapshot, request IDs and captured SQL into the bundle.
3. Reuse the existing panels; add a region renderer only for a new region shape.
4. Validate source/event links, actual graph edges and exact SQL-template matches
   using that app's own recorded case before claiming support.

The existing TTG event format omits source filenames, so this adapter resolves
annex files by ability declarations and labels the resolution. Future compiler
sidecars should emit full file/span information directly. The original compiled
JIR cache was not in the historical case seal: the viewer hashes it separately
and explicitly describes that weaker provenance. No per-hook firing log exists
in this capture, so static hooks are never presented as observed firings.

## Validation

```bash
node tests/model.test.mjs
# With a running viewer and an installed Playwright:
CHROME=/usr/bin/google-chrome node tests/browser.cjs
```

Set `PLAYWRIGHT_MODULE` to reuse an existing Playwright installation. Tests cover
real SQL counts/joins, corrupt relation rejection, declaration/annex navigation,
graph pagination, request switching, controls, bundle import, and mobile layout.
Screenshots and browser results are written to ignored `artifacts/`.

## SQL walkthrough scope

`sql_explainer.js` reads the selected request's **exact-matched region template**.
A bounded tokenizer splits balanced WITH / WITH RECURSIVE definitions, retains
original character offsets, and derives clause excerpts and alias roles from
SQL plus the compiler's constants/slots. Display formatting changes whitespace
only. Raw snippets and the whole original SQL remain accessible.

- LittleX: three visit CTEs, both collect CTEs depending on the Profile CTE;
  all three path outputs plus the separate slot −1 type-catalog branch reach
  the final UNION ALL / ordering step. Catalog rows are outside the path LIMIT.
- JDrive: seed plus UNION recursive origin set, exact boolean/type predicate,
  then a separate ordered path-enumeration pass and result LIMIT. The second
  pass does not repeat the `trashed = false` expansion predicate. The LIMIT is
  not a recursion depth bound.

This is a logical SQL explanation, not a PostgreSQL physical plan or a replay of
intermediate result rows. Bound values and per-CTE rows were not captured.
Native effect/cache checks and separate payload hydration are distinguished
from SQL path calculation. The adapter supports the two recorded certificate
shapes; unknown shapes fail closed to the original SQL view.

Check exact fragment binding, whitespace-only formatting, dependency direction,
ACL/alias roles, catalog handling and recursive LIMIT semantics with:

```bash
node tests/sql_explainer.test.mjs
```
