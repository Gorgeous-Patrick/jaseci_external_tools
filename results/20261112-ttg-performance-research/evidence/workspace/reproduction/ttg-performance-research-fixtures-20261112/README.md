# RecipePantry graph scales and relational oracle

This standard-library module creates larger **initial persistent domain graphs** for the unchanged RecipePantry application. It parameterizes Ingredient, Recipe and Meal counts, requirements per recipe, servings and the exact planned/cooked mix. Cooked meals include real Consumption nodes and conserved initial inventory. It starts no processes or services and imports no Jac/runtime modules.

```bash
python3 -B reproduction/ttg-performance-research-fixtures-20261112/recipe_fixture.py \
  --preset large --output /tmp/recipe-large-new
python3 -B -m unittest discover \
  -s reproduction/ttg-performance-research-fixtures-20261112 \
  -p test_recipe_fixture.py -v
```

The output path must be new. Counts can override presets with `--ingredients`, `--recipes`, `--meals`, `--cooked-meals`, `--requirements-per-recipe` and `--seed`.

| Preset | Ingredients | Recipes | Meals (planned/cooked) | Domain nodes | Typed domain edges | Root edges |
|---|---:|---:|---:|---:|---:|---:|
| tiny | 3 | 2 | 6 (4/2) | 23 | 24 | 11 |
| small | 12 | 8 | 24 (16/8) | 92 | 96 | 44 |
| large | 120 | 80 | 240 (160/80) | 920 | 960 | 440 |

These are logical domain counts, excluding actual user/identity/root infrastructure. Every recipe has three different ingredient targets in these presets; ingredients are shared across recipes. Every Ingredient, Recipe and Meal is attached to the user's root. Every recipe has at least one initial Meal. PantryBoard visits all three root tables; ShoppingList reads all planned meals and their requirements, so the graph growth is actually reachable. Workload operation count stays 14 at each preset; this is not repeated small sessions. Each source PantryBoard ingredient and meal collection has no explicit ordering, as does ShoppingList. Only these named, unique-ID business tables may be compared as unordered relations; row values, types, membership and cardinality remain exact. `canonical_report` rejects duplicate IDs and extra/missing fields and never normalizes arbitrary lists/strings.

## Integration contract for Core t3

1. Load `recipe_fixture.py` by its unique file path. `build_fixture(**config)` returns `graph.nodes`, `graph.edges`, explicit `graph.root_attachments`, config, independent shape proof and initial digest. `write_fixture` exports `nodes.jsonl`, `edges.jsonl`, `root-attachments.json`, fixture, workload and hashes.
2. Copy the **unchanged frozen** `app_suite/apps/recipe_pantry/server.jac`. Preserve its hash and source provenance. A separately hashed test setup/inspection extension may create native objects; do not change Seed/business walkers or replace any user ability.
3. The old frozen `native_seed.import_graph` handles only the original four applications and assumes `item:0` for other apps. It is **not** a ready Recipe importer. The new adapter must construct all six actual classes from the rows, save objects, connect exact typed domain edges, then `Jac.connect` the actual authenticated root to every listed Ingredient/Recipe/Meal exactly once. Requirement/history nodes have no root attachment. Register all six node classes and all five edge classes; no custom access hook is required.
4. Map every fixture logical ID bijectively to its actual native ID. Root `user:0` is obtained independently from the authenticated SuiteRoot response, not from the domain mapping. Preserve the raw mapping, actual submitted body and native identity relation. Do not guess UUIDs or invoke a client-side mapping failure as a business rejection.
5. `RecipeOracle(fixture).apply(walker, logical_body, created_id=..., owner=...)` yields one exact business report and updates its independent relational graph. `workload(fixture)` returns the 14 ordered operations, expected reports, per-step pre/post digests and final graph. Every business rejection is **HTTP success with a report `{ok:false,error:<exact message>}`**, and exact unchanged graph. Transport/auth/permission errors must not satisfy it. Expected private-user rejection explicitly uses the separately authenticated `user:1` token; do not merely modify an owner argument without actual native dispatch.
6. `PlanMeal` returns the actual new Meal ID. Bind it to the step's predeclared logical ID. Purchase/Consumption history has no business-returned identity: independently inspect exact type, parent edge, units, multiplicity and step delta to extend the bijection. Do not collapse duplicate history rows. Check complete initial/final typed graph endpoints and root attachments, not only counts. Preserve exact native UUIDs across fresh sessions and restart.
7. `oracle-workload.json` includes a final graph oracle. Validate current outputs and persisted poststate after negative and positive operations, fresh sessions, final restart and physical census before accepting this scale or timing it. Fixture generation/pure unit checks alone do not constitute native acceptance.

## Fixed workflow and independent arithmetic

The mixed workflow is: Board, ShoppingList, insufficient-stock Cook rejection, invalid purchase rejection, blank-name Plan rejection, valid PlanMeal, three exact purchases for one original planned meal, successful Cook, duplicate Cook rejection, private-user Cook rejection, final Board and ShoppingList. The first planned meal always starts with zero stock; the successful three purchases/cook leave its ingredient stock zero and add three Purchase and three Consumption nodes. Other initial planned meals remain for a scaled final ShoppingList. All-cooked fixtures export only two read-only controls and do not claim a missing-stock branch or successful cook.

The oracle is a relational join/aggregation over independent node/edge tables: `Meal -> RecipeRef -> Recipe -> Needs -> Requirement -> IngredientRef -> Ingredient`, multiplied by servings and grouped by Ingredient for planned meals. Inventory is checked as `initial + purchased = remaining + consumed` on every Ingredient. The tiny fixture has directly hand-derived demand `[18,30,24]`, initial/consumed `[9,14,7]`, and six servings `[3,4,1,2,3,4]` with cooked meal indices 2 and 5. Tests exercise all-planned/all-cooked mixes, real graph growth, wrong typed endpoints, missing/duplicate root links, duplicate typed edges, corruption, exact errors, rollback, successful history and duplicate-cook rejection.

These files are a new preparation artifact. Native correctness, thread/GIL evidence, performance and independent review remain pending. No existing source, harness, snapshot or publication was changed.
