# TTG application performance — October 30, 2026

The study covers 30 entries: LinkedList and 29 full applications, including LittleX,
Jacord and JDrive. All 480 cases passed: 120 excluded warmups and 360 measured
fresh-database trials, with three independent trials per application and policy.

- `report/ttg-app-performance.pdf`: English presentation.
- `report/REPORT.md`: tables, methods and per-application observations.
- `per-app-results.csv` and `results.json`: measured DB protocol times and SQL counts.
- `raw/<app>.tar.gz`: every sealed artifact from that application's 16 cases,
  including excluded warmups, actual SQL traces, fixtures, actions and oracles.
- `raw/separate-diagnostics.tar.gz`: 20 separate diagnostic cases, independent
  PostgreSQL CSV records and preserved CPU captures.
- `raw/provenance.tar.gz`: frozen suite sources, review/release manifests,
  runtime file inventories, acceptance metadata and independent main-agent audits.
- `release.json`: archived member hashes, archive hashes and measurement-source hashes.

The primary metric is send-to-ReadyForQuery protocol completion wall time, including
database work, transport and driver decoding. The report separates summed intervals,
interval unions and driver-call times. It reports actual SQL dispatches and controls.

Original TTG lowered the full-workflow median for LinkedList. All 29 full applications
had higher medians in this local seed42 study. The dependency configurations issued
the same SQL counts as prefetch off; recorded checkpoints considered zero plans.
The report traces concrete admission barriers and added recursive SQL costs.

All CPU comparisons were excluded after impossible negative profile times were found.
The original diagnostic log selector failed; a separately tested reconciliation adapter
validated all 20 cases against actual `jac:<PID>:run` PostgreSQL backend labels.
The report and raw evidence retain both findings.

Archives store paths relative to the original workspace root. Extract them there to
restore the historical evidence tree. Absolute paths in historical manifests identify
the capture location. App implementations live in `../../app_suite`; the measurement
sources are copied unchanged to `../../app_perf`. Their historical README describes
the original workspace layout. A new measurement requires a fresh freeze and release
review rather than reusing the historical authorization. PostgreSQL physical data
directories and compiler caches are retained locally and excluded from this package.
