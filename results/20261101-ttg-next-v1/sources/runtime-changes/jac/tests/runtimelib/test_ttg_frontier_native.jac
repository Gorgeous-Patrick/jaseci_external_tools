"""Persistent queued frontier integration beyond a homogeneous chain."""
import from pathlib { Path }
import json;
import os;
import from hashlib { sha256 }
import from tempfile { mkdtemp }
import from unittest.mock { patch }
import from uuid { UUID }
import from jaclang.runtime.context { ExecutionContext }
import from jaclang.runtime.runtime { JacRuntime }
import from jaclang.runtime.ttg_dependency_prefetch { dependency_prefetch }
import from .fixtures.ttg_frontier_alias_walkers { FrontierAlias }
import from .fixtures.ttg_frontier_walkers {
    FrontierStart,
    FrontierBranch,
    FrontierLeaf,
    FrontierDerivedLeaf,
    FrontierQueue,
    FrontierLeft,
    FrontierRight,
    FrontierWalk,
    FrontierDuplicate,
    FrontierCancel
}


def frontier_context(project: str) -> any {
    ctx = ExecutionContext(
        base_path_dir=project, full_target_path=str(Path(project, 'frontier.jac'))
    );
    JacRuntime.exec_ctx = ctx;
    return ctx;
}


def frontier_seed -> tuple {
    parent = Path('/tmp/ttg-next-native-v1/fixtures');
    parent.mkdir(parents=True, exist_ok=True);
    project = mkdtemp(prefix='case-', dir=str(parent));
    ctx = frontier_context(project);
    try {
        start = FrontierStart();
        root ++> start;
        branches = [FrontierBranch(value=i) for i in range(4)];
        for (index, branch) in enumerate(branches) {
            start +>:FrontierQueue:+> branch;
            branch +>:FrontierLeft:+> FrontierLeaf(value=index * 10 + 1);
            leaf = FrontierDerivedLeaf(value=index * 10 + 2)
                if index == 2
                else FrontierLeaf(value=index * 10 + 2);
            branch +>:FrontierRight:+> leaf;
        }
        return (project, start.__jac__.id, [b.__jac__.id for b in branches]);
    } finally {
        ctx.close();
    }
}


def frontier_run(project: str, uid: UUID, wlk: any, enabled: bool) -> tuple {
    ctx = frontier_context(project);
    try {
        origin = ctx.mem.get(uid).archetype;
        store: any = ctx.mem.store;
        original: any = store.rows;
        calls: list = [];
        def capture(sql: str, params: dict) -> list {
            rows = original(sql, params);
            calls.append(
                {
                    'sql': sql,
                    'sha256': sha256(sql.encode()).hexdigest(),
                    'params': params,
                    'rows': len(rows)
                }
            );
            return rows;
        }
        with patch.object(store, 'rows', side_effect=capture) {
            with dependency_prefetch(
                ctx, max_length=2048, mode='process', workers=1, fused_sql=enabled
            ) as run {
                origin spawn wlk;
            }
        }
        summary = run.summary();
        evidence = os.environ.get('TTG_NEXT_NATIVE_EVIDENCE');
        if evidence {
            with open(evidence, 'a') as output {
                output.write(
                    json.dumps(
                        {
                            'walker': type(wlk).__name__,
                            'project': project,
                            'origin': str(uid),
                            'enabled': enabled,
                            'reports': wlk.reports,
                            'native_i': getattr(wlk, 'i', None),
                            'native_entered': getattr(wlk, 'entered', None),
                            'sql_calls': calls,
                            'summary': summary
                        },
                        **{'default': str}
                    )
                        + '\n'
                );
            }
        }
        assert not run.errors , str(run.errors);
        return (wlk.reports, summary);
    } finally {
        ctx.close();
    }
}

test "A opaque reset prevents proof then B batches B C D E using sequential state" {
    old = JacRuntime.exec_ctx;
    try {
        (project, uid, branches) = frontier_seed();
        baseline = frontier_run(project, uid, FrontierWalk(), False);
        compiled = frontier_run(project, uid, FrontierWalk(), True);
        assert baseline[0] == [1, 12, 22, 32];
        assert compiled[0] == baseline[0];
        regions = [
            r
            for r in compiled[1]['fusion']['regions']
            if r.get('compiled')
        ];
        assert any(len({d['origin'] for d in r['demands']}) == 4 for r in regions) , str(
            regions
        );
        demands = next(
            r['demands']
            for r in regions
            if len({d['origin'] for d in r['demands']}) == 4
        );
        assert [d['activation'] for d in demands] == [str(b) for b in branches];
        assert demands[0]['event'] != demands[1]['event'];
        assert demands[1]['event'] == demands[2]['event'] == demands[3]['event'];
        assert compiled[1]['fusion']['template_queries'] >= 1;
    } finally {
        JacRuntime.exec_ctx = old;
    }
}

test "Native duplicate visits and disengage outputs remain unchanged" {
    old = JacRuntime.exec_ctx;
    try {
        (project, uid, branches) = frontier_seed();
        for enabled in (False, True) {
            alias = frontier_run(project, branches[0], FrontierAlias(), enabled);
            assert alias[0] == [2] , str(alias);
            if enabled {
                assert alias[1]['fusion']['queries'] == 0;
                assert 'alias' in alias[1]['fusion']['fallback_reason'];
            }
            duplicate = frontier_run(
                project, branches[0], FrontierDuplicate(), enabled
            );
            assert duplicate[0] == [2, 2] , str(duplicate);
            wlk = FrontierCancel();
            cancelled = frontier_run(project, uid, wlk, enabled);
            assert cancelled[0] == [] , str(cancelled);
            assert wlk.entered == [0, 1] , str(wlk.entered);
            if enabled {
                assert cancelled[1]['fusion']['template_queries'] >= 1;
                assert cancelled[1]['submitted_ids'];
            }
        }
    } finally {
        JacRuntime.exec_ctx = old;
    }
}

test "Authenticated compiled full path cache cannot replace a shorter prefix" {
    import from jaclang.runtime.archetype { Root, AccessLevel }
    import from jaclang.runtime.graph_query { GraphQuery, QHop }
    import from jaclang.runtime.graph_walk { access_gated }
    import from jaclang.runtime.ttg_dependencies { TraceEvent }
    import from jaclang.runtime.ttg_templates {
        compile_templates,
        hydrate_templates,
        select_template,
        publish_paths
    }
    import from jaclang.data.query_planner { resolve_query_prefix, resolve_ttg_path }
    import jaclang.data.query_planner as planner;
    old = JacRuntime.exec_ctx;
    try {
        parent = Path('/tmp/ttg-next-native-v1/fixtures');
        parent.mkdir(parents=True, exist_ok=True);
        project = mkdtemp(prefix='prefix-', dir=str(parent));
        ctx = frontier_context(project);
        try {
            reader: any = Root().__jac__;
            reader.persistent = True;
            setattr(reader, 'root', reader.id);
            ctx.mem.put(reader);
            a = FrontierBranch(value=0);
            b = FrontierBranch(value=1);
            c = FrontierLeaf(value=2);
            for arch in [a, b, c] {
                anchor: any = arch.__jac__;
                anchor.persistent = True;
                setattr(anchor, 'root', reader.id);
                anchor.own_access().all = AccessLevel.NO_ACCESS;
                ctx.mem.put(anchor);
            }
            a +>:FrontierRight:+> b;
            b +>:FrontierRight:+> c;
            reader_id = reader.id;
            ids = [a.__jac__.id, b.__jac__.id, c.__jac__.id];
        } finally {
            ctx.close();
        }
        ctx = frontier_context(project);
        try {
            ctx.set_user_root(str(reader_id));
            assert access_gated();
            origin: any = ctx.mem.get(ids[0]).archetype;
            query = GraphQuery(
                origin,
                hops=[
                    QHop(dir=2, `edge=FrontierRight, nd=FrontierBranch),
                    QHop(dir=2, `edge=FrontierRight, nd=FrontierLeaf)
                ]
            ).`visit();
            rows = resolve_ttg_path(ctx.mem, query, ids[0], 20);
            assert rows is not None and [UUID(str(r[0])) for r in rows] == [ids[2]];
            event = TraceEvent(
                id=0,
                kind='visit',
                ability='branch',
                line=0,
                hop_chain=(
                    ('FrontierRight', 'FrontierBranch', 2),
                    ('FrontierRight', 'FrontierLeaf', 2)
                )
            );
            bundle = hydrate_templates(compile_templates([event]));
            assert publish_paths(
                ctx.mem,
                [(query, ids[0], rows, select_template(bundle, 'native', True, 0))]
            );
            store: any = ctx.mem.store;
            with patch.object(store, 'rows', wraps=store.rows) as calls, patch.object(
                planner, '_topology_node_ids', return_value=None
            ) {
                assert resolve_query_prefix(ctx.mem, query, 2) == [ids[2]];
                assert calls.call_count == 0;
                assert resolve_query_prefix(ctx.mem, query, 1) == [ids[1]];
                assert calls.call_count == 1 , str(calls.call_args_list);
            }
        } finally {
            ctx.close();
        }
    } finally {
        JacRuntime.exec_ctx = old;
    }
}
