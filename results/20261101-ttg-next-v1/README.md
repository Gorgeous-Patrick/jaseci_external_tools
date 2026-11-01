# TTG-next: queued frontier batching and compiler-emitted SQL

Open the [26-page report](report/ttg-next-performance.pdf) for the problem, concrete graph examples, implementation, measurements and next steps. The [CSV](results/table.csv) and [complete results](results/results.json) contain 18 comparison cells across LinkedList32/1000, LittleX, IssueDesk, KnowledgeMap and JDrive: five applications, six fixtures, three configurations and three measured repeats.

LinkedList1000 Traverse uses 2,012 SQL calls with prefetch off and 16 with both TTG versions. LittleX workflow SQL counts are 153/off, 147/baseline850 and 151/next; its measured DB-wall medians are 42.578, 55.479 and 53.566 ms respectively. The report includes the source-backed batching limitation and the matched SQL/statistics experiments.

## Contents and measurement scope

- **72 captured workflows:** 54 measured trials and 18 excluded warmups.
- **18 correctness workflows:** complete native operations, independent semantic/physical oracles, fresh sessions and final real restart.
- **Two accepted LL1000 SQL recaptures:** exact original Bind, actor/state, completed 1,000-row queries and four first/repeated EXPLAIN plans.
- **Eight controlled plans:** before/after ANALYZE on restored captured fixtures, with exact census, original DDL/indexes/settings and independently checked ordered results.
- **Compiler/runtime construction diagnostics:** eight command results, generated artifacts, inputs, clock controls and separately bound source.
- **Source153 and app90:** all captured execution/acceptance/numeric scripts and immutable application sources. Scoped runtime changes and Git provenance accompany the typing dependency required for a fresh compiler bootstrap.
- **Failed-attempt provenance:** the first diagnostic's storage-boundary rejection, complete recorded case, source snapshot and stopped lifecycle remain available alongside the accepted revision.

DB wall is client-observed sendall-to-ReadyForQuery completion time. SQL counts include foreground/background path, payload and control calls, attributed to their originating business HTTP request. HTTP duration, compiler/runtime CPU and server EXPLAIN times have separate definitions and artifacts. The controlled statistics result establishes plan sensitivity; primary samples retain their observed fast/slow variation and their unobserved statistics state.

The implementation commits are `85026d486de8e16d4b894aa5a5664c7873893e89` and `9282e246d708aff69e21cb52b9d0cc4893fc5f0f`. Common settings are Always admission, process executor, one worker, prefetch limit 2048 and continuation step budget 32768.

## Verify and inspect

Run from this package directory:

```sh
python3 verify_package.py
python3 tools/read_case.py raw/formal72/linked_list1000-next-measured-0.tar.xz --member summary.json
```

Each case archive preserves every sealed member. Event/call gzip streams are represented as their exact decoded bytes inside CRC64/preset3 tar.xz archives. Original gzip hashes, original compression documents, decoded hashes and explicit representation mappings are verified together. All original artifacts remain unchanged in the originating workspace. `manifests/path-mapping.json` resolves workspace references to portable files or archive members; historical/external exclusions are explicit.

## Reproduce in a new workspace

The materializer copies the exact source bytes, app snapshot and required typing dependency. It derives new metadata with relocated source locations; original captured manifests remain archived verbatim.

```sh
python3 tools/reproduce.py materialize /absolute/path/to/new-workspace
```

The packaged smoke record exercises actual Applications30 import, source153 hashes and the real plan builder in a fresh workspace with explicitly mocked runtime metadata. It generates the fixed 18/72 schedules without running a database or application.

For native reproduction, use Linux, PostgreSQL 18.6, Python 3.14 with the tested Jac project's declared dependencies, and sufficient storage for fresh runtime/cluster artifacts. Supply a clean Git checkout at commit `9282e246...`; the runtime command creates a separate baseline850 worktree, reconstructs the byte-bound baseline snapshot, then applies exact committed changes and the reviewed DIRECT observer:

```sh
python3 tools/reproduce.py runtime /absolute/path/to/new-workspace --repository /absolute/path/to/jac-ttg
python3 tools/reproduce.py run /absolute/path/to/new-workspace build_plan.py \
  --output /absolute/path/to/new-workspace/project-notes/measurements/ttg-next-performance-20261101/reproduced-plan \
  --new-clean /absolute/path/to/new-workspace/reproduction/ttg-next-performance/runtime-clean-reproduced-manifest/manifest.json \
  --new-direct /absolute/path/to/new-workspace/reproduction/ttg-next-performance/runtime-direct-reproduced-overlay/manifest.json
```

Use the resulting plan with the original runner's `correctness` entrypoint. Pass `--postgres-bin` and `--python` before the script name when invoking native scripts through `tools/reproduce.py run`. The source runner enforces its fresh correctness and formal-release contract. Captured authorization is preserved as evidence; the materializer creates fresh execution metadata.

The editable final renderer, figure inputs, layout/title proof, raw SQL diagnostics and all original reproduction scripts are indexed through the path map. `sources/runtime-850-to-9282.patch` and `sources/runtime-changes/` expose the scoped implementation; complete runtime checkouts, PostgreSQL data and caches are separate execution dependencies.
