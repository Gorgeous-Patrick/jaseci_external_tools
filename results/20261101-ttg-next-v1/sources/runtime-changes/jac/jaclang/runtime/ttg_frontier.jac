"""Prediction-only queued-prefix batching; native FIFO execution remains untouched."""
import from uuid { UUID }
import from jaclang.runtime.ttg_continuation { plan_continuation, continuation_type }


def collect_frontier(
    graph: any, current: dict, event: any, pending: list, max_nodes: int
) -> tuple[dict, list] {
    demands: list = [];
    def collect(active: dict, future_event: any) -> any {
        demands.append((dict(active), future_event));
        return [];
    }
    result = plan_continuation(
        graph,
        current,
        event.id,
        current['transition_state'],
        pending,
        collect,
        max_nodes,
        32768,
        resume_event=event.id,
        initial_unknown_ints=current.get('transition_unknown_integers'),
        queued_trigger_assumption=True
    );
    return (result, demands);
}


def template_type_matches(resolved: any, token: any) -> bool {
    if resolved is None {
        return token is None;
    }
    name_reader: any = type.__getattribute__;
    return type(resolved) is type and name_reader(resolved, '__name__') == token;
}


def resolve_frontier(
    mem: any,
    wlk: any,
    graph: any,
    current: dict,
    event: any,
    pending: list,
    user_root: any,
    max_nodes: int,
    metrics: dict
) -> any {
    import from jaclang.runtime.ttg_fusion { certify_fused_region }
    import from jaclang.runtime.ttg_templates {
        select_template,
        bind_template,
        publish_paths
    }
    import from jaclang.runtime.graph_query { GraphQuery, QHop }
    import from jaclang.runtime.graph_walk { access_gated }
    import from jaclang.data.query_planner { _acl_pushdown_root }
    bundle = graph.sql_templates;
    if bundle.get('version') != 1 or not bundle.get('sites') {
        metrics['fallback_reason'] = 'No emitted SQL template for this walker';
        return None;
    }
    if 'transition_state' not in current {
        return None;
    }
    (prediction, demands) = collect_frontier(graph, current, event, pending, max_nodes);
    if not demands {
        return None;
    }
    kind = 'batch';
    contract: dict = {};
    if not pending {
        contract = certify_fused_region(
            graph,
            current,
            event.id,
            current['transition_state'],
            [],
            max_nodes,
            32768,
            resume_event=event.id
        );
        if contract['kind'] == 'linear' {
            kind = 'linear';
        }
    }
    sites = bundle['sites']
        if kind == 'batch'
        else [
            next(
                s
                for s in bundle['sites']
                if s['event'] == event.id
            )
        ];
    by_event = {s['event']: i for (i, s) in enumerate(sites)};
    arrays: list = [[] for s in sites];
    queries: list = [];
    witnesses: list = [];
    actor: any = None;
    with mem._lock {
        mem.read_barrier();
        if 'catalog' in bundle {
            mem.query_cache_put(('ttg_compiled_catalog_v1', ), bundle['catalog']);
        }
        for site in sites {
            hops: list = [];
            for (edge, node, direction) in site['hops'] {
                et = continuation_type(wlk, str(edge)) if edge is not None else None;
                nt = continuation_type(wlk, str(node)) if node is not None else None;
                if (edge is not None and et is None)
                    or (node is not None and nt is None) {
                    metrics['fallback_reason'] = 'Unresolved emitted path type';
                    return None;
                }
                if not template_type_matches(et, edge)
                    or not template_type_matches(nt, node) {
                    metrics['fallback_reason'] = 'Emitted type token is an alias or custom metaclass';
                    return None;
                }
                hops.append(QHop(dir=int(direction), `edge=et, nd=nt));
            }
            queries.append(GraphQuery([], hops=hops).`visit());
        }
        selected: list = [];
        for (active, future_event) in demands {
            if future_event.id not in by_event {
                metrics['fallback_reason'] = 'Visit absent from emitted site inventory';
                return None;
            }
            slot = by_event[future_event.id];
            origin = user_root.id
                if future_event.origin == 'root' and user_root is not None
                else active['id'];
            if future_event.origin == 'root' and user_root is None {
                return None;
            }
            uid = UUID(str(origin));
            visibility = _acl_pushdown_root(
                queries[slot], len(queries[slot].hops), mem
            );
            if access_gated() and visibility is None {
                metrics['fallback_reason'] = 'ACL pushdown is unproved for dynamic or custom access';
                return None;
            }
            if selected and visibility != actor {
                return None;
            }
            actor = visibility;
            # Duplicate sites/activations remain in the witness; identical fetches can share cache.
            arrays[slot].append(uid);
            selected.append((active, future_event));
            witnesses.append(
                {
                    'event': future_event.id,
                    'origin': str(uid),
                    'activation': str(active['id']),
                    'slot': slot
                }
            );
        }
        descriptor = select_template(bundle, kind, actor is not None, event.id);
        if descriptor is None {
            return None;
        }
        values: dict = {'row_limit': max_nodes + 1};
        if kind == 'linear' {
            values.update(
                {
                    'origin': arrays[0][0],
                    'source_type': contract['source_type'],
                    'source_module': contract['source_module'],
                    'max_depth': contract['max_origins'] - 1
                }
            );
        } else {
            for (slot, origins) in enumerate(arrays) {
                values['origins_' + str(slot)] = tuple(origins);
            }
        }
        if actor is not None {
            values.update({'actor_uuid': UUID(actor), 'actor_text': actor});
        }
        compiled = bind_template(descriptor, values);
        rows = mem.store.rows(compiled.sql, compiled.params);
        metrics['queries'] += 1;
        if len(rows) > max_nodes {
            metrics['overflow'] += 1;
            metrics['fallback_reason'] = 'Compiled frontier row budget exceeded';
            return None;
        }
        groups: dict = {};
        arities: dict = {};
        for row in rows {
            slot = int(row[0]);
            depth = int(row[1]);
            uid = UUID(str(row[2]));
            if slot < 0 or slot >= len(sites) or depth < 0 {
                raise ValueError('Invalid compiled frontier slot/depth');
            }
            if kind == 'batch'
                and (depth >= len(arrays[slot]) or arrays[slot][depth] != uid) {
                raise ValueError('Compiled frontier origin does not match bound slot');
            }
            key = (slot, depth, uid);
            group = groups.setdefault(key, []);
            if row[3] is None {
                if any(v is not None for v in row[4:]) or group {
                    raise ValueError('Invalid compiled empty path marker');
                }
            } else {
                arity = int(row[8]);
                if arity <= 0
                    or int(row[7]) != len(group) + 1
                    or arities.get(key, arity) != arity {
                    raise ValueError('Invalid compiled path order/cardinality');
                }
                arities[key] = arity;
                group.append((UUID(str(row[3])), UUID(str(row[4])), row[5], row[6]));
            }
        }
        if kind == 'batch' and len(groups) != sum(len(a) for a in arrays) {
            raise ValueError('Missing compiled origin/empty marker');
        }
        paths: dict = {};
        staged: list = [];
        for ((slot, depth, uid), resolved) in groups.items() {
            if len(resolved) != arities.get((slot, depth, uid), 0) {
                raise ValueError('Incomplete compiled frontier path');
            }
            key = (uid, tuple(tuple(h) for h in sites[slot]['hops']));
            if key in paths and paths[key] != resolved {
                raise ValueError('Inconsistent duplicate compiled paths');
            }
            paths[key] = resolved;
            native = select_template(
                bundle, 'native', actor is not None, sites[slot]['event']
            );
            staged.append((queries[slot], uid, resolved, native));
        }
        if not publish_paths(mem, staged) {
            return None;
        }
        metrics['cache_paths'] += len(paths);
        metrics['cache_empty_paths'] += sum(
            1
            for p in paths.values()
            if not p
        );
        metrics['template_queries'] = metrics.get('template_queries', 0) + 1;
        metrics['frontier_origins'] = metrics.get('frontier_origins', 0) + len(demands);
        metrics['regions'].append(
            {
                'kind': kind,
                'compiled': True,
                'demands': witnesses,
                'stop': prediction['stop'],
                'queued_trigger_assumption': True
            }
        );
        return (paths, selected);
    }
}
