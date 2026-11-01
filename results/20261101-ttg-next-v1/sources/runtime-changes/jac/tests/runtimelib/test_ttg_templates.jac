"""DB-free emitted SQL, bind contracts and sequential queued-state tests."""
import json;
import from unittest.mock { patch }
import from uuid { UUID }
import jaclang.sql as q;
import from jaclang.runtime.ttg_templates {
    compile_templates,
    hydrate_templates,
    bind_template,
    select_template,
    template_metrics
}
import from jaclang.runtime.ttg_dependencies {
    analyze_walker_dependencies,
    TraceEvent,
    compile_checkpoint_plan,
    checkpoint_graph
}
import from jaclang.runtime.ttg_frontier { collect_frontier }
import from .fixtures.ttg_frontier_walkers {
    FrontierWalk,
    FrontierBranch,
    FrontierDuplicate,
    FrontierCancel
}


def entry_current(graph: any, ability: str, uid: str = 'b') -> tuple {
    event = TraceEvent(
        id=len(graph.events),
        kind='entry',
        ability=ability,
        line=0,
        next_id=graph.entries[ability]
    );
    graph.events.append(event);
    current = {
        'id': uid,
        'node_type': FrontierBranch,
        'facts': {'value': 0},
        'transition_state': {'self.i': 0}
    };
    return (event, current);
}

test "Queued prefix evolves scalar state once in FIFO order" {
    graph = analyze_walker_dependencies(FrontierWalk);
    (event, current) = entry_current(graph, 'branch');
    pending = [
        {'id': 'c', 'node_type': FrontierBranch},
        {'id': 'd', 'node_type': FrontierBranch}
    ];
    (prediction, demands) = collect_frontier(graph, current, event, pending, 20);
    assert [a['id'] for (a, e) in demands] == ['b', 'c', 'd'] , str(prediction);
    assert [e.hop_chain[0][0] for (a, e) in demands]
        == ['FrontierLeft', 'FrontierRight', 'FrontierRight'];
    assert [a['id'] for a in pending] == ['c', 'd'];
    assert current['transition_state'] == {'self.i': 0};
}

test "Repeated path visits keep distinct site IDs and activations" {
    graph = analyze_walker_dependencies(FrontierDuplicate);
    (event, current) = entry_current(graph, 'branch');
    (prediction, demands) = collect_frontier(
        graph, current, event, [{'id': 'c', 'node_type': FrontierBranch}], 20
    );
    assert [a['id'] for (a, e) in demands] == ['b', 'b', 'c', 'c'];
    assert demands[0][1].id != demands[1][1].id;
    assert demands[0][1].hop_chain == demands[1][1].hop_chain;
}

test "Typed LIMIT binds zero or positive int and rejects bool negative and missing" {
    relation = q.values([q.field('x', q.int64_type())], [[q.int64(1)]]);
    compiled = q.compile_sql(
        q.ordered(relation, [], limit=q.slot('cap', q.int64_type()))
    );
    assert compiled.bind({'cap': 0}).params['cap'] == 0;
    for values in [{'cap': -1}, {'cap': True}, {}, {'cap': 1.2}] {
        rejected = False;
        try {
            compiled.bind(values);
        } except q.SqlError {
            rejected = True;
        }
        assert rejected , str(values);
    }
}

test "Actual compiler checkpoint includes deterministic SQL descriptors" {
    import from jaclang.runtime.ttg { JacTTGGenerator }
    arch = JacTTGGenerator._find_walker_ast_node(FrontierWalk);
    assert arch is not None;
    first = compile_checkpoint_plan(arch);
    second = compile_checkpoint_plan(arch);
    assert first == second;
    assert first['sql_templates']['version'] == 1;
    restored = checkpoint_graph(json.loads(json.dumps(first)), FrontierWalk);
    assert restored.sql_templates['batch']['gated']['_compiled'].sql
        == first['sql_templates']['batch']['gated']['sql'];
    assert 'unnest(' in first['sql_templates']['batch']['open']['sql'];
}

test "Selected hydrated compiled paths bind cold and warm with no SQL AST construction" {
    graph = analyze_walker_dependencies(FrontierWalk);
    template_metrics(True, True);
    emitted = compile_templates(graph.events);
    metrics = template_metrics();
    assert metrics['generation_calls'] == 1;
    assert metrics['emitted_artifact_bytes'] > metrics['emitted_sql_bytes'] > 0;
    bundle = hydrate_templates(json.loads(json.dumps(emitted)));
    template_metrics(True, False);
    with patch.object(q, 'table', side_effect=AssertionError('runtime AST table')) {
        with patch.object(
            q, 'compile_sql', side_effect=AssertionError('runtime SQL renderer')
        ) {
            for warm in (False, True) {
                descriptor = select_template(bundle, 'batch', True);
                values: dict = {
                    'actor_uuid': UUID(int=3),
                    'actor_text': str(UUID(int=3)),
                    'row_limit': 21
                };
                for (slot, site) in enumerate(bundle['sites']) {
                    values['origins_' + str(slot)] = (UUID(int=slot + 1), );
                }
                bound = bind_template(descriptor, values);
                assert bound.sql == descriptor['sql'];
                assert bound.params['row_limit'] == 21;
            }
        }
    }
}

test "Disengage overfetch assumption preserves later queued origin prediction only" {
    graph = analyze_walker_dependencies(FrontierCancel);
    (event, current) = entry_current(graph, 'branch');
    current['facts'] = {'value': 1};
    current['transition_state'] = {'branch::here.value': 1, 'self.entered::list': True};
    pending = [{'id': 'c', 'node_type': FrontierBranch, 'facts': {'value': 0}}];
    (prediction, demands) = collect_frontier(graph, current, event, pending, 20);
    assert [a['id'] for (a, e) in demands] == ['c'] , str(prediction);
}

test "Unknown queued branch state stops before inventing visits" {
    graph = analyze_walker_dependencies(FrontierCancel);
    (event, current) = entry_current(graph, 'branch');
    current['facts'] = {'value': 0};
    current['transition_state'] = {'branch::here.value': 0, 'self.entered::list': True};
    (prediction, demands) = collect_frontier(
        graph, current, event, [{'id': 'unknown', 'node_type': FrontierBranch}], 20
    );
    assert [a['id'] for (a, e) in demands] == ['b'];
    assert not prediction['complete'];
}

test "Compiled cache publication and native consumption do not build SQL and preserve duplicate rows" {
    import from threading { RLock }
    import from unittest.mock { MagicMock }
    import from jaclang.runtime.ttg_templates { publish_paths }
    import from jaclang.runtime.graph_query { GraphQuery, QHop }
    import from jaclang.data.query_planner { _sql_pairs }
    import jaclang.data.query_planner as planner;
    import jaclang.runtime.graph_walk as walk;
    import from .fixtures.ttg_frontier_walkers { FrontierRight, FrontierLeaf }
    graph = analyze_walker_dependencies(FrontierDuplicate);
    bundle = hydrate_templates(compile_templates(graph.events));
    event = next(
        e
        for e in graph.events
        if e.kind == 'visit'
    );
    query = GraphQuery(
        [], hops=[QHop(dir=2, `edge=FrontierRight, nd=FrontierLeaf)]
    ).`visit();
    cache: dict = {};
    mem: any = MagicMock();
    mem._lock = RLock();
    mem.query_cache_get.side_effect = cache.get;
    mem.query_cache_put.side_effect = cache.__setitem__;
    origin = UUID(int=1);
    rows = [
        (UUID(int=2), UUID(int=3), 'FrontierLeaf', FrontierLeaf.__module__),
        (UUID(int=2), UUID(int=4), 'FrontierLeaf', FrontierLeaf.__module__)
    ];
    descriptors = select_template(bundle, 'native', False, event.id);
    with patch.object(planner, '_acl_pushdown_root', return_value=None), patch.object(
        planner, 'access_gated', return_value=False
    ), patch.object(walk, 'access_gated', return_value=False) {
        with patch.object(q, 'table', side_effect=AssertionError('runtime AST')) {
            with patch.object(
                q, 'compile_sql', side_effect=AssertionError('runtime renderer')
            ) {
                with patch.object(
                    planner,
                    'compile_query',
                    side_effect=AssertionError('runtime native builder')
                ) {
                    assert publish_paths(mem, [(query, origin, rows, descriptors)]);
                    (pairs, tail) = _sql_pairs(mem, [origin], query, 1);
                    assert pairs
                        == [(UUID(int=2), UUID(int=3)), (UUID(int=2), UUID(int=4))];
                    assert tail == [];
                    assert publish_paths(mem, [(query, UUID(int=9), [], descriptors)]);
                    assert _sql_pairs(mem, [UUID(int=9)], query, 1) == ([], []);
                    assert mem.store.rows.call_count == 0;
                }
            }
        }
    }
}

test "First future visit after current no-visit ability does not replay queued B" {
    import from .fixtures.ttg_frontier_walkers { FrontierNoVisit, FrontierStart }
    import from jaclang.runtime.ttg_continuation { plan_continuation }
    graph = analyze_walker_dependencies(FrontierNoVisit);
    point = next(
        e.id
        for e in graph.events
        if e.ability == 'start' and e.kind == 'scalar_update'
    );
    pending = [
        {'id': 'b', 'node_type': FrontierBranch},
        {'id': 'c', 'node_type': FrontierBranch}
    ];
    captured: list = [];
    def resolve(active: dict, event: any) -> any {
        if not captured {
            (prediction, demands) = collect_frontier(
                graph, active, event, active['transition_pending'], 20
            );
            captured.extend((a['id'], e.hop_chain[0][0]) for (a, e) in demands);
        }
        return [];
    }
    plan_continuation(
        graph,
        {'id': 'a', 'node_type': FrontierStart},
        point,
        {'self.i': 1},
        pending,
        resolve,
        20,
        resolve_state=True
    );
    assert captured == [('b', 'FrontierLeft'), ('c', 'FrontierRight')] , str(captured);
}

test "Full two-hop compiled cache cannot satisfy a one-hop native prefix" {
    import from threading { RLock }
    import from types { SimpleNamespace }
    import from unittest.mock { MagicMock }
    import from jaclang.runtime.ttg_templates { publish_paths }
    import from jaclang.runtime.graph_query { GraphQuery, QHop }
    import from jaclang.data.query_planner { _sql_pairs }
    import jaclang.data.query_planner as planner;
    import jaclang.runtime.graph_walk as walk;
    import from .fixtures.ttg_frontier_walkers { FrontierRight, FrontierLeaf }
    event = TraceEvent(
        id=0,
        kind='visit',
        ability='branch',
        line=0,
        hop_chain=(
            ('FrontierRight', 'FrontierLeaf', 2),
            ('FrontierRight', 'FrontierLeaf', 2)
        )
    );
    bundle = hydrate_templates(compile_templates([event]));
    query = GraphQuery(
        [],
        hops=[
            QHop(dir=2, `edge=FrontierRight, nd=FrontierLeaf),
            QHop(dir=2, `edge=FrontierRight, nd=FrontierLeaf)
        ]
    ).`visit();
    cache: dict = {};
    mem: any = MagicMock();
    mem._lock = RLock();
    mem.query_cache_get.side_effect = cache.get;
    mem.query_cache_put.side_effect = cache.__setitem__;
    mem.store.rows.return_value = [(UUID(int=2), UUID(int=12))];
    origin = UUID(int=1);
    rows = [(UUID(int=3), UUID(int=23), 'FrontierLeaf', FrontierLeaf.__module__)];
    with patch.object(planner, '_acl_pushdown_root', return_value=None), patch.object(
        planner, 'access_gated', return_value=False
    ), patch.object(walk, 'access_gated', return_value=False) {
        assert publish_paths(
            mem, [(query, origin, rows, select_template(bundle, 'native', False, 0))]
        );
        assert _sql_pairs(mem, [origin], query, 2)[0] == [(UUID(int=3), UUID(int=23))];
        with patch.object(
            planner,
            'compile_query',
            return_value=SimpleNamespace(sql='prefix-one-hop', params={}, residual={})
        ) as build {
            assert _sql_pairs(mem, [origin], query, 1)[0]
                == [(UUID(int=2), UUID(int=12))];
            assert build.call_count == 1;
            assert mem.store.rows.call_count == 1;
        }
    }
}

test "Compiled frontier overflow publishes no partial native cache" {
    import from threading { RLock }
    import from unittest.mock { MagicMock }
    import from jaclang.runtime.ttg_frontier { resolve_frontier }
    import jaclang.data.query_planner as planner;
    import jaclang.runtime.graph_walk as walk;
    graph = analyze_walker_dependencies(FrontierDuplicate);
    graph.sql_templates = hydrate_templates(compile_templates(graph.events));
    (event, current) = entry_current(graph, 'branch', str(UUID(int=1)));
    cache: dict = {};
    mem: any = MagicMock();
    mem._lock = RLock();
    mem.query_cache_get.side_effect = cache.get;
    mem.query_cache_put.side_effect = cache.__setitem__;
    mem.store.rows.return_value = [('truncated-row', ), ('truncated-row', )];
    metrics = {
        'queries': 0,
        'overflow': 0,
        'cache_paths': 0,
        'cache_empty_paths': 0,
        'regions': []
    };
    with patch.object(planner, '_acl_pushdown_root', return_value=None), patch.object(
        walk, 'access_gated', return_value=False
    ) {
        assert resolve_frontier(
            mem, FrontierDuplicate(), graph, current, event, [], None, 1, metrics
        )
            is None;
    }
    assert metrics['overflow'] == 1;
    assert not any(
        key[0] in ('pairs', 'ttg_path', 'ttg_compiled_pairs_v1') for key in cache
    );
}

test "Emitted type token proof rejects alias spelling before query selection" {
    import from jaclang.runtime.ttg_frontier { template_type_matches }
    import from .fixtures.ttg_frontier_walkers { FrontierRight, FrontierLeaf }
    assert template_type_matches(FrontierRight, 'FrontierRight');
    assert template_type_matches(FrontierLeaf, 'FrontierLeaf');
    assert not template_type_matches(FrontierRight, 'LinkAlias');
    assert not template_type_matches(FrontierLeaf, 'TargetAlias');
    assert template_type_matches(None, None);
    assert not template_type_matches(None, 'FrontierLeaf');
    assert not template_type_matches(1, 'FrontierLeaf');
}
