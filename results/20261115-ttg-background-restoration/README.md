# Background TTG recursive-tree restoration

[Four-page slides](report/ttg-background-pushdown-restoration.pdf) · [CSV](table.csv)

Fresh JDrive depth-five comparison, n=5 measured workflows per policy, four separate excluded warmups. Each workflow contains seven business HTTP requests. Four apps also passed 16 separate correctness workflows; only JDrive has new performance measurements in this restoration round.

| Policy | HTTP sum median (ms) | Data SQL | Control SQL | Total SQL |
|---|---:|---:|---:|---:|
| Off | 399.048 | 414 | 49 | 463 |
| Old Conservative | 263.988 | 53 | 54 | 107 |
| Previous Background | 416.749 | 606 | 424 | 1030 |
| Restored Background | 197.124 | 122 | 74 | 196 |

The restored worker reuses the existing predicate-aware output-tree certificate. Three recursive queries and five pool jobs occur in every measured restored workflow. Restoration lowers the HTTP median by 52.7% versus previous Background, 50.6% versus Off, and 25.3% versus old Conservative. Counts include snapshot/worker setup and all recorded foreground/background SQL. Instrumented response-read wall excludes the explicit post-response drain; attributed late SQL is retained.

The extra 89 SQL versus old Conservative comprises 30 ordinary-path queries, 29 payload reads, 15 snapshot/worker-identity setup statements and 15 other control statements. Cache publication is not evidence of timely service; these measurements do not isolate CPU or the cause of remaining foreground reads.

## Source and evidence scope

`commit-binding.json` binds the exact previously tested 38-file baseline and final 41-file runtime to the new commits in the separate `jac-ttg` repository. Historical manifests retain their original precommit HEAD and hashes; they were not rewritten. Old Conservative and previous Background used the immutable previous runtime; Off and restored Background used the restored runtime.

This small bundle preserves the final PDF, its inputs and renderer, vectors/CSV, purpose analysis, correctness/primary indices, plan, lifecycle and independent review summaries. `source-map.json` records byte-identical copies. Referenced raw case files, runtime checkouts, database directories and full transitive harness dependencies remain in the original workspace and are not included. This is not a complete portable benchmark replay package.

## Re-render the slides

With Python and Matplotlib installed, run from this directory:

```sh
python3 render_report.py --inputs inputs-local.json --output regenerated --previews
```

`inputs-local.json` changes only input paths to packaged files. The original frozen input manifest and report output bytes remain under `provenance/` and `report/`. Regenerated PDF metadata may differ.
