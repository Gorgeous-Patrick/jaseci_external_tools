"""Owned PostgreSQL integration: fused SQL, exact native cache and traversal."""
import from pathlib { Path }
import from tempfile { mkdtemp }
import from unittest.mock { patch }
import from uuid { UUID }
import json;
import os;
import from hashlib { sha256 }
import from jaclang.runtime.runtime { JacRuntime, JacRuntimeInterface }
import from jaclang.runtime.context { ExecutionContext }
import from jaclang.runtime.ttg_dependency_prefetch { dependency_prefetch }
import from jaclang.runtime.ttg_fusion_sql { compile_fused_region }
import from jaclang.runtime.graph_query { GraphQuery, QHop }
import from jaclang.data.sqlcompile { compile_query }
import from .fixtures.ttg_fusion_walkers {
    FusedItem,
    FusedNext,
    FusedHub,
    FusedLeaf,
    FusedLeft,
    FusedRight,
    FusedWalk,
    FusedBatch
}


def fusion_project -> str {
    parent = Path('/tmp/ttg-plus-native-v1/fixtures');
    parent.mkdir(parents=True, exist_ok=True);
    return mkdtemp(prefix='case-', dir=str(parent));
}


def fusion_context(project: str) -> ExecutionContext {
    ctx = ExecutionContext(
        base_path_dir=project, full_target_path=str(Path(project, 'fusion.jac'))
    );
    JacRuntime.exec_ctx = ctx;
    return ctx;
}


def fusion_seed(
    project: str, count: int, fanout: bool = False, cycle: bool = False
) -> list {
    ctx = fusion_context(project);
    try {
        items = [FusedItem(value=index) for index in range(count)];
        root ++> items[0];
        for index in range(count - 1) {
            items[index] +>:FusedNext:+> items[index + 1];
        }
        if fanout {
            items[0] +>:FusedNext:+> items[2];
        }
        if cycle {
            items[-1] +>:FusedNext:+> items[0];
        }
        return [item.__jac__.id for item in items];
    } finally {
        ctx.close();
    }
}


def fusion_run(
    project: str, uid: UUID, enabled: bool, limit: int = 20, mode: str = ''
) -> tuple {
    ctx = fusion_context(project);
    try {
        anchor = ctx.mem.get(uid);
        assert anchor is not None;
        origin = anchor.archetype;
        assert isinstance(origin, FusedItem);
        wlk = FusedWalk(limit=limit);
        store: any = ctx.mem.store;
        original_rows: any = store.rows;
        observed_rows: list = [];
        def capture(sql: str, params: dict) -> list {
            result = original_rows(sql, params);
            observed_rows.append(
                {
                    'sql': sql,
                    'params': params,
                    'row_count': len(result),
                    'sql_sha256': sha256(sql.encode()).hexdigest()
                }
            );
            return result;
        }
        with patch.object(store, 'rows', side_effect=capture) as rows {
            with dependency_prefetch(
                ctx, max_length=2048, mode=mode, fused_sql=enabled
            ) as run {
                origin spawn wlk;
            }
            assert not run.errors , str(run.summary());
            evidence = os.environ.get('TTG_PLUS_NATIVE_EVIDENCE');
            if evidence {
                with open(evidence, 'a') as output {
                    output.write(
                        json.dumps(
                            {
                                'kind': 'functional_native_store_rows',
                                'fusion': enabled,
                                'mode': mode,
                                'limit': limit,
                                'reports': wlk.reports,
                                'visited': wlk.visited,
                                'store_rows_calls': observed_rows,
                                'summary': run.summary()
                            },
                            **{'default': str}
                        )
                            + '\n'
                    );
                }
            }
            return (wlk.reports, wlk.visited, run.summary(), rows.call_count);
        }
    } finally {
        ctx.close();
    }
}


test "Fused cold chain collapses path SQL and preserves exact reports and counter cutoff" {
    old = JacRuntime.exec_ctx;
    try {
        project = fusion_project();
        ids = fusion_seed(project, 6);
        for mode in ['', 'thread', 'process'] {
            baseline = fusion_run(project, ids[0], False, 4, mode);
            fused = fusion_run(project, ids[0], True, 4, mode);
            assert baseline[0] == [0, 1, 2, 3] and fused[0] == baseline[0];
            assert baseline[1] == 4 and fused[1] == 4;
            assert fused[2]['fusion']['enabled'];
            assert fused[2]['fusion']['queries'] == 1 , str(fused);
            assert fused[2]['fusion']['cache_paths'] == 3 , str(fused);
            assert fused[3] < baseline[3] , str((baseline, fused));
            assert fused[2]['fusion']['payload_dispatches'] == 1 , str(fused);
        }
    } finally {
        JacRuntime.exec_ctx = old;
    }
}


test "Fused empty hop supplies a complete empty native cache entry" {
    old = JacRuntime.exec_ctx;
    try {
        project = fusion_project();
        ids = fusion_seed(project, 1);
        actual = fusion_run(project, ids[0], True);
        assert actual[0] == [0] and actual[1] == 1;
        assert actual[2]['fusion']['cache_empty_paths'] == 1 , str(actual);
        assert actual[2]['fusion']['queries'] == 1 , str(actual);
        assert actual[3] == 1 , str(actual);
    } finally {
        JacRuntime.exec_ctx = old;
    }
}


test "Fanout boundary retains eager neighbors and generic FIFO counter effects" {
    old = JacRuntime.exec_ctx;
    try {
        project = fusion_project();
        ids = fusion_seed(project, 4, fanout=True);
        baseline = fusion_run(project, ids[0], False, 3);
        fused = fusion_run(project, ids[0], True, 3);
        assert baseline[0] == [0, 1, 2] and fused[0] == baseline[0] , str(
            (baseline, fused)
        );
        assert fused[1] == 3;
        assert len(fused[2]['submitted_ids']) == 2 , str(fused);
        assert fused[2]['fusion']['regions'][0]['kind'] == 'linear';
    } finally {
        JacRuntime.exec_ctx = old;
    }
}


test "Cycle retains repeated activations and stops at the actual scalar bound" {
    old = JacRuntime.exec_ctx;
    try {
        project = fusion_project();
        ids = fusion_seed(project, 2, cycle=True);
        baseline = fusion_run(project, ids[0], False, 5);
        fused = fusion_run(project, ids[0], True, 5);
        assert baseline[0] == [0, 1, 0, 1, 0] and fused[0] == baseline[0];
        assert fused[1] == 5;
        assert fused[2]['fusion']['queries'] == 1 , str(fused);
    } finally {
        JacRuntime.exec_ctx = old;
    }
}


test "Two current ability visits fuse before their target ability barrier" {
    old = JacRuntime.exec_ctx;
    project = fusion_project();
    seed = fusion_context(project);
    try {
        hub = FusedHub();
        root ++> hub;
        hub +>:FusedLeft:+> FusedLeaf(value=1);
        hub +>:FusedRight:+> FusedLeaf(value=2);
        uid = hub.__jac__.id;
    } finally {
        seed.close();
    }
    ctx = fusion_context(project);
    try {
        anchor = ctx.mem.get(uid);
        assert anchor is not None;
        origin = anchor.archetype;
        assert isinstance(origin, FusedHub);
        wlk = FusedBatch();
        with dependency_prefetch(
            ctx, max_length=2048, mode='', fused_sql=True
        ) as run {
            origin spawn wlk;
        }
        assert wlk.seen == [1, 2] , str(run.summary());
        assert run.fusion['queries'] == 1 , str(run.summary());
        assert run.fusion['cache_paths'] == 2;
        assert run.fusion['payload_dispatches'] == 1;
    } finally {
        ctx.close();
        JacRuntime.exec_ctx = old;
    }
}


test "Sum and Find preserve complete scalar results and early-exit payload boundary" {
    import from .fixtures.ttg_fusion_walkers { FusedSum, FusedFind }
    old = JacRuntime.exec_ctx;
    try {
        project = fusion_project();
        ids = fusion_seed(project, 6);
        for enabled in [False, True] {
            ctx = fusion_context(project);
            try {
                anchor = ctx.mem.get(ids[0]);
                assert anchor is not None;
                origin = anchor.archetype;
                assert isinstance(origin, FusedItem);
                sum_walker = FusedSum();
                with dependency_prefetch(
                    ctx, max_length=2048, mode='', fused_sql=enabled
                ) as sum_run {
                    origin spawn sum_walker;
                }
                assert sum_walker.total == 15;
                if enabled {
                    assert sum_run.fusion['queries'] == 1 , str(sum_run.summary());
                    assert sum_run.fusion['cache_empty_paths'] == 1;
                }
            } finally {
                ctx.close();
            }
            ctx = fusion_context(project);
            try {
                anchor = ctx.mem.get(ids[0]);
                assert anchor is not None;
                origin = anchor.archetype;
                assert isinstance(origin, FusedItem);
                find_walker = FusedFind(target=2);
                with dependency_prefetch(
                    ctx, max_length=2048, mode='', fused_sql=enabled
                ) as find_run {
                    origin spawn find_walker;
                }
                assert find_walker.visited == 3 and find_walker.reports == [2];
                assert not (find_run.submitted & set(ids[3:]));
            } finally {
                ctx.close();
            }
        }
    } finally {
        JacRuntime.exec_ctx = old;
    }
}


test "Fused ACL matches native owner public root and group grants with private rejection" {
    import from jaclang.runtime.archetype { Root, EdgeAnchor, AccessLevel }
    import jaclang.sql as q;
    old = JacRuntime.exec_ctx;
    project = fusion_project();
    ctx = fusion_context(project);
    try {
        reader: any = Root().__jac__;
        owner: any = Root().__jac__;
        for anchor in [reader, owner] {
            anchor.persistent = True;
            setattr(anchor, 'root', anchor.id);
            ctx.mem.put(anchor);
        }
        team = FusedHub().__jac__;
        team.persistent = True;
        setattr(team, 'root', owner.id);
        ctx.mem.put(team);
        membership = EdgeAnchor(
            archetype=FusedLeft(), source=reader, target=team, is_undirected=False
        );
        membership.persistent = True;
        reader.edges.append(membership);
        team.edges.append(membership);
        ctx.mem.put(membership);
        docs: list = [];
        for index in range(5) {
            doc = FusedItem(value=index).__jac__;
            doc.persistent = True;
            setattr(doc, 'root', reader.id if index == 0 else owner.id);
            doc.own_access().all = AccessLevel.NO_ACCESS;
            ctx.mem.put(doc);
            docs.append(doc);
            link = EdgeAnchor(
                archetype=FusedNext(), source=reader, target=doc, is_undirected=False
            );
            link.persistent = True;
            reader.edges.append(link);
            doc.edges.append(link);
            ctx.mem.put(link);
        }
        docs[1].own_access().all = AccessLevel.READ;
        JacRuntimeInterface.allow_root(docs[2].archetype, reader.id, AccessLevel.READ);
        JacRuntimeInterface.allow_group(docs[3].archetype, team.id, AccessLevel.READ);
        ctx.mem.commit();
        query = GraphQuery(
            [], hops=[QHop(dir=2, `edge=FusedNext, nd=FusedItem)]
        ).`visit();
        native = compile_query(query, 1, acl_root=str(reader.id), include_type=True);
        native.params['origin'] = [str(reader.id)];
        store: any = ctx.mem.store;
        expected = store.rows(native.sql, native.params);
        contract = {
            'kind': 'batch',
            'rules': [{'hops': (('FusedNext', 'FusedItem', 2), )}]
        };
        compiled = compile_fused_region(contract, [reader.id], str(reader.id), 20);
        actual = store.rows(compiled.sql, compiled.params);
        projected = [(row[3], row[4], row[5], row[6]) for row in actual];
        assert projected == expected , str((projected, expected));
        assert {UUID(str(row[0])) for row in projected} == {d.id for d in docs[:4]};
        assert docs[4].id not in {UUID(str(row[0])) for row in projected};
        table = q.table(
            'anchors', [q.field('id', q.uuid_type()), q.field('props', q.json_type())]
        );
        props = table.col(q.field('props', q.json_type()));
        access = q.json_get(props, q.text('access'));
        json_query = q.select(
            [
                q.named('access', access),
                q.named('all', q.json_text(access, q.text('all'))),
                q.named('present', q.json_has_key(access, q.text('all'))),
                q.named('missing', q.json_get(props, q.text('missing'))),
                q.named('missing_text', q.json_text(props, q.text('missing'))),
                q.named(
                    'null_key', q.json_has_key(q.null(q.json_type()), q.text('missing'))
                )
            ],
            source=table,
            where=q.eq(
                table.col(q.field('id', q.uuid_type())),
                q.param(q.uuid_type(), docs[4].id)
            )
        );
        json_sql = q.compile_sql(json_query);
        values = store.rows(json_sql.sql, json_sql.params);
        assert len(values) == 1;
        # PgWire _decode_value returns JSONB text; decode only this SQL JSON column.
        assert isinstance(values[0][0], str);
        assert json.loads(values[0][0])['all'] == -1;
        assert values[0][1:] == ('-1', True, None, None, None) , str(values);
    } finally {
        ctx.close();
        JacRuntime.exec_ctx = old;
    }
}


test "Parallel and multi-hop paths preserve native ordered pairs and cache completeness" {
    import from jaclang.data.query_planner { cache_ttg_paths, resolve_query_prefix }
    old = JacRuntime.exec_ctx;
    project = fusion_project();
    ctx = fusion_context(project);
    try {
        hub = FusedHub();
        root ++> hub;
        mids = [FusedItem(value=10), FusedItem(value=11)];
        leaves = [FusedLeaf(value=1), FusedLeaf(value=2)];
        hub +>:FusedLeft:+> mids[0];
        hub +>:FusedLeft:+> mids[1];
        mids[0] +>:FusedRight:+> leaves[0];
        mids[0] +>:FusedRight:+> leaves[0];
        mids[0] +>:FusedRight:+> leaves[1];
        mids[1] +>:FusedRight:+> leaves[1];
        ctx.mem.commit();
        query = GraphQuery(
            hub,
            hops=[
                QHop(dir=2, `edge=FusedLeft, nd=FusedItem),
                QHop(dir=2, `edge=FusedRight, nd=FusedLeaf)
            ]
        ).`visit();
        native = compile_query(query, 2, include_type=True);
        native.params['origin'] = [str(hub.__jac__.id)];
        store: any = ctx.mem.store;
        assert not store.in_txn();
        expected = store.rows(native.sql, native.params);
        contract = {
            'kind': 'batch',
            'rules': [
                {
                    'hops': (
                        ('FusedLeft', 'FusedItem', 2),
                        ('FusedRight', 'FusedLeaf', 2)
                    )
                }
            ]
        };
        compiled = compile_fused_region(contract, [hub.__jac__.id], None, 20);
        actual = store.rows(compiled.sql, compiled.params);
        projected = [(row[3], row[4], row[5], row[6]) for row in actual];
        assert len(projected) == 4 and projected == expected , str(
            (projected, expected)
        );
        assert len({row[0] for row in projected}) == 2;
        assert not store.in_txn();
        assert cache_ttg_paths(ctx.mem, [(query, hub.__jac__.id, projected)]);
        with patch.object(store, 'rows', wraps=store.rows) as stale {
            first = resolve_query_prefix(ctx.mem, query, 2);
            assert first == [leaves[0].__jac__.id, leaves[1].__jac__.id];
            assert stale.call_count == 1;
            stale_sql = stale.call_args[0][0];
        }
        assert store.in_txn();
        # Publish rows read in the same Session transaction as native traversal.
        ctx.mem.read_barrier();
        expected = store.rows(native.sql, native.params);
        actual = store.rows(compiled.sql, compiled.params);
        projected = [(row[3], row[4], row[5], row[6]) for row in actual];
        assert projected == expected and len(projected) == 4;
        assert cache_ttg_paths(ctx.mem, [(query, hub.__jac__.id, projected)]);
        with patch.object(store, 'rows', wraps=store.rows) as rows {
            resolved = resolve_query_prefix(ctx.mem, query, 2);
            assert resolved == [leaves[0].__jac__.id, leaves[1].__jac__.id];
            assert rows.call_count == 0;
            evidence = os.environ.get('TTG_PLUS_NATIVE_EVIDENCE');
            if evidence {
                with open(evidence, 'a') as output {
                    output.write(
                        json.dumps(
                            {
                                'kind': 'transaction_boundary_cache_proof',
                                'direct_rows_transaction_active': False,
                                'native_boundary_requeries': 1,
                                'captured_missed_sql': stale_sql,
                                'same_transaction_cache_requeries': rows.call_count,
                                'ordered_pair_rows': len(projected),
                                'distinct_nodes': 2
                            }
                        )
                            + '\n'
                    );
                }
            }
        }
    } finally {
        ctx.close();
        JacRuntime.exec_ctx = old;
    }
}


test "Actual SQL overflow leaves native path cache untouched" {
    import from jaclang.runtime.ttg_dependencies { analyze_walker_dependencies }
    import from jaclang.runtime.ttg_fusion { resolve_fused_region }
    old = JacRuntime.exec_ctx;
    project = fusion_project();
    ids = fusion_seed(project, 4, fanout=True);
    ctx = fusion_context(project);
    try {
        anchor = ctx.mem.get(ids[0]);
        assert anchor is not None;
        last = ctx.mem.get(ids[3]);
        assert last is not None;
        origin = anchor.archetype;
        target = last.archetype;
        assert isinstance(origin, FusedItem) and isinstance(target, FusedItem);
        origin +>:FusedNext:+> target;
        ctx.mem.commit();
        ctx.mem.invalidate_query_cache();
        graph = analyze_walker_dependencies(FusedWalk);
        event = next(
            e
            for e in graph.events
            if e.kind == 'visit'
        );
        active = {
            'id': ids[0],
            'node_type': FusedItem,
            'transition_state': {
                'self.visited': 1,
                'self.limit': 20,
                'walk::here.value': 0
            },
            'transition_pending': []
        };
        metrics = {
            'queries': 0,
            'overflow': 0,
            'cache_paths': 0,
            'cache_empty_paths': 0,
            'regions': []
        };
        with patch.object(
            ctx.mem, 'query_cache_put', wraps=ctx.mem.query_cache_put
        ) as published {
            actual = resolve_fused_region(
                ctx.mem, FusedWalk(), graph, active, event, None, 2, metrics
            );
            assert actual is None;
            assert metrics['queries'] == 1 and metrics['overflow'] == 1;
            assert published.call_count == 0;
        }
    } finally {
        ctx.close();
        JacRuntime.exec_ctx = old;
    }
}
