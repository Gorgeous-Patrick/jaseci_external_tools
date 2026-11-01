"""Observed unsafe fields stay distinct from absent declared scalar facts."""
import from jaclang.runtime.ttg_continuation {
    known_node_fields,
    _integer_expression,
    _append_argument_known,
    plan_continuation
}
import from jaclang.runtime.ttg_dependencies { analyze_walker_dependencies, TraceEvent }
import from .fixtures.ttg_continuation_walkers {
    AnalyzeItem,
    AnalyzeSum,
    AnalyzeTraverse
}

class UnsafeInt(int) {
    def __radd__(self: UnsafeInt, other: any) -> any {
        raise RuntimeError('Unsafe integer arithmetic ran');
    }
}

class UnsafeField {
    def __get__(self: UnsafeField, instance: any, owner: any) -> any {
        raise RuntimeError('Descriptor getter ran');
    }

    def __set__(self: UnsafeField, instance: any, value: any) {
        raise RuntimeError('Descriptor setter ran');
    }
}


def unsafe_prefix(walker_type: type, facts: dict) -> dict {
    graph = analyze_walker_dependencies(walker_type);
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
    values = {'self.total': 0, 'self.visited': 0};
    for (name, value) in facts.items() {
        values['walk::here.' + name] = value;
    }
    def forbidden(active: dict, event: any) -> any {
        raise RuntimeError('Unsafe prefix reached a visit');
    }
    return plan_continuation(
        graph,
        {'id': 'start', 'node_type': AnalyzeItem, 'facts': facts},
        point,
        values,
        [],
        forbidden
    );
}

test "Cached integer subclass cannot requalify as an absent declared int" {
    item = AnalyzeItem(value=UnsafeInt(2));
    facts = known_node_fields(item);
    assert 'value' not in facts;
    assert facts['value::unsafe'];
    values = {'walk::here.value::unsafe': True};
    assert not _integer_expression('here.value', values, set(), AnalyzeItem, 'walk');
    result = unsafe_prefix(AnalyzeSum, facts);
    assert not result['complete'];
    assert result['paths'] == [];
}

test "Cached nonprimitive output stops before traversal" {
    item = AnalyzeItem();
    vars(item)['value'] = ['unsafe'];
    facts = known_node_fields(item);
    result = unsafe_prefix(AnalyzeTraverse, facts);
    assert 'unsafe' in result['stop'];
    assert result['paths'] == [];
}

test "Custom data descriptor cannot retain a raw instance fact" {
    item = AnalyzeItem(value=2);
    original = vars(AnalyzeItem)['value'];
    try {
        setattr(AnalyzeItem, 'value', UnsafeField());
        facts = known_node_fields(item);
        assert 'value' not in facts;
        assert facts['value::unsafe'];
        result = unsafe_prefix(AnalyzeSum, facts);
        assert result['paths'] == [];
    } finally {
        setattr(AnalyzeItem, 'value', original);
    }
}

test "Append refinement rejects observed unsafe arguments" {
    event = TraceEvent(
        id=0,
        kind='append',
        ability='walk',
        line=0,
        expression='here.value',
        reads=('walk::here.value', )
    );
    assert not _append_argument_known(
        event, {'walk::here.value::unsafe': True}, AnalyzeItem
    );
    assert _integer_expression('here.value', {}, set(), AnalyzeItem, 'walk');
    assert known_node_fields(AnalyzeItem(value=3))['value'] == 3;
}

test "Absent custom descriptor cannot use append declaration fallback" {
    original = vars(AnalyzeItem)['value'];
    event = TraceEvent(
        id=0,
        kind='append',
        ability='walk',
        line=0,
        expression='here.value',
        reads=('walk::here.value', )
    );
    try {
        setattr(AnalyzeItem, 'value', UnsafeField());
        assert not _append_argument_known(event, {}, AnalyzeItem);
        assert not _integer_expression('here.value', {}, set(), AnalyzeItem, 'walk');
    } finally {
        setattr(AnalyzeItem, 'value', original);
    }
}

test "Walker descriptor rejects raw snapshot facts before scalar execution" {
    original = vars(AnalyzeSum)['total'];
    try {
        setattr(AnalyzeSum, 'total', UnsafeField());
        result = unsafe_prefix(AnalyzeSum, {'value': 2});
        assert result['paths'] == [];
        assert 'field access' in result['stop'];
    } finally {
        setattr(AnalyzeSum, 'total', original);
    }
}

test "Unsafe marker dominates a conflicting primitive supplied fact" {
    import from jaclang.runtime.ttg_dependencies { _trace_eval }
    rejected = False;
    try {
        _trace_eval(
            'here.value',
            {'walk::here.value': 2, 'walk::here.value::unsafe': True},
            'walk'
        );
    } except ValueError {
        rejected = True;
    }
    assert rejected;
    result = unsafe_prefix(AnalyzeSum, {'value': 2, 'value::unsafe': True});
    assert result['paths'] == [];
}

test "Custom node dictionary descriptor is rejected before vars or getter" {
    import from jaclang.runtime.ttg_dependencies { _trace_safe_storage }
    unsafe_type = type(
        'UnsafeStorageNode', (AnalyzeItem, ), {'__dict__': UnsafeField()}
    );
    constructor: any = object.__new__;
    instance = constructor(unsafe_type);
    assert not _trace_safe_storage(unsafe_type);
    assert known_node_fields(instance) == {};
    assert not _integer_expression('here.value', {}, set(), unsafe_type, 'walk');
    assert _trace_safe_storage(AnalyzeItem);
}

test "Custom walker dictionary descriptor is rejected without executing getter" {
    import from jaclang.runtime.ttg_dependencies {
        _trace_safe_storage,
        _trace_field_effects,
        TraceEffects
    }
    unsafe_type = type(
        'UnsafeStorageWalker', (AnalyzeSum, ), {'__dict__': UnsafeField()}
    );
    graph = analyze_walker_dependencies(AnalyzeSum);
    graph.runtime_walker = unsafe_type;
    effects = TraceEffects();
    _trace_field_effects(graph, {'self.total'}, effects);
    assert effects.unknown;
    assert not _trace_safe_storage(unsafe_type);
    assert _trace_safe_storage(AnalyzeSum);
}
