"""DB-free fused SQL shape and semantic certificate regressions."""
import from uuid { UUID }
import jaclang.sql as q;
import from jaclang.runtime.ttg_fusion { certify_fused_region }
import from jaclang.runtime.ttg_fusion_sql { compile_fused_region }
import from jaclang.runtime.ttg_dependencies { analyze_walker_dependencies, TraceEvent }
import from .fixtures.ttg_continuation_walkers { AnalyzeItem, AnalyzeTraverse }


def bounded_contract -> dict {
    graph = analyze_walker_dependencies(AnalyzeTraverse);
    point = len(graph.events);
    graph.events.append(
        TraceEvent(
            id=point,
            kind='entry',
            ability='walk',
            line=0,
            next_id=graph.entries['walk']
        )
    );
    return certify_fused_region(
        graph,
        {'id': 'start', 'node_type': AnalyzeItem, 'facts': {'value': 0}},
        point,
        {'self.visited': 0, 'walk::here.value': 0},
        [],
        2048
    );
}

test "Counter cutoff certifies actual activations and stable visit program positions" {
    region = bounded_contract();
    assert region['kind'] == 'linear' , str(region);
    assert region['max_origins'] == 3 , str(region);
    assert len(region['transition_trace']) == 3;
    assert [t['scalar_state']['self.visited'] for t in region['transition_trace']]
        == [1, 2, 3];
    assert 'cancel' in region['stop'];
}

test "Fused SQL AST carries actual fanout and exact type guards with empty markers" {
    region = bounded_contract();
    compiled = compile_fused_region(region, [UUID(int=1)], None, 2048);
    assert 'WITH RECURSIVE' in compiled.sql;
    assert 'LEFT JOIN LATERAL' in compiled.sql;
    assert 'COUNT(*) OVER' in compiled.sql;
    assert 'LIMIT 2049' in compiled.sql;
    assert 'arch_module' in compiled.sql;
}

test "Batch region preserves multiple native path slots and structured ACL" {
    region = {
        'kind': 'batch',
        'rules': [
            {'hops': (('AnalyzeNext', None, 2), )},
            {'hops': ((None, 'AnalyzeItem', 1), (None, 'AnalyzeItem', 3))}
        ]
    };
    compiled = compile_fused_region(
        region, [UUID(int=1), UUID(int=2)], str(UUID(int=3)), 20
    );
    assert 'UNION ALL' in compiled.sql;
    assert 'LEFT JOIN LATERAL' in compiled.sql;
    assert '->>' in compiled.sql;
    assert ' ? ' in compiled.sql;
    assert 'undirected' in compiled.sql;
    assert 'ROW_NUMBER() OVER' in compiled.sql;
}

test "JSON operators reject incorrectly typed SQL expressions" {
    caught = False;
    try {
        q._call('JSON_GET', (q.text('wrong').ast, q.text('key').ast));
    } except q.SqlError {
        caught = True;
    }
    assert caught;
}
