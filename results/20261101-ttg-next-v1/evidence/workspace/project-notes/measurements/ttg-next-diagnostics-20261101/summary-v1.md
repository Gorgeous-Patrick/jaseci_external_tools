# LL1000 matched SQL diagnostics

Two full native workflows passed; actual selected queries each completed with1000 rows. The four initial plans and eight controlled plans are separate from primary measurements.

| Query | Regime | Planning ms (first/repeat) | Execution ms (first/repeat) | Root shared hits | Reads |
|---|---|---|---|---:|---:|
| baseline850 | Actual recapture, no ANALYZE | 1.19/0.669 | 52.716/49.895 | 20136 | 0 |
| next | Actual recapture, no ANALYZE | 0.695/0.578 | 63.194/62.847 | 20136 | 0 |
| baseline850 | Restored, before ANALYZE | 0.611/0.601 | 47.97/48.328 | 20126 | 0 |
| baseline850 | After ANALYZE | 0.552/0.572 | 13.386/13.413 | 16126 | 0 |
| next | Restored, before ANALYZE | 0.632/0.593 | 49.923/49.434 | 20126 | 0 |
| next | After ANALYZE | 0.533/0.53 | 13.721/13.382 | 16126 | 0 |

In both restored fixtures, ANALYZE removes a repeated kind-only Bitmap Index Scan beneath BitmapAnd at two path-evaluation sites (1000 rows per loop,1000 loops each before). Endpoint BitmapOr remains; root shared hits fall20126->16126 and execution fallsabout48-50ms->13.4-13.7ms. This establishes controlled plan sensitivity for the captured SQL, not the statistics/autovacuum state of primary samples.

Before ANALYZE both restored tables have reltuples=-1/relpages=0 and no column statistics. Afterward anchors has2005 estimated rows/126pages and graph_types4rows/1page. The repeated kind-only scan estimated18rows but returned1000 per loop; ANALYZE eliminates it from both recursive expansion and path-output evaluation. The actual source/state/Bind/plan-node paths are bound in summary-v1.json.

JIT: on, but no JIT section in any retained plan; jit_above_cost100000, inline/optimize thresholds500000. No JIT cause is established here.

Limitations:
- Primary both versions have slow and fast samples; primary plans/statistics were not captured.
- Same diagnostic Bind/captured anchors/types/indexes/settings and ordered result are verified. Original DDL defaults fill unused uncaptured columns; restored heap layout is not claimed byte-identical.
- Census/result checks warm buffers; EXPLAIN adds instrumentation. No cold-cache or application-speedup claim.
- Statistics views may lag; pre-ANALYZE cumulative table counters are observations, not synchronous modification counts.
- JIT is absent in all12 retained plans; observed estimated costs are below observed jit_above_cost100000.
- Root buffers are reported directly; inclusive parent/child counters are never summed.
