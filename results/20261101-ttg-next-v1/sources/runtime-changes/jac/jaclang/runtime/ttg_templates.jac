"""Compiler-emitted SQL descriptors. Runtime selection and binding build no SQL AST."""
import jaclang.sql as q;
import from uuid { UUID }
import from time { perf_counter_ns, thread_time_ns }

glob _metrics: dict = {},
     _profile: dict = {'enabled': False};


def template_metrics(reset: bool = False, enabled: bool | None = None) -> dict {
    if enabled is not None {
        _profile['enabled'] = enabled;
    }
    result = dict(_metrics);
    if reset {
        _metrics.clear();
    }
    return result;
}


def _record(name: str, wall: int, cpu: int) -> None {
    if not _profile['enabled'] {
        return;
    }
    _metrics[name + '_calls'] = _metrics.get(name + '_calls', 0) + 1;
    _metrics[name + '_wall_ns'] = _metrics.get(name + '_wall_ns', 0) + perf_counter_ns()
        - wall;
    _metrics[name + '_thread_cpu_ns'] = _metrics.get(name + '_thread_cpu_ns', 0)
        + thread_time_ns()
        - cpu;
}


def sql_descriptor(compiled: q.CompiledSQL) -> dict {
    return {
        'sql': compiled.sql,
        'params': dict(compiled.params),
        'slots': [
            [name, dtype.name, dtype.nullable] for (name, dtype) in compiled.slots
        ],
        'nonnegative_slots': list(compiled.nonnegative_slots)
    };
}


def hydrate_descriptor(descriptor: dict) -> any {
    compiled = q.CompiledSQL(
        sql=descriptor['sql'],
        params=dict(descriptor['params']),
        slots=tuple(
            (name, q.DataType(dtype, nullable))
            for (name, dtype, nullable) in descriptor['slots']
        ),
        nonnegative_slots=tuple(descriptor.get('nonnegative_slots', []))
    );
    descriptor['_compiled'] = compiled;
    return compiled;
}


def hydrate_templates(value: any) -> any {
    if type(value) is dict {
        result = {key: hydrate_templates(item) for (key, item) in value.items()};
        if 'sql' in result and 'slots' in result {
            hydrate_descriptor(result);
        }
        return result;
    }
    if type(value) is list {
        return [hydrate_templates(item) for item in value];
    }
    return value;
}


def bind_template(descriptor: dict, values: dict) -> any {
    wall = perf_counter_ns() if _profile['enabled'] else 0;
    cpu = thread_time_ns() if _profile['enabled'] else 0;
    try {
        compiled = descriptor.get('_compiled');
        if compiled is None {
            compiled = hydrate_descriptor(descriptor);
        }
        return compiled.bind(values);
    } finally {
        _record('bind', wall, cpu);
    }
}


def select_template(bundle: dict, kind: str, gated: bool, event: int = -1) -> any {
    wall = perf_counter_ns() if _profile['enabled'] else 0;
    cpu = thread_time_ns() if _profile['enabled'] else 0;
    try {
        mode = 'gated' if gated else 'open';
        if kind == 'batch' {
            return bundle.get('batch', {}).get(mode);
        }
        return bundle.get(kind, {}).get(str(event), {}).get(mode);
    } finally {
        _record('select', wall, cpu);
    }
}


def compile_templates(events: list) -> dict {
    # Called by compile_checkpoint_plan, before serialized checkpoint emission.
    import json;
    import from jaclang.runtime.ttg_fusion_sql { compile_fused_region }
    import from jaclang.runtime.ttg_sql { compile_acl_type_catalog }
    import from jaclang.runtime.graph_query { GraphQuery, QHop }
    import from jaclang.data.sqlcompile { compile_query }
    wall = perf_counter_ns() if _profile['enabled'] else 0;
    cpu = thread_time_ns() if _profile['enabled'] else 0;
    try {
        sites = [
            {'event': e.id, 'hops': e.hop_chain, 'origin': e.origin}
            for e in events
            if e.kind == 'visit'
                and e.hop_chain
                and e.origin in ('here', 'root')
                and all(h[2] in (1, 2, 3) for h in e.hop_chain)
        ];
        bundle: dict = {
            'version': 1,
            'sites': sites,
            'batch': {},
            'linear': {},
            'native': {}
        };
        if not sites {
            return bundle;
        }
        bundle['catalog'] = sql_descriptor(compile_acl_type_catalog());
        for gated in (False, True) {
            mode = 'gated' if gated else 'open';
            actor = {
                'uuid': q.slot('actor_uuid', q.uuid_type()),
                'text': q.slot('actor_text', q.text_type())
            }
                if gated
                else None;
            batch = compile_fused_region(
                {'kind': 'batch', 'rules': sites}, [], actor, 1, template=True
            );
            bundle['batch'][mode] = sql_descriptor(batch);
            for site in sites {
                event = str(site['event']);
                if len(site['hops']) == 1 and site['origin'] == 'here' {
                    linear = compile_fused_region(
                        {'kind': 'linear', 'rules': [site]}, [], actor, 1, template=True
                    );
                    bundle['linear'].setdefault(event, {})[mode] = sql_descriptor(
                        linear
                    );
                }
                hops = [
                    QHop(
                        dir=h[2],
                        `edge=type(h[0], (object, ), {}) if h[0] is not None else None,
                        nd=type(h[1], (object, ), {}) if h[1] is not None else None
                    ) for h in site['hops']
                ];
                native: dict = {};
                for typed in (False, True) {
                    cq = compile_query(
                        GraphQuery([], hops=hops).`visit(),
                        len(hops),
                        acl_root=str(UUID(int=1)) if gated else None,
                        include_type=typed
                    );
                    params = dict(cq.params);
                    params.pop('origin');
                    slots: list = [['origin', 'text[]', False]];
                    for name in list(params) {
                        if name.endswith('amu') or name.endswith('amt') {
                            params.pop(name);
                            slots.append([name, 'text', False]);
                        }
                    }
                    native['typed' if typed else 'pairs'] = {
                        'sql': cq.sql,
                        'params': params,
                        'slots': slots,
                        'nonnegative_slots': []
                    };
                }
                bundle['native'].setdefault(event, {})[mode] = native;
            }
        }
        encoded = json.dumps(bundle, separators=(',', ':'));
        _metrics['emitted_artifact_bytes'] = _metrics.get('emitted_artifact_bytes', 0)
            + len(encoded.encode());
        _metrics['emitted_sql_bytes'] = _metrics.get('emitted_sql_bytes', 0)
            + sum(len(d['sql'].encode()) for d in bundle['batch'].values())
            + sum(
                len(d['sql'].encode()) for modes in bundle['linear'].values()
                for d in modes.values()
            )
            + sum(
                len(d['sql'].encode()) for modes in bundle['native'].values()
                for pair in modes.values() for d in pair.values()
            )
            + len(bundle['catalog']['sql'].encode());
        return bundle;
    } finally {
        _record('generation', wall, cpu);
    }
}


def native_shape(query: any, upto: int) -> any {
    if not query.from_visit
        or upto != len(query.hops)
        or query.edges_only
        or query.slc is not None
        or query.order
        or query.limit is not None
        or query.offset
        or query.level != 'default' {
        return None;
    }
    shape: list = [];
    for hop in query.hops {
        if hop.preds
            or hop.epreds
            or hop.only is not None
            or isinstance(hop.nd, tuple) {
            return None;
        }
        shape.append((hop.`edge, hop.nd, hop.dir));
    }
    return tuple(shape);
}


def cache_key(query: any, origin_ids: list, actor: any) -> any {
    shape = native_shape(query, len(query.hops));
    if shape is None {
        return None;
    }
    return ('ttg_compiled_pairs_v1', tuple(origin_ids), shape, actor);
}


def publish_paths(mem: any, staged: list) -> bool {
    # Atomic publication into the same transaction epoch as native consumers.
    import from jaclang.data.query_planner { _acl_pushdown_root, _query_cache_key }
    import from jaclang.runtime.graph_walk { access_gated }
    puts: list = [];
    for (query, origin_id, rows, descriptors) in staged {
        actor = _acl_pushdown_root(query, len(query.hops), mem);
        if access_gated() and actor is None {
            return False;
        }
        key = cache_key(query, [origin_id], actor);
        if key is None {
            return False;
        }
        pairs = tuple(
            (UUID(str(row[0])), UUID(str(row[1])) if row[1] is not None else None)
            for row in rows
        );
        for name in ('typed', 'pairs') {
            desc = descriptors[name];
            values: dict = {'origin': (str(origin_id), )};
            for (slot, dtype, nullable) in desc['slots'] {
                if slot != 'origin' {
                    values[slot] = actor;
                }
            }
            compiled = bind_template(desc, values);
            # Native legacy keys use lists; the cache freezer canonicalizes both.
            legacy = _query_cache_key(
                'ttg_path' if name == 'typed' else 'pairs',
                compiled.sql,
                compiled.params,
                len(query.hops)
            );
            puts.append(
                (
                    legacy,
                    tuple(tuple(row) for row in rows)
                        if name == 'typed'
                        else (pairs, ())
                )
            );
        }
        puts.append((key, (pairs, ())));
    }
    for (key, value) in puts {
        mem.query_cache_put(key, value);
    }
    return True;
}
