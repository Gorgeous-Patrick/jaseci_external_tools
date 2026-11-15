"""Permission is decided by the query, not by discarding rows afterwards.

`resolve_query` materialised every candidate and then dropped what the caller
could not see, so a gated read paid for rows it was never allowed to return --
and a bound could not be pushed at all, because `LIMIT` ahead of a filter still
running in Python changes `[:n]` from "n you may see" to "up to n, some of which
then vanish".

The standard model compiles: you own it (`root_id`), it is granted to everyone
(`access.all`), or it is granted to you by name (`access.roots.anchors`). A
per-root grant does not scale to a large audience, so a grant may also name a
*group*, and membership is an edge -- one grant, one membership per member,
instead of one dict entry per member on every object.

Custom access hooks are rejected at class registration. Every supported node
uses standard permissions, including untyped intermediate query hops.

"""

import from pathlib { Path }
import from tempfile { TemporaryDirectory }
import from uuid { UUID }
import from jaclang.runtime.archetype { AccessLevel, EdgeAnchor, GenericEdge, Root }
import from jaclang.runtime.graph_walk { acl_read_ok }
import from jaclang.runtime.runtime { JacRuntime, JacRuntimeInterface }
import from jaclang.runtime.context { ExecutionContext }

node Doc {
    has label: str = "";
}

node Team {
    has name: str = "";
}

edge MemberOf {}


def _as_any(v: any) -> any {
    return v;
}


def _ctx(td: str) -> ExecutionContext {
    return ExecutionContext(
        base_path_dir=td, full_target_path=str(Path(td) / "acl_app.jac")
    );
}


def _mk_root(mem: any) -> any {
    anch: any = Root().__jac__;
    anch.persistent = True;
    setattr(anch, "root", anch.id);
    mem.put(anch);
    return anch;
}


"""Attach `n` Docs owned by `owner` under `hub`, granting `granted` of them to all."""
def _seed(ctx: ExecutionContext, hub: any, owner: any, n: int, granted: int) {
    for i in range(n) {
        d = Doc(label=f"d{i}").__jac__;
        d.persistent = True;
        setattr(d, "root", owner.id);
        if i < granted {
            d.own_access().all = AccessLevel.READ;
        }
        ctx.mem.put(d);
        e = EdgeAnchor(
            archetype=GenericEdge(), source=hub, target=d, is_undirected=False
        );
        e.persistent = True;
        hub.edges.append(e);
        d.edges.append(e);
        ctx.mem.put(e);
    }
}


test "a gated read does not materialize rows it may not return" {
    with TemporaryDirectory() as td {
        old = JacRuntime.exec_ctx;
        ctx1 = _ctx(td);
        JacRuntime.exec_ctx = ctx1;
        hub_id: str;
        try {
            owner = _mk_root(ctx1.mem);
            other = _mk_root(ctx1.mem);
            _seed(ctx1, other, owner, 30, 3);
            ctx1.mem.commit();
            hub_id = str(other.id);
        } finally {
            JacRuntime.exec_ctx = old;
            ctx1.close();
        }
        # A cold context: nothing is in __mem__, so every row the read touches
        # is a real store fetch and the counter means something.
        ctx2 = _ctx(td);
        JacRuntime.exec_ctx = ctx2;
        try {
            ctx2.set_user_root(hub_id);
            hub = ctx2.mem.get(UUID(hub_id));
            assert hub is not None;
            ctx2.mem.reset_fetch_count();
            visible = len([x for x in [_as_any(hub).archetype-->[?:Doc]]]);
            fetched = ctx2.mem.get_fetch_count();
            assert visible == 3 , f"expected the 3 granted docs, got {visible}";
            assert fetched <= 3 , (
                f"a gated read materialized {fetched} anchors to return 3; the "
                f"permission test belongs in the query"
            );
        } finally {
            JacRuntime.exec_ctx = old;
            ctx2.close();
        }
    }
}


test "public read acl does not fetch owner root" {
    with TemporaryDirectory() as td {
        old = JacRuntime.exec_ctx;
        ctx1 = _ctx(td);
        JacRuntime.exec_ctx = ctx1;
        doc_id: str;
        viewer_id: str;
        try {
            owner = _mk_root(ctx1.mem);
            viewer = _mk_root(ctx1.mem);
            d = Doc(label="public").__jac__;
            d.persistent = True;
            setattr(d, "root", owner.id);
            d.own_access().all = AccessLevel.READ;
            ctx1.mem.put(d);
            ctx1.mem.commit();
            doc_id = str(d.id);
            viewer_id = str(viewer.id);
        } finally {
            JacRuntime.exec_ctx = old;
            ctx1.close();
        }
        ctx2 = _ctx(td);
        JacRuntime.exec_ctx = ctx2;
        try {
            ctx2.set_user_root(viewer_id);
            d = ctx2.mem.get(UUID(doc_id));
            assert d is not None;
            ctx2.mem.reset_fetch_count();
            assert acl_read_ok(d);
            fetched = ctx2.mem.get_fetch_count();
            assert fetched == 0 , (
                f"public read ACL fetched {fetched} anchors; it should not load "
                f"the owner root after access.all already grants read"
            );
        } finally {
            JacRuntime.exec_ctx = old;
            ctx2.close();
        }
    }
}


test "a bound is pushed even when the request is gated" {
    with TemporaryDirectory() as td {
        old = JacRuntime.exec_ctx;
        ctx = _ctx(td);
        JacRuntime.exec_ctx = ctx;
        hub_id: str;
        try {
            owner = _mk_root(ctx.mem);
            other = _mk_root(ctx.mem);
            _seed(ctx, other, owner, 30, 20);
            ctx.mem.commit();
            hub_id = str(other.id);
        } finally {
            JacRuntime.exec_ctx = old;
            ctx.close();
        }
        ctx2 = _ctx(td);
        JacRuntime.exec_ctx = ctx2;
        try {
            ctx2.set_user_root(hub_id);
            hub = ctx2.mem.get(UUID(hub_id));
            assert hub is not None;
            ctx2.mem.reset_fetch_count();
            head = [_as_any(hub).archetype-->[?:Doc]][:4];
            fetched = ctx2.mem.get_fetch_count();
            assert len(head) == 4 , len(head);
            assert fetched <= 4 , (
                f"a bounded gated read materialized {fetched} anchors for 4 rows"
            );
        } finally {
            JacRuntime.exec_ctx = old;
            ctx2.close();
        }
    }
}


test "a grant to a group reaches every member without a per-root entry" {
    with TemporaryDirectory() as td {
        old = JacRuntime.exec_ctx;
        ctx = _ctx(td);
        JacRuntime.exec_ctx = ctx;
        try {
            owner = _mk_root(ctx.mem);
            reader = _mk_root(ctx.mem);

            team = Team(name="eng").__jac__;
            team.persistent = True;
            setattr(team, "root", owner.id);
            ctx.mem.put(team);

            # membership is an edge, not an entry on every granted object
            m = EdgeAnchor(
                archetype=MemberOf(), source=reader, target=team, is_undirected=False
            );
            m.persistent = True;
            reader.edges.append(m);
            team.edges.append(m);
            ctx.mem.put(m);

            d = Doc(label="team-doc").__jac__;
            d.persistent = True;
            setattr(d, "root", owner.id);
            ctx.mem.put(d);
            e = EdgeAnchor(
                archetype=GenericEdge(), source=reader, target=d, is_undirected=False
            );
            e.persistent = True;
            reader.edges.append(e);
            d.edges.append(e);
            ctx.mem.put(e);

            JacRuntimeInterface.allow_group(d.archetype, team.id, AccessLevel.READ);
            ctx.mem.commit();

            ctx.set_user_root(str(reader.id));
            seen = [_as_any(x).label for x in [_as_any(reader.archetype)-->[?:Doc]]];
            assert seen == ["team-doc"] , (
                f"a group grant must reach a member; got {seen}"
            );
            assert d.access is None or not d.access.roots.anchors , (
                "a group grant must not write a per-root entry on the object"
            );
        } finally {
            JacRuntime.exec_ctx = old;
            ctx.close();
        }
    }
}


test "custom access is rejected before a class can be used" {
    rejected = False;
    try {
        type(
            'ForbiddenDoc',
            (Doc, ),
            {'__jac_access__': lambda (self: any) { AccessLevel.READ; }}
        );
    } except TypeError as error {
        rejected = 'custom __jac_access__' in str(error);
    }
    assert rejected;
}

test "Persisted typed and untyped paths cannot traverse a private intermediate node" {
    import from jaclang.runtime.graph_query { GraphQuery, QHop }
    import from jaclang.data.query_planner { resolve_query }
    import from unittest.mock { patch }
    with TemporaryDirectory() as td {
        old = JacRuntime.exec_ctx;
        ctx = _ctx(td);
        JacRuntime.exec_ctx = ctx;
        try {
            reader = _mk_root(ctx.mem);
            owner = _mk_root(ctx.mem);
            middle: any = Doc(label='private-middle').__jac__;
            leaf: any = Doc(label='public-leaf').__jac__;
            for a in [middle, leaf] {
                a.persistent = True;
                setattr(a, 'root', owner.id);
                ctx.mem.put(a);
            }
            leaf.own_access().all = AccessLevel.READ;
            ctx.mem.put(leaf);
            for (src, dst) in [(reader, middle), (middle, leaf)] {
                link = EdgeAnchor(
                    archetype=GenericEdge(), source=src, target=dst, is_undirected=False
                );
                link.persistent = True;
                src.edges.append(link);
                dst.edges.append(link);
                ctx.mem.put(link);
            }
            ctx.mem.commit();
            reader_id = reader.id;
            middle_id = middle.id;
            leaf_id = leaf.id;
        } finally {
            ctx.close();
            JacRuntime.exec_ctx = old;
        }
        ctx = _ctx(td);
        JacRuntime.exec_ctx = ctx;
        try {
            ctx.set_user_root(str(reader_id));
            reader = ctx.mem.get(reader_id);
            assert reader is not None;
            store: any = ctx.mem.store;
            for target in [None, Doc] {
                query = GraphQuery(
                    [reader.archetype],
                    hops=[QHop(dir=2, nd=target), QHop(dir=2, nd=target)]
                );
                with patch.object(store, 'rows', wraps=store.rows) as rows {
                    assert resolve_query(ctx.mem, query) == [];
                    assert any(
                        'n1.root_id' in c[0][0] and 'n2.root_id' in c[0][0]
                        for c in rows.call_args_list
                    );
                }
            }
            # Make only the intermediate node public; the very same path now succeeds.
            ctx.set_user_root(str(owner.id));
            middle = ctx.mem.get(middle_id);
            assert middle is not None;
            middle.own_access().all = AccessLevel.READ;
            ctx.mem.put(middle);
            ctx.mem.commit();
            ctx.set_user_root(str(reader_id));
            for target in [None, Doc] {
                query = GraphQuery(
                    [reader.archetype],
                    hops=[QHop(dir=2, nd=target), QHop(dir=2, nd=target)]
                );
                assert [a.id for a in resolve_query(ctx.mem, query)] == [leaf_id];
            }
        } finally {
            ctx.close();
            JacRuntime.exec_ctx = old;
        }
    }
}
