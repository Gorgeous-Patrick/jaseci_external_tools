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
    SliceOutputBranch,
    SliceIdentityMap,
    SliceBorrowedMap,
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
    RegionFrontier,
    DagFeed,
    DagCustomTweet,
    DagProfile,
    DagTweet,
    DagPost,
    DagFollow
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
    project: str,
    uid: UUID,
    wlk: any,
    enabled: bool,
    strict_cache: bool = False,
    actor: str = '',
    executor: str = 'process'
) -> tuple {
    ctx = region_context(project);
    try {
        if actor {
            ctx.set_user_root(actor);
        }
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
                ctx, max_length=2048, mode=executor, workers=1, fused_sql=enabled
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


test "One cross ability query composes root and both collect paths with duplicate native visits" {
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
        fused = region_run(project, uid, RegionFrontier(), True, True);
        assert plain[0] == [31, 31] and fused[0] == plain[0];
        assert fused[1]['fusion']['region_queries'] == 1 , str(fused[1]);
        assert fused[1]['fusion']['region_cache_paths'] == 3;
        assert fused[1]['fusion']['fallback_resolver_calls'] == 0;
        assert any(
            r.get('kind') == 'static_interability_dag' and len(r.get('paths', [])) == 3
            for r in fused[1]['fusion']['regions']
        );
    } finally {
        JacRuntime.exec_ctx = old;
    }
}

test "Real Root fanout and multihop feed preserve FIFO duplicates empties and native exit" {
    import from jaclang.runtime.archetype { Root, AccessLevel }
    old = JacRuntime.exec_ctx;
    try {
        for size in (0, 1, 2) {
            project = region_project();
            ctx = region_context(project);
            try {
                origin = Root();
                anchor: any = origin.__jac__;
                anchor.persistent = True;
                setattr(anchor, 'root', anchor.id);
                ctx.mem.put(anchor);
                uid = anchor.id;
                ctx.set_user_root(str(uid));
                other = DagProfile();
                # Not a direct root child: only reached by Follow.
                leaf = DagTweet(value=20);
                other +>:DagPost:+> leaf;
                for i in range(size) {
                    profile = DagProfile();
                    origin ++> profile;
                    profile +>:DagPost:+> DagTweet(value=i);
                    profile +>:DagFollow:+> other;
                }
                hidden = DagTweet(value=999);
                denied: any = hidden.__jac__;
                denied.persistent = True;
                setattr(denied, 'root', UUID(int=123456));
                denied.own_access().all = AccessLevel.NO_ACCESS;
                ctx.mem.put(denied);
                other +>:DagPost:+> hidden;
            } finally {
                ctx.close();
            }
            plain = region_run(project, uid, DagFeed(), False, actor=str(uid));
            fused = region_run(project, uid, DagFeed(), True, True, actor=str(uid));
            assert plain[0]
                == [([] if size == 0 else [0, 20] if size == 1 else [0, 20, 1, 20])];
            assert fused[0] == plain[0] , str(fused[0]);
            assert fused[1]['fusion']['region_queries'] == 1 , str(fused[1]);
            assert fused[1]['fusion']['region_cache_paths'] == 1 + size * 2;
            assert fused[1]['fusion']['fallback_resolver_calls'] == 0;
        }
    } finally {
        JacRuntime.exec_ctx = old;
    }
}

test "DAG overflow and altered entry dispatch never publish partial native paths" {
    import from types { SimpleNamespace }
    old = JacRuntime.exec_ctx;
    try {
        project = region_project();
        ctx = region_context(project);
        try {
            start = RegionFrontRoot();
            hub = RegionFrontHub();
            root ++> start;
            start +>:RegionFrontEdge:+> hub;
            hub +>:RegionFrontLeft:+> RegionC(value=1);
            hub +>:RegionFrontRight:+> RegionC(value=2);
            uid = start.__jac__.id;
        } finally {
            ctx.close();
        }
        ctx = region_context(project);
        try {
            wlk = RegionFrontier();
            arch = JacTTGGenerator._find_walker_ast_node(RegionFrontier);
            assert arch is not None;
            spec = compile_checkpoint_plan(arch);
            graph = checkpoint_graph(spec, RegionFrontier);
            scope = SimpleNamespace(path=[ctx.mem.get(uid)], ignores=[]);
            for altered in (False, True) {
                import from contextlib { nullcontext }
                metrics: dict = {
                    'queries': 0,
                    'cache_paths': 0,
                    'cache_empty_paths': 0,
                    'regions': []
                };
                callback = SimpleNamespace(trigger=RegionFrontier);
                change = patch.object(RegionFrontHub, '_jac_entry_funcs_', [callback])
                    if altered
                    else nullcontext();
                with change, patch(
                    'jaclang.runtime.ttg_region_dag.publish_paths',
                    side_effect=AssertionError('partial publication')
                ) {
                    result = resolve_interability_region(
                        ctx.mem,
                        graph,
                        wlk,
                        scope,
                        spec['entries']['start'],
                        {'id': uid, 'node_type': RegionFrontRoot},
                        [],
                        None,
                        2 if not altered else 20,
                        metrics
                    );
                }
                assert result is None and metrics['cache_paths'] == 0;
                assert metrics['queries'] == (0 if altered else 1);
                assert 'dispatch' in metrics['region_fallback_reason']
                    if altered
                    else 'budget' in metrics['region_fallback_reason'];
            }
        } finally {
            ctx.close();
        }
    } finally {
        JacRuntime.exec_ctx = old;
    }
}

test "DAG inline descendant ACL proof rejects before publication without invoking hooks" {
    import from types { SimpleNamespace }
    import from jaclang.runtime.archetype { Root }
    old = JacRuntime.exec_ctx;
    try {
        project = region_project();
        ctx = region_context(project);
        try {
            actor: any = Root().__jac__;
            actor.persistent = True;
            setattr(actor, 'root', actor.id);
            ctx.mem.put(actor);
            custom: any = DagCustomTweet().__jac__;
            custom.persistent = True;
            setattr(custom, 'root', actor.id);
            ctx.mem.put(custom);
            uid = actor.id;
        } finally {
            ctx.close();
        }
        ctx = region_context(project);
        try {
            ctx.set_user_root(str(uid));
            wlk = DagFeed();
            arch = JacTTGGenerator._find_walker_ast_node(DagFeed);
            assert arch is not None;
            spec = compile_checkpoint_plan(arch);
            graph = checkpoint_graph(spec, DagFeed);
            scope = SimpleNamespace(path=[ctx.mem.get(uid)], ignores=[]);
            metrics: dict = {
                'queries': 0,
                'cache_paths': 0,
                'cache_empty_paths': 0,
                'regions': []
            };
            with patch(
                'jaclang.runtime.ttg_region_dag.publish_paths',
                side_effect=AssertionError('publication')
            ) {
                result = resolve_interability_region(
                    ctx.mem,
                    graph,
                    wlk,
                    scope,
                    spec['entries']['run'],
                    {'id': uid, 'node_type': Root},
                    [],
                    ctx.user_root,
                    20,
                    metrics
                );
            }
            assert result is None
                and metrics['queries'] == 1
                and metrics['cache_paths'] == 0;
            assert 'ACL catalog' in metrics['region_fallback_reason'];
        } finally {
            ctx.close();
        }
    } finally {
        JacRuntime.exec_ctx = old;
    }
}


test "Access slice native thread preserves output branches identities and rejects borrowed maps" {
    import sys;
    if os.environ.get('TTG_REQUIRE_GIL_OFF') == '1' {
        assert not sys._is_gil_enabled();
    }
    old = JacRuntime.exec_ctx;
    try {
        project = region_project();
        ids = region_chain(project, 5);
        plain = SliceOutputBranch();
        optimized = SliceOutputBranch();
        region_run(project, ids[0], plain, False, executor='thread');
        observed = region_run(
            project, ids[0], optimized, True, True, executor='thread'
        );
        assert optimized.total == plain.total == 5;
        assert optimized.first == plain.first == False;
        assert observed[1]['fusion']['region_queries'] == 1;
        first = SliceIdentityMap();
        second = SliceIdentityMap();
        region_run(project, ids[0], first, False, executor='thread');
        diagnostic = region_run(
            project, ids[0], SliceIdentityMap(), True, executor='thread'
        );
        assert diagnostic[1]['fusion']['region_queries'] == 1 , str(
            diagnostic[1]['fusion']
        );
        observed = region_run(project, ids[0], second, True, True, executor='thread');
        assert first.depths == second.depths == {ids[-1].hex: 0};
        assert observed[1]['fusion']['region_queries'] == 1;
        borrowed: dict[str, int] = {};
        third = SliceBorrowedMap(depths=borrowed);
        observed = region_run(project, ids[0], third, True, executor='thread');
        assert len(borrowed) == 5;
        assert observed[1]['fusion']['region_queries'] == 0;
        assert 'Output map ownership is unproved; a fresh dominating allocation is required'
            in observed[1]['fusion']['region_fallback_reasons'];
        def fake_jid(value: any) -> str {
            return 'shadowed';
        }
        with patch.dict(
            vars(sys.modules[SliceIdentityMap.__module__]), {'jid': fake_jid}
        ) {
            shadowed = SliceIdentityMap();
            rejected = region_run(project, ids[0], shadowed, True, executor='thread');
            assert rejected[1]['fusion']['region_queries'] == 0;
            assert 'Identity helper binding is shadowed'
                in rejected[1]['fusion']['region_fallback_reasons'];
            assert shadowed.depths == {'shadowed': 0};
        }
        if os.environ.get('TTG_REQUIRE_GIL_OFF') == '1' {
            assert not sys._is_gil_enabled();
        }
    } finally {
        JacRuntime.exec_ctx = old;
    }
}

test "Output tree thread filtered branches preserve output and loop visit caches" {
    import sys;
    import sysconfig;
    if os.environ.get('TTG_REQUIRE_GIL_OFF') == '1' {
        assert sysconfig.get_config_var('Py_GIL_DISABLED') == 1;
        assert not sys._is_gil_enabled();
    }
    import from .fixtures.ttg_region_walkers {
        OutputFolder,
        OutputContains,
        OutputTree
    }
    project = region_project();
    ctx = region_context(project);
    nodes = [OutputFolder(name=str(i), trashed=i == 3) for i in range(8)];
    root ++> nodes[0];
    for (a, b) in [(0, 1), (0, 2), (0, 3), (1, 4), (1, 5), (2, 6), (3, 7)] {
        nodes[a] +>:OutputContains:+> nodes[b];
    }
    uid = nodes[0].__jac__.id;
    ctx.close();
    baseline = OutputTree();
    baseline_result = region_run(project, uid, baseline, False, executor='thread');
    fused = OutputTree();
    result = region_run(project, uid, fused, True, executor='thread');
    assert [(e.id, e.name, e.depth, e.path) for e in fused.entries]
        == [(e.id, e.name, e.depth, e.path) for e in baseline.entries];
    assert [e.path for e in fused.entries]
        == ['0', '0/1', '0/1/4', '0/1/5', '0/2', '0/2/6'];
    assert result[1]['fusion']['region_queries'] == 1 , str(result[1]);
    assert result[1]['fusion']['region_cache_paths'] == 6 , str(result[1]);
    strict = OutputTree();
    strict_result = region_run(project, uid, strict, True, True, executor='thread');
    assert [e.path for e in strict.entries] == [e.path for e in baseline.entries];
    assert strict_result[1]['fusion']['region_queries'] == 1;
    if os.environ.get('TTG_REQUIRE_GIL_OFF') == '1' {
        assert not sys._is_gil_enabled();
    }
}

test "Output tree refuses cycle row overflow and malformed predicate atomically" {
    import from types { SimpleNamespace }
    import from contextlib { nullcontext }
    import from .fixtures.ttg_region_walkers {
        OutputFolder,
        OutputContains,
        OutputTree
    }
    for variant in ('cycle', 'overflow', 'malformed', 'foreign_exit') {
        project = region_project();
        ctx = region_context(project);
        a = OutputFolder(name='a');
        b = OutputFolder(name='b');
        root ++> a;
        a +>:OutputContains:+> b;
        if variant == 'cycle' {
            b +>:OutputContains:+> a;
        }
        uid = a.__jac__.id;
        bid = b.__jac__.id;
        ctx.close();
        ctx = region_context(project);
        try {
            if variant == 'malformed' {
                ctx.mem.read_barrier();
                store: any = ctx.mem.store;
                store.rows(
                    "UPDATE anchors SET props=jsonb_set(props,'{archetype,trashed}',CAST(:value AS jsonb)) WHERE id=:id",
                    {'id': str(bid), 'value': json.dumps('false')}
                );
            }
            origin = ctx.mem.get(uid);
            wlk = OutputTree();
            arch = JacTTGGenerator._find_walker_ast_node(OutputTree);
            assert arch is not None;
            spec = compile_checkpoint_plan(arch);
            graph = checkpoint_graph(spec, OutputTree);
            scope: any = SimpleNamespace(path=[origin], ignores=[]);
            metrics: dict = {
                'queries': 0,
                'regions': [],
                'cache_paths': 0,
                'cache_empty_paths': 0
            };
            extra_exit = patch.object(OutputTree, '_jac_exit_funcs_', [SimpleNamespace(name='foreign', trigger=OutputFolder)]) if variant == 'foreign_exit' else nullcontext();
            with extra_exit, patch(
                'jaclang.runtime.ttg_templates.publish_paths',
                side_effect=AssertionError('partial publication')
            ) {
                result = resolve_interability_region(
                    ctx.mem,
                    graph,
                    wlk,
                    scope,
                    spec['entries']['walk'],
                    {'id': uid, 'node_type': OutputFolder},
                    [],
                    None,
                    1 if variant == 'overflow' else 20,
                    metrics
                );
            }
            assert result is None;
            reason: str = metrics['region_fallback_reason'];
            assert (
                'cycle' in reason
                    if variant == 'cycle'
                    else (
                        'budget' in reason
                            if variant == 'overflow'
                            else ('exit dispatch' in reason if variant == 'foreign_exit' else 'Malformed' in reason)
                    )
            ) , reason;
            assert metrics['cache_paths'] == 0;
        } finally {
            ctx.close();
        }
    }
}
