import from jaclang.runtime.ttg_continuation { plan_continuation }
import from jaclang.runtime.ttg_dependencies { TraceEffects, _trace_entry_handlers }


def certify_fused_region(
    graph: any,
    current: dict,
    point: int,
    snapshot: dict,
    pending: list[dict],
    max_nodes: int,
    max_steps: int = 32768,
    resume_event: int | None = None
) -> dict {
    ability = graph.events[point].ability;
    prefix: list[dict] = [];
    def collect(active: dict, event: any) -> any {
        if active['id'] != current['id'] or event.ability != ability {
            return None;
        }
        prefix.append(
            {
                'event': event.id,
                'ability': event.ability,
                'origin': event.origin,
                'hops': event.hop_chain,
                'line': event.line,
                'column': event.column
            }
        );

        return [];
    }
    batch_trace: list = [];
    batch = plan_continuation(
        graph,
        current,
        point,
        snapshot,
        [],
        collect,
        max_nodes,
        max_steps,
        transition_trace=batch_trace,
        resume_event=resume_event,
        initial_unknown_ints=current.get('transition_unknown_integers')
    );
    result: dict = {
        'version': 1,
        'program_key': str(getattr(graph, '_model_prefix', graph.walker_name)),
        'scalar_state': dict(snapshot),
        'transition_trace': batch_trace,
        'checkpoint': point,
        'checkpoint_ability': ability,
        'resume_event': graph.events[point].next_id
            if resume_event is None
            else resume_event,
        'source_type': current['node_type'].__name__,
        'source_module': current['node_type'].__module__,
        'origin_id': str(current['id']),
        'pending_count': len(pending),
        'max_nodes': max_nodes,
        'max_steps': max_steps,
        'kind': 'batch',
        'rules': prefix,
        'branches': batch['branches'],
        'stop': batch['stop'],
        'max_origins': 1,
        'cardinality_guard': 'Stop expansion unless actual successor count is one'
    };
    if not prefix or len(prefix) != 1 or pending {
        return result;
    }
    rule = prefix[0];
    if rule['origin'] != 'here' or len(rule['hops']) != 1 {
        return result;
    }
    effects = TraceEffects();
    handlers = _trace_entry_handlers(graph, current['node_type'], effects);
    if effects.unknown or handlers != [ability] {
        return result;
    }
    transitions: list[dict] = [];
    def successor(active: dict, event: any) -> any {
        if event.id != rule['event']
            or event.ability != ability
            or event.origin != 'here'
            or event.hop_chain != rule['hops'] {
            return None;
        }
        transitions.append(
            {'ordinal': len(transitions), 'event': event.id, 'ability': ability}
        );
        return [
            {
                'id': 'fused-symbol-' + str(len(transitions)),
                'node_type': current['node_type']
            }
        ];
    }
    linear_trace: list = [];
    linear = plan_continuation(
        graph,
        current,
        point,
        snapshot,
        [],
        successor,
        max_nodes,
        max_steps,
        transition_trace=linear_trace,
        resume_event=resume_event,
        initial_unknown_ints=current.get('transition_unknown_integers')
    );
    if len(transitions) > 1 {
        result['kind'] = 'linear';
        result['max_origins'] = len(transitions);
        result['transitions'] = transitions;
        result['transition_trace'] = linear_trace;
        result['branches'] = linear['branches'];
        result['stop'] = linear['stop'];
        result['execution_budget_used'] = len(linear['executions']);
        result['homogeneous_guard'] = 'Exact source runtime type and module';
    }
    return result;
}


def resolve_fused_region(
    mem: any,
    wlk: any,
    graph: any,
    active: dict,
    event: any,
    user_root: any,
    max_nodes: int,
    metrics: dict
) -> any {
    import from uuid { UUID }
    import from jaclang.runtime.ttg_continuation { continuation_type }
    import from jaclang.runtime.graph_query { GraphQuery, QHop }
    import from jaclang.runtime.graph_walk { access_gated }
    import from jaclang.data.query_planner { _acl_pushdown_root, cache_ttg_paths }
    import from jaclang.runtime.ttg_fusion_sql { compile_fused_region }
    values = active.get('transition_state');
    if values is None {
        return None;
    }
    contract = certify_fused_region(
        graph,
        active,
        event.id,
        values,
        active.get('transition_pending', []),
        max_nodes,
        32768,
        resume_event=event.id
    );
    if not contract['rules'] {
        return None;
    }
    queries: list = [];
    origins: list = [];
    actor: str | None = None;
    for rule in contract['rules'] {
        origin_id = active['id'];
        if rule['origin'] == 'root' {
            if user_root is None {
                return None;
            }
            origin_id = user_root.id;
        } elif rule['origin'] != 'here' {
            return None;
        }
        hops: list[QHop] = [];
        for hop in rule['hops'] {
            edge_type = continuation_type(wlk, str(hop[0]))
                if hop[0] is not None
                else None;
            node_type = continuation_type(wlk, str(hop[1]))
                if hop[1] is not None
                else None;
            if (hop[0] is not None and edge_type is None)
                or (hop[1] is not None and node_type is None) {
                return None;
            }
            import from jaclang.runtime.ttg_frontier { template_type_matches }
            if not template_type_matches(edge_type, hop[0])
                or not template_type_matches(node_type, hop[1]) {
                metrics['fallback_reason'] = 'Legacy fused type token is an alias or custom metaclass';
                return None;
            }
            hops.append(QHop(dir=int(hop[2]), `edge=edge_type, nd=node_type));
        }
        query = GraphQuery([], hops=hops).`visit();
        visibility = _acl_pushdown_root(query, len(hops), mem);
        if access_gated() and visibility is None {
            metrics['fallback_reason'] = 'ACL pushdown is unproved for dynamic or custom access';
            return None;
        }
        if queries and actor != visibility {
            return None;
        }
        actor = visibility;
        queries.append(query);
        origins.append(origin_id);
    }
    compiled = compile_fused_region(contract, origins, actor, max_nodes);
    with mem._lock {
        mem.read_barrier();
        rows = mem.store.rows(compiled.sql, compiled.params);
        metrics['queries'] += 1;
        if len(rows) > max_nodes {
            metrics['overflow'] += 1;
            return None;
        }
        groups: dict = {};
        arities: dict = {};
        for row in rows {
            slot = int(row[0]);
            depth = int(row[1]);
            if slot < 0 or slot >= len(queries) or depth < 0 {
                raise ValueError('Invalid fused path slot or depth');
            }
            origin_id = UUID(str(row[2]));
            group_key = (slot, depth, origin_id);
            group = groups.setdefault(group_key, []);
            if row[3] is not None {
                arity = int(row[8]);
                if arity <= 0
                    or int(row[7]) != len(group) + 1
                    or arities.get(group_key, arity) != arity {
                    raise ValueError('Invalid fused path cardinality or order');
                }
                arities[group_key] = arity;
                group.append((UUID(str(row[3])), UUID(str(row[4])), row[5], row[6]));
            } elif any(value is not None for value in row[4:]) {
                raise ValueError('Invalid empty fused path marker');
            }
        }
        paths: dict = {};
        staged: list = [];
        for ((slot, depth, origin_id), resolved) in groups.items() {
            if len(resolved) != arities.get((slot, depth, origin_id), 0) {
                raise ValueError('Incomplete fused path result');
            }
            query = queries[slot];
            key = (origin_id, tuple(contract['rules'][slot]['hops']));
            if key in paths and paths[key] != resolved {
                raise ValueError('Inconsistent repeated fused path result');
            }
            paths[key] = resolved;
            staged.append((query, origin_id, resolved));
        }
        if not cache_ttg_paths(mem, staged) {
            return None;
        }
        metrics['cache_paths'] += len(paths);
        metrics['cache_empty_paths'] += sum(
            1
            for value in paths.values()
            if not value
        );
        metrics['regions'].append(contract);
        return paths;
    }
}
