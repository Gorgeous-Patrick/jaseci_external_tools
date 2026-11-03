"""Finite pure-visit frontiers composed across abilities, with SQL-internal origins.

Native FIFO activations are never deduplicated or reordered. Only identical path
fetches share cache. Expand complete pure-entry layers; stop the whole next layer
at an opaque entry so it cannot affect a predicted sibling. Exit abilities run
after the pending queue drains and are outside this entry-prefix certificate.
"""
import from uuid { UUID }
import jaclang.sql as q;
import from jaclang.runtime.ttg_sql { _BuildColumns, _select, _cmp, _union }
import from jaclang.runtime.ttg_fusion_sql { _native_path, _native_anchors }
import from jaclang.runtime.ttg_templates {
    sql_descriptor,
    bind_template,
    publish_paths
}


def compile_dag_regions(graph: any) -> dict {
    pure: dict = {};
    for (ability, entry_id) in graph.entries.items() {
        events = [
            e
            for e in graph.events
            if e.ability == ability
        ];
        types = [
            name
            for (name, handlers) in graph.handlers.items()
            if ability in handlers
        ];
        visits = [
            e
            for e in events
            if e.kind == 'visit'
        ];
        if len(types) == 1
            and types[0] != '*'
            and visits
            and all(e.kind in ('entry', 'exit', 'input', 'visit') for e in events)
            and all(
                e.origin == 'here'
                    and e.hop_chain
                    and all(
                        h[1] is not None and h[2] in (1, 2, 3) for h in e.hop_chain
                    ) for e in visits
            ) {
            pure[ability] = {'type': types[0], 'visits': visits};
        }
    }
    certificates: dict = {};
    for ability in pure {
        # Each parent is a static visit site, not a runtime origin parameter.
        layer: list = [(ability, -1, [])];
        rules: list = [];
        cyclic = False;
        while layer and len(rules) <= 64 {
            if any(name not in pure for (name, parent, history) in layer) {
                break;
            }
            if any(name in history for (name, parent, history) in layer) {
                cyclic = True;
                break;
            }
            following: list = [];
            for (name, parent, history) in layer {
                for event in pure[name]['visits'] {
                    slot = len(rules);
                    handlers = list(graph.dispatch.get(event.id, []));
                    target = handlers[0] if len(handlers) == 1 else '';
                    rules.append(
                        {
                            'slot': slot,
                            'parent': parent,
                            'ability': name,
                            'source_type': pure[name]['type'],
                            'event': event.id,
                            'hops': event.hop_chain,
                            'target_ability': target,
                            'dispatch_edge': [event.id, graph.entries[target]]
                                if target
                                else []
                        }
                    );
                    following.append((target, slot, history + [name]));
                }
            }
            layer = following;
        }
        if cyclic or not rules or len(rules) > 64 {
            continue;
        }
        certificate: dict = {
            'version': 1,
            'kind': 'finite_dag',
            'id': 'dag:' + str(graph.entries[ability]),
            'ability': ability,
            'entry': graph.entries[ability],
            'rules': rules,
            'boundary': 'Stop before the first non-pure entry layer; native exit and output code remains native',
            'checkpoint_proof': 'Origin and actor bound at entry; composed entries have only visits and no sibling-state reads or writes',
            'external_dependencies': [
                'origin identity',
                'exact runtime dispatch',
                'actor/ACL context'
            ],
            'templates': {}
        };
        for gated in (False, True) {
            certificate['templates']['gated' if gated else 'open'] = sql_descriptor(
                compile_dag_sql(rules, gated)
            );
        }
        certificates[str(graph.entries[ability])] = certificate;
    }
    return certificates;
}


def compile_dag_sql(rules: list, gated: bool) -> any {
    cols = _BuildColumns();
    actor = {
        'uuid': q.slot('actor_uuid', q.uuid_type()),
        'text': q.slot('actor_text', q.text_type())
    }
        if gated
        else None;
    schema = [
        q.field('origin_id', q.uuid_type()),
        q.field('target_id', q.nullable(q.uuid_type())),
        q.field('edge_id', q.nullable(q.uuid_type())),
        q.field('arch_type', q.nullable(q.text_type())),
        q.field('arch_module', q.nullable(q.text_type())),
        q.field('ord', q.nullable(q.int64_type())),
        q.field('arity', q.nullable(q.int64_type()))
    ];
    relations: list = [];
    bodies: list = [];
    for rule in rules {
        parent = rule['parent'];
        if parent < 0 {
            origins = _select(None, [('origin_id', q.slot('origin', q.uuid_type()))]);
        } else {
            previous = relations[parent];
            origins = _select(
                previous,
                [
                    (
                        'origin_id',
                        q.coalesce(
                            cols.col(previous, 'target_id'),
                            cols.col(previous, 'origin_id')
                        )
                    )
                ],
                predicate=q.not_(q.is_null(cols.col(previous, 'target_id'))),
                distinct=True
            );
        }
        source = origins.as_source();
        matches = q.optional_source(
            _native_path(cols, cols.col(source, 'origin_id'), rule['hops'], actor, True)
        );
        body = _select(
            source,
            [('origin_id', cols.col(source, 'origin_id'))]
                + cols.pick(
                    matches,
                    ['target_id', 'edge_id', 'arch_type', 'arch_module', 'ord', 'arity']
                ),
            joins=[q.left_join(matches, q.boolean(True))]
        );
        relation = q.cte_ref(schema);
        q.define_cte(relation, body);
        relations.append(relation);
        bodies.append(
            _select(
                relation,
                [('slot', q.int64(rule['slot']))]
                    + cols.pick(relation, [f.name for f in schema])
            )
        );
    }
    paths = q.ordered(
        _union(bodies),
        [
            q.asc(q.output(q.field('slot', q.int64_type()))),
            q.asc(q.output(q.field('origin_id', q.uuid_type()))),
            q.asc(q.output(q.field('ord', q.nullable(q.int64_type()))))
        ],
        limit=q.slot('row_limit', q.int64_type())
    );
    if not gated {
        return q.compile_sql(paths);
    }
    # The same statement proves all persisted subtype access implementations.
    # Limit path rows independently: catalog rows must never be truncated.
    catalog = _native_anchors();
    proof = _select(
        catalog,
        [
            ('slot', q.int64(-1)),
            ('origin_id', q.slot('origin', q.uuid_type())),
            ('target_id', q.null(q.uuid_type())),
            ('edge_id', q.null(q.uuid_type())),
            (
                'arch_type',
                q.cast(cols.col(catalog, 'arch_type'), q.nullable(q.text_type()))
            ),
            ('arch_module', cols.col(catalog, 'arch_module')),
            ('ord', q.null(q.int64_type())),
            ('arity', q.null(q.int64_type()))
        ],
        predicate=_cmp(cols.col(catalog, 'kind'), q.text('NodeAnchor')),
        distinct=True
    );
    return q.compile_sql(
        q.ordered(
            _union([paths, proof]),
            [
                q.asc(q.output(q.field('slot', q.int64_type()))),
                q.asc(q.output(q.field('origin_id', q.uuid_type()))),
                q.asc(q.output(q.field('ord', q.nullable(q.int64_type()))))
            ]
        )
    );
}


def resolve_dag_region(
    mem: any,
    graph: any,
    wlk: any,
    scope: any,
    point: int,
    current: dict,
    pending: list,
    user_root: any,
    max_rows: int,
    metrics: dict,
    cache_token: str,
    certificate: dict
) -> any {
    import from jaclang.runtime.ttg_continuation { continuation_type }
    import from jaclang.runtime.ttg_dependencies {
        _trace_entry_handlers,
        _trace_node_effects,
        _trace_safe_storage,
        TraceEffects
    }
    import from jaclang.runtime.ttg_frontier { template_type_matches }
    import from jaclang.runtime.archetype { NodeArchetype }
    import from jaclang.runtime.graph_query { GraphQuery, QHop }
    import from jaclang.runtime.graph_walk { access_gated }
    import from jaclang.data.query_planner { _acl_pushdown_root }
    import from jaclang.runtime.ttg_regions { region_coverage_key }
    def decline(reason: str) -> any {
        metrics['region_fallbacks'] = metrics.get('region_fallbacks', 0) + 1;
        metrics['region_fallback_reason'] = reason;
        counts = metrics.setdefault('region_fallback_reasons', {});
        counts[reason] = counts.get(reason, 0) + 1;
        return None;
    }
    rules = certificate['rules'];
    queries: list = [];
    sources: list = [];
    for rule in rules {
        source = continuation_type(wlk, rule['source_type']);
        if source is None
            or not template_type_matches(source, rule['source_type'])
            or not issubclass(source, NodeArchetype)
            or not _trace_safe_storage(source)
            or source.__getattribute__ is not NodeArchetype.__getattribute__ {
            return decline('DAG source type or storage is unresolved');
        }
        effects = TraceEffects();
        handlers = _trace_entry_handlers(graph, source, effects);
        _trace_node_effects(graph, source, effects);
        if effects.unknown or handlers != [rule['ability']] {
            return decline('DAG entry dispatch/effects differ from certificate');
        }
        sources.append(source);
        hops: list = [];
        for (edge, node, direction) in rule['hops'] {
            et = continuation_type(wlk, str(edge)) if edge is not None else None;
            nt = continuation_type(wlk, str(node));
            if nt is None
                or not template_type_matches(nt, node)
                or not template_type_matches(et, edge) {
                return decline('DAG path type is unresolved or aliased');
            }
            hops.append(QHop(dir=int(direction), `edge=et, nd=nt));
        }
        queries.append(GraphQuery([], hops=hops).`visit());
    }
    if current['node_type'] is not sources[0] {
        return decline('DAG current dispatch is not exact');
    }
    with mem._lock {
        mem.read_barrier();
        if 'catalog' in graph.sql_templates {
            mem.query_cache_put(
                ('ttg_compiled_catalog_v1', ), graph.sql_templates['catalog']
            );
        }
        import from jaclang.data.ttg_acl {
            standard_catalog_access,
            standard_node_access,
            catalog_node_type
        }
        import from jaclang.data.store { TxnIsolation }
        if access_gated()
            and mem.store.txn_isolation()
                not in (TxnIsolation.SERIALIZABLE, TxnIsolation.SNAPSHOT_READ_ONLY) {
            return decline('DAG ACL proof requires a stable transaction snapshot');
        }
        coverage = region_coverage_key(
            graph,
            scope,
            wlk,
            graph.events[point].ability,
            current['id'],
            user_root,
            cache_token
        );
        if mem.query_cache_get(coverage) is not None
            and (
                not access_gated()
                or (
                    mem.query_cache_get(('ttg_standard_acl_catalog', 1)) is not None
                    and standard_catalog_access(mem)
                )
            ) {
            metrics['region_reuses'] = metrics.get('region_reuses', 0) + 1;
            return {'paths': [], 'payload': [], 'reused': True, 'kind': 'finite_dag'};
        }
        if pending or scope.ignores {
            return decline('DAG has unproved pending/ignored entries');
        }
        actor: any = None;
        for (index, query) in enumerate(queries) {
            visibility = _acl_pushdown_root(query, len(query.hops), mem);
            if access_gated() and visibility is None {
                return decline('DAG ACL pushdown is unproved');
            }
            if index and visibility != actor {
                return decline('DAG actor differs across paths');
            }
            actor = visibility;
        }
        values: dict = {'origin': UUID(str(current['id'])), 'row_limit': max_rows + 1};
        if actor is not None {
            values.update({'actor_uuid': UUID(actor), 'actor_text': actor});
        }
        compiled = bind_template(
            certificate['templates']['gated' if actor is not None else 'open'], values
        );
        rows = mem.store.rows(compiled.sql, compiled.params);
        metrics['region_queries'] = metrics.get('region_queries', 0) + 1;
        metrics['queries'] += 1;
        catalog_types: list = [];
        if actor is not None {
            proof_rows = [
                row
                for row in rows
                if int(row[0]) == -1
            ];
            if not proof_rows {
                return decline('DAG persisted ACL catalog is missing');
            }
            for row in proof_rows {
                resolved = catalog_node_type(row[4], row[5]);
                if UUID(str(row[1])) != UUID(str(current['id']))
                    or any(row[i] is not None for i in (2, 3, 6, 7))
                    or resolved is None
                    or not standard_node_access(resolved) {
                    return decline('DAG persisted ACL catalog is unproved');
                }
                catalog_types.append((row[4], row[5], resolved));
            }
            rows = [
                row
                for row in rows
                if int(row[0]) != -1
            ];
        }
        if len(rows) > max_rows {
            return decline('DAG row budget exceeded; no partial publication');
        }
        groups: dict = {};
        arities: dict = {};
        for row in rows {
            slot = int(row[0]);
            uid = UUID(str(row[1]));
            if slot < 0 or slot >= len(rules) {
                return decline('DAG unknown visit slot');
            }
            key = (slot, uid);
            group = groups.setdefault(key, []);
            if row[2] is None {
                if key in arities or any(v is not None for v in row[3:]) {
                    return decline('DAG invalid empty marker');
                }
                arities[key] = 0;
            } else {
                count = int(row[7]);
                if count <= 0
                    or int(row[6]) != len(group) + 1
                    or arities.get(key, count) != count {
                    return decline('DAG path order/cardinality mismatch');
                }
                arities[key] = count;
                group.append((UUID(str(row[2])), UUID(str(row[3])), row[4], row[5]));
            }
        }
        staged: list = [];
        payload: list = [];
        paths: list = [];
        covered: set = set();
        for (slot, rule) in enumerate(rules) {
            parent = rule['parent'];
            expected = {UUID(str(current['id']))}
                if parent < 0
                else {
                    pair[0]
                    for ((key_slot, uid), pairs) in groups.items()
                    if key_slot == parent for pair in pairs
                };
            actual = {
                uid
                for (key_slot, uid) in groups
                if key_slot == slot
            };
            if actual != expected {
                return decline('DAG missing or foreign origin closure');
            }
            if parent >= 0 {
                for ((key_slot, uid), pairs) in groups.items() {
                    if key_slot == parent
                        and any(
                            p[2] != sources[slot].__name__
                                or p[3] != sources[slot].__module__ for p in pairs
                        ) {
                        return decline('DAG future dispatch is not exact');
                    }
                }
            }
            for uid in expected {
                pairs = groups[(slot, uid)];
                if len(pairs) != arities.get((slot, uid), -1) {
                    return decline('DAG truncated path');
                }
                native = graph.sql_templates['native'][str(rule['event'])][
                    'gated' if actor is not None else 'open'
                ];
                staged.append((queries[slot], uid, pairs, native));
                payload.extend(pairs);
                paths.append(
                    {
                        'event': rule['event'],
                        'origin': str(uid),
                        'ids': [str(p[0]) for p in pairs]
                    }
                );
                covered.add((uid, rule['ability']));
            }
        }
        if not publish_paths(mem, staged) {
            return decline('DAG atomic native publication failed');
        }
        if actor is not None {
            mem.query_cache_put(
                ('ttg_standard_acl_catalog', 1),
                {'approved': True, 'types': catalog_types}
            );
        }
        for (uid, ability) in covered {
            mem.query_cache_put(
                region_coverage_key(
                    graph, scope, wlk, ability, uid, user_root, cache_token
                ),
                True
            );
        }
        metrics['region_cache_paths'] = metrics.get('region_cache_paths', 0)
            + len(staged);
        metrics['cache_paths'] += len(staged);
        metrics['cache_empty_paths'] += sum(
            1
            for p in staged
            if not p[2]
        );
        metrics['region_origins'] = metrics.get('region_origins', 0) + len(covered);
        metrics['regions'].append(
            {
                'kind': 'static_interability_dag',
                'certificate_id': certificate['id'],
                'compiled': True,
                'paths': paths,
                'dispatch_edges': [r['dispatch_edge'] for r in rules],
                'checkpoint': point
            }
        );
        return {
            'paths': paths,
            'payload': payload,
            'reused': False,
            'kind': 'finite_dag'
        };
    }
}
