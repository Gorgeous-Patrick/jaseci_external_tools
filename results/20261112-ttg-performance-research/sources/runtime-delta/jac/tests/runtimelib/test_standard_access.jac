"""No custom ACL execution or persisted type census in the standard-only runtime."""
import from unittest.mock { patch }
import from types { SimpleNamespace }
import from uuid { UUID }
import from jaclang.runtime.archetype { Archetype, NodeArchetype }
import from jaclang.runtime.graph_query { GraphQuery, QHop }
import jaclang.data.query_planner as planner;
import from jaclang.runtime.runtime { JacRuntimeInterface }
import from jaclang.runtime.ttg_dependencies { compile_checkpoint_plan }
import from jaclang.runtime.ttg { JacTTGGenerator }
import from .fixtures.ttg_region_walkers { DagFeed }

test "Custom methods and descriptors are rejected without execution" {
    def forbidden(self: any) -> any {
        raise AssertionError('Custom access executed');
    }
    for value in [forbidden, property(forbidden), None] {
        rejected = False;
        try {
            type('Forbidden', (NodeArchetype, ), {'__jac_access__': value});
        } except TypeError as error {
            rejected = 'custom __jac_access__' in str(error);
        }
        assert rejected;
    }
    mixin = type('AccessMixin', (), {'__jac_access__': forbidden});
    rejected = False;
    try {
        type('InheritedForbidden', (mixin, NodeArchetype), {});
    } except TypeError as error {
        rejected = 'custom __jac_access__' in str(error);
    }
    assert rejected;
}

test "Standard descendants remain supported and instance overrides are rejected" {
    plain = type('StandardParent', (NodeArchetype, ), {});
    child = type('StandardChild', (plain, ), {});
    Archetype.require_standard_access(child);
    rejected = False;
    try {
        setattr(child(), '__jac_access__', lambda { 0; });
    } except TypeError {
        rejected = True;
    }
    assert rejected;
    with patch.object(child, '__jac_access__', lambda (self: any) { 0; }) {
        rejected = False;
        try {
            Archetype.require_standard_access(child);
        } except TypeError {
            rejected = True;
        }
        assert rejected;
    }
}

test "Untyped multihop ACL selection needs no database or catalog" {
    actor = UUID(int=17);
    query = GraphQuery([], hops=[QHop(dir=2), QHop(dir=2)]);
    ctx = SimpleNamespace(user_root=SimpleNamespace(id=actor));
    with patch.object(planner, 'access_gated', return_value=True), patch.object(
        JacRuntimeInterface, 'get_context', return_value=ctx
    ) {
        assert planner._acl_pushdown_root(query, 2, None) == str(actor);
    }
}

test "Authenticated DAG emits per-hop ACLs without a type-catalog output branch" {
    arch = JacTTGGenerator._find_walker_ast_node(DagFeed);
    assert arch is not None;
    spec = compile_checkpoint_plan(arch);
    assert 'catalog' not in spec['sql_templates'];
    region = spec['interability_regions']['regions'][str(spec['entries']['run'])];
    sql = region['templates']['gated']['sql'];
    assert sql.count('"root_id"') == 4;
    assert ':actor_uuid' in sql and ':actor_text' in sql;
    assert sql.endswith('LIMIT CAST(:row_limit AS bigint)');
    assert sql.count('"kind"') == 12;
}
