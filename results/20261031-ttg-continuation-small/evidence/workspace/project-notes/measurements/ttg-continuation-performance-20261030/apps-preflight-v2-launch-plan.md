# New complete 180-case correctness matrix

Status: prepared, not launched. Main and independent cleanup reviews plus main's explicit launch authorization are required. Formal performance remains unauthorized.

Launch update: main explicitly authorized the exact new full180 correctness run and wrote `cleanup-v2-main-review.json`, SHA-256 `770e3e3610d91ee292dee5ff3215802e2e4c46ff4705c0514c12e2e4ee1286ea`. Fresh host/source checks passed: all 33 source hashes and three manifest references match, old and peer PostgreSQL status 3, no owned live processes, 5,202,432,000 bytes free. The new matrix started at `2026-10-31T17:55:11.532239+00:00`, index `apps-preflight-866222-v2/index.json`, with the command below plus `--pause-request project-notes/measurements/ttg-continuation-performance-20261030/apps-preflight-866222-v2.pause-request`. The pause marker is absent. This update supersedes the prepared-only status; the reviewed execution source files remain unchanged.

The suite handed back the DB window after its frozen-v2 SNB/TPC-C off-policy correctness run passed 34 operation identities and 65 ordered business requests. Independent host verification is recorded in `suite-handback-snb-tpcc-v2/handback.json`: 68 recorded creator/session processes dead, no owned live processes, PostgreSQL status 3, and no postmaster PID file.

## Scope and source version

Run all 30 existing applications under all six configurations, seed 42, worker count 1 and prefetch limit 256. This is 180 fresh correctness cases, with zero formal samples. All cases use one reviewed v2 execution source closure and immutable runtime commit `866222f9093cb025950a1857e8175d526cc3a6e3` with its disclosed DIRECT overlay.

There is no carry or resume from the interrupted v1 matrix. Its 58 completed cases, original index, interrupted case, failed database, stopped cluster, and lifecycle evidence remain unchanged historical partial evidence. No case from that prefix counts toward the new 180-case acceptance.

Frozen cleanup candidate: `cleanup-v2-review-candidate1/candidate.json`, SHA-256 `00f26f19477c0df088ce240e49f754e0d707ac1da73a2413f6c732a2a31d1632`. Its 33 execution/oracle source hashes still match. Offline evidence `cleanup-v2-unit-v4/artifacts.json` records 92 passing checks. Both reviews must accept this exact candidate, or a newly frozen replacement, before launch.

## Concrete command

From `/home/baichuan/jaseci`, after main writes the matching cleanup review artifact and explicitly authorizes launch:

```bash
python3 -B reproduction/ttg-continuation-performance/application_matrix_v2.py correctness \
  --runtime-manifest reproduction/ttg-continuation-performance/runtime-clean-866222f90-v1-manifest/manifest.json \
  --overlay-manifest reproduction/ttg-continuation-performance/runtime-direct-866222f90-v1-overlay/manifest.json \
  --postcommit-proof project-notes/measurements/ttg-continuation-runtime-20261030/release-v3/postcommit-evidence.json \
  --cleanup-review project-notes/measurements/ttg-continuation-performance-20261030/cleanup-v2-main-review.json \
  --output project-notes/measurements/ttg-continuation-performance-20261030/apps-preflight-866222-v2 \
  --cluster reproduction/ttg-continuation-performance/pg-apps-866222-v2
```

Both proposed directories are absent at preparation time. No application subset, carry, resume, or timing mode is selected. The command accepts only `correctness`. It requires main's accepted exact-source/runtime/suite cleanup review before creating the cluster.

## Checks and failure handling

Each case must pass the existing logical workload oracle, independent stored-response semantic replay, full response/state equivalence against the fresh off-policy baseline, restart and session-nonce checks, complete nested payload-error checks, source guards, raw artifact seals, and the reviewed cleanup gate. Cleanup joins the exact owned database and cluster owner to case/run evidence, independently checks physical final state, revalidates sources and semantic acceptance, and requires zero active sessions immediately before DROP.

On the first failure or source invalidation, stop the matrix and preserve the failed database and sealed evidence. No in-place repair, mixed source version, silent skipped case, or automatic retry is permitted. Publish separate truthful stopped lifecycle evidence if interruption leaves the original index incomplete.

## Capacity forecast, not performance evidence

At preparation, free disk is 5,211,656,192 bytes (about 4.85 GiB). The historical 58-case correctness prefix has median case elapsed 13.3204 seconds and maximum 111.7348 seconds; median raw evidence is 2,457,618 bytes, maximum 4,699,583 bytes, and median independently gzipped size is 145,144.5 bytes. These values are provisioning/workflow correctness capacity observations and are excluded from performance results.

A simple 180-case median projection is about 40 minutes and 442 MB raw (26 MB gzip equivalent); the observed maximum raw case size projects to 846 MB. Budget 60–90 minutes and up to 1.2 GiB incremental storage for new raw evidence, cleanup proofs and one active owned cluster. This is a forecast: unseen application cost and stronger cleanup verification may change it. The runner stops below 3 GiB free rather than dropping cases. Only one cluster is active; the historical failed cluster remains stopped and preserved. No unrelated files or failed evidence will be removed. Successful current databases are deleted only through the reviewed gate.

## Launch blockers

1. Main's exact-closure/runtime approval artifact and explicit launch authorization remain required. Its separately bound full-tree source rehash is complete.
2. Independent cleanup semantic/source/owner review: SCOPED PASS for immutable candidate1, recorded in `../ttg-continuation-benchmark-review-20261030/perf-cleanup-candidate1-independent-review.json`. It independently ran 22 relationship controls and inspected actual replay wiring plus the owner's 92-test log; it did not rerun all workflows or grant DB launch permission.
3. Main-written matching `cleanup-v2-main-review.json` and explicit authorization for this new 180-case correctness command.

The suite stopped-state handback is already independently verified. No formal authorization is implied by any of these correctness approvals.
