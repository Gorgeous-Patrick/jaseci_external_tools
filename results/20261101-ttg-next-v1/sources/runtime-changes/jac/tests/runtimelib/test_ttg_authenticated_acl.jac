"""Authenticated untyped paths use one shared, snapshot-scoped ACL proof."""
import from pathlib { Path }
import from contextlib { ExitStack }
import jaclang.data.query_planner as planner;
import jaclang.runtime.ttg_fusion_sql as fusion_sql;
import jaclang.runtime.ttg_sql as ttg_sql;
import json;
import os;
import from uuid { UUID }
import from tempfile { mkdtemp }
import from unittest.mock { patch }
import from jaclang.runtime.runtime { JacRuntime }
import from jaclang.runtime.context { ExecutionContext }
import from jaclang.runtime.archetype { Root, EdgeAnchor, AccessLevel }
import from jaclang.runtime.graph_walk { access_gated }
import from jaclang.runtime.graph_query { GraphQuery, QHop }
import from jaclang.runtime.ttg_dependency_prefetch { dependency_prefetch }
import from jaclang.runtime.ttg_sql { compile_acl_type_catalog }
import from jaclang.data.query_planner {
    _acl_pushdown_root,
    resolve_query_prefix,
    resolve_ttg_path
}
import from .fixtures.ttg_fusion_walkers { FusedItem, FusedNext, FusedWalk }
import from .fixtures.ttg_acl_walkers {
    CatalogGrant,
    reset_access_calls,
    access_call_count
}


def acl_context(project: str) -> ExecutionContext {
    ctx = ExecutionContext(
        base_path_dir=project, full_target_path=str(Path(project, 'authenticated.jac'))
    );
    JacRuntime.exec_ctx = ctx;
    return ctx;
}

def acl_evidence(value: dict) {
    target = os.environ.get('TTG_ACL_TEST_EVIDENCE');
    if target {
        with open(target, 'a') as output {
            output.write(json.dumps(value) + '\n');
        }
    }
}


def acl_seed(kind: str = 'standard') -> tuple {
    base = Path('/tmp/ttg-plus-acl-v1/fixtures');
    base.mkdir(parents=True, exist_ok=True);
    project = mkdtemp(prefix='case-', dir=str(base));
    ctx = acl_context(project);
    try {
        reader: any = Root().__jac__;
        reader.persistent = True;
        setattr(reader, 'root', reader.id);
        ctx.mem.put(reader);
        owner: any = Root().__jac__;
        owner.persistent = True;
        setattr(owner, 'root', owner.id);
        ctx.mem.put(owner);
        items: list = [];
        for index in range(6) {
            arch = CatalogGrant(value=index)
                if kind == 'custom' and index == 2
                else FusedItem(value=index);
            anchor = arch.__jac__;
            anchor.persistent = True;
            setattr(
                anchor,
                'root',
                owner.id if kind == 'custom' and index == 2 else reader.id
            );
            anchor.own_access().all = AccessLevel.NO_ACCESS;
            ctx.mem.put(anchor);
            items.append(anchor);
        }
        for index in range(5) {
            edge_anchor = EdgeAnchor(
                archetype=FusedNext(),
                source=items[index],
                target=items[index + 1],
                is_undirected=False
            );
            edge_anchor.persistent = True;
            items[index].edges.append(edge_anchor);
            items[index + 1].edges.append(edge_anchor);
            ctx.mem.put(edge_anchor);
        }
        if kind == 'unknown' {
            orphan = FusedItem(value=99).__jac__;
            orphan.persistent = True;
            setattr(orphan, 'root', owner.id);
            ctx.mem.put(orphan);
        }
        ctx.mem.commit();
        if kind == 'unknown' {
            ctx.mem.read_barrier();
            store = ctx.mem.store;
            assert store is not None;
            store.rows(
                'UPDATE anchors SET arch_module = :module WHERE id = CAST(:id AS uuid)',
                {'module': 'ttg_missing_catalog_module', 'id': str(orphan.id)}
            );
            store.commit();
            ctx.mem.invalidate_query_cache();
        }
        return (project, reader.id, [item.id for item in items]);
    } finally {
        ctx.close();
    }
}


test "Authenticated heterogeneous untyped paths activate both modes with shared native cache keys" {
    old = JacRuntime.exec_ctx;
    try {
        (project, reader, ids) = acl_seed();
        for enabled in [False, True] {
            ctx = acl_context(project);
            try {
                ctx.set_user_root(str(reader));
                assert access_gated();
                anchor = ctx.mem.get(ids[0]);
                assert anchor is not None;
                origin = anchor.archetype;
                assert isinstance(origin, FusedItem);
                wlk = FusedWalk(limit=6);
                store: any = ctx.mem.store;
                before_spawn = {
                    'in_txn': store.in_txn(),
                    'cache_entries': len(ctx.mem._query_cache),
                    'cache_identity': id(ctx.mem._query_cache)
                };
                with patch.object(store, 'rows', wraps=store.rows) as rows {
                    with ExitStack() as compiled_guards {
                        install_guard: any = compiled_guards.enter_context;
                        if enabled {
                            install_guard(
                                patch.object(
                                    planner,
                                    'compile_query',
                                    side_effect=AssertionError(
                                        'runtime native path builder'
                                    )
                                )
                            );
                            install_guard(
                                patch.object(
                                    fusion_sql,
                                    'compile_fused_region',
                                    side_effect=AssertionError(
                                        'runtime fused SQL AST builder'
                                    )
                                )
                            );
                            install_guard(
                                patch.object(
                                    ttg_sql,
                                    'compile_acl_type_catalog',
                                    side_effect=AssertionError(
                                        'runtime ACL catalog AST builder'
                                    )
                                )
                            );
                        }
                        with dependency_prefetch(
                            ctx, max_length=2048, mode='process', fused_sql=enabled
                        ) as run {
                            origin spawn wlk;
                        }
                    }
                    assert wlk.reports == [0, 1, 2, 3, 4, 5] and wlk.visited == 6;
                    assert len(run.submitted) == 5 , str(run.summary());
                    assert not run.errors;
                    catalog_calls = [
                        c
                        for c in rows.call_args_list
                        if c[0][0] == compile_acl_type_catalog().sql
                    ];
                    assert len(catalog_calls) == 1 , str(rows.call_args_list);
                    assert not any(
                        c[0][0].startswith('SELECT n1.id, e1.id FROM')
                        for c in rows.call_args_list
                    );
                    if enabled {
                        assert run.fusion['queries'] == 1 , str(run.summary());
                    }
                }
                after_spawn = {
                    'in_txn': store.in_txn(),
                    'cache_entries': len(ctx.mem._query_cache),
                    'cache_identity': id(ctx.mem._query_cache)
                };
                # A completed walker may end its transaction. Publish and consume
                # the actor-bound key within one explicit live transaction.
                query = GraphQuery(
                    origin, hops=[QHop(dir=2, `edge=FusedNext)]
                ).`visit();
                assert _acl_pushdown_root(query, 1, ctx.mem) == str(reader);
                after_barrier = {
                    'in_txn': store.in_txn(),
                    'cache_entries': len(ctx.mem._query_cache),
                    'cache_identity': id(ctx.mem._query_cache)
                };
                acl_evidence(
                    {
                        'case': 'transaction_boundary',
                        'fused_sql': enabled,
                        'before_spawn': before_spawn,
                        'after_spawn': after_spawn,
                        'after_barrier': after_barrier
                    }
                );
                typed = resolve_ttg_path(ctx.mem, query, ids[0], 2048);
                assert typed is not None
                    and [UUID(str(row[0])) for row in typed] == [ids[1]] , str(typed);
                with patch.object(store, 'rows', wraps=store.rows) as rows {
                    assert resolve_query_prefix(ctx.mem, query, 1) == [ids[1]];
                    assert rows.call_count == 0 , str(rows.call_args_list);
                }
                acl_evidence(
                    {
                        'case': 'standard',
                        'fused_sql': enabled,
                        'before_spawn': before_spawn,
                        'after_spawn': after_spawn,
                        'after_barrier': after_barrier,
                        'catalog_sql_count': len(catalog_calls),
                        'native_consumer_sql_count': rows.call_count,
                        'summary': run.summary()
                    }
                );
            } finally {
                ctx.close();
            }
        }
    } finally {
        JacRuntime.exec_ctx = old;
    }
}


test "Custom access grant remains native and untyped prefetch declines in both modes without invoking hook" {
    old = JacRuntime.exec_ctx;
    try {
        (project, reader, ids) = acl_seed('custom');
        for enabled in [False, True] {
            ctx = acl_context(project);
            try {
                ctx.set_user_root(str(reader));
                assert access_gated();
                query = GraphQuery([], hops=[QHop(dir=2, `edge=FusedNext)]).`visit();
                reset_access_calls();
                assert _acl_pushdown_root(query, 1, ctx.mem) is None;
                assert access_call_count() == 0;
                anchor = ctx.mem.get(ids[0]);
                assert anchor is not None;
                origin = anchor.archetype;
                assert isinstance(origin, FusedItem);
                wlk = FusedWalk(limit=6);
                with dependency_prefetch(
                    ctx, max_length=2048, mode='process', fused_sql=enabled
                ) as run {
                    origin spawn wlk;
                }
                assert wlk.reports == [0, 1, 2, 3, 4, 5];
                assert access_call_count() > 0;
                assert not run.submitted;
                assert any(p['status'] == 'acl_unproved' for p in run.plans);
                assert run.fusion['queries'] == 0;
            } finally {
                ctx.close();
            }
        }
    } finally {
        JacRuntime.exec_ctx = old;
    }
}


test "Unknown persisted type conservatively declines both modes without narrowing ordinary successors" {
    old = JacRuntime.exec_ctx;
    try {
        (project, reader, ids) = acl_seed('unknown');
        for enabled in [False, True] {
            ctx = acl_context(project);
            try {
                ctx.set_user_root(str(reader));
                anchor = ctx.mem.get(ids[0]);
                assert anchor is not None;
                origin = anchor.archetype;
                assert isinstance(origin, FusedItem);
                wlk = FusedWalk(limit=6);
                with dependency_prefetch(
                    ctx, max_length=2048, mode='process', fused_sql=enabled
                ) as run {
                    origin spawn wlk;
                }
                assert wlk.reports == [0, 1, 2, 3, 4, 5];
                assert not run.submitted;
                assert any(p['status'] == 'acl_unproved' for p in run.plans);
                assert run.fusion['queries'] == 0;
            } finally {
                ctx.close();
            }
        }
    } finally {
        JacRuntime.exec_ctx = old;
    }
}


test "Catalog proof refreshes on transaction and writes and rechecks raw hook identity" {
    old = JacRuntime.exec_ctx;
    try {
        (project, reader, ids) = acl_seed();
        ctx = acl_context(project);
        try {
            ctx.set_user_root(str(reader));
            query = GraphQuery([], hops=[QHop(dir=2, `edge=FusedNext)]).`visit();
            store: any = ctx.mem.store;
            with patch.object(store, 'rows', wraps=store.rows) as rows {
                assert _acl_pushdown_root(query, 1, ctx.mem) == str(reader);
                assert _acl_pushdown_root(query, 1, ctx.mem) == str(reader);
                assert sum(
                    c[0][0] == compile_acl_type_catalog().sql
                    for c in rows.call_args_list
                )
                    == 1;
                def changed_access(self: any) -> any {
                    raise RuntimeError('Guard executed an access hook');
                }
                with patch.object(FusedItem, '__jac_access__', changed_access) {
                    assert _acl_pushdown_root(query, 1, ctx.mem) is None;
                }
                assert _acl_pushdown_root(query, 1, ctx.mem) == str(reader);
                ctx.mem.commit();
                assert _acl_pushdown_root(query, 1, ctx.mem) == str(reader);
                assert sum(
                    c[0][0] == compile_acl_type_catalog().sql
                    for c in rows.call_args_list
                )
                    == 2;
                extra = CatalogGrant(value=55).__jac__;
                extra.persistent = True;
                setattr(extra, 'root', reader);
                ctx.mem.put(extra);
                assert _acl_pushdown_root(query, 1, ctx.mem) is None;
                assert sum(
                    c[0][0] == compile_acl_type_catalog().sql
                    for c in rows.call_args_list
                )
                    == 3;
            }
        } finally {
            ctx.close();
        }
    } finally {
        JacRuntime.exec_ctx = old;
    }
}
