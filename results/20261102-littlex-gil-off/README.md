# LittleX: GIL-off thread, process, and off

All three modes use the repaired runtime [5ce63eacd](https://github.com/Gorgeous-Patrick/jaseci/commit/5ce63eacde69f11817ed791b2d93544d7524be49) and the same **CPython 3.14.6 free-threading build**. Twelve fresh full LittleX workflows passed: one excluded warmup plus three measured repetitions per mode. This is a small executor comparison, not a GIL-on versus GIL-off causal experiment.

| Mode | All SQL | DB interval sum, median | Nine primary HTTP response intervals, summed median |
|---|---:|---:|---:|
| Off | 153 | 38.131 ms | **98.909 ms** |
| Thread | 143 | 50.085 ms | **138.421 ms** |
| Process | 143 | 57.023 ms | **2415.932 ms** |

Thread is substantially faster than process here, but remains 39.9% slower than off. No foreground/background SQL interval overlap was observed. All business responses, restart checks and independently replayed final states passed. Every workflow used a fresh database and successful validation preceded its zero-active-session DROP.

The actual processes assert `Py_GIL_DISABLED == 1` and `sys._is_gil_enabled() is False` at startup, SQL completion boundaries and native outcome/close boundaries. All **7,384 SQL records** join matching GIL-off assertion records. A deliberate `-X gil=1` negative exits before executing its body. Actual thread-mode SQL uses a different native thread and PostgreSQL backend in the foreground's OS process; no process fallback is accepted.

## What are the 143 SQL calls?

They cover **nine business requests**, not one feed: four feeds, two likes, follow, profile and create-tweet. All three measured thread repetitions have exactly these counts:

| Purpose | Calls |
|---|---:|
| BEGIN / COMMIT / SET / DISCARD | 69 |
| Node/edge payload and adjacency reads | 44 |
| Identity reads | 9 |
| Compiled merged-path queries | 6 |
| Other native path queries | 7 |
| Anchor writes | 4 |
| Type registrations | 4 |
| Total | **143** |

One feed has **14 calls**: one cross-ability path SQL, four payload reads, one identity read and eight controls. Background work across the whole workflow is six payload queries plus six `DISCARD ALL` calls. The fused path query connects Root → Profile → own/followed Tweets within SQL; payload loading and native `to_view()` work remain separate.

## Contents and verification

- [Detailed report](workspace/project-notes/ttg-littlex-freethreaded.md)
- [Exact results and vectors](workspace/project-notes/measurements/ttg-littlex-freethreaded-20261102/comparison-v2/results.json)
- [Interpreter positive/negative assertions](workspace/project-notes/measurements/ttg-littlex-freethreaded-20261102/interpreter-assertions.json)
- [Executed harness and GIL checks](workspace/reproduction/ttg-littlex-freethreaded/)
- `raw/`: all 12 accepted sealed cases, with original gzip files preserved byte-for-byte inside tar.xz containers.
- `manifests/`: source/path mapping, archive members and external interpreter identity.

Run `python3 -B verify_package.py` from any directory. It checks the exact file inventory, every archive member and original raw seal, final source references, SQL/GIL joins, primary SQL/HTTP arithmetic and n=3 aggregates. No database or third-party Python package is required.

The capture used uniform pre-workflow ANALYZE, one prefetch worker and limit 2048. Construction/setup, excluded steady reads and the three warmups do not enter primary measurements. No large dataset was run.

The first observer attempt is preserved in the accompanying v1 logs/source copies: free-threaded Python's inherited ContextVars caused background SQL to be labeled foreground. The repaired observer prioritizes the existing explicit worker binding, with a real ContextVar regression. It does not change native contexts or scheduling. All accepted samples are from the fresh v2 capture.

The package includes the captured harness/source closure except the external Python executable, whose exact hash and download identity are declared. The Python installation, PostgreSQL data directories and compiler caches are not bundled. Core runtime code is pinned by the linked Git commit and the captured overlay manifests; this portable package verifies evidence without claiming to contain a standalone installed runtime.
