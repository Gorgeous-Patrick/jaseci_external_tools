"""Filtered output-tree compiler and cache contracts without a database."""
import from types { SimpleNamespace }
import from unittest.mock { patch }
import from jaclang.runtime.ttg { JacTTGGenerator }
import from jaclang.runtime.ttg_output_tree {
    compile_effect_certificate,
    validate_effects
}
import from jaclang.runtime.ttg_dependencies { compile_checkpoint_plan }
import from jaclang.runtime.ttg_templates { cache_key, native_shape }
import from jaclang.runtime.graph_query { GraphQuery, QHop, QPred }
import from .fixtures.ttg_region_walkers { OutputTree, OutputFolder, OutputContains }

test "Filtered tree compiler emits constant path predicates and output proof" {
    arch = JacTTGGenerator._find_walker_ast_node(OutputTree);
    assert arch is not None;
    certificate = compile_effect_certificate(arch);
    assert certificate is not None;
    assert certificate['predicates'] == [['trashed', '==', False]];
    assert certificate['node_fields'] == ['name', 'trashed'];
    spec = compile_checkpoint_plan(arch);
    regions = spec['interability_regions']['regions'];
    assert len(regions) == 1;
    assert list(regions.values())[0]['kind'] == 'output_tree';
    assert 'WITH RECURSIVE' in list(regions.values())[0]['templates']['open']['sql'];
}

test "Filtered cache distinguishes predicates and shares loop with visit" {
    query = GraphQuery(
        [],
        hops=[
            QHop(
                dir=2,
                `edge=OutputContains,
                nd=OutputFolder,
                preds=[QPred('trashed', '==', False)]
            )
        ]
    );
    original = cache_key(query, [], None);
    assert original is not None;
    assert cache_key(query.`visit(), [], None) == original;
    assert native_shape(query, 0) is None;
    other = GraphQuery(
        [],
        hops=[
            QHop(
                dir=2,
                `edge=OutputContains,
                nd=OutputFolder,
                preds=[QPred('trashed', '==', True)]
            )
        ]
    );
    assert cache_key(other, [], None) != original;
    plain = GraphQuery([], hops=[QHop(dir=2, `edge=OutputContains, nd=OutputFolder)]);
    assert cache_key(plain, [], None) != original;
    other.limit = 1;
    assert cache_key(other, [], None) is None;
}

test "Output effect checker proves fresh defaults and rejects graph alias" {
    arch = JacTTGGenerator._find_walker_ast_node(OutputTree);
    assert arch is not None;
    certificate = compile_effect_certificate(arch);
    wlk = OutputTree();
    memory: any = SimpleNamespace(__mem__={});
    assert validate_effects(certificate, wlk, OutputFolder, memory, None)
        == {'name': 'str', 'trashed': 'bool'};
    memory.__mem__ = {'test': {'aliased': wlk.depths}};
    failed = False;
    try {
        validate_effects(certificate, wlk, OutputFolder, memory, None);
    } except ValueError as error {
        failed = 'aliases graph or queue' in str(error);
    }
    assert failed;
}

test "Output constructor and descriptor checks do not execute unknown effects" {
    import from .fixtures.ttg_region_walkers { OutputRow }
    import sys;
    arch = JacTTGGenerator._find_walker_ast_node(OutputTree);
    assert arch is not None;
    certificate = compile_effect_certificate(arch);
    wlk = OutputTree();
    memory: any = SimpleNamespace(__mem__={});
    calls: list = [];
    def unsafe(*args: any, **kwargs: any) -> any {
        calls.append(True);
        raise AssertionError('Unknown code executed');
    }
    for mode in ('initializer', 'descriptor', 'jid', 'walker_setter', 'node_setter') {
        failed = False;
        guard = patch.object(OutputRow, '__init__', unsafe)
            if mode == 'initializer'
            else (
                patch.object(OutputRow, 'path', property(unsafe, unsafe))
                    if mode == 'descriptor'
                    else patch.dict(
                        vars(sys.modules[OutputTree.__module__]), {'jid': unsafe}
                    )
            );
        if mode == 'walker_setter' { guard = patch.object(OutputTree, '__setattr__', unsafe); }
        if mode == 'node_setter' { guard = patch.object(OutputFolder, '__setattr__', unsafe); }
        with guard {
            try {
                validate_effects(certificate, wlk, OutputFolder, memory, None);
            } except ValueError {
                failed = True;
            }
        }
        assert failed and not calls;
    }
}
