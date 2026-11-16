# Background SQL: 30-entry TTG performance portfolio

[Final 28-page English slides](report/ttg-background-pushdown-all30.pdf) · [Complete CSV](table.csv) · [Full vectors and request-level records](data/inputs.json)

One LinkedList microbenchmark and 29 applications, four policies, five fresh measured workflows per cell. The main matrix contains 120 policy cells and 720 primary workflows: 120 excluded warmups and 600 measured workflows. Correctness covers 120 identities (108 fresh plus 12 explicitly carried); no timing samples were carried. JDrive uses depth7, with 4,374 initial nodes. Most other fixtures start small; this is broad coverage, not 30 large-scale validations.

Restored Background has lower instrumented HTTP response-sum medians than Off in two cases: JDrive (2130.899 → 801.967 ms, 62.4% lower) and LinkedList (208.977 → 111.783 ms, 46.5% lower). All 28 regressions remain. Extra worker/snapshot setup and reads are observed; the study does not isolate CPU causes or establish timely prefetch service.

## Reading the slides

- Pages 3–6: Jac graph, embedded ability-local dependency graphs, cross-ability SQL regions and worker/cache boundaries. The finite heterogeneous example is prior functional evidence, explicitly separate from current performance samples.
- Page 7: current Always admission versus future cost-aware admission.
- Pages 8–22: all 30 entries and 120 policy rows, with HTTP count, median/range, data/control/TOTAL SQL and data SQL per HTTP request.
- Pages 23–26: performance overview, actual JDrive activation, slow cases and support limitations.
- Page 27: sibling dependency; page 28: next steps and evidence.

The four modes are Off, Old Conservative, Previous Background and Restored Background. They are not a relabeling of the historical aggressive-TTG study. Off/restored use the restored runtime; the two old controls use the frozen previous runtime. The runtime commits were already published in the separate jac-ttg repository: restored `5cb1e0d0749004fb0a4a7a4b481ee74b089cc4eb`, previous `7e9beb7eaefaef30b6134e345728dd3a0d4bee23`.

## Measurement and evidence scope

HTTP is the sum of instrumented business-request response-read wall times; explicit post-response drain is separate. SQL counts include all recorded roles, snapshot/worker setup and attributed late calls through drain. Column medians need not add, although data + control = TOTAL in each trial. Primary captures retain SQL text and frontend frame metadata, not original Bind values or raw packets. SQL catalogs are included under `provenance/datasets/`.

This derived publication bundle preserves the frozen PDF, PNGs, numeric inputs, renderer, CSV, explanation, review records and selected provenance. `source-map.json` records byte-identical copies; `bundle-integrity.json` hashes every other bundle file. Original absolute references are retained as provenance. Raw case archives, databases, runtime checkouts and full benchmark/harness dependencies remain in the original workspace. The three lossless relocation maps are included, but their archives are external. This is not a complete portable benchmark replay package. The failed B1 v1 harness attempt remains separate and excluded from timing; the successful repaired fresh B1 v2 measurements are included.

## Re-render the presentation

With Python and Matplotlib installed (original version 3.10.5), run from this bundle directory:

```sh
python3 reproduction/ttg-background-pushdown-portfolio-report-20261115/render_report_v2.py \
  --input data/inputs.json --purpose analysis/purpose-examples.json \
  --output regenerated --previews
```

The renderer and inputs are the exact reviewed bytes; the packaged directory layout resolves its prior-method artifact locally. The regenerated PDF metadata and manifest paths may differ. The supplied frozen PDF SHA256 is `de0a661d0af1f26f15e9eb46dd1d8e0697f5c021a44e1154b127c63f37a67ee1`.
