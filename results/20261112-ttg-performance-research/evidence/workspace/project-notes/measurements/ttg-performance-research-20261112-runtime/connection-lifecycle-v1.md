# LL1000 Aggressive: source-bound connection lifecycle

This read-only diagnosis covers one preserved correctness request, generation2/request2:7, `Find(target=0)`, in `linked_list-1000-aggressive-correctness-0`. It neither reruns a test nor changes runtime, observer or validator. The bound JSON retains source hashes/ranges, exact raw record lines, intervals and lifecycle references.

**Study decision:** preserve the isolation-gate failure. No runtime fix or validator relaxation. LL1000 Off is correctness-only; Aggressive failed the isolation gate; Conservative was not run. Its failed database and all raw sources remain preserved. The failed cell has no independent acceptance. The other19 fixtures/17apps may continue only under the separately accepted lineage plan. No LL1000 n5 timing or precision values are invented.

## Three threads are involved

- `124806031853376`: server main thread, corroborated by the GIL startup record (native TID1149040). It performs initial request/root/target SQL and response/context cleanup.
- `124806013904448`: native spawn worker, which also executes aggressive planning. It is labeled foreground because `asyncio.to_thread(_spawn_with_profile)` inherits the HTTP request binding. Foreground does not mean main thread.
- `124805997119040`: explicitly tagged prefetch payload thread. `sitecustomize` gives its `_ttg_perf_binding` priority over inherited foreground ContextVars. Its label is background/thread.

Frozen `server/impl/server.impl.jac:644–658` creates the synchronous spawn callable and passes it to asyncio.to_thread. `prefetch.jac:165–172` explicitly binds only actual payload threads. `continuation_probe.binding` and the sitecustomize override explain these role labels; the direct PgWire boundary snapshots the actual calling thread and role at entry.

## Observed main connection1149158 / object3988616441872

| Raw line | Thread / role | Statement | Send → ReadyForQuery ns |
|---|---|---|---|
| 1074 | spawn/planner, foreground | recursive planning query | 3004806994612208 → 3004807098417251 |
| 1075 | spawn/planner, foreground | COMMIT | 3004807112204245 → 3004807112577370 |
| 1076 | payload worker, background | BEGIN REPEATABLE READ READ ONLY | 3004807112733806 → 3004807112836248 |
| 1077 | payload worker, background | SET LOCAL lock_timeout | 3004807112861203 → 3004807112936061 |
| 1078 | main, foreground | COMMIT | 3004807113091064 → 3004807113209758 |
| 1079 | main, foreground | DISCARD ALL | 3004807113548357 → 3004807113666144 |

Background BEGIN precedes main DISCARD/release. It is therefore not explained by a simple prior pool return. The source directly exposes a shared-store path: `Session.prefetch:985` calls **self.read_barrier() on the original Session**; only afterward at989 does it create `store.reader_clone()`. `read_barrier:1285` calls `_ensure_txn:1143`; that method may begin the main store's transaction. `PgStore._run:397` and transaction methods serialize statements with the per-store RLock. The selected18-call request contains no cross-thread send-to-ready overlap on this connection. That observation is bounded to retained statement intervals, not a general transaction/lifetime proof.

Main-thread COMMIT is consistent with request finalization (`_finalize_call_response` calls acommit) and shared Session cleanup. The exact COMMIT caller stack is not retained. The native context-close interval is3004807113439181–3004807113704877 and contains DISCARD ALL, matching `PgStore.close` → `_park_conn` → DISCARD → pool.release. Pool return uses a process-global locked bucket keyed by connection info, not by caller thread. No pool checkout/lease events were retained, so generic lease ownership cannot be reconstructed solely from backend PID.

## Actual background payload uses another reader

Raw1080 is the payload SELECT on object3988683621008/backend1149191, background thread124805997119040:3004807113852790–3004807122437623,999returned rows. Its DISCARD is raw1081. This reader is distinct from the shared main-store barrier connection. The HTTP response ends3004807114029440; explicit post-response drain ends3004807134264073 with pending0.

`Session.close:1510` joins threads only when process readers exist; this ordinary aggressive thread worker can still be active during native close. The source and trace therefore explain why a global “every foreground/background backend differs” assertion fails, including background transaction controls. They do **not** prove generic harmlessness, safe closed-Session reuse under all schedules, or actual business-data corruption. The strict isolation gate remains unchanged and failed by the study decision.

This is a source-backed mechanism and preserved failed correctness case, not a new performance sample or measured slowdown decomposition. Native business response/state evidence must remain separately labeled; HTTP200 alone does not confer independent acceptance.
