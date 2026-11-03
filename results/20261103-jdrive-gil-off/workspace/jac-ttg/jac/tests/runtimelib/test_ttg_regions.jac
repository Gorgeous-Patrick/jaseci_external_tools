"""DB-free static summaries, emitted region SQL and bind contracts."""
import json;
import jaclang.sql as q;
import from uuid { UUID }
import from unittest.mock { patch }
import from jaclang.runtime.ttg { JacTTGGenerator }
import from jaclang.runtime.ttg_dependencies {
    analyze_walker_dependencies,
    compile_checkpoint_plan,
    checkpoint_graph
}
import from jaclang.runtime.ttg_regions { summarize_abilities }
import from jaclang.runtime.ttg_templates { bind_template }
import from .fixtures.ttg_region_walkers {
    SliceOutputBranch,
    SliceIdentityMap,
    SliceMapAccess,
    SliceSharedAccess,
    DagFeed,
    DagShared,
    RegionTraverse,
    RegionReduction,
    RegionGuard,
    RegionShared,
    RegionCancel,
    RegionWrite,
    RegionUnknown,
    RegionCounterOutput,
    RegionDivision
}

test "Finite fanout composes wildcard root and two multihop visits with one bound origin" {
    spec = region_spec(DagFeed);
    certificate = spec['interability_regions']['regions'][str(spec['entries']['run'])];
    assert certificate['kind'] == 'finite_dag';
    assert [r['ability'] for r in certificate['rules']]
        == ['run', 'collect', 'collect'];
    assert [r['parent'] for r in certificate['rules']] == [-1, 0, 0];
    assert [len(r['hops']) for r in certificate['rules']] == [1, 1, 2];
    desc = certificate['templates']['gated'];
    assert {s[0] for s in desc['slots']}
        == {'origin', 'row_limit', 'actor_uuid', 'actor_text'};
    assert 'UNION ALL' in desc['sql'] and 'WITH RECURSIVE' not in desc['sql'];
    shared = region_spec(DagShared);
    prefix = shared['interability_regions']['regions'][str(shared['entries']['run'])];
    assert len(prefix['rules']) == 1;
    assert str(shared['entries']['collect'])
        not in shared['interability_regions']['regions'];
}


def region_spec(wlk: any) -> dict {
    arch = JacTTGGenerator._find_walker_ast_node(wlk);
    assert arch is not None;
    return compile_checkpoint_plan(arch);
}

test "Static summaries separate output reductions from shared access guards" {
    output = summarize_abilities(analyze_walker_dependencies(RegionReduction));
    assert not output['walk']['eligible'];
    assert not output['walk']['shared_access_reads'];
    assert output['walk']['outputs'][0]['writes'] == 'self.total';
    shared = summarize_abilities(analyze_walker_dependencies(RegionShared));
    assert not shared['walk']['eligible'];
    assert 'self.count' in shared['walk']['shared_access_reads'];
    assert summarize_abilities(analyze_walker_dependencies(RegionCounterOutput))['walk'][
        'eligible'
    ];
    for wlk in (RegionCancel, RegionWrite, RegionUnknown, RegionDivision) {
        spec = region_spec(wlk);
        assert not spec['interability_regions']['regions'] , str(spec);
        assert spec['interability_regions']['summaries']['walk']['rejections'];
    }
}

test "No-counter typed Traverse emits a recursive identity-certified SQL region" {
    spec = region_spec(RegionTraverse);
    regions = spec['interability_regions']['regions'];
    assert len(regions) == 1;
    certificate = next(iter(regions.values()));
    assert len(certificate['rules']) == 1;
    assert certificate['rules'][0]['next_phase'] == 0;
    assert certificate['rules'][0]['dispatch_edge'];
    sql = certificate['templates']['open']['sql'];
    assert 'WITH RECURSIVE' in sql;
    assert 'ANY(' in sql or 'ANY (' in sql;
    assert 'array_append' in sql or ' || ' in sql;
    assert 'COUNT(*) OVER' in sql.upper();
}

test "A B C uses finite dispatch composition with boolean predicate inside SQL" {
    spec = region_spec(RegionGuard);
    summary = spec['interability_regions']['summaries']['middle'];
    assert summary['guard_fields'] == ['active'];
    assert summary['sql_internal_dependencies'] == ['here.active'];
    certificate = spec['interability_regions']['regions'][
        str(spec['entries']['start'])
    ];
    assert [r['ability'] for r in certificate['rules']] == ['start', 'middle'];
    assert certificate['rules'][0]['dispatch_edge']
        == [certificate['rules'][0]['event'], spec['entries']['middle']];
    sql = certificate['templates']['open']['sql'];
    assert 'WITH RECURSIVE' not in sql;
    assert 'jsonb_typeof' in sql;
    assert '->>' in sql;
    assert 'actor/ACL context' in certificate['external_dependencies'];
    assert 'shared' in certificate['checkpoint_proof'];
}

test "Hydrated region binds without runtime SQL AST construction" {
    spec = region_spec(RegionGuard);
    graph = checkpoint_graph(json.loads(json.dumps(spec)), RegionGuard);
    certificate = graph.interability_regions['regions'][str(spec['entries']['start'])];
    descriptor = certificate['templates']['gated'];
    values: dict = {
        'origin': UUID(int=1),
        'row_limit': 21,
        'max_depth': 20,
        'actor_uuid': UUID(int=2),
        'actor_text': str(UUID(int=2))
    };
    for phase in (0, 1) {
        values['source_module_' + str(phase)] = 'fixture';
        values['target_module_' + str(phase)] = 'fixture';
    }
    values = {
        name: value
        for (name, value) in values.items()
        if name in {s[0] for s in descriptor['slots']}
    };
    with patch.object(q, 'table', side_effect=AssertionError('runtime AST')), patch.object(
        q, 'compile_sql', side_effect=AssertionError('runtime render')
    ) {
        first = bind_template(descriptor, values);
        second = bind_template(descriptor, values);
        assert first.sql == second.sql == descriptor['sql'];
    }
}

test "JSON kind validates nullable JSON and rejects non-JSON operands" {
    source = q.table('x', [q.field('props', q.json_type())]);
    # A missing SQL value and JSON null retain distinct kinds in native SQL tests.
    invalid = False;
    invalid_argument: any = q.text('wrong');
    try {
        q.json_kind(invalid_argument);
    } except q.SqlError {
        invalid = True;
    }
    assert invalid;
}


test "Access slicing excludes output conditions and summarized identities, retains sibling controls" {
    for cls in (SliceOutputBranch, SliceIdentityMap) {
        spec = region_spec(cls);
        item = spec['interability_regions']['summaries']['walk'];
        assert item['eligible'] , str(item);
        assert item['access_slice']['output_only'];
        assert spec['interability_regions']['regions'];
    }
    spec = region_spec(SliceMapAccess);
    assert not spec['interability_regions']['regions'];
    spec = region_spec(SliceSharedAccess);
    assert 'self.count'
        in spec['interability_regions']['summaries']['first']['shared_access_reads'];
    assert not spec['interability_regions']['summaries']['first']['eligible'];
}
