# Aggressive vs. Conservative TTG: Access coverage and unnecessary fetches

[Open the updated 12-page English slides](slides/report-v3/ttg-access-visit-comparison.pdf) · [Summary table — page 4](slides/report-v3/slide-04.png) · [Editable renderer](slides/render_v3.py)

The slides show the latest accepted results, without a repair-history or before/after progression. RecipePantry Conservative now includes unified Access extraction for ordinary calls and condition calls. Its current result is **118/164 = 71.95% coverage**, with **118 prefetched and used objects, 0 unused prefetches**, and **213 data + 166 control SQL calls**. All three measured repetitions agree; business outputs and persisted state pass.

The RecipePantry Conservative result comes from November 11. Aggressive and the JDrive/LittleX results retain their November 10 captures; they were not rerun with this repair. The table is an explicitly versioned summary, not a simultaneous new three-app comparison.

| App | Aggressive coverage | Conservative coverage | Aggressive unnecessary fetches | Conservative unnecessary fetches |
|---|---:|---:|---:|---:|
| JDrive | 319/349 = 91.40% | 265/288 = 92.01% | At least 832 | 0 confirmed |
| LittleX | 357/384 = 92.97% | 357/384 = 92.97% | 0 confirmed | 0 confirmed |
| RecipePantry | 112/167 = 67.07% | **118/164 = 71.95%** | At least 3 | **Not audited** |

## Definitions

**Observed demand coverage**, called hit rate in the slides, is foreground-demand IDs returned by prefetch divided by all successful foreground-demand IDs. Counts are unique within each HTTP request / Session and summed over the workflow. The denominator includes roots and memory hits; this is not a PostgreSQL cache-hit rate.

**Unnecessary full-node payload** is a payload that need not be transferred/materialized at the client to preserve the business result. A helper can need a node without visiting it. Conversely, a predicate or identity check can touch a node whose complete payload need not have been fetched.

The previously audited unnecessary counts are lower bounds: unused prefetches plus disjoint filter-only payloads. JDrive's 832 comprise 771 unused and 61 rejected trashed Folder candidates. RecipePantry Aggressive's 3 are cooked Meal candidates rejected in ShoppingList. “0 confirmed” means none found in those audited classes. **The updated RecipePantry Conservative run has zero unused prefetches, but its semantic unnecessary-payload count has not been re-audited.** Ownership membership may need only IDs rather than full neighbor payloads.

## Slide guide

- Page 4: Aggressive / Conservative coverage and unnecessary-fetch table.
- Page 5: Prefetched, used, unused and audited filter-only counts.
- Page 8: Current RecipePantry Conservative results.
- Page 9: Unified helper/condition Access analysis, native bindings and short-circuit guards.
- Page 10: Data and control SQL counts.
- Pages 11–12: Next steps and evidence scope.

## Evidence and reproduction

The original package retains 24 exact case archives (6 warmups + 18 measurements), runtime/instrumentation inputs, accepted semantic/physical/GIL/lifecycle proofs and source-bound derivation. Those original archives and earlier PDFs are unchanged.

The November 11 validation ran 8 fresh RecipePantry workflows (2 warmups + 6 measurements); the deck presents only repaired results. It passed 61 pure tests and 89 native regression tests, plus all application and cleanup gates. `slides/update-20261111/` contains copied accepted derived results, index, validation records, tests and original path/hash references. Its eight raw case archives remain in the measurement workspace and are **not** added to this package. The original workspace audit checked all 256 new sealed case files. All owned services and PostgreSQL stopped.

Portable verification (Python standard library, no DB):

```bash
python3 verify_package.py
```

This checks package contents, the original 24 archives, mapped inputs, updated result arithmetic and report bindings. It does not re-execute applications or re-audit the eight new raw cases.

Regenerate in a copy of the package (Matplotlib required):

```bash
python3 slides/derive_update.py
python3 slides/render_v3.py
```

The current renderer consumes `slides/slide-data.json` for the retained original configurations and `slides/slide-data-v3.json` for repaired RecipePantry. `slides/derive_update.py` validates and derives the update from copied accepted results. Regeneration changes output metadata/hashes; resealing is required afterward.

Coverage and payload-use findings alone do not establish a latency speedup or minimum semantically required demand.
