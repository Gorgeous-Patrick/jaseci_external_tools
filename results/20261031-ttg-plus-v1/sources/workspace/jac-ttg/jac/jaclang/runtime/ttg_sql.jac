import from uuid { UUID }
import from functools { lru_cache }
import jaclang.sql as q;


obj _BuildColumns {
    has schemas: dict[int, q.Schema] = {},
        sources: dict[int, any] = {},
        fields: dict[int, dict[str, q.FieldDef]] = {},
        columns: dict[tuple[int, str], any] = {};

    def schema(source: any) -> q.Schema {
        self.sources[id(source)] = source;
        return q._compile_schema(source, self.schemas);
    }

    def col(source: any, name: str) -> any {
        key = (id(source), name);
        if key not in self.columns {
            identity = id(source);
            if identity not in self.fields {
                self.fields[identity] = {f.name: f for f in self.schema(source).fields};
            }
            definition = self.fields[identity][name];
            self.columns[key] = source.col(q.Field(name=name, dtype=definition.dtype));
        }
        return self.columns[key];
    }

    def pick(
        source: any, names: list[str], overrides: dict[str, any] = {}
    ) -> list[tuple[str, any]] {
        return [
            (name, overrides[name] if name in overrides else self.col(source, name))
            for name in names
        ];
    }

    def names(source: any) -> list[str] {
        return [f.name for f in self.schema(source).fields];
    }
}


def _all(terms: list[any]) -> any {
    if not terms {
        return q.boolean(True);
    }
    return q.and_nullable(terms)
        if `any([t.ast.dtype.nullable for t in terms])
        else q.and_(terms);
}

def _either(terms: list[any]) -> any {
    if not terms {
        return q.boolean(False);
    }
    return q.or_nullable(terms)
        if `any([t.ast.dtype.nullable for t in terms])
        else q.or_(terms);
}

def _cmp(left: any, right: any, op: str = '=') -> any {
    return q.compare_nullable(left, right, op)
        if left.ast.dtype.nullable or right.ast.dtype.nullable
        else q._compare(left, right, op);
}

def _negated(term: any) -> any {
    return q.not_nullable(term) if term.ast.dtype.nullable else q.not_(term);
}

def _present(term: any) -> any {
    return q.is_not_null(term) if term.ast.dtype.nullable else q.boolean(True);
}

def _select(
    source: any,
    columns: list[tuple[str, any]],
    joins: list[any] = [],
    predicate: any = None,
    groups: list[any] = [],
    order: list[any] = [],
    distinct: bool = False,
    distinct_on: list[any] = []
) -> any {
    return q.select(
        [q.named(name, expr) for (name, expr) in columns],
        source=source,
        joins=joins,
        where=predicate,
        group_by=[g.ast for g in groups],
        order_by=order,
        distinct=distinct,
        distinct_on=[e.ast for e in distinct_on]
    );
}

def _anchors -> any {
    return q.table(
        'anchors',
        [
            q.field('id', q.uuid_type()),
            q.field('kind', q.text_type()),
            q.field('arch_type', q.text_type()),
            q.field('root_id', q.nullable(q.uuid_type())),
            q.field('src', q.nullable(q.uuid_type())),
            q.field('dst', q.nullable(q.uuid_type())),
            q.field('undirected', q.bool_type()),
            q.field('seq', q.nullable(q.int64_type()))
        ]
    );
}

def _types -> any {
    return q.table(
        'graph_types',
        [q.field('type_name', q.text_type()), q.field('ancestor', q.text_type())]
    );
}

def _expected(value: any) -> any {
    return q.param(q.nullable(q.text_type()), value);
}

def _match(cols: _BuildColumns, arch_type: any, expected: any) -> any {
    ancestry = _types();
    inherited = _select(
        ancestry,
        [('one', q.int64(1))],
        predicate=_all(
            [
                _cmp(cols.col(ancestry, 'type_name'), arch_type),
                _cmp(cols.col(ancestry, 'ancestor'), expected)
            ]
        )
    );
    missing = q.is_null(expected) if expected.ast.dtype.nullable else q.boolean(False);
    return _either([missing, _cmp(arch_type, expected), q.exists(inherited)]);
}

def _owner(cols: _BuildColumns, anchor: any) -> any {
    return q.case_nullable(
        [
            (
                _all(
                    [
                        _cmp(cols.col(anchor, 'kind'), q.text('NodeAnchor')),
                        _cmp(cols.col(anchor, 'arch_type'), q.text('Root'))
                    ]
                ),
                cols.col(anchor, 'id')
            )
        ],
        cols.col(anchor, 'root_id')
    );
}

def _union(queries: list[any], distinct: bool = False) -> any {
    if not queries {
        raise ValueError('TTG requires a nonempty query set');
    }
    result = queries[0];
    for query in queries[1:] {
        result = q.union(result, query) if distinct else q.union_all(result, query);
    }
    return result;
}

def _edge_branch(
    cols: _BuildColumns,
    origin: any,
    source_name: str,
    target_name: str,
    edge_type: any,
    node_type: any
) -> any {
    edge_source = _anchors();
    target = _anchors();
    condition = _all(
        [
            _cmp(cols.col(target, 'id'), cols.col(edge_source, target_name)),
            _cmp(cols.col(target, 'kind'), q.text('NodeAnchor'))
        ]
    );
    return _select(
        edge_source,
        [
            ('edge_id', cols.col(edge_source, 'id')),
            ('edge_seq', q.coalesce(cols.col(edge_source, 'seq'), q.int64(0))),
            ('node_id', cols.col(target, 'id')),
            ('arch_type', cols.col(target, 'arch_type'))
        ],
        joins=[q.inner_join(target, condition)],
        predicate=_all(
            [
                _cmp(cols.col(edge_source, 'kind'), q.text('EdgeAnchor')),
                _cmp(cols.col(edge_source, source_name), origin),
                _present(cols.col(edge_source, target_name)),
                _match(cols, cols.col(edge_source, 'arch_type'), edge_type),
                _match(cols, cols.col(target, 'arch_type'), node_type)
            ]
        )
    );
}

def _hop(cols: _BuildColumns, origin: any, prior: list[any], hop: any) -> any {
    direction = int(hop[2] or 2);
    branches: list[any] = [];
    edge_type = _expected(hop[0]);
    node_type = _expected(hop[1]);
    if direction in (2, 3) {
        branches.append(_edge_branch(cols, origin, 'src', 'dst', edge_type, node_type));
    }
    if direction in (1, 3) {
        branches.append(_edge_branch(cols, origin, 'dst', 'src', edge_type, node_type));
    }
    if not branches {
        raise ValueError(f'Unsupported TTG direction {direction}');
    }
    edges = _union(branches).as_source(lateral=True);
    conditions = [_cmp(cols.col(edges, 'node_id'), origin, '<>')]
        + [_cmp(cols.col(edges, 'node_id'), n, '<>') for n in prior];
    return _select(
        edges, cols.pick(edges, cols.names(edges)), predicate=_all(conditions)
    ).as_source(
        lateral=True
    );
}

def _hop_key(cols: _BuildColumns, source: any) -> any {
    return q.concat(
        [
            q.lpad(
                q.cast(cols.col(source, 'edge_seq'), q.text_type()),
                q.int32(20),
                q.text('0')
            ),
            q.text(':'),
            q.cast(cols.col(source, 'edge_id'), q.text_type())
        ]
    );
}

def _frontier_spec(cols: _BuildColumns, frontier: any, spec: dict) -> any {
    chain = spec.get('chain') or [];
    if not chain {
        raise ValueError('TTG requires a nonempty hop chain');
    }
    prior: list[any] = [];
    joins: list[any] = [];
    edge_ids: list[any] = [];
    keys: list[any] = [];
    origin = cols.col(frontier, 'node_id');
    final_source: any = None;
    for hop in chain {
        final_source = _hop(cols, origin, prior, hop);
        joins.append(q.cross_join(final_source));
        origin = cols.col(final_source, 'node_id');
        prior.append(origin);
        edge_ids.append(cols.col(final_source, 'edge_id'));
        keys.append(_hop_key(cols, final_source));
    }
    step_order = keys[0];
    for key in keys[1:] {
        step_order = q.text_concat(q.text_concat(step_order, q.text(':')), key);
    }
    return _select(
        frontier,
        [
            ('depth', q.add(cols.col(frontier, 'depth'), q.int64(1))),
            ('node_id', origin),
            ('arch_type', cols.col(final_source, 'arch_type')),
            ('parent_depth', cols.col(frontier, 'depth')),
            ('parent_bfs_ord', cols.col(frontier, 'bfs_ord')),
            ('parent_node_id', cols.col(frontier, 'node_id')),
            ('step_nodes', q.array(q.uuid_type(), prior)),
            ('step_edges', q.array(q.uuid_type(), edge_ids)),
            ('step_ord', step_order),
            ('is_frontier', q.boolean(bool(spec.get('is_visit')))),
            ('spec_idx', q.int64(int(spec['idx'])))
        ],
        joins=joins,
        predicate=_match(
            cols, cols.col(frontier, 'arch_type'), _expected(spec.get('from_type'))
        )
    );
}

def _group_keys(cols: _BuildColumns, source: any) -> list[any] {
    return [
        cols.col(source, name)
        for name in ['parent_bfs_ord', 'spec_idx', 'parent_node_id']
    ];
}

def _partition_count(cols: _BuildColumns, source: any) -> any {
    return q.over(q.count(), partition_by=[e.ast for e in _group_keys(cols, source)]);
}

def _build_specialized(
    specs: list[dict], include_roots: bool = False, complete_optimization: bool = True
) -> q.CompiledSQL {
    cols = _BuildColumns();
    bound_limit = q.slot('limit', q.int64_type());
    bound_depth = q.slot('max_depth', q.int64_type());
    numeric_limit = q.cast(bound_limit, q.numeric_type());
    walk_fields = [
        q.field('depth', q.int64_type()),
        q.field('bfs_ord', q.int64_type()),
        q.field('node_id', q.uuid_type()),
        q.field('arch_type', q.text_type()),
        q.field('parent_depth', q.nullable(q.int64_type())),
        q.field('parent_bfs_ord', q.nullable(q.int64_type())),
        q.field('parent_node_id', q.nullable(q.uuid_type())),
        q.field('step_nodes', q.array_type(q.uuid_type())),
        q.field('step_edges', q.array_type(q.uuid_type())),
        q.field('is_frontier', q.bool_type()),
        q.field('step_spec_idx', q.nullable(q.int64_type())),
        q.field('step_group_complete', q.nullable(q.bool_type()))
    ];
    walk = q.cte_ref(walk_fields);
    seed_id = q.field('id', q.uuid_type());
    seed_ord = q.field('ord', q.int64_type());
    seeds = q.unnest(
        q.slot('origin_ids', q.array_type(q.uuid_type())), seed_id, seed_ord
    );
    seed_nodes = _anchors();
    anchor = _select(
        seeds,
        [
            ('depth', q.int64(0)),
            ('bfs_ord', cols.col(seeds, 'ord')),
            ('node_id', cols.col(seeds, 'id')),
            ('arch_type', cols.col(seed_nodes, 'arch_type')),
            ('parent_depth', q.null(q.int64_type())),
            ('parent_bfs_ord', q.null(q.int64_type())),
            ('parent_node_id', q.null(q.uuid_type())),
            ('step_nodes', q.array(q.uuid_type(), [cols.col(seeds, 'id')])),
            ('step_edges', q.array(q.uuid_type(), [])),
            ('is_frontier', q.boolean(True)),
            ('step_spec_idx', q.null(q.int64_type())),
            ('step_group_complete', q.boolean(True))
        ],
        joins=[
            q.inner_join(
                seed_nodes,
                _all(
                    [
                        _cmp(cols.col(seed_nodes, 'id'), cols.col(seeds, 'id')),
                        _cmp(cols.col(seed_nodes, 'kind'), q.text('NodeAnchor'))
                    ]
                )
            )
        ]
    );
    frontier = q.cte(
        _select(
            walk,
            cols.pick(walk, cols.names(walk)),
            predicate=_all(
                [
                    cols.col(walk, 'is_frontier'),
                    _cmp(cols.col(walk, 'depth'), bound_depth, '<')
                ]
            )
        ),
        materialized=True
    );
    frontier_nodes = q.cte(
        _select(frontier, cols.pick(frontier, ['node_id'])), materialized=True
    );
    raw = q.cte(_union([_frontier_spec(cols, frontier, spec) for spec in specs]));
    already = q.exists(
        _select(
            frontier_nodes,
            [('one', q.int64(1))],
            predicate=_cmp(
                cols.col(frontier_nodes, 'node_id'), cols.col(raw, 'node_id')
            )
        )
    );
    annotated = q.cte(
        _select(
            raw,
            cols.pick(raw, cols.names(raw))
                + [
                    ('already_frontier', already),
                    ('raw_group_count', _partition_count(cols, raw))
                ]
        )
    );
    unseen = q.cte(
        _select(
            annotated,
            cols.pick(annotated, cols.names(annotated)),
            predicate=q.not_(cols.col(annotated, 'already_frontier'))
        )
    );
    dedup = q.cte(
        _select(
            unseen,
            cols.pick(unseen, cols.names(unseen)),
            distinct_on=[cols.col(unseen, 'node_id')],
            order=[
                q.asc(cols.col(unseen, k))
                for k in [
                    'node_id',
                    'parent_bfs_ord',
                    'spec_idx',
                    'parent_node_id',
                    'step_ord'
                ]
            ]
        )
    );
    dedup_grouped = q.cte(
        _select(
            dedup,
            cols.pick(dedup, cols.names(dedup))
                + [('dedup_group_count', _partition_count(cols, dedup))]
        )
    );
    group_order = [q.asc(e) for e in _group_keys(cols, dedup_grouped)];
    grouped = q.cte(
        _select(
            dedup_grouped,
            cols.pick(dedup_grouped, cols.names(dedup_grouped))
                + [
                    ('group_ord', q.dense_rank(order_by=group_order)),
                    (
                        'group_row_rank',
                        q.row_number(
                            partition_by=[
                                e.ast for e in _group_keys(cols, dedup_grouped)
                            ],
                            order_by=[
                                q.asc(cols.col(dedup_grouped, 'step_ord')),
                                q.asc(cols.col(dedup_grouped, 'node_id'))
                            ]
                        )
                    ),
                    ('group_count', _partition_count(cols, dedup_grouped))
                ]
        )
    );
    distinct_groups = q.cte(
        _select(
            grouped, cols.pick(grouped, ['group_ord', 'group_count']), distinct=True
        )
    );
    order_groups = [q.asc(cols.col(distinct_groups, 'group_ord'))];
    prior_count = q.coalesce(
        q.over(
            q.sum_int64(cols.col(distinct_groups, 'group_count')),
            order_by=order_groups,
            frame=q.rows_between(q.unbounded_preceding(), q.preceding(1))
        ),
        q.numeric(0)
    );
    cume_count = q.over(
        q.sum_int64(cols.col(distinct_groups, 'group_count')),
        order_by=order_groups,
        frame=q.rows_between(q.unbounded_preceding(), q.current_row())
    );
    budget = q.cte(
        _select(
            distinct_groups,
            cols.pick(distinct_groups, cols.names(distinct_groups))
                + [('group_prior_count', prior_count), ('group_cume_count', cume_count)]
        )
    );
    complete = _all(
        [
            _cmp(cols.col(budget, 'group_cume_count'), numeric_limit, '<='),
            _cmp(
                cols.col(grouped, 'dedup_group_count'),
                cols.col(grouped, 'raw_group_count')
            )
        ]
    );
    budgeted = q.cte(
        _select(
            grouped,
            cols.pick(grouped, cols.names(grouped))
                + cols.pick(budget, ['group_prior_count', 'group_cume_count'])
                + [('group_complete', complete)],
            joins=[
                q.inner_join(
                    budget,
                    _cmp(cols.col(budget, 'group_ord'), cols.col(grouped, 'group_ord'))
                )
            ],
            predicate=_all(
                [
                    _cmp(cols.col(budget, 'group_prior_count'), numeric_limit, '<'),
                    _cmp(
                        q.cast(cols.col(grouped, 'group_row_rank'), q.numeric_type()),
                        q.numeric_sub(
                            numeric_limit, cols.col(budget, 'group_prior_count')
                        ),
                        '<='
                    )
                ]
            )
        )
    );
    ranked = q.cte(
        _select(
            budgeted,
            cols.pick(budgeted, cols.names(budgeted))
                + [
                    (
                        'local_rank',
                        q.row_number(
                            order_by=[
                                q.asc(cols.col(budgeted, k))
                                for k in ['group_ord', 'group_row_rank', 'node_id']
                            ]
                        )
                    ),
                    ('layer_count', q.over(q.count()))
                ]
        )
    );
    step = _select(
        ranked,
        cols.pick(ranked, ['depth'], {})
            + [('bfs_ord', cols.col(ranked, 'local_rank'))]
            + cols.pick(
                ranked,
                [
                    'node_id',
                    'arch_type',
                    'parent_depth',
                    'parent_bfs_ord',
                    'parent_node_id',
                    'step_nodes',
                    'step_edges'
                ]
            )
            + [
                (
                    'is_frontier',
                    _all(
                        [
                            cols.col(ranked, 'is_frontier'),
                            _cmp(cols.col(ranked, 'layer_count'), bound_limit, '<')
                        ]
                    )
                ),
                ('step_spec_idx', cols.col(ranked, 'spec_idx')),
                ('step_group_complete', cols.col(ranked, 'group_complete'))
            ]
    );
    local = [
        frontier,
        frontier_nodes,
        raw,
        annotated,
        unseen,
        dedup,
        dedup_grouped,
        grouped,
        distinct_groups,
        budget,
        budgeted,
        ranked
    ];
    q.define_cte(walk, q.union_all(anchor, q.with_ctes(step, local)), recursive=True);
    anchor_source = _anchors();
    candidate = q.cte(
        _select(
            walk,
            cols.pick(walk, ['depth', 'bfs_ord'])
                + [('target_id', cols.col(walk, 'node_id'))]
                + cols.pick(
                    walk,
                    [
                        'parent_depth',
                        'parent_bfs_ord',
                        'parent_node_id',
                        'step_nodes',
                        'step_edges',
                        'is_frontier'
                    ]
                )
                + [
                    ('spec_idx', cols.col(walk, 'step_spec_idx')),
                    ('group_complete', cols.col(walk, 'step_group_complete')),
                    ('owner_root', _owner(cols, anchor_source))
                ],
            joins=[
                q.inner_join(
                    anchor_source,
                    _all(
                        [
                            _cmp(
                                cols.col(anchor_source, 'id'), cols.col(walk, 'node_id')
                            ),
                            _cmp(cols.col(anchor_source, 'kind'), q.text('NodeAnchor'))
                        ]
                    )
                )
            ]
        )
    );
    path_names = [
        'depth',
        'bfs_ord',
        'path_node_id',
        'parent_depth',
        'parent_bfs_ord',
        'parent_node_id',
        'step_nodes',
        'step_edges',
        'spec_idx'
    ];
    path_columns = cols.pick(candidate, ['depth', 'bfs_ord'])
        + [('path_node_id', cols.col(candidate, 'target_id'))]
        + cols.pick(
            candidate,
            [
                'parent_depth',
                'parent_bfs_ord',
                'parent_node_id',
                'step_nodes',
                'step_edges',
                'spec_idx'
            ]
        );
    node_additions = _select(
        candidate,
        path_columns
            + [
                ('sub_ord', q.int64(0)),
                ('id', cols.col(candidate, 'target_id')),
                ('is_frontier', cols.col(candidate, 'is_frontier'))
            ]
    );
    owner_additions = _select(
        candidate,
        path_columns
            + [
                ('sub_ord', q.int64(1)),
                ('id', cols.col(candidate, 'owner_root')),
                ('is_frontier', q.boolean(False))
            ],
        predicate=_all(
            [
                _present(cols.col(candidate, 'owner_root')),
                q.boolean(include_roots),
                _cmp(
                    cols.col(candidate, 'owner_root'),
                    cols.col(candidate, 'target_id'),
                    '<>'
                )
            ]
        )
    );
    additions = q.cte(q.union_all(node_additions, owner_additions));
    flags = q.cte(
        _select(
            additions,
            [
                ('id', cols.col(additions, 'id')),
                ('is_frontier', q.bool_or(cols.col(additions, 'is_frontier')))
            ],
            predicate=_present(cols.col(additions, 'id')),
            groups=[cols.col(additions, 'id')]
        )
    );
    dedup_additions = q.cte(
        _select(
            additions,
            cols.pick(additions, ['id'] + path_names + ['sub_ord'])
                + [('is_frontier', cols.col(flags, 'is_frontier'))],
            joins=[
                q.inner_join(
                    flags, _cmp(cols.col(flags, 'id'), cols.col(additions, 'id'))
                )
            ],
            predicate=_present(cols.col(additions, 'id')),
            distinct_on=[cols.col(additions, 'id')],
            order=[
                q.asc(cols.col(additions, k))
                for k in ['id', 'depth', 'bfs_ord', 'sub_ord']
            ]
        )
    );
    plan_fields = ['id'] + path_names + ['is_frontier'];
    ordered_plan = q.cte(
        _select(
            dedup_additions,
            cols.pick(dedup_additions, plan_fields)
                + [
                    (
                        'ord',
                        q.row_number(
                            order_by=[
                                q.asc(cols.col(dedup_additions, k))
                                for k in ['depth', 'bfs_ord', 'sub_ord', 'id']
                            ]
                        )
                    )
                ]
        )
    );
    prefetch = q.cte(
        _select(
            ordered_plan,
            cols.pick(ordered_plan, plan_fields + ['ord']),
            predicate=_cmp(cols.col(ordered_plan, 'ord'), bound_limit, '<=')
        )
    );
    stats = q.cte(q.aggregate([q.named('total', q.count())], source=ordered_plan));
    chosen_names = [
        'depth',
        'bfs_ord',
        'node_id',
        'parent_depth',
        'parent_bfs_ord',
        'parent_node_id',
        'step_nodes',
        'step_edges',
        'spec_idx'
    ];
    selected = q.cte(
        q.union_all(
            _select(
                prefetch,
                cols.pick(
                    prefetch,
                    chosen_names,
                    {'node_id': cols.col(prefetch, 'path_node_id')}
                )
            ),
            _select(
                candidate,
                cols.pick(
                    candidate,
                    chosen_names,
                    {'node_id': cols.col(candidate, 'target_id')}
                ),
                joins=[q.cross_join(stats)],
                predicate=_cmp(cols.col(stats, 'total'), bound_limit, '<=')
            )
        )
    );
    chosen = q.cte_ref(list(cols.schema(selected).fields));
    parent = walk.ref();
    child = chosen.ref();
    ancestry_step = _select(
        parent,
        cols.pick(
            parent, chosen_names, {'spec_idx': cols.col(parent, 'step_spec_idx')}
        ),
        joins=[
            q.inner_join(
                child,
                _all(
                    [
                        _present(cols.col(child, 'parent_node_id')),
                        _cmp(
                            cols.col(parent, 'depth'), cols.col(child, 'parent_depth')
                        ),
                        _cmp(
                            cols.col(parent, 'bfs_ord'),
                            cols.col(child, 'parent_bfs_ord')
                        ),
                        _cmp(
                            cols.col(parent, 'node_id'),
                            cols.col(child, 'parent_node_id')
                        )
                    ]
                )
            )
        ]
    );
    q.define_cte(
        chosen,
        q.union(_select(selected, cols.pick(selected, chosen_names)), ancestry_step),
        recursive=True
    );
    plan = _plan_rows(cols, prefetch, True);
    pn = q.unnest(cols.col(chosen, 'step_nodes'), q.field('id', q.uuid_type()));
    pe = q.unnest(cols.col(chosen, 'step_edges'), q.field('id', q.uuid_type()));
    node_ids = q.cte(
        q.except_(
            _select(
                chosen,
                [('id', cols.col(pn, 'id'))],
                joins=[q.cross_join(pn)],
                distinct=True
            ),
            _select(
                prefetch,
                cols.pick(prefetch, ['id']),
                predicate=_present(cols.col(prefetch, 'id'))
            )
        )
    );
    edge_ids = q.cte(
        _select(
            chosen,
            [('id', cols.col(pe, 'id'))],
            joins=[q.cross_join(pe)],
            distinct=True
        )
    );
    available_nodes = q.cte(
        q.union(
            _select(
                prefetch,
                cols.pick(prefetch, ['id']),
                predicate=_present(cols.col(prefetch, 'id'))
            ),
            _select(node_ids, cols.pick(node_ids, ['id']))
        )
    );
    complete_specs = [
        spec
        for spec in specs
        if len(spec.get('chain') or []) == 1
    ];
    complete_queries = [
        _select(
            walk,
            [
                ('origin_id', cols.col(walk, 'node_id')),
                ('spec_idx', q.int64(int(spec['idx'])))
            ],
            predicate=_all(
                [
                    cols.col(walk, 'is_frontier'),
                    _cmp(cols.col(walk, 'depth'), bound_depth, '<'),
                    _match(
                        cols,
                        cols.col(walk, 'arch_type'),
                        _expected(spec.get('from_type'))
                    )
                ]
            ),
            distinct=True
        ) for spec in complete_specs
    ];
    complete_origins = q.cte(
        _union(complete_queries)
            if complete_queries
            else _select(
                None,
                [
                    ('origin_id', q.null(q.uuid_type())),
                    ('spec_idx', q.null(q.int64_type()))
                ],
                predicate=q.boolean(False)
            )
    );
    exp_edges = q.unnest(
        cols.col(candidate, 'step_edges'), q.field('id', q.uuid_type())
    );
    relevant = _either(
        [
            _cmp(cols.col(candidate, 'spec_idx'), q.int64(int(spec['idx'])))
            for spec in complete_specs
        ]
    );
    expected = q.cte(
        _select(
            candidate,
            [
                ('origin_id', cols.col(candidate, 'parent_node_id')),
                ('spec_idx', cols.col(candidate, 'spec_idx')),
                ('target_id', cols.col(candidate, 'target_id')),
                ('edge_id', cols.col(exp_edges, 'id')),
                ('group_complete', cols.col(candidate, 'group_complete'))
            ],
            joins=[q.cross_join(exp_edges)],
            predicate=_all([_present(cols.col(candidate, 'parent_node_id')), relevant])
        )
    );
    complete_hops = _complete_rows(
        cols,
        complete_origins,
        expected,
        available_nodes,
        edge_ids,
        complete_optimization
    );
    topology_nodes = _topology_rows(cols, node_ids, False);
    topology_edges = _topology_rows(cols, edge_ids, True);
    result = _union(
        [
            _output(cols, plan, 0),
            _output(cols, topology_nodes, 1),
            _output(cols, topology_edges, 2),
            _output(cols, complete_hops, 3)
        ]
    );
    outputs = {
        f.name: q.Field(name=f.name, dtype=f.dtype)
        for f in cols.schema(result.ast).fields
    };
    return q.compile_sql(
        q.ordered(
            result,
            [
                q.asc(q.output(outputs['row_kind'])),
                q.asc(q.output(outputs['ord']), nulls='LAST'),
                q.asc(q.output(outputs['seq']), nulls='FIRST'),
                q.asc(q.output(outputs['id']))
            ]
        )
    );
}

def _plan_rows(cols: _BuildColumns, prefetch: any, specialized: bool) -> any {
    anchors = _anchors();
    ancestry = q.optional_source(_types());
    columns = cols.pick(
        prefetch, ['ord', 'id'] + (['depth'] if specialized else []) + ['is_frontier']
    );
    columns += [
        ('arch_type', cols.col(anchors, 'arch_type')),
        ('owner_root', _owner(cols, anchors)),
        (
            'ancestors',
            q.coalesce(
                q.string_agg(
                    cols.col(ancestry, 'ancestor'), q.text(','), distinct=True
                ),
                cols.col(anchors, 'arch_type')
            )
        )
    ];
    groups = [
        cols.col(prefetch, k)
        for k in (['ord', 'id'] + (['depth'] if specialized else []) + ['is_frontier'])
    ];
    groups += [cols.col(anchors, k) for k in ['id', 'kind', 'arch_type', 'root_id']];
    return q.cte(
        _select(
            prefetch,
            columns,
            joins=[
                q.inner_join(
                    anchors,
                    _all(
                        [
                            _cmp(cols.col(anchors, 'id'), cols.col(prefetch, 'id')),
                            _cmp(cols.col(anchors, 'kind'), q.text('NodeAnchor'))
                        ]
                    )
                ),
                q.left_join(
                    ancestry,
                    _cmp(
                        cols.col(ancestry, 'type_name'), cols.col(anchors, 'arch_type')
                    )
                )
            ],
            groups=groups
        )
    );
}

def _topology_rows(cols: _BuildColumns, ids: any, edges: bool) -> any {
    anchors = _anchors();
    ancestry = q.optional_source(_types());
    names = ['id', 'arch_type']
        + (['src', 'dst', 'undirected', 'seq'] if edges else []);
    columns = cols.pick(anchors, names)
        + ([] if edges else [('owner_root', _owner(cols, anchors))]);
    columns += [
        (
            'ancestors',
            q.coalesce(
                q.string_agg(
                    cols.col(ancestry, 'ancestor'), q.text(','), distinct=True
                ),
                cols.col(anchors, 'arch_type')
            )
        )
    ];
    groups = [
        cols.col(anchors, k)
        for k in (
            ['id', 'arch_type', 'src', 'dst', 'undirected', 'seq']
                if edges
                else ['id', 'kind', 'arch_type', 'root_id']
        )
    ];
    return q.cte(
        _select(
            anchors,
            columns,
            joins=[
                q.inner_join(ids, _cmp(cols.col(ids, 'id'), cols.col(anchors, 'id'))),
                q.left_join(
                    ancestry,
                    _cmp(
                        cols.col(ancestry, 'type_name'), cols.col(anchors, 'arch_type')
                    )
                )
            ],
            predicate=_cmp(
                cols.col(anchors, 'kind'),
                q.text('EdgeAnchor' if edges else 'NodeAnchor')
            ),
            groups=groups
        )
    );
}

def _complete_rows(
    cols: _BuildColumns,
    origins: any,
    expected: any,
    available_nodes: any,
    available_edges: any,
    optimized: bool
) -> any {
    if optimized {
        nodes = q.optional_source(available_nodes.ref());
        edges = q.optional_source(available_edges.ref());
        all_available = q.bool_and(
            _all(
                [
                    cols.col(expected, 'group_complete'),
                    _present(cols.col(nodes, 'id')),
                    _present(cols.col(edges, 'id'))
                ]
            )
        );
        status = q.cte(
            _select(
                expected,
                cols.pick(expected, ['origin_id', 'spec_idx'])
                    + [('all_available', all_available)],
                joins=[
                    q.left_join(
                        nodes,
                        _cmp(cols.col(nodes, 'id'), cols.col(expected, 'target_id'))
                    ),
                    q.left_join(
                        edges,
                        _cmp(cols.col(edges, 'id'), cols.col(expected, 'edge_id'))
                    )
                ],
                groups=[cols.col(expected, 'origin_id'), cols.col(expected, 'spec_idx')]
            )
        );
        optional_status = q.optional_source(status);
        join = q.left_join(
            optional_status,
            _all(
                [
                    _cmp(
                        cols.col(optional_status, 'origin_id'),
                        cols.col(origins, 'origin_id')
                    ),
                    _cmp(
                        cols.col(optional_status, 'spec_idx'),
                        cols.col(origins, 'spec_idx')
                    )
                ]
            )
        );
        return q.cte(
            _select(
                origins,
                cols.pick(origins, ['origin_id', 'spec_idx']),
                joins=[join],
                predicate=_all(
                    [
                        _present(cols.col(origins, 'origin_id')),
                        _present(cols.col(origins, 'spec_idx')),
                        cols.col(optional_status, 'all_available')
                    ]
                )
            )
        );
    }
    exp1 = expected.ref();
    exp2 = expected.ref();
    nodes = available_nodes.ref();
    edges = available_edges.ref();
    existing = q.exists(
        _select(
            exp1,
            [('one', q.int64(1))],
            predicate=_all(
                [
                    _cmp(cols.col(exp1, 'origin_id'), cols.col(origins, 'origin_id')),
                    _cmp(cols.col(exp1, 'spec_idx'), cols.col(origins, 'spec_idx'))
                ]
            )
        )
    );
    node_missing = q.not_(
        q.exists(
            _select(
                nodes,
                [('one', q.int64(1))],
                predicate=_cmp(cols.col(nodes, 'id'), cols.col(exp2, 'target_id'))
            )
        )
    );
    edge_missing = q.not_(
        q.exists(
            _select(
                edges,
                [('one', q.int64(1))],
                predicate=_cmp(cols.col(edges, 'id'), cols.col(exp2, 'edge_id'))
            )
        )
    );
    bad = q.exists(
        _select(
            exp2,
            [('one', q.int64(1))],
            predicate=_all(
                [
                    _cmp(cols.col(exp2, 'origin_id'), cols.col(origins, 'origin_id')),
                    _cmp(cols.col(exp2, 'spec_idx'), cols.col(origins, 'spec_idx')),
                    _either(
                        [
                            _negated(cols.col(exp2, 'group_complete')),
                            node_missing,
                            edge_missing
                        ]
                    )
                ]
            )
        )
    );
    return q.cte(
        _select(
            origins,
            cols.pick(origins, ['origin_id', 'spec_idx']),
            predicate=_all(
                [
                    _present(cols.col(origins, 'origin_id')),
                    _present(cols.col(origins, 'spec_idx')),
                    existing,
                    q.not_(bad)
                ]
            )
        )
    );
}

def _output(cols: _BuildColumns, source: any, kind: int) -> any {
    return _select(
        source,
        [
            ('row_kind', q.int64(kind)),
            ('ord', cols.col(source, 'ord') if kind == 0 else q.null(q.int64_type())),
            ('id', cols.col(source, 'origin_id' if kind == 3 else 'id')),
            (
                'arch_type',
                q.null(q.text_type()) if kind == 3 else cols.col(source, 'arch_type')
            ),
            (
                'owner_root',
                cols.col(source, 'owner_root')
                    if kind in (0, 1)
                    else q.null(q.uuid_type())
            ),
            ('src', cols.col(source, 'src') if kind == 2 else q.null(q.uuid_type())),
            ('dst', cols.col(source, 'dst') if kind == 2 else q.null(q.uuid_type())),
            (
                'undirected',
                cols.col(source, 'is_frontier')
                    if kind == 0
                    else (
                        cols.col(source, 'undirected')
                            if kind == 2
                            else q.boolean(False)
                    )
            ),
            (
                'ancestors',
                q.null(q.text_type()) if kind == 3 else cols.col(source, 'ancestors')
            ),
            (
                'seq',
                cols.col(source, 'depth')
                    if kind == 0
                    else (
                        cols.col(source, 'seq')
                            if kind == 2
                            else (
                                cols.col(source, 'spec_idx')
                                    if kind == 3
                                    else q.null(q.int64_type())
                            )
                    )
            )
        ]
    );
}

def _build_layered(
    specs: list[dict],
    has_undirected: bool,
    include_roots: bool = False,
    allow_path_revisits: bool = False
) -> q.CompiledSQL {
    cols = _BuildColumns();
    spec_fields = [
        q.field('idx', q.int64_type()),
        q.field('from_type', q.nullable(q.text_type())),
        q.field('is_visit', q.bool_type()),
        q.field('chain_len', q.int64_type())
    ];
    hop_fields = [
        q.field('spec_idx', q.int64_type()),
        q.field('hop_idx', q.int64_type()),
        q.field('edge_type', q.nullable(q.text_type())),
        q.field('node_type', q.nullable(q.text_type())),
        q.field('direction', q.int64_type())
    ];
    spec_rows: list[any] = [];
    hop_rows: list[any] = [];
    directions: list[int] = [];
    for spec in specs {
        chain = spec.get('chain') or [];
        idx = int(spec['idx']);
        spec_rows.append(
            [
                q.int64(idx),
                _expected(spec.get('from_type')),
                q.boolean(bool(spec.get('is_visit'))),
                q.int64(len(chain))
            ]
        );
        for (hop_idx, hop) in enumerate(chain) {
            direction = int(hop[2] or 2);
            directions.append(direction);
            hop_rows.append(
                [
                    q.int64(idx),
                    q.int64(hop_idx),
                    _expected(hop[0]),
                    _expected(hop[1]),
                    q.int64(direction)
                ]
            );
        }
    }
    spec_source = q.cte(q.values(spec_fields, spec_rows));
    hops = q.cte(q.values(hop_fields, hop_rows));
    seeds = q.unnest(
        q.slot('frontier_ids', q.array_type(q.uuid_type())),
        q.field('id', q.uuid_type()),
        q.field('ord', q.int64_type())
    );
    seed_node = _anchors();
    frontier = q.cte(
        _select(
            seeds,
            [
                ('node_id', cols.col(seeds, 'id')),
                ('frontier_ord', cols.col(seeds, 'ord'))
            ],
            joins=[
                q.inner_join(
                    seed_node,
                    _all(
                        [
                            _cmp(cols.col(seed_node, 'id'), cols.col(seeds, 'id')),
                            _cmp(cols.col(seed_node, 'kind'), q.text('NodeAnchor'))
                        ]
                    )
                )
            ]
        )
    );
    walk_fields = [
        q.field('spec_idx', q.int64_type()),
        q.field('chain_len', q.int64_type()),
        q.field('is_visit', q.bool_type()),
        q.field('seed_ord', q.int64_type()),
        q.field('hop_idx', q.int64_type()),
        q.field('node_id', q.uuid_type()),
        q.field('path_nodes', q.array_type(q.uuid_type())),
        q.field('hop_ord', q.array_type(q.int64_type()))
    ];
    walk = q.cte_ref(walk_fields);
    current = _anchors();
    anchor = _select(
        frontier,
        [
            ('spec_idx', cols.col(spec_source, 'idx')),
            ('chain_len', cols.col(spec_source, 'chain_len')),
            ('is_visit', cols.col(spec_source, 'is_visit')),
            ('seed_ord', cols.col(frontier, 'frontier_ord')),
            ('hop_idx', q.int64(0)),
            ('node_id', cols.col(frontier, 'node_id')),
            ('path_nodes', q.array(q.uuid_type(), [cols.col(frontier, 'node_id')])),
            ('hop_ord', q.array(q.int64_type(), []))
        ],
        joins=[
            q.inner_join(
                current,
                _all(
                    [
                        _cmp(cols.col(current, 'id'), cols.col(frontier, 'node_id')),
                        _cmp(cols.col(current, 'kind'), q.text('NodeAnchor'))
                    ]
                )
            ),
            q.inner_join(
                spec_source,
                _all(
                    [
                        _cmp(cols.col(spec_source, 'chain_len'), q.int64(0), '>'),
                        _match(
                            cols,
                            cols.col(current, 'arch_type'),
                            cols.col(spec_source, 'from_type')
                        )
                    ]
                )
            )
        ]
    );
    edge_source = _anchors();
    target = _anchors();
    base_conditions = [
        _cmp(cols.col(edge_source, 'kind'), q.text('EdgeAnchor')),
        _present(cols.col(edge_source, 'src')),
        _present(cols.col(edge_source, 'dst'))
    ];
    direct_out = not has_undirected and all([d == 2 for d in directions]);
    direct_in = not has_undirected and all([d == 1 for d in directions]);
    if direct_out or direct_in {
        base_conditions.append(
            _cmp(
                cols.col(edge_source, 'src' if direct_out else 'dst'),
                cols.col(walk, 'node_id')
            )
        );
        target_id = cols.col(edge_source, 'dst' if direct_out else 'src');
    } else {
        base_conditions.append(
            _either(
                [
                    _all(
                        [
                            q.in_(
                                cols.col(hops, 'direction'), [q.int64(2), q.int64(3)]
                            ),
                            _cmp(
                                cols.col(edge_source, 'src'), cols.col(walk, 'node_id')
                            )
                        ]
                    ),
                    _all(
                        [
                            q.in_(
                                cols.col(hops, 'direction'), [q.int64(1), q.int64(3)]
                            ),
                            _cmp(
                                cols.col(edge_source, 'dst'), cols.col(walk, 'node_id')
                            )
                        ]
                    ),
                    _all(
                        [
                            _cmp(cols.col(hops, 'direction'), q.int64(1)),
                            cols.col(edge_source, 'undirected'),
                            _cmp(
                                cols.col(edge_source, 'src'), cols.col(walk, 'node_id')
                            )
                        ]
                    ),
                    _all(
                        [
                            _cmp(cols.col(hops, 'direction'), q.int64(2)),
                            cols.col(edge_source, 'undirected'),
                            _cmp(
                                cols.col(edge_source, 'dst'), cols.col(walk, 'node_id')
                            )
                        ]
                    )
                ]
            )
        );
        target_id = q.case_(
            [
                (
                    _cmp(cols.col(edge_source, 'src'), cols.col(walk, 'node_id')),
                    cols.col(edge_source, 'dst')
                )
            ],
            cols.col(edge_source, 'src')
        );
    }
    step = _select(
        walk,
        cols.pick(walk, ['spec_idx', 'chain_len', 'is_visit', 'seed_ord'])
            + [
                ('hop_idx', q.add(cols.col(hops, 'hop_idx'), q.int64(1))),
                ('node_id', cols.col(target, 'id')),
                (
                    'path_nodes',
                    q.array_append(cols.col(walk, 'path_nodes'), cols.col(target, 'id'))
                ),
                (
                    'hop_ord',
                    q.array_append(
                        cols.col(walk, 'hop_ord'),
                        q.coalesce(cols.col(edge_source, 'seq'), q.int64(0))
                    )
                )
            ],
        joins=[
            q.inner_join(
                hops,
                _all(
                    [
                        _cmp(cols.col(hops, 'spec_idx'), cols.col(walk, 'spec_idx')),
                        _cmp(cols.col(hops, 'hop_idx'), cols.col(walk, 'hop_idx'))
                    ]
                )
            ),
            q.inner_join(edge_source, _all(base_conditions)),
            q.inner_join(
                target,
                _all(
                    [
                        _cmp(cols.col(target, 'id'), target_id),
                        _cmp(cols.col(target, 'kind'), q.text('NodeAnchor'))
                    ]
                )
            )
        ],
        predicate=_all(
            [
                _cmp(cols.col(walk, 'hop_idx'), cols.col(walk, 'chain_len'), '<'),
                _match(
                    cols,
                    cols.col(edge_source, 'arch_type'),
                    cols.col(hops, 'edge_type')
                ),
                _match(
                    cols, cols.col(target, 'arch_type'), cols.col(hops, 'node_type')
                ),
                q.boolean(True)
                    if allow_path_revisits
                    else _negated(
                        q.any_eq(cols.col(target, 'id'), cols.col(walk, 'path_nodes'))
                    )
            ]
        )
    );
    q.define_cte(walk, q.union_all(anchor, step), recursive=True);
    seed_rows = _select(
        frontier,
        [
            ('phase', q.int64(0)),
            ('seed_ord', cols.col(frontier, 'frontier_ord')),
            ('spec_idx', q.int64(-1)),
            ('hop_ord', q.array(q.int64_type(), [])),
            ('target_id', cols.col(frontier, 'node_id')),
            ('is_frontier', q.boolean(False))
        ]
    );
    visited_rows = _select(
        walk,
        [('phase', q.int64(1))]
            + cols.pick(walk, ['seed_ord', 'spec_idx', 'hop_ord'])
            + [
                ('target_id', cols.col(walk, 'node_id')),
                ('is_frontier', cols.col(walk, 'is_visit'))
            ],
        predicate=_cmp(cols.col(walk, 'hop_idx'), cols.col(walk, 'chain_len'))
    );
    candidates = q.cte(q.union_all(seed_rows, visited_rows));
    anchors = _anchors();
    node_rows = q.cte(
        _select(
            candidates,
            cols.pick(candidates, cols.names(candidates))
                + [('owner_root', _owner(cols, anchors))],
            joins=[
                q.inner_join(
                    anchors,
                    _all(
                        [
                            _cmp(
                                cols.col(anchors, 'id'),
                                cols.col(candidates, 'target_id')
                            ),
                            _cmp(cols.col(anchors, 'kind'), q.text('NodeAnchor'))
                        ]
                    )
                )
            ]
        )
    );
    ordering_names = ['phase', 'seed_ord', 'spec_idx', 'hop_ord'];
    additions = q.cte(
        q.union_all(
            _select(
                node_rows,
                cols.pick(node_rows, ordering_names)
                    + [
                        ('sub_ord', q.int64(0)),
                        ('id', cols.col(node_rows, 'target_id')),
                        ('is_frontier', cols.col(node_rows, 'is_frontier'))
                    ]
            ),
            _select(
                node_rows,
                cols.pick(node_rows, ordering_names)
                    + [
                        ('sub_ord', q.int64(1)),
                        ('id', cols.col(node_rows, 'owner_root')),
                        ('is_frontier', q.boolean(False))
                    ],
                predicate=_all(
                    [
                        _present(cols.col(node_rows, 'owner_root')),
                        q.boolean(include_roots),
                        _cmp(
                            cols.col(node_rows, 'owner_root'),
                            cols.col(node_rows, 'target_id'),
                            '<>'
                        )
                    ]
                )
            )
        )
    );
    seen_array = q.slot('seen_ids', q.array_type(q.uuid_type()));
    filtered = q.cte(
        _select(
            additions,
            cols.pick(additions, cols.names(additions)),
            predicate=_all(
                [
                    _present(cols.col(additions, 'id')),
                    _either(
                        [
                            q.slot('seen_empty', q.bool_type()),
                            _negated(q.any_eq(cols.col(additions, 'id'), seen_array))
                        ]
                    )
                ]
            )
        )
    );
    dedup = q.cte(
        _select(
            filtered,
            cols.pick(filtered, ['id'] + ordering_names + ['sub_ord', 'is_frontier']),
            distinct_on=[cols.col(filtered, 'id')],
            order=[
                q.asc(cols.col(filtered, k))
                for k in (['id'] + ordering_names + ['sub_ord'])
            ]
        )
    );
    ordered_plan = q.cte(
        _select(
            dedup,
            cols.pick(dedup, ['id', 'is_frontier'])
                + [
                    (
                        'ord',
                        q.row_number(
                            order_by=[
                                q.asc(cols.col(dedup, k))
                                for k in (ordering_names + ['sub_ord', 'id'])
                            ]
                        )
                    )
                ]
        )
    );
    prefetch = q.cte(
        _select(
            ordered_plan,
            cols.pick(ordered_plan, cols.names(ordered_plan)),
            predicate=_cmp(
                cols.col(ordered_plan, 'ord'), q.slot('limit', q.int64_type()), '<='
            )
        )
    );
    plan = _plan_rows(cols, prefetch, False);
    return q.compile_sql(
        _select(
            plan,
            cols.pick(
                plan,
                ['ord', 'id', 'arch_type', 'owner_root', 'ancestors', 'is_frontier']
            ),
            order=[q.asc(cols.col(plan, 'ord'))]
        )
    );
}

def compile_undirected_probe -> q.CompiledSQL {
    cols = _BuildColumns();
    edges = _anchors();
    query = _select(
        edges,
        [('one', q.int64(1))],
        predicate=_all(
            [
                _cmp(cols.col(edges, 'kind'), q.text('EdgeAnchor')),
                cols.col(edges, 'undirected')
            ]
        )
    );
    return q.compile_sql(_select(None, [('present', q.exists(q.limit_one(query)))]));
}


def _spec_key(specs: list[dict]) -> tuple[any, ...] {
    return tuple(
        (
            int(spec['idx']),
            spec.get('from_type'),
            bool(spec.get('is_visit')),
            tuple(
                (hop[0], hop[1], int(hop[2] or 2)) for hop in (spec.get('chain') or [])
            )
        ) for spec in specs
    );
}

def _specs_from_key(key: tuple[any, ...]) -> list[dict] {
    return [
        {'idx': item[0], 'from_type': item[1], 'is_visit': item[2], 'chain': item[3]}
        for item in key
    ];
}

@lru_cache(maxsize=128)
def _specialized_plan(
    key: tuple[any, ...], include_roots: bool, complete_optimization: bool
) -> q.CompiledSQL {
    return _build_specialized(
        _specs_from_key(key), include_roots, complete_optimization
    );
}

@lru_cache(maxsize=128)
def _layered_plan(
    key: tuple[any, ...],
    has_undirected: bool,
    include_roots: bool,
    allow_path_revisits: bool = False
) -> q.CompiledSQL {
    return _build_layered(
        _specs_from_key(key), has_undirected, include_roots, allow_path_revisits
    );
}

def compile_specialized(
    specs: list[dict],
    origins: list[UUID],
    limit: int,
    max_depth: int,
    include_roots: bool = False,
    complete_optimization: bool = True
) -> q.CompiledSQL {
    plan = _specialized_plan(_spec_key(specs), include_roots, complete_optimization);
    return plan.bind(
        {'origin_ids': tuple(origins), 'limit': limit, 'max_depth': max_depth}
    );
}

def compile_layered(
    specs: list[dict],
    frontier_ids: list[UUID],
    seen_ids: list[UUID],
    limit: int,
    has_undirected: bool,
    include_roots: bool = False,
    allow_path_revisits: bool = False
) -> q.CompiledSQL {
    plan = _layered_plan(
        _spec_key(specs), has_undirected, include_roots, allow_path_revisits
    );
    return plan.bind(
        {
            'frontier_ids': tuple(frontier_ids),
            'seen_ids': tuple(seen_ids),
            'seen_empty': not bool(seen_ids),
            'limit': limit
        }
    );
}


@lru_cache(maxsize=1)
def compile_acl_type_catalog -> q.CompiledSQL {
    cols = _BuildColumns();
    catalog = q.table(
        'anchors',
        [
            q.field('kind', q.text_type()),
            q.field('arch_type', q.text_type()),
            q.field('arch_module', q.nullable(q.text_type()))
        ]
    );
    return q.compile_sql(
        _select(
            catalog,
            cols.pick(catalog, ['arch_type', 'arch_module']),
            predicate=_cmp(cols.col(catalog, 'kind'), q.text('NodeAnchor')),
            distinct=True,
            order=[
                q.asc(cols.col(catalog, 'arch_type')),
                q.asc(cols.col(catalog, 'arch_module'))
            ]
        )
    );
}
