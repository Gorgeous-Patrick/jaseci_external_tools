import jaclang.sql as q;
import from uuid { UUID }
import from jaclang.runtime.ttg_sql {
    _BuildColumns,
    _select,
    _all,
    _either,
    _cmp,
    _match,
    _expected,
    _union
}


def _native_anchors -> any {
    return q.table(
        'anchors',
        [
            q.field('id', q.uuid_type()),
            q.field('kind', q.text_type()),
            q.field('arch_type', q.text_type()),
            q.field('arch_module', q.nullable(q.text_type())),
            q.field('root_id', q.nullable(q.uuid_type())),
            q.field('src', q.nullable(q.uuid_type())),
            q.field('dst', q.nullable(q.uuid_type())),
            q.field('undirected', q.bool_type()),
            q.field('seq', q.nullable(q.int64_type())),
            q.field('props', q.json_type())
        ]
    );
}


def _visibility(cols: _BuildColumns, node_source: any, actor: any) -> any {
    if actor is None {
        return q.boolean(True);
    }
    actor_uuid = actor['uuid']
        if type(actor) is dict
        else q.param(q.uuid_type(), UUID(actor));
    actor_text = actor['text'] if type(actor) is dict else q.text(actor);
    props = cols.col(node_source, 'props');
    access = q.json_get(props, q.text('access'));
    roots = q.json_get(q.json_get(access, q.text('roots')), q.text('anchors'));
    groups = q.json_get(q.json_get(access, q.text('groups')), q.text('anchors'));
    group_edge = _native_anchors();
    member = _select(
        group_edge,
        [('one', q.int64(1))],
        predicate=_all(
            [
                _cmp(cols.col(group_edge, 'kind'), q.text('EdgeAnchor')),
                _cmp(cols.col(group_edge, 'src'), actor_uuid),
                q.json_has_key(
                    groups,
                    q.cast(cols.col(group_edge, 'dst'), q.nullable(q.text_type()))
                )
            ]
        )
    );
    return _either(
        [
            _cmp(cols.col(node_source, 'root_id'), actor_uuid),
            _cmp(
                q.cast(q.json_text(access, q.text('all')), q.nullable(q.int64_type())),
                q.int64(-1),
                '>'
            ),
            q.json_has_key(roots, actor_text),
            q.exists(member)
        ]
    );
}


def _fusion_match(
    cols: _BuildColumns, arch_type: any, expected: any, template: bool
) -> any {
    if not template {
        return _match(cols, arch_type, _expected(expected));
    }
    expected_expr = _expected(expected);
    ancestry = q.table(
        'graph_types',
        [q.field('type_name', q.text_type()), q.field('ancestor', q.text_type())]
    );
    inherited = _select(
        ancestry,
        [('type_name', cols.col(ancestry, 'type_name'))],
        predicate=_cmp(cols.col(ancestry, 'ancestor'), expected_expr)
    );
    return _either(
        [
            q.is_null(expected_expr),
            _cmp(arch_type, expected_expr),
            q.in_query(arch_type, inherited, q.field('type_name', q.text_type()))
        ]
    );
}


def _native_path(
    cols: _BuildColumns, origin: any, hops: tuple, actor: any, template: bool = False
) -> any {
    joins: list = [];
    predicates: list = [];
    order: list = [];
    first: any = None;
    last_node: any = None;
    last_edge: any = None;
    for hop in hops {
        edge_source = _native_anchors();
        node_source = _native_anchors();
        forward = _cmp(cols.col(edge_source, 'src'), origin);
        backward = _cmp(cols.col(edge_source, 'dst'), origin);
        direction = int(hop[2]);
        if direction not in (1, 2, 3) {
            raise ValueError('Unsupported native hop direction');
        }
        direction_test = _either([forward, backward])
            if direction == 3
            else _either(
                [
                    backward if direction == 1 else forward,
                    _all(
                        [
                            cols.col(edge_source, 'undirected'),
                            forward if direction == 1 else backward
                        ]
                    )
                ]
            );
        edge_test = _all(
            [
                _cmp(cols.col(edge_source, 'kind'), q.text('EdgeAnchor')),
                direction_test,
                _fusion_match(
                    cols, cols.col(edge_source, 'arch_type'), hop[0], template
                )
            ]
        );
        if first is None {
            first = edge_source;
            predicates.append(edge_test);
        } else {
            joins.append(q.inner_join(edge_source, edge_test));
        }
        other = q.case_nullable(
            [(forward, cols.col(edge_source, 'dst'))], cols.col(edge_source, 'src')
        );
        joins.append(
            q.inner_join(
                node_source,
                _all(
                    [
                        _cmp(cols.col(node_source, 'id'), other),
                        _cmp(cols.col(node_source, 'kind'), q.text('NodeAnchor')),
                        _fusion_match(
                            cols, cols.col(node_source, 'arch_type'), hop[1], template
                        ),
                        _visibility(cols, node_source, actor)
                    ]
                )
            )
        );
        order.extend(
            [q.asc(cols.col(edge_source, 'seq')), q.asc(cols.col(edge_source, 'id'))]
        );
        origin = cols.col(node_source, 'id');
        last_node = node_source;
        last_edge = edge_source;
    }
    if first is None {
        raise ValueError('A fused path must contain at least one hop');
    }
    return _select(
        first,
        [
            ('target_id', cols.col(last_node, 'id')),
            ('edge_id', cols.col(last_edge, 'id')),
            ('arch_type', cols.col(last_node, 'arch_type')),
            ('arch_module', cols.col(last_node, 'arch_module')),
            ('ord', q.row_number(order_by=order)),
            ('arity', q.over(q.count()))
        ],
        joins=joins,
        predicate=_all(predicates)
    ).as_source(
        lateral=True
    );
}


def _path_output(
    cols: _BuildColumns,
    source: any,
    origin: any,
    depth: any,
    hops: tuple,
    slot: int,
    actor: any,
    template: bool = False
) -> any {
    matches = q.optional_source(_native_path(cols, origin, hops, actor, template));
    return _select(
        source,
        [('slot', q.int64(slot)), ('depth', depth), ('origin_id', origin)]
            + cols.pick(
                matches,
                ['target_id', 'edge_id', 'arch_type', 'arch_module', 'ord', 'arity']
            ),
        joins=[q.left_join(matches, q.boolean(True))]
    );
}


def compile_fused_region(
    contract: dict, origins: list, actor: any, max_rows: int, template: bool = False
) -> any {
    origins = [
        value if isinstance(value, UUID) else UUID(str(value)) for value in origins
    ];
    cols = _BuildColumns();
    rules = contract['rules'];
    if not rules or max_rows < 1 {
        raise ValueError('Empty fused region or nonpositive row budget');
    }
    if contract['kind'] == 'linear' {
        rule = rules[0];
        walk = q.cte_ref(
            [q.field('origin_id', q.uuid_type()), q.field('depth', q.int64_type())]
        );
        anchor = _select(
            None,
            [
                (
                    'origin_id',
                    q.slot('origin', q.uuid_type())
                        if template
                        else q.param(q.uuid_type(), origins[0])
                ),
                ('depth', q.int64(0))
            ]
        );
        matches = _native_path(
            cols, cols.col(walk, 'origin_id'), rule['hops'], actor, template
        );
        step = _select(
            walk,
            [
                ('origin_id', cols.col(matches, 'target_id')),
                ('depth', q.add(cols.col(walk, 'depth'), q.int64(1)))
            ],
            joins=[q.cross_join(matches)],
            predicate=_all(
                [
                    _cmp(cols.col(matches, 'arity'), q.int64(1)),
                    _cmp(
                        cols.col(matches, 'arch_type'),
                        q.slot('source_type', q.text_type())
                            if template
                            else q.text(contract['source_type'])
                    ),
                    _cmp(
                        cols.col(matches, 'arch_module'),
                        q.slot('source_module', q.text_type())
                            if template
                            else q.text(contract['source_module'])
                    ),
                    _cmp(
                        cols.col(walk, 'depth'),
                        q.slot('max_depth', q.int64_type())
                            if template
                            else q.int64(contract['max_origins'] - 1),
                        '<'
                    )
                ]
            )
        );
        q.define_cte(walk, q.union_all(anchor, step), recursive=True);
        body = _path_output(
            cols,
            walk,
            cols.col(walk, 'origin_id'),
            cols.col(walk, 'depth'),
            rule['hops'],
            0,
            actor,
            template
        );
    } else {
        bodies: list = [];
        for (index, rule) in enumerate(rules) {
            seed = q.unnest(
                q.slot('origins_' + str(index), q.array_type(q.uuid_type())),
                q.field('origin_id', q.uuid_type()),
                q.field('origin_order', q.int64_type())
            )
                if template
                else q.values(
                    [q.field('origin_id', q.uuid_type())],
                    [[q.param(q.uuid_type(), origins[index])]]
                ).as_source();
            bodies.append(
                _path_output(
                    cols,
                    seed,
                    cols.col(seed, 'origin_id'),
                    q.sub(cols.col(seed, 'origin_order'), q.int64(1))
                        if template
                        else q.int64(0),
                    rule['hops'],
                    index,
                    actor,
                    template
                )
            );
        }
        body = _union(bodies);
    }
    ordered = q.ordered(
        body,
        [
            q.asc(q.output(q.field('slot', q.int64_type()))),
            q.asc(q.output(q.field('depth', q.int64_type()))),
            q.asc(q.output(q.field('ord', q.nullable(q.int64_type()))))
        ],
        limit=q.slot('row_limit', q.int64_type()) if template else max_rows + 1
    );
    return q.compile_sql(ordered);
}
