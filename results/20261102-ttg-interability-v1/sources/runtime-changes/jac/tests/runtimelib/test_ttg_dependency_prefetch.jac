"""Exercise selected-visit SQL, real background loading and cache consumption."""
import from pathlib { Path }
import from tempfile { TemporaryDirectory }
import from types { SimpleNamespace }
import from threading { Event, Lock }
import from unittest.mock { patch }
import from uuid { UUID }
import from jaclang.runtime.runtime { JacRuntime }
import from jaclang.runtime.context { ExecutionContext }
import from jaclang.runtime.ttg_dependency_prefetch {
    dependency_prefetch,
    DependencyPrefetchRun
}
import from jaclang.runtime.ttg_checkpoints { capture_dependency_checkpoints }
import from jaclang.runtime.prefetch { dispatch_prefetch }
import from .fixtures.ttg_prefetch_walkers {
    FetchA,
    FetchB,
    FetchC,
    FetchSubC,
    FetchD,
    FetchStop,
    FetchLink,
    FetchOther,
    FetchSubLink,
    FetchBranch,
    FetchCancelled,
    FetchMultiHop,
    FetchMultiCycle,
    FetchMultiSequence,
    FetchFilteredMultiHop,
    FetchNoise
}
import from jaclang.runtime.ttg_dependencies { analyze_walker_dependencies }

import from .fixtures.ttg_prefetch_helpers {
    seed_fetch_graph,
    open_fetch_context,
    fetch_origin
}

test "dependency prefetch: multi-hop path retains types directions and terminal dispatch" {
    graph = analyze_walker_dependencies(FetchMultiHop);
    visits = [
        e
        for e in graph.events
        if e.ability == 'choose' and e.kind == 'visit'
    ];
    assert len(visits) == 1;
    assert visits[0].hop_chain
        == (('FetchOther', 'FetchNoise', 2), ('FetchLink', 'FetchC', 2)) , str(
        visits[0].hop_chain
    );
    assert visits[0].targets == ('FetchC', );
    assert graph.dispatch[visits[0].id] == ['collect'];
    assert graph.predict_handler('choose', {}).complete;
    mixed = analyze_walker_dependencies(FetchMultiSequence).predict_handler(
        'choose', {}
    );
    assert mixed.complete , str(mixed.unresolved);
    assert len(mixed.visits) == 2;
    cycle = analyze_walker_dependencies(FetchMultiCycle);
    event = [
        e
        for e in cycle.events
        if e.ability == 'choose' and e.kind == 'visit'
    ][0];
    assert event.hop_chain
        == (
            ('FetchOther', 'FetchNoise', 2),
            ('FetchOther', 'FetchB', 1),
            ('FetchLink', 'FetchC', 2)
        ) , str(event.hop_chain);
}

test "dependency prefetch: multi-hop value filters remain explicit barriers" {
    graph = analyze_walker_dependencies(FetchFilteredMultiHop);
    assert not graph.predict_handler('choose', {}).complete;
    assert any(
        e.kind == 'barrier'
        for e in graph.events
        if e.ability == 'choose'
    );
}

def run_multi_walk(origin: FetchA, cyclic: bool) -> list[str] {
    if cyclic {
        cycle = FetchMultiCycle();
        origin spawn cycle;
        return cycle.seen;
    }
    direct = FetchMultiHop();
    origin spawn direct;
    assert direct.intermediate_visits == 0;
    return direct.seen;
}

test "dependency prefetch: multi-hop and finite cyclic paths consume terminal payloads in native order" {
    original = JacRuntime.exec_ctx;
    try {
        for cyclic in [False, True] {
            for mode in ['', 'thread'] {
                with TemporaryDirectory() as project {
                    ids = seed_fetch_graph(project, multihop=True);
                    ctx = open_fetch_context(project);
                    try {
                        expected = run_multi_walk(
                            fetch_origin(ctx, ids['start']), cyclic
                        );
                        assert set(expected) == {'c0', 'c1', 'c2'} , str(expected);
                    } finally {
                        ctx.close();
                    }
                    ctx = open_fetch_context(project);
                    try {
                        origin = fetch_origin(ctx, ids['start']);
                        with capture_dependency_checkpoints() as capture {
                            with dependency_prefetch(ctx, mode=mode) as run {
                                seen = run_multi_walk(origin, cyclic);
                            }
                        }
                        assert run.errors == [] , str(run.errors);
                        assert seen == expected , str(seen);
                        assert run.submitted == ids['c'] | ids['b'] , str(
                            run.summary()
                        );
                        assert run.promoted == run.submitted , str(run.summary());
                        assert not (run.submitted & ids['intermediate']);
                        assert ids['decoy'] not in run.submitted;
                        assert any(len(r['paths']) >= 2 for r in run.continuations) , str(
                            run.continuations
                        );
                    } finally {
                        ctx.close();
                    }
                }
            }
        }
    } finally {
        JacRuntime.exec_ctx = original;
    }
}

test "dependency prefetch: chosen branch and edge subtypes populate and consume raw cache" {
    import jaclang.runtime.prefetch as prefetch_module;
    original_dispatch: any = dispatch_prefetch;
    def complete_dispatch(
        ctx: any,
        prefetch_ids: list,
        mode: str,
        workers: int = 1,
        append: bool = False,
        observer: any = None
    ) {
        original_dispatch(
            ctx, prefetch_ids, mode, workers, append=append, observer=observer
        );
        # This checks completed raw-cache promotion, not the production deadline.
        # Preserve thread execution while synchronizing before native demand.
        for thread in list(getattr(ctx.mem, '_prefetch_threads', [])) {
            thread.join(timeout=5);
            assert not thread.is_alive() , 'Test prefetch worker did not complete';
        }
    }
    original = JacRuntime.exec_ctx;
    try {
        for (value, chosen, mode) in [(13, 'c', ''), (3, 'd', 'thread')] {
            with TemporaryDirectory() as project {
                ids = seed_fetch_graph(project, value);
                ctx = open_fetch_context(project);
                try {
                    origin = fetch_origin(ctx, ids['start']);
                    wlk = FetchBranch();
                    with patch.object(
                        prefetch_module,
                        'dispatch_prefetch',
                        side_effect=complete_dispatch
                    ), capture_dependency_checkpoints() as capture {
                        with dependency_prefetch(ctx, mode=mode) as run {
                            origin spawn wlk;
                        }
                    }
                    assert run.errors == [] , str(run.errors);
                    assert run.submitted == ids[chosen] | ids['b'] , str(run.summary());
                    assert run.promoted == run.submitted , str(run.summary());
                    assert sorted(wlk.seen) == [chosen + str(i) for i in range(3)];
                    assert ids['decoy'] not in run.submitted;
                    assert len(run.plans) == 2 , str(run.plans);
                    assert run.summary()['unused_cached_ids'] == [];
                    assert run.summary()['unavailable_ids'] == [];
                    statuses = [
                        r.get('prefetch_status')
                        for r in capture.records
                        if r['target_ability'] == 'choose'
                    ];
                    assert statuses and set(statuses) == {'continuation'} , str(
                        statuses
                    );
                } finally {
                    ctx.close();
                }
            }
        }
    } finally {
        JacRuntime.exec_ctx = original;
    }
}

test "dependency prefetch: configured policy activates with ordinary spawn" {
    import jaclang.project.config as config;
    from_cfg = config.get_config();
    assert from_cfg is not None;
    original = JacRuntime.exec_ctx;
    try {
        with TemporaryDirectory() as project {
            ids = seed_fetch_graph(project);
            ctx = open_fetch_context(project);
            try {
                origin = fetch_origin(ctx, ids['start']);
                with patch.object(from_cfg.run, 'prefetching', 'ttg_dependency'), patch.object(
                    from_cfg.run, 'async_prefetch', 'thread'
                ) {
                    origin spawn FetchBranch();
                }
                metrics = getattr(ctx, '_ttg_dependency_metrics');
                assert set(metrics['submitted_ids'])
                    == {str(uid) for uid in (ids['c'] | ids['b'])} , str(metrics);
                assert set(metrics['promoted_ids']) == set(metrics['submitted_ids']) , str(
                    metrics
                );
            } finally {
                ctx.close();
            }
        }
    } finally {
        JacRuntime.exec_ctx = original;
    }
}

test "dependency prefetch: cap preserves demand results and skips unselected branch" {
    original = JacRuntime.exec_ctx;
    try {
        with TemporaryDirectory() as project {
            ids = seed_fetch_graph(project);
            ctx = open_fetch_context(project);
            try {
                origin = fetch_origin(ctx, ids['start']);
                wlk = FetchBranch();
                with dependency_prefetch(ctx, max_length=2, mode='') as run {
                    origin spawn wlk;
                }
                assert len(run.submitted) == 2;
                assert ids['b'] <= run.submitted;
                assert run.submitted <= ids['b'] | ids['c'];
                assert run.promoted == run.submitted;
                assert sorted(wlk.seen) == ['c0', 'c1', 'c2'];
            } finally {
                ctx.close();
            }
        }
    } finally {
        JacRuntime.exec_ctx = original;
    }
}

test "dependency prefetch: cancelled queued target submits no work" {
    original = JacRuntime.exec_ctx;
    try {
        with TemporaryDirectory() as project {
            ids = seed_fetch_graph(project);
            ctx = open_fetch_context(project);
            try {
                origin = fetch_origin(ctx, ids['start']);
                model = TestAdmissionModel(reject_phase='never');
                with dependency_prefetch(ctx, mode='', model=model) as run {
                    origin spawn FetchCancelled();
                }
                assert run.submitted == ids['stop'] | ids['b'];
                assert not (run.submitted & ids['c']);
                assert run.errors == [];
                assert model.calls;
            } finally {
                ctx.close();
            }
        }
    } finally {
        JacRuntime.exec_ctx = original;
    }
}

test "dependency prefetch: lookup uses ordinary SQL transaction error handling" {
    original = JacRuntime.exec_ctx;
    try {
        with TemporaryDirectory() as project {
            ctx = open_fetch_context(project);
            try {
                store = ctx.mem.store;
                assert store is not None;
                store.rows('CREATE TABLE dependency_query_error_test (n integer)', {});
                ctx.mem.read_barrier();
                store.rows('INSERT INTO dependency_query_error_test VALUES (7)', {});
                raised = False;
                try {
                    store.rows('SELECT 1 / 0', {});
                } except Exception {
                    raised = True;
                }
                assert raised;
                assert store.rows('SELECT n FROM dependency_query_error_test', {})
                    == [];
            } finally {
                ctx.close();
            }
        }
    } finally {
        JacRuntime.exec_ctx = original;
    }
}

test "dependency prefetch: resolver error propagates instead of continuing traversal" {
    import jaclang.data.query_planner as planner;
    original = JacRuntime.exec_ctx;
    try {
        with TemporaryDirectory() as project {
            ids = seed_fetch_graph(project);
            ctx = open_fetch_context(project);
            try {
                origin = fetch_origin(ctx, ids['start']);
                wlk = FetchBranch();
                raised = False;
                with patch.object(
                    planner,
                    'compile_query',
                    return_value=SimpleNamespace(
                        sql='SELECT 1 / 0', params={}, residual={}
                    )
                ) {
                    with dependency_prefetch(ctx) as run {
                        try {
                            origin spawn wlk;
                        } except Exception {
                            raised = True;
                        }
                    }
                }
                assert raised;
                assert run.submitted == set();
                assert run.errors;
                assert wlk.seen == [];
            } finally {
                ctx.close();
            }
        }
    } finally {
        JacRuntime.exec_ctx = original;
    }
}

test "dependency prefetch: appending batches retains every outstanding worker" {
    first = Event();
    second = Event();
    entered = [Event(), Event()];
    gates = [first, second];
    ids = [UUID(int=1), UUID(int=2)];
    loaded: list = [];
    def load(batch: list) {
        index = 0 if batch[0] == ids[0] else 1;
        entered[index].set();
        assert gates[index].`wait(timeout=5);
        loaded.extend(batch);
    }
    mem = SimpleNamespace(prefetch=load);
    ctx = SimpleNamespace(mem=mem);
    try {
        dispatch_prefetch(ctx, [ids[0]], 'thread', append=True);
        assert entered[0].`wait(timeout=5);
        dispatch_prefetch(ctx, [ids[1]], 'thread', append=True);
        assert entered[1].`wait(timeout=5);
        assert mem._prefetch_ids == set(ids);
        assert len(mem._prefetch_threads) == 2;
        second.set();
        mem._prefetch_threads[1].join(timeout=5);
        assert not mem._prefetch_done.is_set();
        first.set();
        assert mem._prefetch_done.`wait(timeout=5);
        assert set(loaded) == set(ids);
    } finally {
        first.set();
        second.set();
        for thread in getattr(mem, '_prefetch_threads', []) {
            thread.join(timeout=5);
        }
    }
}

test "dependency prefetch: worker failure preserves foreground demand results" {
    import from jaclang.server.session { Session }
    original = JacRuntime.exec_ctx;
    try {
        with TemporaryDirectory() as project {
            ids = seed_fetch_graph(project);
            ctx = open_fetch_context(project);
            try {
                origin = fetch_origin(ctx, ids['start']);
                wlk = FetchBranch();
                with patch.object(
                    Session, 'prefetch', side_effect=RuntimeError('worker failed')
                ) {
                    with dependency_prefetch(ctx, mode='thread') as run {
                        origin spawn wlk;
                    }
                }
                assert run.submitted == ids['c'] | ids['b'];
                assert run.promoted == set();
                assert set(run.summary()['unavailable_ids'])
                    == {str(uid) for uid in run.submitted};
                assert sorted(wlk.seen) == ['c0', 'c1', 'c2'];
            } finally {
                ctx.close();
            }
        }
    } finally {
        JacRuntime.exec_ctx = original;
    }
}

test "dependency prefetch: two selected visit sites load both batches into the same cache" {
    import from .fixtures.ttg_prefetch_walkers { FetchBoth }
    original = JacRuntime.exec_ctx;
    try {
        with TemporaryDirectory() as project {
            ids = seed_fetch_graph(project);
            ctx = open_fetch_context(project);
            try {
                origin = fetch_origin(ctx, ids['start']);
                wlk = FetchBoth();
                with dependency_prefetch(ctx, mode='thread') as run {
                    origin spawn wlk;
                }
                assert run.errors == [] , str(run.errors);
                assert run.submitted == ids['c'] | ids['d'] | ids['b'] , str(
                    run.summary()
                );
                assert run.promoted == run.submitted , str(run.summary());
                assert sorted(wlk.seen) == ['c0', 'c1', 'c2', 'd0', 'd1', 'd2'];
                assert len(run.plans) == 3;
                assert run.summary()['unused_cached_ids'] == [];
            } finally {
                ctx.close();
            }
        }
    } finally {
        JacRuntime.exec_ctx = original;
    }
}

import from jaclang.runtime.ttg_prefetch_model {
    PrefetchDecisionModel,
    PrefetchFeatures,
    PrefetchAdmission,
    PrefetchOutcome
}

obj TestAdmissionModel(PrefetchDecisionModel) {
    has reject_phase: str = 'resolve',
        calls: list[str] = [];

    def decide(features: PrefetchFeatures) -> PrefetchAdmission {
        import from jaclang.runtime.ttg_prefetch_model { PrefetchAdmission }
        self.calls.append(features.phase);
        if self.reject_phase == 'error' {
            raise ValueError('model failure');
        }
        return PrefetchAdmission(features.phase != self.reject_phase, 'test admission');
    }

    def observe(outcome: PrefetchOutcome) { }
}

test "dependency prefetch: replaceable model skips resolution or payload with identical results" {
    import from jaclang.runtime.ttg_prefetch_profile { OnlinePrefetchProfile }
    import from jaclang.data.query_planner { resolve_ttg_path }
    original = JacRuntime.exec_ctx;
    try {
        for phase in ['resolve', 'load', 'error'] {
            with TemporaryDirectory() as project {
                ids = seed_fetch_graph(project);
                ctx = open_fetch_context(project);
                try {
                    origin = fetch_origin(ctx, ids['start']);
                    wlk = FetchBranch();
                    model = TestAdmissionModel(reject_phase=phase);
                    with patch(
                        'jaclang.data.query_planner.resolve_ttg_path',
                        wraps=resolve_ttg_path
                    ) as rows {
                        with dependency_prefetch(
                            ctx, model=model, provider=OnlinePrefetchProfile()
                        ) as run {
                            origin spawn wlk;
                        }
                        assert rows.call_count == (2 if phase == 'load' else 0) , str(
                            rows.call_count
                        );
                    }
                    assert sorted(wlk.seen) == ['c0', 'c1', 'c2'];
                    assert run.submitted == set();
                    assert len(run.plans) == 2;
                    assert all(item['demanded'] for item in run.feedback) , str(
                        run.summary()
                    );
                    assert model.calls
                        == (
                            ['resolve', 'resolve', 'load', 'load']
                                if phase == 'load'
                                else ['resolve', 'resolve']
                        ) , str(model.calls);
                    assert bool(run.errors) == (phase == 'error');
                } finally {
                    ctx.close();
                }
            }
        }
    } finally {
        JacRuntime.exec_ctx = original;
    }
}

test "dependency prefetch: live profile observes actual branches and payload readiness" {
    import from jaclang.runtime.ttg_prefetch_profile { OnlinePrefetchProfile }
    original = JacRuntime.exec_ctx;
    profile = OnlinePrefetchProfile();
    outcomes: list = [];
    try {
        for value in [13, 3] {
            with TemporaryDirectory() as project {
                ids = seed_fetch_graph(project, value);
                ctx = open_fetch_context(project);
                try {
                    origin = fetch_origin(ctx, ids['start']);
                    with dependency_prefetch(ctx, provider=profile) as run {
                        origin spawn FetchBranch();
                    }
                    assert run.errors == [] , str(run.errors);
                    assert len(run.feedback) == 2 , str(run.summary());
                    current_run = run as DependencyPrefetchRun;
                    metrics = current_run.summary();
                    outcome: dict = [
                        item
                        for item in metrics['feedback']
                        if ':choose:' in item['ability_key']
                    ][0];
                    assert outcome['demanded'] , str(outcome);
                    assert outcome['payload_ms'] is not None;
                    assert outcome['overlap_ms'] >= 0;
                    assert outcome['resolved_nodes'] == 3;
                    outcomes.append(outcome);
                } finally {
                    ctx.close();
                }
            }
        }
        assert outcomes[0]['ability_key'] == outcomes[1]['ability_key'];
        branch = profile.branches[outcomes[0]['ability_key']];
        assert branch['entries'] == 2 , str(branch);
        for outcome in outcomes {
            assert branch['visits'][outcome['site_key']] == 1 , str(branch);
        }
    } finally {
        JacRuntime.exec_ctx = original;
    }
}

test "dependency prefetch: configured model and scoped override select policy" {
    import jaclang.project.config as config;
    import from jaclang.runtime.ttg_prefetch_model {
        use_prefetch_model,
        AlwaysPrefetch
    }
    cfg = config.get_config();
    assert cfg is not None;
    original = JacRuntime.exec_ctx;
    try {
        with TemporaryDirectory() as project {
            ids = seed_fetch_graph(project);
            for use_override in [False, True] {
                ctx = open_fetch_context(project);
                try {
                    origin = fetch_origin(ctx, ids['start']);
                    wlk = FetchBranch();
                    with patch.object(cfg.run, 'prefetching', 'ttg_dependency'), patch.object(
                        cfg.run, 'async_prefetch', ''
                    ), patch.object(
                        cfg.run, 'ttg_prefetch_model', 'expected_benefit'
                    ) {
                        if use_override {
                            with use_prefetch_model(AlwaysPrefetch()) {
                                origin spawn wlk;
                            }
                        } else {
                            origin spawn wlk;
                        }
                    }
                    metrics: dict = getattr(ctx, '_ttg_dependency_metrics');
                    assert len(metrics['submitted_ids'])
                        == (4 if use_override else 0) , str(metrics);
                    assert metrics['model']
                        == ('AlwaysPrefetch' if use_override else 'ExpectedBenefit');
                    assert len(metrics['feedback']) == 2 , str(metrics);
                    assert sorted(wlk.seen) == ['c0', 'c1', 'c2'];
                } finally {
                    ctx.close();
                }
            }
        }
    } finally {
        JacRuntime.exec_ctx = original;
    }
}
