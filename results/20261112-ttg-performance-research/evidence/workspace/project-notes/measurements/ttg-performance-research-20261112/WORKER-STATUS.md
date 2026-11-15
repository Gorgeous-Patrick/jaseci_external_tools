# Active Nov12 performance research

Core terminals: performance t3; main t1; independent reviewer t4; runtime,
Recipe fixtures, diagnostic plan and presentation source t13. Use `hc send`;
no old Herdr pane addresses. No subagents. All long jobs use `hc run --bg` and
`hc wait`, with one owned DB/timing window and no competing heavy work.

## Frozen execution version

- OWN `reproduction/ttg-performance-research-20261112`;18 owned Python files
  frozen in `candidate-v1/sources`.
- Candidate manifest `4e4df1b06b788ddf197ac2d5c8296f980a7c6279548f7e0a6a3ff635f4d2c2e4`.
- `plan-v1/plan.json` `143ecc1e397a3f9b4c1ca3a2284c7f2a86ca2fd10dd1f62cd31e04b348634866`;
  `sources.json` `8d3c3e3afaded659aca55d28110304e22d86afa1069e723d5566c413d4c8a047`.
-11640 owned/accepted transitive source + effective CLEAN/overlay references
  verified at preflight in1.04s; controller verifies pre/post and uses stat
  mutation checks at case boundaries. No repeated historical70k-tree audit.
- Six DB-free focused tests passed in `offline-v3.log`; earlier two mock/import
  failures remain preserved. Exact frozen-source review is828ec4b0… in reviewer
  measurement root.
- Latest common runtime is the immutable Nov11 condition-access snapshot,
  clean39ab46b8… /overlay4deaf0ea…. It includes unified normal/condition-call
  Access, jobj and `_owns`; live dirty checkout is not executed. t13 bound30
  dirty files and11 legacy/shared files to prior aggressive source; this is a
  scoped equality argument, not historical whole-program equivalence.

Policies: none/ttg/ttg_dependency; fused only for conservative. Same Always,
THREAD1, prefetch_limit2048, compiled32768 steps, actual GIL disabled at observed
SQL/outcome/close boundaries. Primary still includes DIRECT/compact/GIL
callbacks: label **instrumented**, not clean/uninstrumented. Full Session
precision wrappers activate only for the separate precision stage.

## Scope and release

Fixed17: JDrive, LittleX, RecipePantry, original LinkedList plus the unchanged13
domain apps from prior15. No substitutions/slowcase pruning. All small fixtures
smoke. Ready larger cases are JDrive depth5, LittleX50×20 and original LL1000;
17+3=20 fixtures /60 policy cells. LL uses the original six-operation oracle,
not the old finite single-Traverse variant. Recipe920-node and JDrive depth7
are separate additive scopes requiring native scale acceptance.

Main `main-continuation-release-v1.json` authorizes sequential unchanged stages
without another permission question, conditional on previous complete/source
passed/owned stop/capacity: small-rest210 →larger45 →extend-n5 120 →precision60.
First n3 are the predeclared first3 of n5 only with unchanged execution version.
20 fixtures total:60 correctness +60 excluded warmups +300 measured n5 =420
primary-stage records. Precision60 is n1/cell, separate; never pool its timings.

First45 completed in terminal t16/PID968248: index46eba79b…, source-after true,
45 validated owner/active-zero drops, all GIL proofs, PG3/noPID/retained[].
Stopped/capacity proof4c4a3edb…, raw audit t4 PASS98c80c06…/summary439433ae…,
one-pass1.338s. Export `export-first-v1/results.json`239739e4… /CSV2a294907…:
9 correctness,9 warmups,27 measured,9 n3 cells. Regressions retained.

**Current authoritative progress:** `small-rest-v1/index.json` and log.
Launched Herdr t17/PID1023036; last reported126/210, no failures. Do not infer
current state from this prose. Guards startup3GiB /between2.5GiB /stop2GiB;
last free~8.2GB. Other nonowned services retained; lightweight host observations
in `host-observations-v1.jsonl`, no whole-host quiet claim.

## Exact next commands after natural stage stop

Use `hc wait t17 --timeout 40`; on complete read the index/log, run the existing
NEW `stage_proof_v1.py` with current index/cluster/new output. It checks known
owned PIDs, exact owned argv, PG3/noPID, GIL refs, drops/retained databases and
metadata-only case byte forecast. Do not repeat raw/full-tree hashing.

Then launch via `hc run --bg --name ttg-nov12-larger --cwd /home/baichuan/jaseci`:

`python3 -B reproduction/ttg-performance-research-20261112/runner.py --plan project-notes/measurements/ttg-performance-research-20261112/plan-v1/plan.json --stage larger --output project-notes/measurements/ttg-performance-research-20261112/larger-v1 --cluster reproduction/ttg-performance-research-20261112/pg-larger-v1 > project-notes/measurements/ttg-performance-research-20261112/larger-v1.log 2>&1`

Repeat complete/stop/capacity, then same runner `--stage extend-n5`, new
`extend-n5-v1`/`pg-extend-n5-v1`, then `--stage precision`, new
`precision-v1`/`pg-precision-v1`. Announce actual terminal/PID to t1 and quiet
to t4/t13. First failure stops; preserve case/DB; never patch running sources.

## Postprocessors and report handoff

`postprocess_v1.py` is frozen outside captured18. Actual first export passed.
After primary, pass all completed index paths to export n5 vectors. Validates
saved metric/proof/acceptance/GIL references and consumed sealed HTTP; t4 raw
reaggregation remains distinct. HTTP response sum/union/span, DBsum/union,
data/control/total SQL and data SQL per business request, complete inventory.
No p95 claim from n5. No CPU inference from HTTP minus DB.

`precision_postprocess_v1.py` is **source-only draft**, unexecuted/untested.
It separates actual returned IDs P, successful foreground demand D, P∩D,
post-return overlap, promotion-backed service, late discarded deliveries and
unused nodes. Session joins use actual native-close nonce; ambiguity fails.
P∩D is not itself timely service. Empty denominators null; Off P=0 valid.
Use no-raw-mutation synthetic checks at a stopped boundary before actual
precision export. `_owns`/jid root-neighbor IDs are valid Access demands.
White-read lower bound Pnode−Dnode; extra disjoint query-filter candidates need
source-validated necessity audit. Never equate Access demand with OSP entry.

t13 owns `reproduction/ttg-performance-research-report-20261112` source-only
renderer/adapter, and `reproduction/ttg-performance-research-fixtures-20261112`
pure Recipe generator/oracle. No rendering during timing. Actual first export
schema delivered; all final figures await complete accepted data.

Post-primary diagnostics PLAN ONLY at
`reproduction/ttg-performance-research-diagnostics-20261112/POST-PRIMARY-PLAN.md`.
Choose1–2 sites from actual n5; valid thread CPU control and max4 matched READ
EXPLAIN plans only if warranted. Never wrap `access_checkpoint`: it reads its
native caller frame via sys._getframe(1). Prefer already-bound prefetch_accesses
or disclosed internal clocks; native outputs AND activation/query counts must
match unprofiled. No experiments before main's post-primary coordinated window.

All old publications, sources and archives remain unchanged. No historical
deletions. Main performs final package review/commit/push.
