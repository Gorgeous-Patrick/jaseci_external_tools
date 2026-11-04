import from contextlib { contextmanager, nullcontext }
import from contextvars { ContextVar }
import from logging { getLogger }
import from time { perf_counter }
import from threading { get_ident }
import from uuid { UUID, uuid4 }
import from jaclang.runtime.ttg_prefetch_model {
    PrefetchDecisionModel,
    AlwaysPrefetch,
    PrefetchFeatures,
    PrefetchAdmission,
    PrefetchOutcome,
    create_prefetch_model,
    _model_override
}
import from jaclang.runtime.ttg_prefetch_profile {
    PrefetchFeatureProvider,
    default_prefetch_profile
}

glob _active: any = ContextVar('ttg_dependency_prefetch', `default=None),
     _logger = getLogger(__name__);

obj DependencyPrefetchRun {
    has ctx: any,
        max_length: int = 200,
        mode: str = 'thread',
        workers: int = 1,
        owner_thread: int = 0,
        submitted: set[UUID] = set(),
        promoted: set[UUID] = set(),
        resolved: set[tuple] = set(),
        plans: list[dict] = [],
        errors: list[str] = [],
        model: PrefetchDecisionModel | None = None,
        provider: PrefetchFeatureProvider | None = None,
        considered: dict[tuple, dict] = {},
        feedback: list[dict] = [],
        continuations: list[dict] = [],
        cache_token: str = '',
        fused_sql: bool = False,
        fusion: dict = {},
        scope_snapshots: dict[int, dict] = {};

    def summary -> dict {
        mem = self.ctx.mem;
        with mem._raw_lock {
            unused = self.submitted & set(mem.__raw_mem__);
        }
        return {
            'submitted_ids': sorted(str(uid) for uid in self.submitted),
            'promoted_ids': sorted(str(uid) for uid in self.promoted),
            'unused_cached_ids': sorted(str(uid) for uid in unused),
            'unavailable_ids': sorted(
                str(uid) for uid in (self.submitted - self.promoted - unused)
            ),
            'plans': self.plans,
            'errors': self.errors,
            'model': type(self.model).__name__,
            'executor': self.mode or 'sync',
            'worker_process_pids': list(getattr(mem, '_prefetch_process_pids', [])),
            'worker_process_startup_ms': list(
                getattr(mem, '_prefetch_process_startup_ms', [])
            ),
            'feature_provider': type(self.provider).__name__,
            'feedback': self.feedback,
            'continuations': self.continuations,
            'fusion': self.fusion
        };
    }
}

@contextmanager
def dependency_prefetch(
    ctx: any,
    max_length: int = 200,
    mode: str = 'thread',
    workers: int = 1,
    model: PrefetchDecisionModel | None = None,
    provider: PrefetchFeatureProvider | None = None,
    fused_sql: bool = False
) -> any {
    import from jaclang.runtime.ttg_checkpoints {
        _capture,
        capture_dependency_checkpoints
    }
    state = DependencyPrefetchRun(
        ctx=ctx,
        max_length=max_length,
        mode=mode,
        workers=max(1, workers),
        owner_thread=get_ident(),
        model=model or _model_override.get() or create_prefetch_model('always'),
        provider=provider or default_prefetch_profile
    );
    state.cache_token = str(uuid4());
    state.fused_sql = fused_sql and type(state.model) is AlwaysPrefetch;
    state.fusion = {
        'enabled': state.fused_sql,
        'requested': fused_sql,
        'effective_mode': 'fused_sql' if state.fused_sql else 'per_path',
        'fallback_reason': 'Fusion requires exact AlwaysPrefetch'
            if fused_sql and not state.fused_sql
            else '',
        'admission': 'AlwaysPrefetch only; shared batch costs are diagnostic and excluded from training',
        'queries': 0,
        'template_queries': 0,
        'region_queries': 0,
        'region_cache_paths': 0,
        'region_origins': 0,
        'region_reuses': 0,
        'region_fallbacks': 0,
        'region_fallback_reason': '',
        'region_fallback_reasons': {},
        'frontier_origins': 0,
        'legacy_fusion_calls': 0,
        'overflow': 0,
        'cache_paths': 0,
        'cache_empty_paths': 0,
        'cache_hits': 0,
        'fallback_resolver_calls': 0,
        'payload_dispatches': 0,
        'regions': []
    };
    existing = _capture.get();
    observer = nullcontext(existing)
        if existing is not None
        else capture_dependency_checkpoints(record_decisions=False);
    with observer {
        token = _active.set(state);
        try {
            yield state;
        } finally {
            try {
                for thread in list(getattr(ctx.mem, '_prefetch_threads', [])) {
                    thread.join();
                }
                import from jaclang.runtime.ttg_process_reader { close_process_readers }
                close_process_readers(ctx.mem);
                finish_prefetch_feedback(state);
            } finally {
                _active.reset(token);
            }
        }
    }
}

@contextmanager
def configured_dependency_prefetch(ctx: any, cfg: any) -> any {
    run_cfg = cfg?.run;
    if ctx is None
        or run_cfg is None
        or str(getattr(run_cfg, 'prefetching', '')).strip().lower() != 'ttg_dependency'
        or int(getattr(run_cfg, 'prefetch_limit', 0) or 0) <= 0 {
        yield None;
        return;
    }
    with dependency_prefetch(
        ctx,
        max_length=int(run_cfg.prefetch_limit),
        mode=str(getattr(run_cfg, 'async_prefetch', '')),
        workers=int(getattr(run_cfg, 'prefetch_workers', 1) or 1),
        fused_sql=bool(getattr(run_cfg, 'ttg_fused_sql', False)),
        model=_model_override.get()
            or create_prefetch_model(
                str(getattr(run_cfg, 'ttg_prefetch_model', 'always'))
            )
    ) as state {
        try {
            yield state;
        } finally {
            for thread in list(getattr(ctx.mem, '_prefetch_threads', [])) {
                thread.join();
            }
            setattr(ctx, '_ttg_dependency_metrics', state.summary());
        }
    }
}

def record_dependency_promotion(mem: any, uid: UUID) {
    state = _active.get();
    if state is not None
        and state.ctx.mem is mem
        and state.owner_thread == get_ident()
        and uid in state.submitted {
        state.promoted.add(uid);
    }
}

def prefetch_continuation(graph: any, scope: any, point: int) {
    state = _active.get();
    if state is None or state.owner_thread != get_ident() or scope.disengaged {
        return;
    }
    mem = state.ctx.mem;
    if mem.store is None or not scope.path {
        return;
    }
    import from jaclang.runtime.archetype { Archetype, NodeAnchor, NodeArchetype }
    import from jaclang.runtime.ttg { JacTTGGenerator }
    import from jaclang.runtime.ttg_continuation {
        continuation_type,
        known_node_fields
    }
    import from jaclang.runtime.graph_query { GraphQuery, QHop }
    import from jaclang.data.query_planner { resolve_ttg_path }
    import from jaclang.runtime.prefetch { dispatch_prefetch }
    anchor = scope.path[-1];
    if not isinstance(anchor, NodeAnchor) or anchor.id is None {
        return;
    }
    remaining = state.max_length - len(state.submitted);
    if remaining <= 0 {
        return;
    }
    scope_key = id(scope);
    if scope_key not in state.scope_snapshots {
        state.scope_snapshots[scope_key] = {
            'scope': scope,
            'path_count': 0,
            'types': set()
        };
    }
    scope_snapshot = state.scope_snapshots[scope_key];
    for index in range(scope_snapshot['path_count'], len(scope.path)) {
        scope_snapshot['types'].add(type(scope.path[index].archetype));
    }
    scope_snapshot['path_count'] = len(scope.path);
    values: dict = {};
    import from jaclang.runtime.ttg_dependencies { _trace_safe_storage }
    if type(scope.wlk).__getattribute__ is not Archetype.__getattribute__
        or not _trace_safe_storage(type(scope.wlk)) {
        return;
    }
    for (name, value) in vars(scope.wlk).items() {
        if type(value) in (bool, int, float, str, type(None)) {
            values['self.' + name] = value;
        } elif type(value) is list {
            values['self.' + name + '::list'] = True;
        }
    }
    ability = graph.events[point].ability;
    current_facts = known_node_fields(anchor.archetype);
    for (name, value) in current_facts.items() {
        values[ability + '::here.' + name] = value;
    }
    ignored = {item.id for item in scope.ignores};
    pending: list[dict] = [];
    pending_truncated = False;
    for index in range(scope.next_head, len(scope.next)) {
        item = scope.next[index];
        if item in scope.ignores {
            continue;
        }
        pending.append(
            {'id': item.id, 'node_type': type(item.archetype), 'anchor': item}
        );
        if len(pending) >= state.max_length {
            pending_truncated = index + 1 < len(scope.next);
            break;
        }
    }
    import from jaclang.runtime.ttg_regions { region_coverage_key }
    if state.fused_sql
        and graph.events[point].kind != 'entry'
        and mem.query_cache_get(
            region_coverage_key(
                graph,
                scope,
                scope.wlk,
                ability,
                anchor.id,
                state.ctx.user_root,
                state.cache_token
            )
        )
            is not None {
        return;
    }
    if state.fused_sql and graph.events[point].kind == 'entry' {
        import from jaclang.runtime.ttg_regions { resolve_interability_region }
        resolved = resolve_interability_region(
            mem,
            graph,
            scope.wlk,
            scope,
            point,
            {'id': anchor.id, 'node_type': type(anchor.archetype)},
            pending,
            state.ctx.user_root,
            state.max_length,
            state.fusion,
            state.cache_token
        );
        if resolved is not None {
            state.fusion['sql_construction'] = 'compiler_emitted_interability_regions';
            state.fusion['effective_region_mode'] = resolved.get(
                'kind', 'static_single_successor'
            );
            if resolved['reused'] {
                return;
            }
            plan: dict = {
                'origin': str(anchor.id),
                'ability': ability,
                'visit_event': point,
                'hops': [],
                'ids': [],
                'status': 'resolved',
                'decisions': [],
                'demanded': False,
                'decision_ms': 0.0,
                'queue_position': 0,
                'candidate_at': perf_counter(),
                'resolved_nodes': len(resolved['payload']),
                'site_key': model_site_key(state, graph, point),
                'ability_key': model_ability_key(state, graph, ability)
            };
            state.plans.append(plan);
            with mem._raw_lock {
                excluded = set(mem.__mem__) | set(mem.__raw_mem__) | state.submitted;
            }
            ids: list = [];
            for row in resolved['payload'] {
                uid = row[0];
                if uid not in excluded
                    and uid not in mem._deleted
                    and uid not in ignored {
                    ids.append(uid);
                    excluded.add(uid);
                }
            }
            ids = ids[:remaining];
            if ids {
                dispatch_fused_payload(state, {len(state.plans) - 1: ids});
            }
            return;
        }
    }
    local_paths: dict = {};
    fused_paths: dict = {};
    attempted_regions: set = set();
    frontier_demands: list = [];
    frontier_attempted: set = set();
    def resolve(active: dict, event: any) -> any {
        origin = state.ctx.user_root if event.origin == 'root' else None;
        origin_id = origin.id if origin is not None else active['id'];
        if event.origin == 'root' and origin is None {
            return None;
        }
        key = (origin_id, tuple(event.hop_chain));
        if key in local_paths {
            return local_paths[key];
        }
        reuse_key = ('ttg_continuation', state.cache_token, id(scope), key);
        reused = mem.query_cache_get(reuse_key);
        if reused is False {
            return None;
        }
        if reused is not None {
            return list(reused);
        }
        plan: dict = {
            'origin': str(origin_id),
            'ability': event.ability,
            'visit_event': event.id,
            'hops': event.hop_chain,
            'ids': [],
            'status': 'considering',
            'candidate_at': perf_counter(),
            'queue_position': len(pending),
            'site_key': model_site_key(state, graph, event.id),
            'ability_key': model_ability_key(state, graph, event.ability),
            'decisions': [],
            'demanded': False,
            'decision_ms': 0.0
        };
        state.plans.append(plan);
        index = len(state.plans) - 1;
        state.considered[(id(scope), origin_id, tuple(event.hop_chain))] = plan;
        admission = admit_prefetch(state, plan, 'resolve', remaining);
        if not admission.admit {
            plan['status'] = 'model_skipped';
            mem.query_cache_put(reuse_key, False);
            return None;
        }
        plan['probe'] = admission.probe;
        started = perf_counter();
        hops: list[QHop] = [];
        for hop in event.hop_chain {
            edge_type = continuation_type(scope.wlk, str(hop[0]))
                if hop[0] is not None
                else None;
            node_type = continuation_type(scope.wlk, str(hop[1]))
                if hop[1] is not None
                else None;
            if (hop[0] is not None and edge_type is None)
                or (hop[1] is not None and node_type is None) {
                plan['status'] = 'unresolved_path_type';
                return None;
            }
            hops.append(QHop(dir=int(hop[2]), `edge=edge_type, nd=node_type));
        }
        query = GraphQuery([], hops=hops).`visit();
        rows: any = None;
        if state.fused_sql {
            if graph.sql_templates {
                import from jaclang.runtime.ttg_templates { cached_emitted_path }
                cached = cached_emitted_path(
                    mem, query, origin_id, graph.sql_templates, event.id
                );
                if cached is not None {
                    rows = list(cached);
                    state.fusion['native_path_reuses'] = state.fusion.get(
                        'native_path_reuses', 0
                    )
                        + 1;
                }
            }
            frontier_key = (event.ability, str(active['id']), event.id);
            independent = graph.interability_regions.get('summaries', {}).get(
                event.ability, {}
            ).get(
                'frontier_independent_prefix', False
            );
            if rows is None
                and key not in fused_paths
                and graph.sql_templates
                and frontier_key not in frontier_attempted
                and (not frontier_attempted or independent) {
                state.fusion['sql_construction'] = 'compiler_emitted_templates';
                frontier_attempted.add(frontier_key);
                state.fusion['frontier_region_attempts'] = state.fusion.get(
                    'frontier_region_attempts', 0
                )
                    + 1;
                import from jaclang.runtime.ttg_frontier { resolve_frontier }
                frontier = resolve_frontier(
                    mem,
                    scope.wlk,
                    graph,
                    active,
                    event,
                    active.get('transition_pending', []),
                    state.ctx.user_root,
                    state.max_length,
                    state.fusion
                );
                if frontier is not None {
                    fused_paths.update(frontier[0]);
                    frontier_demands.extend(frontier[1]);
                }
            }
            if not graph.sql_templates
                and key not in fused_paths
                and key not in attempted_regions {
                state.fusion['sql_construction'] = 'legacy_runtime_builder';
                state.fusion['fallback_reason'] = 'Legacy checkpoint artifact has no emitted SQL templates';
                state.fusion['legacy_fusion_calls'] += 1;
                attempted_regions.add(key);
                import from jaclang.runtime.ttg_fusion { resolve_fused_region }
                fused = resolve_fused_region(
                    mem,
                    scope.wlk,
                    graph,
                    active,
                    event,
                    state.ctx.user_root,
                    state.max_length,
                    state.fusion
                );
                if fused is not None {
                    fused_paths.update(fused);
                }
            }
            if key in fused_paths {
                rows = fused_paths[key];
                state.fusion['cache_hits'] += 1;
            }
        }
        if rows is None {
            state.fusion['fallback_resolver_calls'] += 1;
            rows = resolve_ttg_path(mem, query, origin_id, max(200, state.max_length));
        }
        plan['resolve_ms'] = (perf_counter() - started) * 1000;
        if rows is None {
            plan['status'] = str(
                getattr(mem, '_ttg_path_decline_reason', 'resolution_budget')
            );
            return None;
        }
        targets: list[dict] = [];
        seen: set[UUID] = set();
        for row in rows {
            uid = UUID(str(row[0]));
            if uid in ignored or uid in seen or uid in mem._deleted {
                continue;
            }
            node_type = continuation_type(scope.wlk, str(row[2]), str(row[3] or ''));
            if node_type is None or not issubclass(node_type, NodeArchetype) {
                plan['status'] = 'unresolved_runtime_type';
                return None;
            }
            seen.add(uid);
            target: dict = {'id': uid, 'node_type': node_type, 'plan': index};
            cached_anchor = mem.__mem__.get(uid);
            if cached_anchor is not None and cached_anchor.is_populated() {
                target['anchor'] = cached_anchor;
            }
            targets.append(target);
        }
        plan['resolved_nodes'] = len(targets);
        plan['status'] = 'resolved';
        local_paths[key] = targets;
        mem.query_cache_put(reuse_key, tuple(targets));
        return targets;
    }
    try {
        outcome = JacTTGGenerator.get_continuation_plan(
            graph,
            {
                'id': anchor.id,
                'node_type': type(anchor.archetype),
                'facts': current_facts,
                'pending_truncated': pending_truncated,
                'ancestor_types': list(scope_snapshot['types'])
            },
            point,
            values,
            pending,
            resolve,
            state.max_length,
            max_steps=32768,
            resolve_state=state.fused_sql
        );
    } except Exception as error {
        state.errors.append(str(error));
        raise;
    }
    # Complete payload demands for the queued prefix, even if native prediction
    # stopped at disengage. Actual execution still follows the native queue.
    for (future_active, future_event) in frontier_demands {
        future_origin = state.ctx.user_root.id
            if future_event.origin == 'root' and state.ctx.user_root is not None
            else future_active['id'];
        if (future_origin, tuple(future_event.hop_chain)) in fused_paths {
            for target in resolve(future_active, future_event) or [] {
                if not any(n['id'] == target['id'] for n in outcome['nodes']) {
                    outcome['nodes'].append(target);
                }
            }
        }
    }
    state.continuations.append(
        {
            'point': point,
            'ability': ability,
            'complete': outcome['complete'],
            'stop': outcome['stop'],
            'steps': outcome['steps'],
            'executions': outcome['executions'],
            'paths': outcome['paths'],
            'branches': outcome['branches'],
            'pending_snapshot_count': len(pending),
            'pending_truncated': pending_truncated
        }
    );
    groups: dict[int, list] = {};
    with mem._raw_lock {
        excluded = set(mem.__mem__) | set(mem.__raw_mem__) | state.submitted;
    }
    for item in outcome['nodes'] {
        uid = item['id'];
        if 'plan' not in item or uid in excluded or uid in mem._deleted {
            continue;
        }
        if len(excluded & state.submitted) >= state.max_length {
            break;
        }
        groups.setdefault(item['plan'], []).append(uid);
        excluded.add(uid);
    }
    if state.fused_sql {
        dispatch_fused_payload(state, groups);
        return;
    }
    for (index, ids) in groups.items() {
        ids = ids[:state.max_length - len(state.submitted)];
        if not ids {
            break;
        }
        plan = state.plans[index];
        if plan['status'] == 'model_skipped_load' {
            continue;
        }
        admission = admit_prefetch(
            state, plan, 'load', len(ids), bool(plan.get('probe', False))
        );
        if not admission.admit {
            plan['status'] = 'model_skipped_load';
            continue;
        }
        plan['ids'] = [str(uid) for uid in ids];
        plan['dispatch_at'] = perf_counter();
        state.fusion['payload_dispatches'] += 1;
        dispatch_prefetch(
            state.ctx,
            ids,
            state.mode,
            state.workers,
            append=True,
            observer=payload_observer(state, plan)
        );
        plan['launch_finished_at'] = perf_counter();
        plan['launch_ms'] = (plan['launch_finished_at'] - plan['dispatch_at']) * 1000;
        state.submitted.update(ids);
        plan['status'] = 'submitted';
    }
}


def model_ability_key(state: any, graph: any, ability: str) -> str {
    return str(getattr(graph, '_model_prefix', graph.walker_name))
        + ':'
        + ability
        + ':'
        + str(state.mode or 'sync')
        + ':'
        + str(state.workers);
}

def model_site_key(state: any, graph: any, point: int) -> str {
    return model_ability_key(state, graph, graph.events[point].ability)
        + ':'
        + str(point);
}

def admit_prefetch(
    state: any, plan: dict, phase: str, remaining: int, probe: bool = False
) -> PrefetchAdmission {
    started = perf_counter();
    inputs: dict = {};
    try {
        context = PrefetchFeatures(
            site_key=plan['site_key'],
            ability_key=plan['ability_key'],
            phase=phase,
            queue_position=plan['queue_position'],
            remaining_budget=remaining,
            mode=state.mode,
            resolved_nodes=plan.get('resolved_nodes'),
            probe=probe
        );
        features = state.provider.estimate(context);
        inputs = features.to_dict();
        admission = state.model.decide(features);
        if not isinstance(admission, PrefetchAdmission)
            or type(admission.admit) is not bool {
            raise TypeError(
                'Decision model must return PrefetchAdmission with a boolean admit field'
            );
        }
        result = admission;
    } except Exception as error {
        state.errors.append('Decision model: ' + str(error));
        result = PrefetchAdmission(
            False, 'model or feature-provider error: ' + str(error)
        );
    }
    elapsed = (perf_counter() - started) * 1000;
    plan['decision_ms'] += elapsed;
    plan['decisions'].append(
        {
            'model': type(state.model).__name__,
            'inputs': inputs,
            'output': result.to_dict(),
            'elapsed_ms': elapsed
        }
    );
    return result;
}

def payload_observer(state: any, plan: dict) -> any {
    def completed(ids: list, elapsed_ms: float, error: str | None) {
        ready_ms = (perf_counter() - plan['dispatch_at']) * 1000;
        plan['payload_ms'] = max(float(plan.get('payload_ms', 0.0)), ready_ms);
        if error is not None {
            plan['payload_error'] = error;
        }
    }
    return completed;
}

def record_model_event(wlk: any, serialized: str, point: int, owner: type) {
    state = _active.get();
    if state is None or type(wlk) is not owner or state.owner_thread != get_ident() {
        return;
    }
    import from jaclang.runtime.osp_kernel { _current_scope }
    import from jaclang.runtime.archetype { NodeAnchor }
    import from jaclang.runtime.ttg_checkpoints { _capture, cached_checkpoint_plan }
    scope = _current_scope();
    capture = _capture.get();
    if scope is None
        or capture is None
        or scope.wlk is not wlk
        or not scope.path
        or not isinstance(scope.path[-1], NodeAnchor) {
        return;
    }
    (graph, candidates) = cached_checkpoint_plan(capture, wlk, serialized);
    event = graph.events[point];
    ability_key = model_ability_key(state, graph, event.ability);
    try {
        if event.kind == 'entry' {
            state.provider.record_entry(ability_key);
        } elif event.kind == 'visit' {
            site_key = model_site_key(state, graph, point);
            state.provider.record_visit(ability_key, site_key);
            origin = state.ctx.user_root if event.origin == 'root' else scope.path[-1];
            if origin is None or origin.id is None {
                return;
            }
            key = (id(scope), origin.id, tuple(event.hop_chain));
            plan = state.considered.get(key);
            if plan is not None and not plan['demanded'] {
                plan['demanded'] = True;
                plan['demand_at'] = perf_counter();
            }
        }
    } except Exception as error {
        state.errors.append('Model observation: ' + str(error));
    }
    if event.kind == 'entry' {
        prefetch_continuation(graph, scope, point);
    }
}

def finish_prefetch_feedback(state: any) {
    for plan in state.plans {
        demand_at = plan.get('demand_at');
        overlap: float | None = None;
        if demand_at is not None {
            if 'dispatch_at' in plan {
                anchor = plan.get('launch_finished_at', plan['dispatch_at']);
            } else {
                anchor = plan['candidate_at']
                    + (plan.get('resolve_ms', 0.0) + plan['decision_ms']) / 1000;
            }
            overlap = max(0.0, (demand_at - anchor) * 1000);
        }
        outcome = PrefetchOutcome(
            site_key=plan['site_key'],
            ability_key=plan['ability_key'],
            demanded=plan['demanded'],
            resolution_ms=plan.get('resolve_ms'),
            payload_ms=plan.get('payload_ms') if 'payload_error' not in plan else None,
            overlap_ms=overlap,
            resolved_nodes=plan.get('resolved_nodes')
        );
        feedback = outcome.to_dict();
        if state.fused_sql {
            feedback['training_observed'] = False;
            feedback['cost_scope'] = 'Shared fused batch diagnostic';
            state.feedback.append(feedback);
            continue;
        }
        state.feedback.append(feedback);
        for observer in [state.provider, state.model] {
            try {
                observer.observe(outcome);
            } except Exception as error {
                state.errors.append('Model feedback: ' + str(error));
            }
        }
    }
}


def dispatch_fused_payload(state: any, groups: dict) {
    import from jaclang.runtime.prefetch { dispatch_prefetch }
    combined: list = [];
    admitted: list = [];
    for (index, candidates) in groups.items() {
        ids = candidates[:state.max_length - len(state.submitted) - len(combined)];
        if not ids {
            break;
        }
        plan = state.plans[index];
        admission = admit_prefetch(
            state, plan, 'load', len(ids), bool(plan.get('probe', False))
        );
        if not admission.admit {
            plan['status'] = 'model_skipped_load';
            continue;
        }
        plan['ids'] = [str(uid) for uid in ids];
        plan['dispatch_at'] = perf_counter();
        admitted.append((plan, set(ids), payload_observer(state, plan)));
        combined.extend(ids);
    }
    if not combined {
        return;
    }
    def completed(ids: list, elapsed_ms: float, error: str | None) {
        loaded = set(ids);
        for (plan, members, observer) in admitted {
            selected = list(loaded & members);
            if selected {
                observer(selected, elapsed_ms, error);
            }
        }
    }
    state.fusion['payload_dispatches'] += 1;
    dispatch_prefetch(
        state.ctx, combined, state.mode, state.workers, append=True, observer=completed
    );
    finished = perf_counter();
    for (plan, members, observer) in admitted {
        plan['launch_finished_at'] = finished;
        plan['launch_ms'] = (finished - plan['dispatch_at']) * 1000;
        plan['status'] = 'submitted';
        plan['fused_payload_batch_size'] = len(combined);
    }
    state.submitted.update(combined);
}
