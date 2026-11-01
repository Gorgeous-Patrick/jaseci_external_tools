# Bounded LittleX diagnostic preparation

Status: source authored; not imported, tested or executed. The independent
primary raw audit owns the heavy I/O window. All DB/capture jobs remain held
until its explicit quiet signal and main/perf handoff.

The accepted attribution identifies two fused foreground fingerprints. Select
the first business `load_feed` request `2:20`, generation 2, occurrence 1 for
both targets. This request contains both and precedes the subsequent mutation
sequence, avoiding a create_tweet state-selection ambiguity. The first target
returns 12 rows in measured repeat 0; the recursive target returns one row.
These are primary selection observations, not diagnostic results.

- Batch: `3166e1168d5af494a52220b6fb86be01ce9fcf6212432459dbd28ee88d631efa`.
- Recursive: `d106730720c848bc3c3244c8bc13dfcd5c9d8848db39db0e593580644993a4bc`.
- Source: `project-notes/measurements/ttg-plus-performance-20261031/littlex-attribution-v1/results.json`,
  supplied SHA-256 `4acc4f96cfe9aa67798b5a509fdf94044ecdae5cbbbe7dfe1e0b3e882b544e61`.

Helper paths: `reproduction/ttg-plus-diagnostics/capture.py`, `overlay.py`,
`explain.py`, `test_helpers.py`, and `README.md`. The actual Bind packet is
captured before send in a separately copied driver. Same-connection pre-statement
state includes every anchor, the persisted type/ancestor table, indexes,
relevant settings, database role, transaction isolation and snapshot. Added
census SELECTs are disclosed and can warm buffers. The selected original packet
is sent unchanged. EXPLAIN rebinds the exact captured text parameter bytes through
the same native named-to-positional mapper and encoder; no primary Bind is guessed.

Following main's simplification, EXPLAIN now runs inline before the selected
send, in the same connection and transaction, with the original parameters and
verified packet Bind bytes. Snapshot, catalogs, indexes and statistics are thus
those of the actual recapture. No clone/import/statistics-matching framework is
introduced. Plans remain provisional until the full native workflow/oracles and
actual selected-query completion pass. Census-warmed first/repeated plan times,
rows, loops and buffers are reported separately from primary n3 measurements.

Pending before DB acceptance: pure helper checks after quiet; final reviewed
selection including native comparator fingerprints; thin existing-workload
server/controller wiring; source/overlay/input seal; explicit exclusive DB
handoff. No executable selection or successful acceptance is fabricated. The
existing LittleX source, deterministic corpus preparation, ordered full workflow,
logical/full-response/restart/physical oracles are reused unchanged. Primary850
and its50 execution sources remain frozen.
