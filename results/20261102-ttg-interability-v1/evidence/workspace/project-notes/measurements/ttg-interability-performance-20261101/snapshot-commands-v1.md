# Post-handoff snapshot and launch commands

Prepared only. None of the snapshot, import/bootstrap, compiler or database
commands below has been executed for this round. P6 retains the sole native
correctness window. The changed harness candidate remains `93ae77c7aac4a0ece262f07ce963624704cc3b2bc7bdf7e17bca0e8076a7fa92`.

## Inputs to bind at handoff

- Exact clean tested runtime commit and owner verification JSON with
  `passed`, `runtime_commit` and `source_files`.
- P6 stopped-service/PG proof and explicit quiet handoff.
- P8 bounded changed-harness review; concrete findings resolved in a new
  source revision before native launch.
- Actual free bytes and incremental snapshot/cluster forecast. Existing scoped
  proposal: startup 768 MiB, between cases 640 MiB, in-case stop 512 MiB.

## Immutable snapshot command

Reuse the accepted hardlink/atomic-replacement implementation in
`reproduction/ttg-next-performance/snapshot.py`. Its existing immutable850
base is present, including physical ignored typeshed. The9282 CLEAN/DIRECT
baseline is also present and reused directly for the experiment. Using850 as
the snapshot construction base changes neither the resulting exact committed
tree nor the comparison baseline. Its manifest and unchanged-base verification
remain explicit. No live mutable source inode is linked.

Set `TTG_IA_FINAL_COMMIT` and `TTG_IA_FINAL_PROOF` from P6's actual release, then
run the following only after handoff. The sole in-memory adapter sets the
helper's owned output root; transformation and snapshot algorithms are unchanged.
New files use temporary-file replacement, preserving shared base inodes.

```bash
python3 -B -c '
import os, pathlib, runpy, sys
root = pathlib.Path.cwd()
helper = root / "reproduction/ttg-next-performance"
sys.path.insert(0, str(helper))
module = runpy.run_path(str(helper / "snapshot.py"), run_name="_ia_snapshot_reuse")
own = root / "reproduction/ttg-interability-performance"
module["freeze"].__globals__["OWN"] = own
clean = module["freeze"](
    root / "jac-ttg", os.environ["TTG_IA_FINAL_COMMIT"],
    pathlib.Path(os.environ["TTG_IA_FINAL_PROOF"]).resolve(),
    own / "runtime-clean-final-v1")
direct = module["direct"](clean, own / "runtime-direct-final-v1")
print(clean)
print(direct)
'
```

Record this command document together with the existing generator, input
verification and CLEAN/DIRECT manifest hashes. The helper verifies the exact
clean HEAD, tested source hashes, all resulting members and unchanged immutable
base. The direct patch retains the accepted clocks, protocol counters and child
environment propagation. Recheck identical component bytes before treating
earlier component calibration as applicable; changed component bytes require
targeted validation.

Import-only bootstrap follows the accepted bootstrap helper under the explicit
new runtime/PYTHONPATH and owned cache environment. It may invoke the Jac
compiler, so it is also held until P6's handoff. Preserve each failed log and
use a new output log for any corrected invocation.

## Final metadata and native correctness

After snapshot/bootstrap and the bounded review checkpoint:

```bash
python3 -B reproduction/ttg-interability-performance/ia_build_plan.py \
  --output project-notes/measurements/ttg-interability-performance-20261101/correctness-plan-v1 \
  --clean reproduction/ttg-interability-performance/runtime-clean-final-v1-manifest/manifest.json \
  --direct reproduction/ttg-interability-performance/runtime-direct-final-v1-overlay/manifest.json

python3 -B reproduction/ttg-interability-performance/ia_runner.py correctness \
  --plan project-notes/measurements/ttg-interability-performance-20261101/correctness-plan-v1/plan.json \
  --output project-notes/measurements/ttg-interability-performance-20261101/correctness-v1 \
  --cluster reproduction/ttg-interability-performance/pg-correctness-v1
```

The plan builder binds sources once, including accepted borrowed helpers. Do
not run it during P6's native window merely to fill runtime placeholders. The
native command performs twelve primary cases and three fresh false-guard
subchecks, with ANALYZE before the first business/reset clock. Failed evidence
and its database are preserved. LL acceptance includes actual activation and
all-role TOTAL SQL reduction; the tiny chain retains any fixed-overhead cost.

## Formal command held for main release

Only main writes the fixed new authorization. After complete correctness,
capacity projection and quiet handoff, the intended command is:

```bash
python3 -B reproduction/ttg-interability-performance/ia_runner.py formal \
  --plan project-notes/measurements/ttg-interability-performance-20261101/correctness-plan-v1/plan.json \
  --output project-notes/measurements/ttg-interability-performance-20261101/formal-v1 \
  --cluster reproduction/ttg-interability-performance/pg-formal-v1
```

Exact schedule:48 fresh workflows,12 excluded warmups and36 measured trials;
four fixtures × three modes × n3. The false alternatives remain correctness-only.
Source review findings may require a new plan/source version before either
launch; these paths describe the current candidate rather than authorize it.
