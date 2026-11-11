# Aggressive vs. Conservative TTG: Access, coverage and unnecessary fetches

[Open the 12-page English slides](slides/report/ttg-access-visit-comparison.pdf) · [Slide previews](slides/report/contact-sheet.png) · [Editable renderer](slides/render.py) · [Source-bound slide data](slides/slide-data.json)

This report compares the legacy Aggressive policy with Conservative plus the new Access-demand implementation. Both policies use the same tested current runtime, GIL-off Python and thread executor. The fixed JDrive, LittleX and RecipePantry workflows ran 24 fresh cases: 6 excluded warmups and 18 measured cases, n=3 per app/policy. All business responses and state checks passed. Counts are identical in all three measured repetitions.

## Definitions

**Observed demand coverage (the hit rate shown here)** is the number of request/session-local foreground-demand IDs also returned by prefetch, divided by all foreground-demand IDs. It includes root reads and memory hits. It is not a PostgreSQL cache-hit rate or a proof of the minimum semantically required demand.

**Unnecessary full-node payload** means a payload that need not be transferred/materialized at the client to preserve the measured business result. A node may be useful without being visited. Conversely, reading a node only to reject it by a predicate does not make fetching the entire payload necessary: the database can evaluate that predicate without returning the node.

The confirmed unnecessary count below is a **lower bound**: unused prefetches plus a disjoint set of source/state-validated filter-only prefetches. Zero means no examples were found in those two audited classes, not that a complete semantic-minimality proof has established zero unnecessary reads. Database predicate evaluation and scanned rows are outside this payload count.

All node counts are unique **within each request/session**, then summed over a workflow; they are not globally unique graph-node counts.

| App / policy | Prefetched | Used | Observed coverage | Unused | Filter-only | Confirmed unnecessary (lower bound) |
|---|---:|---:|---:|---:|---:|---:|
| JDrive / Aggressive | 1,090 | 319 | 319/349 = 91.40% | 771 | 61 | 832 |
| JDrive / Conservative | 265 | 265 | 265/288 = 92.01% | 0 | 0 | 0 found |
| LittleX / Aggressive | 357 | 357 | 357/384 = 92.97% | 0 | 0 | 0 found |
| LittleX / Conservative | 357 | 357 | 357/384 = 92.97% | 0 | 0 | 0 found |
| RecipePantry / Aggressive | 112 | 112 | 112/167 = 67.07% | 0 | 3 | 3 |
| RecipePantry / Conservative | 51 | 51 | 51/164 = 31.10% | 0 | 0 | 0 found |

JDrive's extra 61 are trashed Folder candidates in `VisibleFolderTree`; RecipePantry's extra 3 are cooked Meal candidates in `ShoppingList`. Paired request ID sets, original predicates and actual state establish that Conservative avoids their full payload while retaining the same business result. All three repetitions agree. These counts refine the earlier “unused only” table without rewriting the earlier evidence.

RecipePantry has 39 root-demand counts in each policy. Excluding roots gives 112/128 = **87.50%** for Aggressive and 51/125 = **40.80%** for Conservative. This separate view still leaves a substantial Conservative coverage gap. The current Access compiler stops at `jobj` and does not insert a new Access checkpoint after that origin becomes known. The report retains this limitation and the higher Conservative data-SQL count.

LittleX now matches 357 useful prefetches in both modes, including 70 objects used without a Visit. Historical same-workflow Conservative counts were 287. Historical numbers are clearly separated from this run, and no cross-run latency claim is made.

## Contents and verification

- `slides/`: English PDF, PNG previews, editable renderer, definition/numeric inputs and read-only derivation script.
- `raw/`: 24 exact case archives, including original compressed event bytes and seals.
- `workspace/`: accepted results/CSV/index, metrics, acceptance/physical/GIL/lifecycle evidence, test evidence and execution/source inputs.
- `runtime-delta/`, `instrumentation/`: captured runtime changes and effective instrumentation copies. The tested working tree is not represented as a new clean runtime commit.
- `manifests/`: original-to-packaged path mapping, archive member hashes, file inventory and explicit external runtime identities.

Run from any directory using Python 3:

```bash
python3 verify_package.py
```

This verifies all package files, all 24 archive member sets and hashes, every mapped derivation input, and the reported arithmetic. It requires no PostgreSQL, Jac import, network access or original workspace. It verifies preserved evidence; it does not re-execute the applications.

To regenerate the PDF from the packaged data (Matplotlib required):

```bash
python3 slides/render.py
```

Regeneration changes output hashes/metadata; use a copy of the package. The PDF's numerical source is `slides/slide-data.json`. `slides/derive.py` shows the original raw-to-slide derivation; original absolute paths are preserved in evidence and resolved through `manifests/path-mapping.json` by the verifier. Re-executing the benchmark needs the recorded interpreter/runtime dependencies and workspace layout; full installed runtimes, PostgreSQL clusters and caches are excluded.

No new DB workload was run to create these slides. All 24 owned test databases were validated and dropped, and the owned PostgreSQL cluster stopped. This precision-instrumented study establishes coverage and payload use, not an uninstrumented latency speedup.
