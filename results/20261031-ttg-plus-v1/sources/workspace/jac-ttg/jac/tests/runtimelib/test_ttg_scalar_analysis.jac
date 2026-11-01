"""Activation and safety regressions for effect-aware continuation analysis."""
import from jaclang.runtime.ttg { JacTTGGenerator }
import from jaclang.runtime.ttg_dependencies { analyze_walker_dependencies }
import from .fixtures.ttg_continuation_walkers {
    AnalyzeItem,
    AnalyzeTraverse,
    AnalyzeSum,
    AnalyzeFind,
    AnalyzeDiv,
    AnalyzeAlias
}

def analyze_chain(walker_type: type, snapshot: dict, known: bool = False) -> tuple {
    graph = analyze_walker_dependencies(walker_type);
    calls: list[int] = [];
    def resolve(active: dict, event: any) -> list[dict] {
        index = int(active['id']);
        calls.append(index);
        if index >= 5 {
            return [];
        }
        item: dict = {'id': str(index + 1), 'node_type': AnalyzeItem};
        if known {
            item['facts'] = {'value': index + 1};
        }
        return [item];
    }
    # Entry checkpoint is represented by a no-op predecessor, so the entire
    # first ability is interpreted as well as all future FIFO activations.
    import from jaclang.runtime.ttg_dependencies { TraceEvent }
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
    result = JacTTGGenerator.get_continuation_plan(
        graph,
        {'id': '0', 'node_type': AnalyzeItem, 'facts': {'value': 0}},
        point,
        {'walk::here.value': 0} | dict(snapshot),
        [],
        resolve
    );
    return (result, calls, graph);
}

test "Scalar counter and passive report activate untyped multi-node traversal" {
    (result, calls, graph) = analyze_chain(AnalyzeTraverse, {'self.visited': 0});
    assert calls == [0, 1, 2] , str(result);
    assert [node['id'] for node in result['nodes']] == ['1', '2', '3'];
    assert result['executions'] == ['1', '2', '3'];
    assert 'cancel' in result['stop'];
    assert any(event.kind == 'scalar_update' for event in graph.events);
    assert any(event.kind == 'output' for event in graph.events);
    assert not any(event.kind == 'barrier' for event in graph.events);
}

test "Unknown integer accumulation does not block independent Next visits" {
    (result, calls, graph) = analyze_chain(AnalyzeSum, {'self.total': 0});
    assert result['complete'] , str(result);
    assert calls == [0, 1, 2, 3, 4, 5];
    assert len(result['nodes']) == 5;
}

test "Find uses known data to stop at its actual early exit" {
    (result, calls, graph) = analyze_chain(AnalyzeFind, {'self.target': 2}, True);
    assert calls == [0, 1] , str(result);
    assert [node['id'] for node in result['nodes']] == ['1', '2'];
    assert 'cancel' in result['stop'];
}

test "Unknown branch and potentially failing division stop future prediction" {
    (result, calls, graph) = analyze_chain(AnalyzeFind, {'self.target': 2});
    assert calls == [0] , str(result);
    assert not result['complete'];
    (divided, calls, graph) = analyze_chain(AnalyzeDiv, {'self.total': 1});
    assert not divided['complete'];
    assert calls == [];
    (unknown_division, calls, graph) = analyze_chain(
        AnalyzeDiv, {'self.total': 1, 'walk::here.value': 1}
    );
    assert not unknown_division['complete'];
    assert calls == [0];
}

test "Aliased augmented writes remain barriers" {
    (result, calls, graph) = analyze_chain(AnalyzeAlias, {});
    assert calls == [];
    assert 'barrier' in result['stop'];
}

test "Unknown accumulation blocks only branches that consume its result" {
    import from .fixtures.ttg_continuation_walkers {
        AnalyzeDependentSum,
        AnalyzeRecover
    }
    (result, calls, graph) = analyze_chain(AnalyzeDependentSum, {'self.total': 0});
    assert calls == [0] , str(result);
    assert not result['complete'];
    (recovered, calls, graph) = analyze_chain(AnalyzeRecover, {'self.total': 0});
    assert recovered['complete'] , str(recovered);
    assert calls == [0, 1, 2, 3, 4, 5];
}

test "Known scalar updates remain available as runtime checkpoints" {
    graph = analyze_walker_dependencies(AnalyzeTraverse);
    point = [
        e.id
        for e in graph.events
        if e.kind == 'scalar_update'
    ][0];
    result = graph.predict_after(
        point, {'self.visited': 4, 'walk::here.value': 0}, isolated=True
    );
    assert not result.complete;
    assert result.visits == [];
    assert any('Unsupported effect' in reason for reason in result.unresolved);
}

test "Native hooks activate scalar traversal and preserve reports and exit bound" {
    import from pathlib { Path }
    import from tempfile { TemporaryDirectory }
    import from jaclang.runtime.runtime { JacRuntime }
    import from jaclang.runtime.context { ExecutionContext }
    import from jaclang.runtime.ttg_dependency_prefetch { dependency_prefetch }
    import from .fixtures.ttg_continuation_walkers { AnalyzeNext }
    original = JacRuntime.exec_ctx;
    try {
        for mode in ['', 'thread', 'process'] {
            with TemporaryDirectory() as project {
                target = str(Path(project, 'scalar-analysis.jac'));
                seed = ExecutionContext(base_path_dir=project, full_target_path=target);
                JacRuntime.exec_ctx = seed;
                items = [AnalyzeItem(value=index) for index in range(6)];
                root ++> items[0];
                for index in range(5) {
                    items[index] +>:AnalyzeNext:+> items[index + 1];
                }
                start_id = items[0].__jac__.id;
                expected = {item.__jac__.id for item in items[1:4]};
                forbidden = {item.__jac__.id for item in items[4:]};
                seed.close();
                ctx = ExecutionContext(base_path_dir=project, full_target_path=target);
                JacRuntime.exec_ctx = ctx;
                try {
                    anchor = ctx.mem.get(start_id);
                    assert anchor is not None;
                    origin = anchor.archetype;
                    assert isinstance(origin, AnalyzeItem);
                    wlk = AnalyzeTraverse();
                    with dependency_prefetch(ctx, mode=mode) as run {
                        origin spawn wlk;
                    }
                    assert wlk.visited == 4;
                    assert wlk.reports == [0, 1, 2, 3] , str(wlk.reports);
                    assert run.submitted == expected , str(run.summary());
                    assert not (run.submitted & forbidden);
                    assert run.plans , str(run.summary());
                    assert not run.errors , str(run.errors);
                } finally {
                    ctx.close();
                }
            }
        }
    } finally {
        JacRuntime.exec_ctx = original;
    }
}

test "Field type refinement never evaluates a property getter" {
    import from jaclang.runtime.ttg_continuation { _plain_scalar_field }
    calls: list = [];
    def read_value(instance: any) -> int {
        calls.append('getter');
        return 1;
    }
    original = vars(AnalyzeItem)['value'];
    try {
        setattr(AnalyzeItem, 'value', property(read_value));
        assert not _plain_scalar_field(AnalyzeItem, 'value', (int, 'int'));
        assert calls == [];
    } finally {
        setattr(AnalyzeItem, 'value', original);
    }
}
