# TTG+ application measurements

This package contains the accepted LinkedList32, LinkedList1000 and LittleX
comparison on runtime `85026d486de8e16d4b894aa5a5664c7873893e89`: three primary
samples per configuration, nine excluded full-workflow warmups, nine correctness
cases and two separate matched LittleX diagnostic recaptures. All **47 captured
cases** retain their complete original seals and portable raw evidence.

Read the [19-page English report/slides](report/ttg-plus-performance.pdf),
[exact JSON results](results/results.json) and [CSV table](results/table.csv).
The report's [editable renderer](report/render_report_v2_final.py) and
[figure inputs](report/figure-inputs.json) reproduce its numerical figures.

| Workflow | OFF DB wall ms | Pre-fusion DB wall ms | TTG+ DB wall ms | OFF / pre-fusion / TTG+ SQL |
|---|---:|---:|---:|---|
| LinkedList32 | 114.324675 | 121.755441 | 94.458510 | 360 / 365 / 243 |
| LinkedList1000 | 3310.437373 | 3481.763318 | 2336.291121 | 9072 / 9077 / 5083 |
| LittleX | 41.426034 | 49.323894 | 55.435178 | 153 / 159 / 147 |

Values are n=3 medians for the complete ordered business workflow. DB wall is
client-observed send-to-ReadyForQuery interval sum across all foreground and
background roles and controls. Per-request sums/unions, exact observations,
variation, protocol rows/bytes and separate HTTP e2e values are in the data.
Setup, state inspection, restart and excluded warmups have explicit phases.

The matched LittleX diagnostics retain exact diagnostic SQL/Bind/state and ten
server EXPLAIN plans. They show different endpoint access paths, repeated type
checks and higher measured plan costs for the selected fused shapes. The report
keeps first/repeated EXPLAIN observations separate from primary n3 measurements.
Native logical/full-response, fresh-session, restart and physical-state checks
pass for the accepted cases. The runtime, source50 and borrowed app90 manifests
bind the implementation and oracles.

## Verify and inspect

Python3.11+ is sufficient for portable evidence verification:

```sh
python3 verify_package.py
python3 tools/read_case.py raw/formal36/linked_list32-off-measured-0.tar.xz
python3 tools/read_case.py raw/formal36/linked_list32-off-measured-0.tar.xz --member http-raw.jsonl
```

The verifier checks every package file, archive member, original case seal,
source closure, trial selection, current required reference and report hash.
It streams decoded event bytes without parsing huge native-outcome JSON.

## Exact raw representations

Each `raw/` case is a preset3 XZ/CRC64 tar archive. Original sealed gzip traces
appear as their exact decoded JSONL members. Every byte, newline, field, order
and duplicate is retained. `manifests/archive-members.json` binds the original
gzip SHA-256 and size, original `compression.json` digest, decoded SHA-256 and
size, and the new archive SHA-256. Original case seals and compression documents
are included unchanged. Compressed gzip and tar.xz bytes have distinct hashes;
the representation mapping explicitly verifies decoded equality. All original
gzip files remain in the local measurement archive.

Each case archive includes every member in its original seal, including any
sealed compiler artifact. Unsealed runtime caches, full runtime checkouts and
PostgreSQL data are outside the publication package. Source locations and
historical references resolve through `manifests/path-mapping.json` or the
explicit historical/external exclusions. Current required inputs are enumerated
and verified separately. Optional PNG previews and draft PDFs are kept locally;
this package includes one approved final PDF.

## Reproduce from exact sources

Measurements used Python3.14, PostgreSQL18.6, a process reader with one worker,
prefetch limit2048 and continuation step budget32768. OFF, pre-fusion and TTG+
share the repaired runtime and fixture/action inputs. Runtime package metadata
and dependencies should be installed from the pinned runtime's `jac/pyproject.toml`
using Python3.14. Provide the PostgreSQL18.6 binary directory and Python executable
explicitly for the reviewed runner; host paths are configuration rather than
measurement substitutions.

```sh
python3 tools/reproduce.py materialize /tmp/ttg-plus-reproduction
# Use a clean upstream checkout at the exact commit above, available remotely.
python3 tools/reproduce.py runtime /tmp/ttg-plus-reproduction --repository /path/to/jac-ttg
python3 tools/reproduce.py run /tmp/ttg-plus-reproduction --postgres-bin /path/to/postgres18.6/bin --python /path/to/python3.14 review.py --output /tmp/ttg-plus-reproduction/review-correctness --runtime /tmp/ttg-plus-reproduction/reproduction/ttg-plus-performance/runtime-clean-reproduced-manifest/manifest.json --overlay /tmp/ttg-plus-reproduction/reproduction/ttg-plus-performance/runtime-direct-reproduced-overlay/manifest.json
```

Use the generated plan with the original `runner.py correctness` entrypoint,
then generate a new final review from its completed index. The included original
README/source documents the exact correctness/formal/export commands. A new
formal run uses a new main-approved release bound to its regenerated plan,
runtime and sources. The materializer copies exact source bytes, the suite snapshot and imported
freeze helper. It derives a NEW instrument metadata file with relocated previous
source paths, binding the original instrument hash while preserving its archived
bytes. It restores only the old866222 ignored stdlib dependency subtree needed by
the frozen `snapshot.freeze`; it carries no experiment authorization. A DB-free
fresh-workspace smoke passed Applications30, source50 and36/9 plan schedules
(`evidence/reproduction-smoke-v2.log`). Historical full
snapshot restoration is documented in the provenance metadata.

## Package contents and provenance

- `raw/formal36/`: 27 measured workflows and nine excluded warmups.
- `raw/correctness9/`: complete accepted same-runtime correctness matrix.
- `raw/diagnostics2/`: two bounded matched recaptures and exact SQL/Bind/state/plans.
- `sources/`: captured50 execution files, borrowed90 app/oracle files, exact runtime
  source references, ignored type-stub dependencies and diagnostic/analysis code.
- `evidence/`: release/plan/indexes, acceptance and metric records, runtime/overlay
  provenance, main/reviewer proofs, classification, diagnostics and lifecycle.
- `manifests/`: package hashes, original-to-portable mappings, representation
  chains, source closure and explicit historical/external provenance boundaries.

`verify_package.py` is adapted from the previously reviewed publication verifier.
`package_from_originals.py` retains the source mapper/archive workflow used to
assemble the original evidence. Main owns the final scoped Git publication.
