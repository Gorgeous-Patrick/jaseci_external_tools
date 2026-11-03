"""Compile-time, single-successor interability regions; no FIFO SQL interpreter."""
import ast as pa;
import from jaclang.runtime.ttg_templates {
    sql_descriptor,
    bind_template,
    publish_paths
}
import from jaclang.runtime.ttg_sql { _BuildColumns, _select, _all, _cmp, _union }
import from jaclang.runtime.ttg_fusion_sql { _native_anchors, _native_path }
import jaclang.sql as q;


def _boolean_guard(expression: str) -> any {
    tree = pa.parse(expression, mode='eval').body;
    def lower(node_source: any) -> any {
        if isinstance(node_source, pa.Attribute)
            and isinstance(node_source.value, pa.Name)
            and node_source.value.id == 'here' {
            return {'field': node_source.attr};
        }
        if isinstance(node_source, pa.Constant) and type(node_source.value) is bool {
            return {'constant': node_source.value};
        }
        if isinstance(node_source, pa.UnaryOp) and isinstance(node_source.op, pa.Not) {
            return {'not': lower(node_source.operand)};
        }
        if isinstance(node_source, pa.BoolOp)
            and isinstance(node_source.op, (pa.And, pa.Or)) {
            return {
                'and' if isinstance(node_source.op, pa.And) else 'or': [
                    lower(n) for n in node_source.values
                ]
            };
        }
        if isinstance(node_source, pa.Compare)
            and len(node_source.ops) == 1
            and isinstance(node_source.ops[0], (pa.Eq, pa.NotEq)) {
            return {
                'equal' if isinstance(node_source.ops[0], pa.Eq) else 'different': [
                    lower(node_source.left),
                    lower(node_source.comparators[0])
                ]
            };
        }
        raise ValueError(
            'Region predicate is not a node_source-local boolean expression'
        );
    }
    return lower(tree);
}


def _guard_fields(predicate: dict) -> list[str] {
    if 'field' in predicate {
        return [predicate['field']];
    }
    result: list = [];
    for value in predicate.values() {
        if type(value) is dict {
            result.extend(_guard_fields(value));
        } elif type(value) is list {
            for child in value {
                result.extend(_guard_fields(child));
            }
        }
    }
    return sorted(set(result));
}


def _integer_output(expression: str) -> bool {
    def check(node_source: any) -> bool {
        if isinstance(node_source, pa.Constant) {
            return type(node_source.value) is int;
        }
        if isinstance(node_source, pa.Attribute)
            and isinstance(node_source.value, pa.Name) {
            return node_source.value.id == 'self';
        }
        if isinstance(node_source, pa.BinOp)
            and isinstance(node_source.op, (pa.Add, pa.Sub, pa.Mult)) {
            return check(node_source.left) and check(node_source.right);
        }
        if isinstance(node_source, pa.UnaryOp)
            and isinstance(node_source.op, (pa.USub, pa.UAdd)) {
            return check(node_source.operand);
        }
        return False;
    }
    return check(pa.parse(expression, mode='eval').body);
}


def summarize_abilities(graph: any) -> dict {
    # Effect and guarded-visit summaries are computed once by the compiler.
    import from jaclang.runtime.ttg_access_slice { access_slice }
    sliced: dict = access_slice(
        [
            {
                'id': e.id,
                'kind': e.kind,
                'ability': e.ability,
                'reads': list(e.reads),
                'writes': e.writes,
                'effect': e.effect
            } for e in graph.events
        ],
        [{'source': e.source, 'target': e.target, 'kind': e.kind} for e in graph.edges]
    );
    ignored = set(sliced['output_only']);
    access_reads: set = set(sliced['shared_access_reads']);
    integer_fields: set = set();
    for e in graph.events {
        if e.kind in ('assign', 'scalar_update', 'append') {
            expr = pa.parse(e.expression, mode='eval').body;
            if isinstance(expr, (pa.BinOp, pa.UnaryOp)) {
                integer_fields.update(
                    key
                    for key in e.reads
                    if key.startswith('self.')
                );
            }
            if e.kind == 'scalar_update' {
                integer_fields.add(e.writes);
            }
        }
    }
    summaries: dict = {};
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
        rejected: list = [];
        outputs: list = [];
        for event in events {
            if event.kind == 'barrier' and event.id in ignored and event.effect {
                outputs.append(
                    {
                        'event': event.id,
                        'kind': event.effect['contract'],
                        'writes': event.writes,
                        'reads': list(event.reads),
                        'expression': event.expression,
                        'effect': event.effect
                    }
                );
            } elif event.kind in ('barrier', 'cancel') {
                rejected.append(
                    {
                        'event': event.id,
                        'reason': 'Unknown effect, loop, helper call, write or cancellation'
                    }
                );
            } elif event.kind in ('assign', 'scalar_update', 'append') {
                if event.id not in ignored {
                    rejected.append(
                        {
                            'event': event.id,
                            'reason': 'Shared access state or non-output assignment'
                        }
                    );
                } else {
                    outputs.append(
                        {
                            'event': event.id,
                            'kind': event.kind,
                            'integer': event.kind == 'scalar_update'
                                or event.writes in integer_fields
                                or isinstance(
                                    pa.parse(event.expression, mode='eval').body,
                                    (pa.BinOp, pa.UnaryOp)
                                ),
                            'writes': event.writes,
                            'reads': list(event.reads),
                            'expression': event.expression
                        }
                    );
                    expr = pa.parse(event.expression, mode='eval').body;
                    if event.kind == 'scalar_update'
                        or event.writes in integer_fields
                        or not isinstance(expr, (pa.Constant, pa.Name, pa.Attribute)) {
                        if not _integer_output(event.expression) {
                            rejected.append(
                                {
                                    'event': event.id,
                                    'reason': 'Output arithmetic requires a total integer constant/self expression; division and node operands are unsupported'
                                }
                            );
                        }
                    }
                }
            } elif event.kind == 'output' {
                outputs.append(
                    {
                        'event': event.id,
                        'kind': event.kind,
                        'writes': '',
                        'reads': list(event.reads),
                        'expression': event.expression
                    }
                );
            }
        }
        if len(types) != 1 or types[0] == '*' or len(visits) > 1 {
            rejected.append(
                {
                    'event': entry_id,
                    'reason': 'Region requires one exact dispatch type and at most one visit site'
                }
            );
        }
        guard: dict = {'constant': True};
        if visits {
            visit_event = visits[0];
            if visit_event.origin != 'here'
                or len(visit_event.hop_chain) != 1
                or visit_event.hop_chain[0][0] is None
                or visit_event.hop_chain[0][1] is None {
                rejected.append(
                    {
                        'event': visit_event.id,
                        'reason': 'Region requires a single explicitly typed hop'
                    }
                );
            }
            guards: list = [];
            for edge_type in graph.edges {
                if edge_type.kind == 'control' and edge_type.target == visit_event.id {
                    source = graph.events[edge_type.source];
                    try {
                        term = _boolean_guard(source.expression);
                        guards.append(
                            term if edge_type.label == 'true' else {'not': term}
                        );
                    } except (ValueError, SyntaxError) {
                        rejected.append(
                            {
                                'event': source.id,
                                'reason': 'Access predicate is not node_source-local boolean'
                            }
                        );
                    }
                }
            }
            guard = {'and': guards} if guards else guard;
        }
        # Every branch must be representable, even if it only guards output.
        for event in events {
            if event.kind == 'branch' and event.id in ignored {
                # Dependency independence is not permission to invoke a custom
                # truthiness/comparison hook. The runtime checks exact scalars.
                expression = pa.parse(event.expression, mode='eval').body;
                if any(
                    isinstance(
                        n,
                        (pa.Call, pa.Subscript, pa.BinOp, pa.Lt, pa.LtE, pa.Gt, pa.GtE)
                    ) for n in pa.walk(expression)
                )
                    or any(
                        '::' in key and '::here.' not in key for key in event.reads
                    ) {
                    rejected.append(
                        {
                            'event': event.id,
                            'reason': 'Output condition has unproved effects'
                        }
                    );
                } else {
                    outputs.append(
                        {
                            'event': event.id,
                            'kind': 'output_condition',
                            'writes': '',
                            'reads': list(event.reads),
                            'expression': event.expression
                        }
                    );
                }
            } elif event.kind == 'branch' {
                try {
                    _boolean_guard(event.expression);
                } except (ValueError, SyntaxError) {
                    rejected.append(
                        {'event': event.id, 'reason': 'Shared or unsupported branch'}
                    );
                }
            }
        }
        summaries[ability] = {
            'ability': ability,
            'access_slice': sliced,
            'entry': entry_id,
            'source_type': types[0] if len(types) == 1 else '',
            'eligible': not rejected,
            'rejections': rejected,
            'outputs': outputs,
            'frontier_independent_prefix': bool(visits)
                and all(e.kind in ('entry', 'exit', 'input', 'visit') for e in events),
            'shared_access_reads': sorted(access_reads),
            'visit': visits[0].id if visits else -1,
            'guard': guard,
            'guard_fields': sorted(
                set(_guard_fields(guard))
                    | {
                        read.split('::here.', 1)[1]
                        for output in outputs
                        if output['kind'] == 'output_condition'
                        for read in output['reads']
                        if '::here.' in read
                    }
            ),
            'dispatch': list(graph.dispatch.get(visits[0].id, [])) if visits else [],
            'external_dependencies': [
                'origin identity',
                'exact runtime dispatch',
                'actor/ACL context'
            ],
            'sql_internal_dependencies': [
                'here.' + name for name in _guard_fields(guard)
            ],
            'checkpoint_proof': 'Entry follows origin/context binding; no shared guard input or mutable external threshold is admitted'
        };
    }
    return summaries;
}


def compile_interability_regions(graph: any) -> dict {
    summaries = summarize_abilities(graph);
    regions: dict = {};
    for (ability, summary) in summaries.items() {
        if not summary['eligible'] or summary['visit'] < 0 {
            continue;
        }
        rules: list = [];
        seen: dict = {};
        active = ability;
        while active not in seen {
            item = summaries[active];
            if not item['eligible'] or item['visit'] < 0 {
                break;
            }
            seen[active] = len(rules);
            event = graph.events[item['visit']];
            handlers = item['dispatch'];
            target = handlers[0] if len(handlers) == 1 else '';
            rules.append(
                {
                    'ability': active,
                    'entry': item['entry'],
                    'event': event.id,
                    'source_type': item['source_type'],
                    'hops': event.hop_chain,
                    'target_type': event.hop_chain[0][1],
                    'guard': item['guard'],
                    'guard_fields': item['guard_fields'],
                    'required_fields': sorted(
                        set(item['guard_fields'])
                            | {
                                key.split('::here.', 1)[1]
                                for output in item['outputs']
                                for key in output['reads']
                                if '::here.' in key
                            }
                    ),
                    'target_ability': target,
                    'dispatch_edge': [event.id, graph.entries[target]]
                        if target
                        else [],
                    'next_phase': -1,
                    'phase': len(rules)
                }
            );
            if not target
                or not summaries[target]['eligible']
                or summaries[target]['visit'] < 0 {
                break;
            }
            active = target;
        }
        for rule in rules {
            rule['next_phase'] = seen.get(rule['target_ability'], -1);
        }
        if any(r['next_phase'] >= 0 and r['next_phase'] <= r['phase'] for r in rules)
            and len(rules) != 1 {
            continue;
        }
        certificate: dict = {
            'version': 1,
            'id': 'entry:' + str(summary['entry']),
            'entry': summary['entry'],
            'ability': ability,
            'rules': rules,
            'summaries': list(seen),
            'boundary': 'Fetch target but do not expand an unsupported or terminal target ability',
            'external_dependencies': summary['external_dependencies'],
            'checkpoint_proof': summary['checkpoint_proof'],
            'cardinality_proof': 'Runtime SQL certificate requires every enabled immediate path arity <= 1',
            'acyclicity_proof': 'SQL identity history rejects a repeated target before cache publication',
            'templates': {}
        };
        for gated in (False, True) {
            certificate['templates']['gated' if gated else 'open'] = sql_descriptor(
                compile_region_sql(rules, gated)
            );
        }
        regions[str(summary['entry'])] = certificate;
    }
    import from jaclang.runtime.ttg_region_dag { compile_dag_regions }
    for (entry_id, certificate) in compile_dag_regions(graph).items() {
        if entry_id not in regions
            or len(certificate['rules']) > len(regions[entry_id]['rules']) {
            regions[entry_id] = certificate;
        }
    }
    return {
        'version': 1,
        'summaries': summaries,
        'regions': regions,
        'helper_policy': 'Unresolved helpers are explicit barrier effects; no opaque call is assumed pure'
    };
}


def _sql_guard(predicate: dict, props: any) -> any {
    if 'constant' in predicate {
        return q.boolean(predicate['constant']);
    }
    if 'field' in predicate {
        return _cmp(q.json_text(props, q.text(predicate['field'])), q.text('true'));
    }
    if 'not' in predicate {
        return q.not_nullable(_sql_guard(predicate['not'], props));
    }
    if 'and' in predicate {
        return _all([_sql_guard(p, props) for p in predicate['and']]);
    }
    if 'or' in predicate {
        return q.or_nullable([_sql_guard(p, props) for p in predicate['or']]);
    }
    terms: list[dict] = predicate['equal']
        if 'equal' in predicate
        else predicate['different'];
    return _cmp(
        _sql_guard(terms[0], props),
        _sql_guard(terms[1], props),
        '=' if 'equal' in predicate else '<>'
    );
}


def _region_rows(cols: any, walk: any, rules: list, actor: any) -> any {
    bodies: list = [];
    for rule in rules {
        phase = rule['phase'];
        node_source = _native_anchors();
        props = q.json_get(cols.col(node_source, 'props'), q.text('archetype'));
        guard_value = _sql_guard(rule['guard'], props);
        enabled = q.coalesce(guard_value, q.boolean(False))
            if guard_value.ast.dtype.nullable
            else guard_value;
        valid = _all(
            [
                _cmp(q.json_kind(q.json_get(props, q.text(name))), q.text('boolean'))
                for name in rule['guard_fields']
            ]
        );
        matches = _native_path(
            cols, cols.col(walk, 'origin_id'), rule['hops'], actor, True
        );
        filtered = _select(
            matches,
            cols.pick(
                matches,
                ['target_id', 'edge_id', 'arch_type', 'arch_module', 'ord', 'arity']
            ),
            predicate=enabled
        ).as_source(
            lateral=True
        );
        optional = q.optional_source(filtered);
        target = cols.col(optional, 'target_id');
        cycle = q.coalesce(q.any_eq(target, cols.col(walk, 'seen')), q.boolean(False));
        dispatch_valid = q.or_nullable(
            [
                q.is_null(target),
                _all(
                    [
                        _cmp(
                            cols.col(optional, 'arch_type'), q.text(rule['target_type'])
                        ),
                        _cmp(
                            cols.col(optional, 'arch_module'),
                            q.slot('target_module_' + str(phase), q.text_type())
                        )
                    ]
                )
            ]
        );
        bodies.append(
            _select(
                node_source,
                [
                    ('slot', q.int64(phase)),
                    ('depth', cols.col(walk, 'depth')),
                    ('origin_id', cols.col(walk, 'origin_id'))
                ]
                    + cols.pick(
                        optional,
                        [
                            'target_id',
                            'edge_id',
                            'arch_type',
                            'arch_module',
                            'ord',
                            'arity'
                        ]
                    )
                    + [
                        (
                            'valid',
                            q.coalesce(_all([valid, dispatch_valid]), q.boolean(False))
                        ),
                        ('enabled', enabled),
                        ('cycle', cycle),
                        ('next_phase', q.int64(rule['next_phase']))
                    ],
                joins=[q.left_join(optional, q.boolean(True))],
                predicate=_all(
                    [
                        _cmp(cols.col(walk, 'phase'), q.int64(phase)),
                        _cmp(cols.col(node_source, 'id'), cols.col(walk, 'origin_id')),
                        _cmp(cols.col(node_source, 'kind'), q.text('NodeAnchor')),
                        _cmp(
                            cols.col(node_source, 'arch_type'),
                            q.text(rule['source_type'])
                        ),
                        _cmp(
                            cols.col(node_source, 'arch_module'),
                            q.slot('source_module_' + str(phase), q.text_type())
                        )
                    ]
                )
            )
        );
    }
    return _union(bodies).as_source(lateral=True);
}


def compile_region_sql(rules: list, gated: bool) -> any {
    cols = _BuildColumns();
    actor = {
        'uuid': q.slot('actor_uuid', q.uuid_type()),
        'text': q.slot('actor_text', q.text_type())
    }
        if gated
        else None;
    schema = [
        q.field('origin_id', q.uuid_type()),
        q.field('phase', q.int64_type()),
        q.field('depth', q.int64_type()),
        q.field('seen', q.array_type(q.uuid_type()))
    ];
    origin = q.slot('origin', q.uuid_type());
    anchor = _select(
        None,
        [
            ('origin_id', origin),
            ('phase', q.int64(0)),
            ('depth', q.int64(0)),
            ('seen', q.array(q.uuid_type(), [origin]))
        ]
    );
    recursive = len(rules) == 1 and rules[0]['next_phase'] == 0;
    walk = q.cte_ref(schema);
    bodies: list = [];
    for (phase, rule) in enumerate(rules) {
        emitted = _region_rows(cols, walk, [rule], actor);
        body = _select(
            walk,
            cols.pick(
                emitted,
                [
                    'slot',
                    'depth',
                    'origin_id',
                    'target_id',
                    'edge_id',
                    'arch_type',
                    'arch_module',
                    'ord',
                    'arity',
                    'valid',
                    'enabled',
                    'cycle',
                    'next_phase'
                ]
            ),
            joins=[q.cross_join(emitted)]
        );
        bodies.append(body);
        if recursive or phase + 1 < len(rules) {
            rows = _region_rows(cols, walk, [rule], actor);
            target = q.coalesce(
                cols.col(rows, 'target_id'), cols.col(walk, 'origin_id')
            );
            step = _select(
                walk,
                [
                    ('origin_id', target),
                    ('phase', cols.col(rows, 'next_phase')),
                    ('depth', q.add(cols.col(walk, 'depth'), q.int64(1))),
                    ('seen', q.array_append(cols.col(walk, 'seen'), target))
                ],
                joins=[q.cross_join(rows)],
                predicate=_all(
                    [
                        cols.col(rows, 'valid'),
                        cols.col(rows, 'enabled'),
                        q.not_(cols.col(rows, 'cycle')),
                        _cmp(cols.col(rows, 'arity'), q.int64(1)),
                        _cmp(cols.col(rows, 'next_phase'), q.int64(0), '>='),
                        _cmp(
                            cols.col(walk, 'depth'),
                            q.slot('max_depth', q.int64_type()),
                            '<'
                        )
                    ]
                )
            );
            if recursive {
                q.define_cte(walk, q.union_all(anchor, step), recursive=True);
            } else {
                q.define_cte(walk, anchor);
                walk = q.cte_ref(schema);
                anchor = step;
            }
        } else {
            q.define_cte(walk, anchor);
        }
    }
    return q.compile_sql(
        q.ordered(
            _union(bodies),
            [
                q.asc(q.output(q.field('depth', q.int64_type()))),
                q.asc(q.output(q.field('ord', q.nullable(q.int64_type()))))
            ],
            limit=q.slot('row_limit', q.int64_type())
        )
    );
}


def region_coverage_key(
    graph: any,
    scope: any,
    wlk: any,
    ability: str,
    origin: any,
    user_root: any,
    cache_token: str
) -> tuple {
    import from jaclang.runtime.graph_walk { access_gated }
    actor = str(user_root.id) if access_gated() and user_root is not None else None;
    return (
        'ttg_interability_coverage_v1',
        cache_token,
        id(graph),
        id(scope),
        id(wlk),
        ability,
        str(origin),
        actor
    );
}


def resolve_interability_region(
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
    cache_token: str = ''
) -> any {
    import from uuid { UUID }
    import from jaclang.runtime.ttg_continuation {
        continuation_type,
        _plain_scalar_field,
        known_node_fields
    }
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
    bundle = graph.interability_regions;
    certificate = bundle.get('regions', {}).get(str(point));
    if certificate is None {
        return None;
    }
    if certificate.get('kind') == 'output_tree' {
        import from jaclang.runtime.ttg_output_tree { resolve_output_tree }
        return resolve_output_tree(
            mem,
            graph,
            wlk,
            scope,
            point,
            current,
            pending,
            user_root,
            max_rows,
            metrics,
            cache_token,
            certificate
        );
    }
    if certificate.get('kind') == 'finite_dag' {
        import from jaclang.runtime.ttg_region_dag { resolve_dag_region }
        return resolve_dag_region(
            mem,
            graph,
            wlk,
            scope,
            point,
            current,
            pending,
            user_root,
            max_rows,
            metrics,
            cache_token,
            certificate
        );
    }
    def decline(reason: str) -> any {
        metrics['region_fallbacks'] = metrics.get('region_fallbacks', 0) + 1;
        metrics['region_fallback_reason'] = reason;
        counts = metrics.setdefault('region_fallback_reasons', {});
        counts[reason] = counts.get(reason, 0) + 1;
        return None;
    }
    if pending {
        return decline('Static region has pending queue interference');
    }
    if scope.ignores {
        return decline('Static region cannot expand ignored nodes');
    }
    rules = certificate['rules'];
    import from jaclang.runtime.ttg_dependencies { _trace_field_effects }
    field_effects = TraceEffects();
    _trace_field_effects(
        graph,
        {key for e in graph.events for key in e.reads}
            | {
                e.writes
                for e in graph.events
                if e.writes
            },
        field_effects
    );
    if field_effects.unknown {
        return decline('Walker field descriptors are unresolved');
    }
    queries: list = [];
    values: dict = {'origin': UUID(str(current['id'])), 'row_limit': max_rows + 1};
    if any(rule['next_phase'] >= 0 for rule in rules) {
        values['max_depth'] = max_rows;
    }
    actor: any = None;
    for (phase, rule) in enumerate(rules) {
        source = continuation_type(wlk, rule['source_type']);
        target = continuation_type(wlk, rule['target_type']);
        edge_type = continuation_type(wlk, rule['hops'][0][0]);
        if not template_type_matches(source, rule['source_type'])
            or not template_type_matches(target, rule['target_type'])
            or not template_type_matches(edge_type, rule['hops'][0][0]) {
            return decline('Static region type token is unresolved or aliased');
        }
        if source is None or target is None or edge_type is None {
            return decline('Unresolved static region type');
        }
        for node_source in (source, target) {
            if not issubclass(node_source, NodeArchetype)
                or not _trace_safe_storage(node_source)
                or node_source.__getattribute__ is not NodeArchetype.__getattribute__ {
                return decline('Custom node_source storage or attribute access');
            }
        }
        effects = TraceEffects();
        handlers = _trace_entry_handlers(graph, source, effects);
        _trace_node_effects(graph, source, effects);
        if effects.unknown or handlers != [rule['ability']] {
            return decline('Static source dispatch differs from compiled ability');
        }
        for callback in getattr(type(wlk), '_jac_exit_funcs_', []) {
            if callback.trigger is None or issubclass(source, callback.trigger) {
                return decline(
                    'Walker exit effects are outside the static region kernel'
                );
            }
        }
        for callback in getattr(source, '_jac_exit_funcs_', []) {
            if callback.trigger is None or issubclass(type(wlk), callback.trigger) {
                return decline(
                    'Node exit effects are outside the static region kernel'
                );
            }
        }
        for field in rule['guard_fields'] {
            if not _plain_scalar_field(source, field, (bool, 'bool')) {
                return decline(
                    'Region predicate is not an ordinary declared bool field'
                );
            }
        }
        for output in bundle['summaries'][rule['ability']]['outputs'] {
            if output['kind'] == 'node_identity' {
                descriptor = next(
                    (
                        vars(owner)['__jac__']
                        for owner in source.__mro__
                        if '__jac__' in vars(owner)
                    ),
                    None
                );
                if descriptor is not vars(NodeArchetype)['__jac__'] {
                    return decline(
                        'Identity anchor descriptor is not the framework builtin'
                    );
                }
                import sys;
                namespace = vars(sys.modules[type(wlk).__module__]);
                import from jaclang.runtime.runtime { JacPersistence }
                if namespace.get('jid') is not JacPersistence.object_ref
                    or any(e.writes.endswith('::jid') for e in graph.events) {
                    return decline('Identity helper binding is shadowed');
                }
            }
            if output['kind'] == 'identity_map_write'
                and not output['effect'].get('fresh', False) {
                return decline(
                    'Output map ownership is unproved; a fresh dominating allocation is required'
                );
            }
            if output['kind'] == 'output_condition'
                and any(
                    type(vars(wlk).get(key[5:]))
                        not in (bool, int, float, str, type(None))
                    for key in output['reads']
                    if key.startswith('self.')
                ) {
                return decline('Output condition requires exact scalar state');
            }
            if output.get('integer', False) {
                if not all(
                    type(vars(wlk).get(key[5:])) is int
                    for key in output['reads']
                    if key.startswith('self.')
                ) {
                    return decline(
                        'Integer output receiver/operand has an observed wrong type'
                    );
                }
            }
            if output['kind'] == 'append'
                and type(vars(wlk).get(output['writes'][5:])) is not list {
                return decline('Output append receiver is not an exact list');
            }
            for read in output['reads'] {
                if '::here.' in read {
                    field = read.split('::here.', 1)[1];
                    if not _plain_scalar_field(
                        source,
                        field,
                        (bool, int, float, str, 'bool', 'int', 'float', 'str')
                    ) {
                        return decline('Output read is not an ordinary scalar field');
                    }
                } elif read.startswith('self.') {
                    value = vars(wlk).get(read[5:]);
                    if type(value) not in (bool, int, float, str, list, type(None)) {
                        return decline('Output state has nonprimitive effects');
                    }
                }
            }
        }
        if phase == 0 {
            if current['node_type'] is not source {
                return decline('Current dispatch is not exact');
            }
            facts = known_node_fields(scope.path[-1].archetype);
            if any(
                facts.get(name + '::unsafe', False) for name in rule['required_fields']
            ) {
                return decline('Current node has observed unsafe required fields');
            }
        }
        query = GraphQuery(
            [], hops=[QHop(dir=int(rule['hops'][0][2]), `edge=edge_type, nd=target)]
        ).`visit();
        queries.append(query);
        values['source_module_' + str(phase)] = source.__module__;
        values['target_module_' + str(phase)] = target.__module__;
    }
    with mem._lock {
        mem.read_barrier();
        if 'catalog' in graph.sql_templates {
            mem.query_cache_put(
                ('ttg_compiled_catalog_v1', ), graph.sql_templates['catalog']
            );
        }
        for query in queries {
            visibility = _acl_pushdown_root(query, 1, mem);
            if access_gated() and visibility is None {
                return decline('Static region ACL proof failed');
            }
            if actor is not None and actor != visibility {
                return decline('Static region actor differs');
            }
            actor = visibility;
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
        if mem.query_cache_get(coverage) is not None {
            metrics['region_reuses'] = metrics.get('region_reuses', 0) + 1;
            return {'paths': [], 'payload': [], 'reused': True};
        }
        if actor is not None {
            values.update({'actor_uuid': UUID(actor), 'actor_text': actor});
        }
        descriptor = certificate['templates']['gated' if actor is not None else 'open'];
        # Finite terminal regions have no depth slot; use the emitted contract exactly.
        slots = {slot[0] for slot in descriptor['slots']};
        values = {
            name: value
            for (name, value) in values.items()
            if name in slots
        };
        compiled = bind_template(descriptor, values);
        rows = mem.store.rows(compiled.sql, compiled.params);
        metrics['region_queries'] = metrics.get('region_queries', 0) + 1;
        metrics['queries'] += 1;
        if len(rows) > max_rows {
            return decline('Static region row budget exceeded; no partial cache');
        }
        if not rows {
            return decline('Static region origin/dispatch is missing');
        }
        staged: list = [];
        payload: list = [];
        paths: list = [];
        covered: list = [];
        expected: tuple[int, int, UUID] | None = (0, 0, UUID(str(current['id'])));
        for row in rows {
            phase = int(row[0]);
            depth = int(row[1]);
            uid = UUID(str(row[2]));
            if (phase, depth, uid) != expected {
                return decline('Static region path closure/order mismatch');
            }
            cached = mem.__mem__.get(uid);
            if cached is not None and cached.is_populated() {
                if any(
                    o['kind'] == 'node_identity'
                    for o in bundle['summaries'][rules[phase]['ability']]['outputs']
                ) {
                    import from jaclang.runtime.archetype { NodeAnchor }
                    if type(cached) is not NodeAnchor
                        or vars(cached.archetype).get('__jac__') is not cached {
                        return decline('Cached node identity has an overridden anchor');
                    }
                }
                observed = known_node_fields(cached.archetype);
                if any(
                    observed.get(name + '::unsafe', False)
                    for name in rules[phase]['required_fields']
                ) {
                    return decline(
                        'Cached future node has observed unsafe required fields'
                    );
                }
            }
            if row[9] is not True {
                return decline('Malformed boolean field or unexpected dispatch');
            }
            if row[11] is not False {
                return decline('Static region cycle detected');
            }
            enabled = row[10];
            if type(enabled) is not bool {
                return decline('Invalid static guard result');
            }
            pairs: list = [];
            if row[3] is not None {
                if int(row[8]) != 1 or int(row[7]) != 1 {
                    return decline('Static region fanout requires native fallback');
                }
                pairs = [(UUID(str(row[3])), UUID(str(row[4])), row[5], row[6])];
                payload.extend(pairs);
            } elif any(v is not None for v in row[4:9]) {
                return decline('Invalid static empty path marker');
            }
            if not enabled and pairs {
                return decline('Disabled predicate produced path rows');
            }
            if enabled {
                native = graph.sql_templates['native'][str(rules[phase]['event'])][
                    'gated' if actor is not None else 'open'
                ];
                staged.append((queries[phase], uid, pairs, native));
                paths.append(
                    {
                        'event': rules[phase]['event'],
                        'origin': str(uid),
                        'ids': [str(p[0]) for p in pairs]
                    }
                );
            }
            covered.append((uid, rules[phase]['ability']));
            next_phase = int(row[12]);
            expected = (next_phase, depth + 1, UUID(str(pairs[0][0])))
                if pairs and enabled and next_phase >= 0
                else None;
        }
        if expected is not None {
            return decline('Static region was truncated before its terminal boundary');
        }
        if not publish_paths(mem, staged) {
            return decline('Static native cache publication failed');
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
            for entry_id in staged
            if not entry_id[2]
        );
        metrics['region_origins'] = metrics.get('region_origins', 0) + len(covered);
        metrics['regions'].append(
            {
                'kind': 'static_interability',
                'certificate_id': certificate['id'],
                'compiled': True,
                'dispatch_edges': [r['dispatch_edge'] for r in rules],
                'paths': paths,
                'external_dependencies': certificate['external_dependencies'],
                'checkpoint': point
            }
        );
        return {'paths': paths, 'payload': payload, 'reused': False};
    }
}
