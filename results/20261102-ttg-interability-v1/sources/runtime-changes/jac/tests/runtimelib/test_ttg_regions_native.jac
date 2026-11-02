"""Persistent static regions: native execution, exact guards/cache and refusals."""
import json;
import os;
import from pathlib { Path }
import from tempfile { mkdtemp }
import from uuid { UUID }
import from unittest.mock { patch }
import from jaclang.runtime.context { ExecutionContext }
import from jaclang.runtime.runtime { JacRuntime }
import from jaclang.runtime.ttg_dependency_prefetch { dependency_prefetch }
import from jaclang.runtime.ttg_dependencies {
    compile_checkpoint_plan,
    checkpoint_graph
}
import from jaclang.runtime.ttg { JacTTGGenerator }
import from jaclang.runtime.ttg_regions { resolve_interability_region }
import from .fixtures.ttg_region_walkers {
    RegionItem,
    RegionNext,
    RegionTraverse,
    RegionReduction,
    RegionCounterOutput,
    RegionAssign,
    RegionA,
    RegionB,
    RegionC,
    RegionAB,
    RegionBC,
    RegionGuard,
    RegionFrontRoot,
    RegionFrontHub,
    RegionFrontEdge,
    RegionFrontLeft,
    RegionFrontRight,
    RegionFrontier
}


def region_project -> str {
    parent = Path('/tmp/ttg-interability-fixtures');
    parent.mkdir(parents=True, exist_ok=True);
    return mkdtemp(prefix='case-', dir=str(parent));
}


def region_context(project: str) -> any {
    ctx = ExecutionContext(
        base_path_dir=project, full_target_path=str(Path(project, 'region.jac'))
    );
    JacRuntime.exec_ctx = ctx;
    return ctx;
}


def region_chain(
    project: str, count: int, fanout: bool = False, cycle: bool = False
) -> list {
    ctx = region_context(project);
    try {
        items = [RegionItem(value=i) for i in range(count)];
        root ++> items[0];
        for i in range(count - 1) {
            items[i] +>:RegionNext:+> items[i + 1];
        }
        if fanout {
            items[0] +>:RegionNext:+> items[2];
        }
        if cycle {
            items[-1] +>:RegionNext:+> items[0];
        }
        return [n.__jac__.id for n in items];
    } finally {
        ctx.close();
    }
}


def region_run(
    project: str, uid: UUID, wlk: any, enabled: bool, strict_cache: bool = False
) -> tuple {
    ctx = region_context(project);
    try {
        origin = ctx.mem.get(uid).archetype;
        calls: list = [];
        store: any = ctx.mem.store;
        original: any = store.rows;
        def capture(sql: str, params: dict) -> list {
            rows = original(sql, params);
            calls.append({'sql': sql, 'params': params, 'rows': len(rows)});
            return rows;
        }
        import jaclang.data.query_planner as planner;
        import from contextlib { nullcontext }
        native_reads: list = [];
        original_pairs: any = planner._sql_pairs;
        def pairs(mem: any, origin_ids: list, query: any, upto: int) -> any {
            before = len(calls);
            result = original_pairs(mem, origin_ids, query, upto);
            native_reads.append(
                {
                    'origins': [str(x) for x in origin_ids],
                    'upto': upto,
                    'sql_calls': len(calls) - before
                }
            );
            return result;
        }
        compiler_guard = patch.object(
            planner, 'compile_query', side_effect=AssertionError('native SQL rebuild')
        )
            if strict_cache
            else nullcontext();
        topology_guard = patch.object(planner, '_topology_node_ids', return_value=None)
            if strict_cache
            else nullcontext();
        with patch.object(store, 'rows', side_effect=capture), patch.object(
            planner, '_sql_pairs', side_effect=pairs
        ), compiler_guard, topology_guard {
            with dependency_prefetch(
                ctx, max_length=2048, mode='process', workers=1, fused_sql=enabled
            ) as run {
                origin spawn wlk;
            }
        }
        assert not run.errors , str(run.errors);
        summary = run.summary();
        if strict_cache {
            assert native_reads
                and all(read['sql_calls'] == 0 for read in native_reads) , str(
                native_reads
            );
        }
        evidence = os.environ.get('TTG_INTERABILITY_EVIDENCE');
        if evidence {
            with open(evidence, 'a') as output {
                output.write(
                    json.dumps(
                        {
                            'wlk': type(wlk).__name__,
                            'enabled': enabled,
                            'reports': wlk.reports,
                            'calls': calls,
                            'native_pair_reads': native_reads,
                            'strict_cache': strict_cache,
                            'summary': summary
                        },
                        **{'default': str}
                    )
                        + '\n'
                );
            }
        }
        return (wlk.reports, summary, calls);
    } finally {
        ctx.close();
    }
}

test "Actual no-counter native chain uses one static query and ordered empty cache" {
    old = JacRuntime.exec_ctx;
    try {
        project = region_project();
        ids = region_chain(project, 8);
        plain = region_run(project, ids[0], RegionTraverse(), False);
        fused = region_run(project, ids[0], RegionTraverse(), True, True);
        assert plain[0] == list(range(8)) and fused[0] == plain[0];
        assert fused[1]['fusion']['region_queries'] == 1 , str(fused[1]);
        assert fused[1]['fusion']['region_cache_paths'] == 8;
        assert fused[1]['fusion']['cache_empty_paths'] >= 1;
        assert fused[1]['fusion']['region_origins'] == 8;
        assert fused[1]['fusion']['payload_dispatches'] == 1;
        counted = RegionCounterOutput();
        observed = region_run(project, ids[0], counted, True, True);
        assert counted.visited == 8 and observed[0] == fused[0];
        assert observed[1]['fusion']['region_queries'] == 1;
        # Actual native _sql_pairs calls are measured by region_run strict_cache; no SQL-spelling heuristic.
    } finally {
        JacRuntime.exec_ctx = old;
    }
}

test "Finite A B C true false exact native reports and guard remains inside SQL" {
    old = JacRuntime.exec_ctx;
    try {
        for active in (True, False) {
            project = region_project();
            ctx = region_context(project);
            try {
                a = RegionA();
                b = RegionB(active=active);
                c = RegionC(value=17);
                root ++> a;
                a +>:RegionAB:+> b;
                b +>:RegionBC:+> c;
                uid = a.__jac__.id;
            } finally {
                ctx.close();
            }
            plain = region_run(project, uid, RegionGuard(), False);
            fused = region_run(project, uid, RegionGuard(), True, True);
            assert plain[0] == ([17] if active else []);
            assert fused[0] == plain[0];
            assert fused[1]['fusion']['region_queries'] == 1 , str(fused[1]);
            assert fused[1]['fusion']['region_cache_paths'] == (2 if active else 1);
            selected = [
                call
                for call in fused[2]
                if 'jsonb_typeof' in call['sql'] and 'origin_id' in call['sql']
            ];
            assert len(selected) == 1 , str(selected);
        }
    } finally {
        JacRuntime.exec_ctx = old;
    }
}

test "Fanout uses native fallback without changing duplicate FIFO visits" {
    old = JacRuntime.exec_ctx;
    try {
        project = region_project();
        ids = region_chain(project, 3, fanout=True);
        plain = region_run(project, ids[0], RegionTraverse(), False);
        fused = region_run(project, ids[0], RegionTraverse(), True);
        assert fused[0] == plain[0];
        assert fused[1]['fusion']['region_fallbacks'] >= 1;
        assert fused[1]['fusion']['region_fallback_reasons'].get(
            'Static region fanout requires native fallback', 0
        )
            >= 1;
    } finally {
        JacRuntime.exec_ctx = old;
    }
}

test "Cycle and overflow refuse atomically before any native cache publication" {
    import from types { SimpleNamespace }
    old = JacRuntime.exec_ctx;
    try {
        for cycle in (False, True) {
            project = region_project();
            ids = region_chain(project, 4, cycle=cycle);
            ctx = region_context(project);
            try {
                wlk = RegionTraverse();
                origin = ctx.mem.get(ids[0]);
                arch = JacTTGGenerator._find_walker_ast_node(RegionTraverse);
                assert arch is not None;
                spec = compile_checkpoint_plan(arch);
                graph = checkpoint_graph(spec, RegionTraverse);
                scope = SimpleNamespace(path=[origin], ignores=[]);
                metrics: dict = {
                    'queries': 0,
                    'regions': [],
                    'cache_paths': 0,
                    'cache_empty_paths': 0
                };
                with patch(
                    'jaclang.runtime.ttg_regions.publish_paths',
                    side_effect=AssertionError('partial cache')
                ) {
                    result = resolve_interability_region(
                        ctx.mem,
                        graph,
                        wlk,
                        scope,
                        spec['entries']['walk'],
                        {'id': ids[0], 'node_type': RegionItem},
                        [],
                        None,
                        20 if cycle else 2,
                        metrics
                    );
                }
                assert result is None;
                assert 'cycle' in metrics['region_fallback_reason']
                    if cycle
                    else 'budget' in metrics['region_fallback_reason'];
            } finally {
                ctx.close();
            }
        }
    } finally {
        JacRuntime.exec_ctx = old;
    }
}


test "Null missing and wrong Boolean storage reject statically but retain native behavior" {
    old = JacRuntime.exec_ctx;
    try {
        for variant in ('null', 'missing', 'string') {
            project = region_project();
            ctx = region_context(project);
            try {
                a = RegionA();
                b = RegionB(active=True);
                c = RegionC(value=23);
                root ++> a;
                a +>:RegionAB:+> b;
                b +>:RegionBC:+> c;
                uid = a.__jac__.id;
                bid = b.__jac__.id;
            } finally {
                ctx.close();
            }
            ctx = region_context(project);
            try {
                ctx.mem.read_barrier();
                store: any = ctx.mem.store;
                if variant == 'missing' {
                    store.rows(
                        "UPDATE anchors SET props = props #- '{archetype,active}' WHERE id=:id",
                        {'id': str(bid)}
                    );
                } else {
                    store.rows(
                        "UPDATE anchors SET props=jsonb_set(props,'{archetype,active}',CAST(:value AS jsonb)) WHERE id=:id",
                        {
                            'id': str(bid),
                            'value': 'null' if variant == 'null' else json.dumps('true')
                        }
                    );
                }
            } finally {
                ctx.close();
            }
            plain = region_run(project, uid, RegionGuard(), False);
            ctx = region_context(project);
            try {
                ctx.mem.read_barrier();
                store: any = ctx.mem.store;
                if variant == 'missing' {
                    store.rows(
                        "UPDATE anchors SET props = props #- '{archetype,active}' WHERE id=:id",
                        {'id': str(bid)}
                    );
                } else {
                    store.rows(
                        "UPDATE anchors SET props=jsonb_set(props,'{archetype,active}',CAST(:value AS jsonb)) WHERE id=:id",
                        {
                            'id': str(bid),
                            'value': 'null' if variant == 'null' else json.dumps('true')
                        }
                    );
                }
            } finally {
                ctx.close();
            }
            fused = region_run(project, uid, RegionGuard(), True);
            assert fused[0] == plain[0];
            assert fused[1]['fusion']['region_fallbacks'] >= 1;
            assert 'Malformed' in fused[1]['fusion']['region_fallback_reason'];
        }
    } finally {
        JacRuntime.exec_ctx = old;
    }
}


test "Output setter and applicable node exit reject before publication" {
    import from types { SimpleNamespace }
    old = JacRuntime.exec_ctx;
    try {
        project = region_project();
        ids = region_chain(project, 3);
        ctx = region_context(project);
        try {
            origin = ctx.mem.get(ids[0]);
            for mode in ('setter', 'exit') {
                wlk = RegionAssign() if mode == 'setter' else RegionTraverse();
                cls: any = type(wlk);
                arch = JacTTGGenerator._find_walker_ast_node(cls);
                assert arch is not None;
                spec = compile_checkpoint_plan(arch);
                graph = checkpoint_graph(spec, cls);
                scope = SimpleNamespace(path=[origin], ignores=[]);
                metrics: dict = {
                    'queries': 0,
                    'regions': [],
                    'cache_paths': 0,
                    'cache_empty_paths': 0
                };
                calls: list = [];
                def forbidden(value: any) -> any {
                    calls.append(value);
                    raise AssertionError('descriptor called');
                }
                if mode == 'setter' {
                    with patch.object(cls, 'sink', property(forbidden, forbidden)), patch(
                        'jaclang.runtime.ttg_regions.publish_paths',
                        side_effect=AssertionError('published')
                    ) {
                        result = resolve_interability_region(
                            ctx.mem,
                            graph,
                            wlk,
                            scope,
                            spec['entries']['walk'],
                            {'id': ids[0], 'node_type': RegionItem},
                            [],
                            None,
                            20,
                            metrics
                        );
                    }
                } else {
                    callback = SimpleNamespace(trigger=cls);
                    with patch.object(RegionItem, '_jac_exit_funcs_', [callback]), patch(
                        'jaclang.runtime.ttg_regions.publish_paths',
                        side_effect=AssertionError('published')
                    ) {
                        result = resolve_interability_region(
                            ctx.mem,
                            graph,
                            wlk,
                            scope,
                            spec['entries']['walk'],
                            {'id': ids[0], 'node_type': RegionItem},
                            [],
                            None,
                            20,
                            metrics
                        );
                    }
                }
                assert result is None and not calls;
                assert metrics['queries'] == 0;
            }
        } finally {
            ctx.close();
        }
    } finally {
        JacRuntime.exec_ctx = old;
    }
}

test "Static process submission respects the remaining payload cap" {
    old = JacRuntime.exec_ctx;
    try {
        project = region_project();
        ids = region_chain(project, 4);
        ctx = region_context(project);
        try {
            origin = ctx.mem.get(ids[0]).archetype;
            assert isinstance(origin, RegionItem);
            wlk = RegionTraverse();
            with dependency_prefetch(
                ctx, max_length=4, mode='process', workers=1, fused_sql=True
            ) as run {
                run.submitted.update(
                    [UUID(int=10001), UUID(int=10002), UUID(int=10003)]
                );
                origin spawn wlk;
            }
            assert not run.errors , str(run.errors);
            assert wlk.reports == [0, 1, 2, 3];
            assert len(run.submitted) == 4 , str(run.summary());
            assert len(set(ids) & run.submitted) == 1;
        } finally {
            ctx.close();
        }
    } finally {
        JacRuntime.exec_ctx = old;
    }
}


test "Authenticated published paths include ordered empty native cache with zero SQL rebuild" {
    import from types { SimpleNamespace }
    import from jaclang.runtime.archetype { Root, AccessLevel }
    import from jaclang.runtime.graph_query { GraphQuery, QHop }
    import from jaclang.runtime.graph_walk { access_gated }
    import from jaclang.data.query_planner { resolve_query_prefix }
    import jaclang.data.query_planner as planner;
    import jaclang.sql as q;
    old = JacRuntime.exec_ctx;
    try {
        project = region_project();
        ctx = region_context(project);
        try {
            reader: any = Root().__jac__;
            reader.persistent = True;
            setattr(reader, 'root', reader.id);
            ctx.mem.put(reader);
            nodes = [RegionItem(value=i) for i in range(3)];
            for item in nodes {
                anchor: any = item.__jac__;
                anchor.persistent = True;
                setattr(anchor, 'root', reader.id);
                anchor.own_access().all = AccessLevel.NO_ACCESS;
                ctx.mem.put(anchor);
            }
            for i in range(2) {
                nodes[i] +>:RegionNext:+> nodes[i + 1];
            }
            ids = [n.__jac__.id for n in nodes];
            reader_id = reader.id;
        } finally {
            ctx.close();
        }
        ctx = region_context(project);
        try {
            ctx.set_user_root(str(reader_id));
            assert access_gated();
            anchors = [ctx.mem.get(uid) for uid in ids];
            wlk = RegionTraverse();
            arch = JacTTGGenerator._find_walker_ast_node(RegionTraverse);
            assert arch is not None;
            spec = compile_checkpoint_plan(arch);
            graph = checkpoint_graph(spec, RegionTraverse);
            scope = SimpleNamespace(path=[anchors[0]], ignores=[]);
            metrics: dict = {
                'queries': 0,
                'regions': [],
                'cache_paths': 0,
                'cache_empty_paths': 0
            };
            with patch.object(q, 'table', side_effect=AssertionError('runtime AST')), patch.object(
                q, 'compile_sql', side_effect=AssertionError('runtime renderer')
            ) {
                result = resolve_interability_region(
                    ctx.mem,
                    graph,
                    wlk,
                    scope,
                    spec['entries']['walk'],
                    {'id': ids[0], 'node_type': RegionItem},
                    [],
                    ctx.user_root,
                    20,
                    metrics
                );
                assert result is not None , str(metrics);
                store: any = ctx.mem.store;
                with patch.object(
                    store, 'rows', side_effect=AssertionError('native cache requery')
                ), patch.object(planner, '_topology_node_ids', return_value=None) {
                    for (i, anchor) in enumerate(anchors) {
                        query = GraphQuery(
                            anchor.archetype,
                            hops=[QHop(dir=2, `edge=RegionNext, nd=RegionItem)]
                        ).`visit();
                        assert resolve_query_prefix(ctx.mem, query, 1)
                            == ([ids[i + 1]] if i < 2 else []);
                    }
                }
            }
            assert metrics['queries'] == 1 and metrics['cache_paths'] == 3;
        } finally {
            ctx.close();
        }
    } finally {
        JacRuntime.exec_ctx = old;
    }
}


test "A later independent collect region batches both paths once after an untyped root" {
    old = JacRuntime.exec_ctx;
    try {
        project = region_project();
        ctx = region_context(project);
        try {
            start = RegionFrontRoot();
            hub = RegionFrontHub();
            root ++> start;
            start +>:RegionFrontEdge:+> hub;
            leaf = RegionC(value=31);
            hub +>:RegionFrontLeft:+> leaf;
            hub +>:RegionFrontRight:+> leaf;
            uid = start.__jac__.id;
        } finally {
            ctx.close();
        }
        plain = region_run(project, uid, RegionFrontier(), False);
        fused = region_run(project, uid, RegionFrontier(), True);
        assert plain[0] == [31, 31] and fused[0] == plain[0];
        assert fused[1]['fusion']['template_queries'] == 2 , str(fused[1]);
        assert fused[1]['fusion']['frontier_region_attempts'] == 2;
        assert fused[1]['fusion']['fallback_resolver_calls'] == 0;
        assert any(
            r.get('kind') == 'batch' and len(r.get('demands', [])) == 2
            for r in fused[1]['fusion']['regions']
        );
    } finally {
        JacRuntime.exec_ctx = old;
    }
}
