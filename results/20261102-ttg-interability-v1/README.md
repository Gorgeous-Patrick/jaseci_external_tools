# TTG+ interability SQL regions

[Read the 27-page English slides](report/ttg-interability-performance.pdf). The editable renderer, full numerical inputs and page previews accompany the PDF.

This release implements compile-time composition of supported typed ability summaries, runtime selection/binding and validated native path-cache publication. A separate Stage2 improvement retries independent LittleX visit prefixes. The report explains both mechanisms, the existing admission model, the full 30-app + 61-operation research inventory, and sibling dependence of future access.

## Measured results

Primary instrumented HTTP response-wall medians, milliseconds (n=3):

| Fixture | Off | 9282 baseline | Interability |
|---|---:|---:|---:|
| LinkedList32 |60.516|652.823|254.941|
| LinkedList1000 |1240.857|30841.349|726.128|
| A→B→C |8.449|444.501|241.448|
| LittleX |98.207|1586.361|1592.227|

Each LinkedList trial measures one Traverse. LittleX sums its nine primary response intervals. Database protocol time, ranges, counts and interval unions are separately reported in the slides and CSV. All modes use the same explicit pre-workflow ANALYZE regime.

The long-list gain accompanies elimination of quadratic abstract continuation work. Short workflows still pay roughly190ms per new child process; LittleX starts six scoped readers. The new list SQL also performs more validation and carries cycle history: matched diagnostic plans show extra source-index checks and temporary writes. These observations motivate worker reuse, cold-start-aware admission and narrower exact recursive state. They are distinct measurements, not a wall-minus-DB CPU estimate.

## Evidence

- 15 native correctness cases;48 fresh formal trials:12 excluded warmups +36 measured samples across12 cells.
- Two matched native SQL recaptures and four EXPLAIN plans; full original completion/native-state checks.
- Frozen172 execution-source references,90 application-suite sources, exact runtime patches/provenance, raw SQL/HTTP traces and semantic/physical acceptance.
- Independent primary48 and HTTP/startup reviews completed. Main completed final diagnostic/PDF checks after the existing subagents reached their usage limit.
- Larger-dataset follow-up is paused at the user's request; no larger runs were started.

Runtime commits: `9282e246d708aff69e21cb52b9d0cc4893fc5f0f` and `addd3a4fb08819699d88afcf9a4ef8f1744d1ae4` in [Gorgeous-Patrick/jaseci](https://github.com/Gorgeous-Patrick/jaseci/tree/feat/ttg-interability-regions).

## Verify and reproduce

Run `python3 -B verify_package.py`. It needs only Python's standard library and verifies every packaged file,65 archives, exact matrix membership, source hashes and raw decoded-byte representation chains. Optionally pass `--original-root /home/baichuan/jaseci` in the original workspace.

`manifests/path-mapping.json` maps original workspace paths to packaged files or archive members. Raw JSONL gzip streams are stored as byte-identical decoded members in tar.xz; original compressed hashes and compression manifests remain explicitly bound. Original gzip files are retained in the research workspace.

Run `python3 -B materialize_workspace.py --output /tmp/ttg-interability-review` to copy non-archive source/evidence files into their recorded relative workspace layout. The source renderer then reads those local figure inputs; rerendering needs matplotlib. Re-executing benchmarks additionally needs the pinned Jac runtime checkout, PostgreSQL and the dependencies specified by the frozen harness. It is a new experiment, not reuse of a timing sample.

Historical failures, superseded references and excluded full runtime/DB/cache trees are explicitly catalogued. Current accepted cases are complete.
