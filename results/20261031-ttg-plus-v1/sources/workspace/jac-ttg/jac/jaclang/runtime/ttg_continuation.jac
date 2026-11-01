import from jaclang.runtime.ttg_dependencies {
    _trace_snapshot,
    _trace_safe_storage,
    _trace_eval,
    _trace_entry_handlers,
    _trace_node_effects,
    _trace_field_effects,
    TraceEffects
}
import ast as pyast;
import from dataclasses { fields }
import from jaclang.runtime.archetype { NodeArchetype }
import sys;

def _plain_scalar_field(node_type: type, name: str, types: tuple) -> bool {
    if not _trace_safe_storage(node_type) {
        return False;
    }
    if any(
        name in vars(base)
            and any(
                '__get__' in vars(owner) for owner in type(vars(base)[name]).__mro__
            ) for base in node_type.__mro__
    ) {
        return False;
    }
    return any(
        field.name == name and field.type in types for field in fields(node_type)
    );
}

def _integer_expression(
    expression: str, values: dict, unknowns: set[str], node_type: type, ability: str
) -> bool {
    import from jaclang.runtime.ttg_dependencies { _trace_attribute, _trace_key }
    def check(expr_node: any) -> bool {
        if isinstance(expr_node, pyast.Constant) {
            return type(expr_node.value) is int;
        }
        if isinstance(expr_node, (pyast.Name, pyast.Attribute)) {
            name = _trace_attribute(expr_node);
            key = _trace_key(name, ability);
            if values.get(key + '::unsafe', False) {
                return False;
            }
            if key in values {
                return type(values[key]) is int;
            }
            return key in unknowns
                or (
                    name.startswith('here.')
                    and _plain_scalar_field(node_type, name[5:], (int, 'int'))
                );
        }
        if isinstance(expr_node, pyast.BinOp)
            and isinstance(expr_node.op, (pyast.Add, pyast.Sub, pyast.Mult)) {
            return check(expr_node.left) and check(expr_node.right);
        }
        if isinstance(expr_node, pyast.UnaryOp)
            and isinstance(expr_node.op, (pyast.UAdd, pyast.USub)) {
            return check(expr_node.operand);
        }
        return False;
    }
    return check(pyast.parse(expression, mode='eval').body);
}

def known_node_fields(arch: any) -> dict {
    if type(arch).__getattribute__ is not NodeArchetype.__getattribute__ {
        return {};
    }
    if not _trace_safe_storage(type(arch)) {
        return {};
    }
    result: dict = {};
    for (name, value) in vars(arch).items() {
        descriptor = any(
            name in vars(base)
                and any(
                    '__get__' in vars(owner) for owner in type(vars(base)[name]).__mro__
                ) for base in type(arch).__mro__
        );
        if not descriptor and type(value) in (bool, int, float, str, type(None)) {
            result[name] = value;
        } else {
            result[name + '::unsafe'] = True;
        }
    }
    return result;
}

def continuation_type(wlk: any, name: str, module_name: str = '') -> any {
    import from jaclang.runtime.runtime { JacRuntime }
    scope_name = module_name or type(wlk).__module__;
    module = JacRuntime.loaded_modules.get(scope_name) or sys.modules.get(scope_name);
    if module is None {
        return None;
    }
    direct = vars(module).get(name);
    if isinstance(direct, type) {
        return direct;
    }
    matches = {
        value
        for value in vars(module).values()
        if isinstance(value, type)
            and value.__name__ == name
            and (not module_name or value.__module__ == module_name)
    };
    return next(iter(matches)) if len(matches) == 1 else None;
}

def _append_argument_known(event: any, values: dict, node_type: type) -> bool {
    if any(values.get(key + '::unsafe', False) for key in event.reads) {
        return False;
    }
    try {
        _trace_eval(event.expression, values, event.ability);
        return True;
    } except KeyError {
        if node_type.__getattribute__ is not NodeArchetype.__getattribute__ {
            return False;
        }
        tree: any = pyast.parse(event.expression, mode='eval').body;
        if not isinstance(tree, pyast.Attribute)
            or not isinstance(tree.value, pyast.Name)
            or tree.value.id != 'here' {
            return False;
        }
        declared = {field.name for field in fields(node_type)};
        if tree.attr not in declared {
            return False;
        }
        return not any(
            tree.attr in vars(base)
                and any(
                    '__get__' in vars(owner)
                    for owner in type(vars(base)[tree.attr]).__mro__
                ) for base in node_type.__mro__
        );
    }
}

def _finish_entry_prefix(result: dict, graph: any, node_types: list) -> dict {
    if getattr(graph.runtime_walker, '_jac_exit_funcs_', [])
        or any(
            getattr(node_type, '_jac_exit_funcs_', []) for node_type in node_types
        ) {
        result['stop'] = 'Exit callbacks require a later continuation';
    } else {
        result['complete'] = True;
    }
    return result;
}

def plan_continuation(
    graph: any,
    current: dict,
    point: int,
    snapshot: dict,
    pending: list[dict],
    resolve: any,
    max_nodes: int = 200,
    max_steps: int = 32768,
    transition_trace: list | None = None,
    resume_event: int | None = None,
    resolve_state: bool = False,
    initial_unknown_ints: set[str] | None = None
) -> dict {
    result: dict = {
        'nodes': [],
        'paths': [],
        'branches': [],
        'stop': '',
        'complete': False,
        'steps': 0,
        'executions': []
    };
    values = _trace_snapshot(snapshot);
    effects = TraceEffects();
    field_keys = set(values);
    for event in graph.events {
        field_keys.update(event.reads);
        if event.writes {
            field_keys.add(event.writes);
        }
    }
    _trace_field_effects(graph, field_keys, effects);
    if effects.unknown {
        result['stop'] = 'Walker field access has unknown effects';
        return result;
    }
    queue = list(pending);

    unknown_ints: set[str] = set(initial_unknown_ints or ());
    demanded: set[str] = set();
    exit_types = list(current.get('ancestor_types', [current['node_type']]));
    head = 0;
    active = current;
    if not issubclass(active['node_type'], NodeArchetype)
        or not _trace_safe_storage(active['node_type'])
        or active['node_type'].__getattribute__ is not NodeArchetype.__getattribute__ {
        result['stop'] = 'Custom node attribute access is unresolved';
        return result;
    }
    event = graph.events[point];
    handlers = _trace_entry_handlers(graph, active['node_type'], effects);
    if effects.unknown or event.ability not in handlers {
        result['stop'] = 'Current entry dispatch is unresolved';
        return result;
    }
    handler_index = handlers.index(event.ability);
    transition_guard_head = 0;
    cursor = event.next_id if resume_event is None else resume_event;
    while result['steps'] < max_steps {
        result['steps'] += 1;
        if cursor == -1 {
            handler_index += 1;
            if handler_index < len(handlers) {
                ability = handlers[handler_index];
                unknown_ints = {
                    key
                    for key in unknown_ints
                    if key.startswith('self.')
                };
                values = {
                    k: v
                    for (k, v) in values.items()
                    if k.startswith('self.')
                };
                for (name, value) in active.get('facts', {}).items() {
                    values[ability + '::here.' + name] = value;
                }
                cursor = graph.entries[ability];
                continue;
            }
            effects = TraceEffects();
            _trace_node_effects(graph, active['node_type'], effects);
            if effects.unknown {
                result['stop'] = 'Node entry handler has unknown effects';
                return result;
            }
            if head >= len(queue) {
                if current.get('pending_truncated', False) {
                    result['stop'] = 'Pending queue budget exhausted';
                    return result;
                }
                return _finish_entry_prefix(result, graph, exit_types);
            }
            if len(result['executions']) >= max_nodes {
                result['stop'] = 'Node execution budget exhausted';
                return result;
            }
            active = queue[head];
            if not issubclass(active['node_type'], NodeArchetype)
                or not _trace_safe_storage(active['node_type'])
                or active['node_type'].__getattribute__
                    is not NodeArchetype.__getattribute__ {
                result['stop'] = 'Custom node attribute access is unresolved';
                return result;
            }
            if 'anchor' in active {
                active['facts'] = known_node_fields(active['anchor'].archetype);
            }
            exit_types.append(active['node_type']);
            head += 1;
            result['executions'].append(str(active['id']));
            effects = TraceEffects();
            handlers = _trace_entry_handlers(graph, active['node_type'], effects);
            if effects.unknown {
                result['stop'] = 'Future entry dispatch is unresolved';
                return result;
            }
            unknown_ints = {
                key
                for key in unknown_ints
                if key.startswith('self.')
            };
            values = {
                k: v
                for (k, v) in values.items()
                if k.startswith('self.')
            };
            handler_index = -1;
            continue;
        }
        event = graph.events[cursor];
        try {
            if event.kind in ('barrier', 'cancel') {
                result['stop'] = event.kind
                    + ' at '
                    + event.ability
                    + ':'
                    + str(event.line);
                return result;
            }
            if event.kind in ('assign', 'scalar_update') {
                if event.kind == 'scalar_update'
                    and type(values.get(event.writes)) not in (int, float)
                    and event.writes not in unknown_ints {
                    result['stop'] = 'Augmented receiver is not a known numeric scalar';
                    return result;
                }
                try {
                    value = _trace_eval(event.expression, values, event.ability);
                    values[event.writes] = value;
                    unknown_ints.discard(event.writes);
                } except KeyError {
                    if not _integer_expression(
                        event.expression,
                        values,
                        unknown_ints,
                        active['node_type'],
                        event.ability
                    ) {
                        raise ValueError('Assignment may have unresolved effects');
                    }
                    values.pop(event.writes, None);
                    unknown_ints.add(event.writes);
                }
                values.pop(event.writes + '::list', None);
            } elif event.kind == 'output' {
                for key in event.reads {
                    if values.get(key + '::unsafe', False) {
                        result['stop'] = 'Output value has observed unsafe effects';
                        return result;
                    }
                    if key in unknown_ints {
                        continue;
                    }
                    if key in values
                        and type(values[key]) in (bool, int, float, str, type(None)) {
                        continue;
                    }
                    prefix = event.ability + '::here.';
                    if key.startswith(prefix)
                        and _plain_scalar_field(
                            active['node_type'],
                            key[len(prefix):],
                            (bool, int, float, str, 'bool', 'int', 'float', 'str')
                        ) {
                        continue;
                    }
                    result['stop'] = 'Output value has unresolved effects';
                    return result;
                }
            } elif event.kind == 'append' {
                if not values.get(event.writes + '::list', False)
                    or not _append_argument_known(event, values, active['node_type']) {
                    result['stop'] = 'List append receiver or argument is unresolved';
                    return result;
                }
                values.pop(event.writes, None);
            } elif event.kind == 'branch' {
                choice = bool(_trace_eval(event.expression, values, event.ability));
                result['branches'].append({'event': event.id, 'taken': choice});
                cursor = event.true_id if choice else event.false_id;
                continue;
            } elif event.kind == 'visit' {
                if not event.hop_chain or event.origin not in ('here', 'root') {
                    result['stop'] = 'Visit origin or path is unresolved';
                    return result;
                }
                if transition_trace is not None {
                    transition_trace.append(
                        {
                            'event': event.id,
                            'ability': event.ability,
                            'resume_event': event.next_id,
                            'ability_activation': len(result['executions']),
                            'pending_count': len(queue) - head,
                            'scalar_state': dict(values),
                            'unknown_integers': sorted(unknown_ints),
                            'guards': list(result['branches'][transition_guard_head:])
                        }
                    );
                    transition_guard_head = len(result['branches']);
                }
                resolution_active = active;
                if resolve_state {
                    resolution_active = dict(active);
                    resolution_active['transition_state'] = dict(values);
                    resolution_active['transition_unknown_integers'] = set(
                        unknown_ints
                    );
                    resolution_active['transition_pending'] = queue[head:];
                }
                targets = resolve(resolution_active, event);
                if targets is None {
                    result['stop'] = 'Path resolution declined';
                    return result;
                }
                result['paths'].append(
                    {
                        'event': event.id,
                        'origin': str(active['id']),
                        'origin_kind': event.origin,
                        'targets': [str(item['id']) for item in targets]
                    }
                );
                for item in targets {
                    identity = str(item['id']);
                    if identity in demanded {
                        continue;
                    }
                    if len(demanded) >= max_nodes {
                        result['stop'] = 'Payload budget exhausted';
                        return result;
                    }
                    demanded.add(identity);
                    result['nodes'].append(item);
                }
                queue.extend(targets);
            }
        } except (KeyError, ValueError, TypeError, ArithmeticError) as error {
            result['stop'] = 'Unknown scalar fact: ' + str(error);
            return result;
        }
        cursor = event.next_id;
    }
    result['stop'] = 'Abstract execution step budget exhausted';
    return result;
}
