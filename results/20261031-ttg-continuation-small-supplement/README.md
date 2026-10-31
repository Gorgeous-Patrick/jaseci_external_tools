# TTG continuation: report and trace supplement

This supplement accompanies the [published two-application study](../20261031-ttg-continuation-small/README.md), committed as `be37d8f8`. It presents the same accepted LittleX and IssueDesk results: six configurations, three measured workflows per application/configuration, 36 measured workflows and 12 excluded warmups. The base also contains the separate 30-entry, six-configuration correctness matrix.

## Contents

- [Seven-page report, version 2](report/small-report-v2/ttg-small-performance.pdf), [report text](report/small-report-v2/report.md), figure inputs, seven PNG previews, and the renderer-bound integrity manifest.
- [LittleX trace attribution](analysis/littlex-trace-attribution-v1/attribution.md), full JSON, and its original seal. The analysis records client-observed SQL protocol intervals, interval unions, foreground/background roles, backend/process/thread identities, SQL fingerprint contributions, and source-bound model scope/checkpoint observations. Page 7 ties model observations and barriers to the recorded scopes and their source definitions.
- The exact [report renderer](sources/reproduction/ttg-continuation-performance/small_render_v2.py) and [attribution script](sources/reproduction/ttg-continuation-performance/littlex_trace_attribution_v1.py), versioned alongside the original 38-file execution closure.
- [Independent actual48 review](review/small-actual48-independent-review.json), [final review binding](review/small-actual48-final-review-binding.json), [LittleX interval-pair review](review/littlex-thread-interval-pairs-review.json), and the [reviewer's report](review/ttg-continuation-benchmark-review.md). The final review binding identifies the base version 1 PDF and numerical export; version 2 has its own report-integrity manifest.

## Data and provenance

The [base CSV](../20261031-ttg-continuation-small/results/small-export-v1/table.csv), [numerical export](../20261031-ttg-continuation-small/results/small-export-v1/results.json), and [per-trial raw archives](../20261031-ttg-continuation-small/raw/small48/) remain the underlying data. Version 1 PDF and its provenance are available in the [base report directory](../20261031-ttg-continuation-small/report/small-report-v1/).

[origins.json](manifests/origins.json) maps each copied artifact to its original workspace-relative path and hash. [base-bindings.json](manifests/base-bindings.json) identifies the exact underlying numerical export, CSV, version 1 PDF, trial index, and base integrity record. [files.json](manifests/files.json), `SHA256SUMS`, and `package-integrity.json` seal this sibling supplement independently.

From this supplement directory, verify the copied files, original seals, source/reviewer bindings, and selected base hashes:

```bash
python3 -B verify_supplement.py
```

Keep this directory next to `20261031-ttg-continuation-small` so the relative data links and base hash checks resolve.
