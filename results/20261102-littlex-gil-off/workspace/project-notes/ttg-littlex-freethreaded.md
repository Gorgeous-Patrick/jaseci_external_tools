# LittleX on free-threaded Python: actual thread execution

Completed 12 fresh full workflows using the repaired runtime commit `5ce63eacde69f11817ed791b2d93544d7524be49`: off, thread and process, each with one excluded warmup followed by three measured repetitions. All modes use the same CPython **3.14.6 free-threading build**, fixture, native business workflow, uniform ANALYZE, one worker and prefetch limit 2048. The model is Always. No large dataset was run.

## GIL and executor assertions

The actual application and worker processes assert both:

```python
assert sysconfig.get_config_var("Py_GIL_DISABLED") == 1
assert sys._is_gil_enabled() is False
```

The assertions run at Python startup, every instrumented SQL completion boundary, native dependency outcome/context close, and normal Python exit. Failure exits the process with status 86 so import handling or a worker exception cannot silently hide it. `PYTHON_GIL=0` is deliberately not forced: an incompatible extension that enables the GIL would fail the checks. Loading the Jac runtime and native HTTP server also passed. A negative subprocess with `-X gil=1` exited 86 before its body executed.

The independent raw audit joined **7,384 SQL records** to exactly matching GIL-off assertion records. All 12 workflows passed the original full-response, restart, independent semantic replay and physical-state checks. Their semantic digests match; every workflow used a fresh database.

Each measured thread workflow executed **12 actual background SQL statements** in the same OS process as the foreground, on different native threads and PostgreSQL backend PIDs. No process fallback was accepted. Each process workflow instead used six distinct child processes. Off had no background SQL.

## Results

These are medians of three fresh measured workflows. HTTP time is the sum of nine instrumented primary request/response intervals, ending after response read; it is not total fixture/setup wall time. DB time is the sum of all-role send-to-ReadyForQuery intervals, including controls.

| Mode, all on GIL-off Python | All SQL | DB sum | HTTP response sum | HTTP range |
|---|---:|---:|---:|---:|
| Off | 153 | 38.131 ms | **98.909 ms** | 97.569–110.210 ms |
| Thread | 143 | 50.085 ms | **138.421 ms** | 132.373–140.765 ms |
| Process | 143 | 57.023 ms | **2415.932 ms** | 2403.667–2446.443 ms |

Thread's response sum is about **94.3% lower than process**, but still **39.9% higher than off** on this small fixture. This compares executors under GIL-off Python; it does not isolate the effect of enabling versus disabling the GIL.

The repaired cross-ability path is active in both prefetch modes: each feed uses one region query. Reducing SQL count has not made DB time lower than off. No foreground/background SQL protocol overlap was observed in any measured sample; DB sum equals interval union. This observation does not establish absence of CPU concurrency.

Process mode records six child startup-to-ready intervals per workflow, summing to 2023.346 / 2011.666 / 2031.505 ms. Thread mode launches none of these child processes. These readiness intervals include interpreter/Jac imports and store-object construction; they are neither isolated Popen time nor an additive critical-path decomposition. No CPU or IPC duration is derived from HTTP minus DB time.

The next performance questions are reducing merged-query DB cost and admitting prefetch only when useful work/round-trip savings justify it. Thread removes the large child-startup cost here, but the off control remains faster. Persistent-worker reuse and cost-model changes were not made in this experiment.

## One preserved instrumentation failure

`comparison-v1` stopped after the first thread warmup because the old observer labeled its SQL as foreground. Actual thread IDs differed and all GIL checks were false. CPython free-threaded builds default to inheriting the parent's ContextVars; the observer selected that inherited foreground context before the explicit native worker binding. See the [Python documentation](https://docs.python.org/3/howto/free-threading-python.html#context-variables).

The v2 observer gives the existing explicit worker binding precedence. A real free-threaded ContextVar regression verifies that the parent remains foreground while the bound child is background. This changes only measurement attribution, not native contexts, thread scheduling, application code or SQL. The failed v1 data and its stopped database were preserved, the latter in a verified lossless archive. None of v1's samples enter v2 results.

## Reproduction and evidence

All paths below are relative to `/home/baichuan/jaseci`:

- Harness and fail-closed GIL assertions: `reproduction/ttg-littlex-freethreaded/`
- Interpreter positive/negative checks: `project-notes/measurements/ttg-littlex-freethreaded-20261102/interpreter-assertions.json`
- Jac/runtime import check: same directory, `runtime-import.log`
- Context inheritance regression: same directory, `binding-regression.log`
- Exact captured plan, source hashes, 12 acceptance/raw references: same directory, `comparison-v2/index.json` and `plan.json`
- Independently reaggregated vectors/counts/intervals: same directory, `comparison-v2/results.json`
- Native child readiness vectors: same directory, `comparison-v2/startup-observations.json`

Executed comparison: `python3 -B reproduction/ttg-littlex-freethreaded/compare.py`. The fixed output directory must not already exist; the script deliberately refuses to overwrite evidence. Raw verification: `python3 -B reproduction/ttg-littlex-freethreaded/analyze.py`.

The runtime code remains unchanged from the pushed LittleX repair. The independent Python installation and new observer/harness live outside that runtime and outside previous frozen publication directories.
