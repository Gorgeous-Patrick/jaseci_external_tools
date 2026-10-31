# LittleX: measured SQL and interval attribution

Read-only analysis of18 accepted measured workflows. Protocol completion wall includes client decoding/progress. No CPU-cause inference or new DB execution.

## Exact accounting of summed DB calls minus interval union

| Configuration | Repeat | Gap ms | Excess integral by actual role/backend class (ms) |
|---|---:|---:|---|
| none | 0 | 0.000000 | None |
| continuation_expected_benefit_process | 0 | 0.000000 | None |
| continuation_expected_benefit_thread | 0 | 4.139315 | BG_only/distinct_backends: 4.139315 |
| continuation_always_process | 0 | 0.000000 | None |
| continuation_always_thread | 0 | 6.530886 | BG_only/distinct_backends: 6.530886 |
| legacy_ttg_thread | 0 | 0.094682 | FG_and_BG/distinct_backends: 0.094682 |
| continuation_always_thread | 1 | 6.288602 | BG_only/distinct_backends: 6.288602 |
| continuation_always_process | 1 | 0.000000 | None |
| continuation_expected_benefit_thread | 1 | 5.564781 | BG_only/distinct_backends: 5.564781 |
| continuation_expected_benefit_process | 1 | 0.000000 | None |
| none | 1 | 0.000000 | None |
| legacy_ttg_thread | 1 | 0.183798 | FG_and_BG/distinct_backends: 0.183798 |
| continuation_always_thread | 2 | 7.591817 | BG_only/distinct_backends: 7.591817 |
| legacy_ttg_thread | 2 | 0.141279 | FG_and_BG/distinct_backends: 0.141279 |
| none | 2 | 0.000000 | None |
| continuation_expected_benefit_process | 2 | 0.000000 | None |
| continuation_expected_benefit_thread | 2 | 4.972579 | BG_only/distinct_backends: 4.972579 |
| continuation_always_process | 2 | 0.000000 | None |

Every gap is exactly accounted for by sweep segments. Pairwise intersections can overlap each other and are not added to explain a triple-overlap gap. Actual call indices, backend/client PIDs and pair intervals are retained in attribution.json.

## SQL fingerprint contributions

Counts/times below are pooled across THREE measured workflows, not median workflow times. Every exact fingerprint and data/control classification is retained in JSON.

### none

| Fingerprint prefix | Kind / role | Pooled calls | Pooled protocol ms | SQL excerpt |
|---|---|---:|---:|---|
| b0075df9e735 | data / foreground | 156 | 41.699022 | SELECT a.id, a.kind, a.arch_type, a.arch_module, a.fingerprint, a.root_id, a.src, a.dst, a.undirected, a.props, a.version, CASE WH |
| 79663c1d3b43 | control / foreground | 54 | 19.899309 | COMMIT |
| 6dc81f61e5e5 | data / foreground | 33 | 17.383994 | SELECT n1.id, e1.id FROM unnest(CAST($1 AS uuid[])) WITH ORDINALITY AS f0(id, ord) LEFT JOIN anchors s1 ON s1.id = f0.id JOIN anch |
| 33d1c6d4f6d1 | data / foreground | 12 | 13.908777 | SELECT n2.id, e2.id FROM unnest(CAST($1 AS uuid[])) WITH ORDINALITY AS f0(id, ord) LEFT JOIN anchors s1 ON s1.id = f0.id JOIN anch |
| 0a54b4ae9f01 | data / foreground | 15 | 8.293206 | SELECT n1.id, e1.id FROM unnest(CAST($1 AS uuid[])) WITH ORDINALITY AS f0(id, ord) LEFT JOIN anchors s1 ON s1.id = f0.id JOIN anch |
| 7c031ced90a8 | data / foreground | 27 | 3.422278 | SELECT doc FROM identity_users WHERE user_id = $1 |
| e7b550770798 | control / foreground | 54 | 2.432876 | SET LOCAL lock_timeout = '10s' |
| 58ed4051f7fc | data / foreground | 9 | 2.420050 | INSERT INTO anchors (id, kind, arch_type, arch_module, fingerprint, root_id, src, dst, undirected, props, format_version, version, |

### continuation_expected_benefit_process

| Fingerprint prefix | Kind / role | Pooled calls | Pooled protocol ms | SQL excerpt |
|---|---|---:|---:|---|
| b0075df9e735 | data / background_prefetch | 39 | 33.605483 | SELECT a.id, a.kind, a.arch_type, a.arch_module, a.fingerprint, a.root_id, a.src, a.dst, a.undirected, a.props, a.version, CASE WH |
| b0075df9e735 | data / foreground | 117 | 30.184219 | SELECT a.id, a.kind, a.arch_type, a.arch_module, a.fingerprint, a.root_id, a.src, a.dst, a.undirected, a.props, a.version, CASE WH |
| 79663c1d3b43 | control / foreground | 54 | 21.824996 | COMMIT |
| 9a36ea7adf29 | data / foreground | 12 | 15.067538 | SELECT n2.id, e2.id, n2.arch_type, n2.arch_module FROM unnest(CAST($1 AS uuid[])) WITH ORDINALITY AS f0(id, ord) LEFT JOIN anchors |
| 6dc81f61e5e5 | data / foreground | 18 | 9.529147 | SELECT n1.id, e1.id FROM unnest(CAST($1 AS uuid[])) WITH ORDINALITY AS f0(id, ord) LEFT JOIN anchors s1 ON s1.id = f0.id JOIN anch |
| 1f501894bd8c | data / foreground | 15 | 8.941545 | SELECT n1.id, e1.id, n1.arch_type, n1.arch_module FROM unnest(CAST($1 AS uuid[])) WITH ORDINALITY AS f0(id, ord) LEFT JOIN anchors |
| f341dab97d76 | data / foreground | 12 | 7.325784 | SELECT n1.id, e1.id, n1.arch_type, n1.arch_module FROM unnest(CAST($1 AS uuid[])) WITH ORDINALITY AS f0(id, ord) LEFT JOIN anchors |
| 7c031ced90a8 | data / foreground | 27 | 4.570096 | SELECT doc FROM identity_users WHERE user_id = $1 |

### continuation_expected_benefit_thread

| Fingerprint prefix | Kind / role | Pooled calls | Pooled protocol ms | SQL excerpt |
|---|---|---:|---:|---|
| b0075df9e735 | data / foreground | 120 | 29.824718 | SELECT a.id, a.kind, a.arch_type, a.arch_module, a.fingerprint, a.root_id, a.src, a.dst, a.undirected, a.props, a.version, CASE WH |
| b0075df9e735 | data / background_prefetch | 36 | 28.994594 | SELECT a.id, a.kind, a.arch_type, a.arch_module, a.fingerprint, a.root_id, a.src, a.dst, a.undirected, a.props, a.version, CASE WH |
| 79663c1d3b43 | control / foreground | 54 | 19.116359 | COMMIT |
| 9a36ea7adf29 | data / foreground | 9 | 11.429845 | SELECT n2.id, e2.id, n2.arch_type, n2.arch_module FROM unnest(CAST($1 AS uuid[])) WITH ORDINALITY AS f0(id, ord) LEFT JOIN anchors |
| 1f501894bd8c | data / foreground | 15 | 8.829409 | SELECT n1.id, e1.id, n1.arch_type, n1.arch_module FROM unnest(CAST($1 AS uuid[])) WITH ORDINALITY AS f0(id, ord) LEFT JOIN anchors |
| 6dc81f61e5e5 | data / foreground | 18 | 8.723618 | SELECT n1.id, e1.id FROM unnest(CAST($1 AS uuid[])) WITH ORDINALITY AS f0(id, ord) LEFT JOIN anchors s1 ON s1.id = f0.id JOIN anch |
| f341dab97d76 | data / foreground | 12 | 7.228341 | SELECT n1.id, e1.id, n1.arch_type, n1.arch_module FROM unnest(CAST($1 AS uuid[])) WITH ORDINALITY AS f0(id, ord) LEFT JOIN anchors |
| 98f36323c6bc | control / background_prefetch | 36 | 5.942975 | DISCARD ALL |

### continuation_always_process

| Fingerprint prefix | Kind / role | Pooled calls | Pooled protocol ms | SQL excerpt |
|---|---|---:|---:|---|
| b0075df9e735 | data / background_prefetch | 42 | 34.323023 | SELECT a.id, a.kind, a.arch_type, a.arch_module, a.fingerprint, a.root_id, a.src, a.dst, a.undirected, a.props, a.version, CASE WH |
| b0075df9e735 | data / foreground | 114 | 29.497246 | SELECT a.id, a.kind, a.arch_type, a.arch_module, a.fingerprint, a.root_id, a.src, a.dst, a.undirected, a.props, a.version, CASE WH |
| 79663c1d3b43 | control / foreground | 54 | 22.319031 | COMMIT |
| 9a36ea7adf29 | data / foreground | 12 | 16.889505 | SELECT n2.id, e2.id, n2.arch_type, n2.arch_module FROM unnest(CAST($1 AS uuid[])) WITH ORDINALITY AS f0(id, ord) LEFT JOIN anchors |
| 1f501894bd8c | data / foreground | 18 | 11.895337 | SELECT n1.id, e1.id, n1.arch_type, n1.arch_module FROM unnest(CAST($1 AS uuid[])) WITH ORDINALITY AS f0(id, ord) LEFT JOIN anchors |
| f341dab97d76 | data / foreground | 12 | 8.207083 | SELECT n1.id, e1.id, n1.arch_type, n1.arch_module FROM unnest(CAST($1 AS uuid[])) WITH ORDINALITY AS f0(id, ord) LEFT JOIN anchors |
| 6dc81f61e5e5 | data / foreground | 15 | 7.318434 | SELECT n1.id, e1.id FROM unnest(CAST($1 AS uuid[])) WITH ORDINALITY AS f0(id, ord) LEFT JOIN anchors s1 ON s1.id = f0.id JOIN anch |
| 7c031ced90a8 | data / foreground | 27 | 4.750629 | SELECT doc FROM identity_users WHERE user_id = $1 |

### continuation_always_thread

| Fingerprint prefix | Kind / role | Pooled calls | Pooled protocol ms | SQL excerpt |
|---|---|---:|---:|---|
| b0075df9e735 | data / background_prefetch | 42 | 37.207647 | SELECT a.id, a.kind, a.arch_type, a.arch_module, a.fingerprint, a.root_id, a.src, a.dst, a.undirected, a.props, a.version, CASE WH |
| b0075df9e735 | data / foreground | 114 | 30.988878 | SELECT a.id, a.kind, a.arch_type, a.arch_module, a.fingerprint, a.root_id, a.src, a.dst, a.undirected, a.props, a.version, CASE WH |
| 79663c1d3b43 | control / foreground | 54 | 19.231130 | COMMIT |
| 9a36ea7adf29 | data / foreground | 12 | 16.909375 | SELECT n2.id, e2.id, n2.arch_type, n2.arch_module FROM unnest(CAST($1 AS uuid[])) WITH ORDINALITY AS f0(id, ord) LEFT JOIN anchors |
| 1f501894bd8c | data / foreground | 18 | 11.397653 | SELECT n1.id, e1.id, n1.arch_type, n1.arch_module FROM unnest(CAST($1 AS uuid[])) WITH ORDINALITY AS f0(id, ord) LEFT JOIN anchors |
| 98f36323c6bc | control / background_prefetch | 42 | 9.165859 | DISCARD ALL |
| 6dc81f61e5e5 | data / foreground | 15 | 8.328429 | SELECT n1.id, e1.id FROM unnest(CAST($1 AS uuid[])) WITH ORDINALITY AS f0(id, ord) LEFT JOIN anchors s1 ON s1.id = f0.id JOIN anch |
| f341dab97d76 | data / foreground | 12 | 8.204840 | SELECT n1.id, e1.id, n1.arch_type, n1.arch_module FROM unnest(CAST($1 AS uuid[])) WITH ORDINALITY AS f0(id, ord) LEFT JOIN anchors |

### legacy_ttg_thread

| Fingerprint prefix | Kind / role | Pooled calls | Pooled protocol ms | SQL excerpt |
|---|---|---:|---:|---|
| 9a54ec61abbb | data / foreground | 12 | 180.318134 | WITH RECURSIVE "_cte0" ("depth", "bfs_ord", "node_id", "arch_type", "parent_depth", "parent_bfs_ord", "parent_node_id", "step_node |
| 3384eed90e3d | data / foreground | 3 | 31.974853 | WITH RECURSIVE "_cte0" ("depth", "bfs_ord", "node_id", "arch_type", "parent_depth", "parent_bfs_ord", "parent_node_id", "step_node |
| b0075df9e735 | data / foreground | 105 | 26.876749 | SELECT a.id, a.kind, a.arch_type, a.arch_module, a.fingerprint, a.root_id, a.src, a.dst, a.undirected, a.props, a.version, CASE WH |
| 79663c1d3b43 | control / foreground | 54 | 20.620114 | COMMIT |
| 168587cef952 | data / foreground | 3 | 17.378655 | WITH RECURSIVE "_cte0" ("depth", "bfs_ord", "node_id", "arch_type", "parent_depth", "parent_bfs_ord", "parent_node_id", "step_node |
| 33d1c6d4f6d1 | data / foreground | 12 | 14.756099 | SELECT n2.id, e2.id FROM unnest(CAST($1 AS uuid[])) WITH ORDINALITY AS f0(id, ord) LEFT JOIN anchors s1 ON s1.id = f0.id JOIN anch |
| 280f96b2d26b | data / foreground | 3 | 14.400748 | WITH RECURSIVE "_cte0" ("depth", "bfs_ord", "node_id", "arch_type", "parent_depth", "parent_bfs_ord", "parent_node_id", "step_node |
| b0075df9e735 | data / background_prefetch | 21 | 14.275440 | SELECT a.id, a.kind, a.arch_type, a.arch_module, a.fingerprint, a.root_id, a.src, a.dst, a.undirected, a.props, a.version, CASE WH |

## Native model/checkpoint evidence

Every dependency_outcome is retained with event/scope identity. Totals use each scope's final cumulative summary. Submitted/promoted/unused_cached/unavailable are separate native categories. Empty explicit capture arrays are not interpreted as zero native checkpoint activity.

| Configuration | Repeat | Scope events / unique scopes | Plans / multihop | Native continuation snapshots | Decisions / probes / below3 samples |
|---|---:|---|---|---:|---|
| none | 0 | 0/0 | 0/0 | 0 | 0/0/0 |
| continuation_expected_benefit_process | 0 | 9/9 | 14/4 | 86 | 27/22/22 |
| continuation_expected_benefit_thread | 0 | 9/9 | 14/4 | 86 | 26/22/22 |
| continuation_always_process | 0 | 9/9 | 14/4 | 86 | 28/0/22 |
| continuation_always_thread | 0 | 9/9 | 14/4 | 86 | 28/0/22 |
| legacy_ttg_thread | 0 | 0/0 | 0/0 | 0 | 0/0/0 |
| continuation_always_thread | 1 | 9/9 | 14/4 | 86 | 28/0/22 |
| continuation_always_process | 1 | 9/9 | 14/4 | 86 | 28/0/22 |
| continuation_expected_benefit_thread | 1 | 9/9 | 14/4 | 86 | 26/22/22 |
| continuation_expected_benefit_process | 1 | 9/9 | 14/4 | 86 | 27/22/22 |
| none | 1 | 0/0 | 0/0 | 0 | 0/0/0 |
| legacy_ttg_thread | 1 | 0/0 | 0/0 | 0 | 0/0/0 |
| continuation_always_thread | 2 | 9/9 | 14/4 | 86 | 28/0/22 |
| legacy_ttg_thread | 2 | 0/0 | 0/0 | 0 | 0/0/0 |
| none | 2 | 0/0 | 0/0 | 0 | 0/0/0 |
| continuation_expected_benefit_process | 2 | 9/9 | 14/4 | 86 | 27/22/22 |
| continuation_expected_benefit_thread | 2 | 9/9 | 14/4 | 86 | 26/22/22 |
| continuation_always_process | 2 | 9/9 | 14/4 | 86 | 28/0/22 |
