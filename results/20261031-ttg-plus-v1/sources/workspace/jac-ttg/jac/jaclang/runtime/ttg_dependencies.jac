import ast as pyast;
import operator;
import jaclang.compiler.frontend.unitree as uni;
import from jaclang.runtime.ttg { JacTTGGenerator }

glob pa: any = pyast,
     ops: any = operator;

obj TraceEvent {
    has id: int,
        kind: str,
        ability: str,
        line: int,
        column: int = 0,
        expression: str = '',
        writes: str = '',
        reads: tuple[str, ...] = (),
        targets: tuple[str, ...] = (),
        hop_chain: tuple = (),
        origin: str = 'here',
        next_id: int = -1,
        true_id: int = -1,
        false_id: int = -1,
        definitions: dict[str, int] = {};
}

obj TraceDependency {
    has source: int,
        target: int,
        kind: str,
        label: str = '',
        context: int = -1;
}

obj TracePrediction {
    has complete: bool = False,
        visits: list[dict] = [],
        branches: list[dict] = [],
        unresolved: list[str] = [];
}

obj TraceEffects {
    has writes: set[str] = set(),
        unknown: bool = False,
        may_cancel: bool = False;
}

obj PendingTraceNode {
    has node_type: type,
        identity: str = '';
}

obj QueueTraceDecision {
    has dependencies: tuple[str, ...] = (),
        intervening_writes: tuple[str, ...] = (),
        stable: bool = False,
        path_determined: bool = False,
        execution_preserved: bool = False,
        prediction: TracePrediction | None = None,
        reasons: list[str] = [];
}

obj WalkerDependencyGraph {
    has walker_name: str,
        runtime_walker: type | None = None,
        events: list[TraceEvent] = [],
        edges: list[TraceDependency] = [],
        entries: dict[str, int] = {},
        handlers: dict[str, list[str]] = {},
        dispatch: dict[int, list[str]] = {};

    def dependencies(event_id: int) -> list[TraceDependency] {
        return [
            e
            for e in self.edges
            if e.target == event_id
        ];
    }

    def predict_handler(
        ability: str, snapshot: dict[str, any], max_steps: int = 1000
    ) -> TracePrediction {
        result = TracePrediction();
        values = _trace_snapshot(snapshot);
        current = self.entries[ability];
        for step in range(max_steps) {
            if current == -1 {
                result.complete = True;
                return result;
            }
            event = self.events[current];
            try {
                if event.kind in ('barrier', 'cancel', 'append') {
                    result.unresolved.append(
                        'Unknown effect or cancellation at ' + str(event.line)
                    );
                    return result;
                }
                if event.kind in ('assign', 'scalar_update') {
                    if event.kind == 'scalar_update'
                        and type(values.get(event.writes)) not in (int, float) {
                        raise ValueError(
                            'Augmented receiver is not a known numeric scalar'
                        );
                    }
                    values[event.writes] = _trace_eval(
                        event.expression, values, ability
                    );
                } elif event.kind == 'output' {
                    output = _trace_eval(event.expression, values, event.ability);
                    if type(output) not in (bool, int, float, str, type(None)) {
                        raise ValueError('Output value has unresolved effects');
                    }
                } elif event.kind == 'branch' {
                    choice = bool(_trace_eval(event.expression, values, ability));
                    result.branches.append({'event': event.id, 'taken': choice});
                    current = event.true_id if choice else event.false_id;
                    continue;
                } elif event.kind == 'visit' {
                    result.visits.append(
                        {
                            'event': event.id,
                            'from_ability': ability,
                            'target_types': event.targets
                        }
                    );
                }
            } except (KeyError, ValueError, TypeError, ArithmeticError) as error {
                result.unresolved.append(str(error));
                return result;
            }
            current = event.next_id;
        }
        result.unresolved.append('Prediction step budget exhausted');
        return result;
    }

    def decide_pending(
        pending: list[PendingTraceNode],
        target_index: int,
        ability: str,
        snapshot: dict[str, any],
        point: int | None = None,
        current_type: type | None = None
    ) -> QueueTraceDecision {
        if target_index < 0 or target_index >= len(pending) {
            raise ValueError('Invalid target queue position');
        }
        decision = QueueTraceDecision();
        values = _trace_snapshot(snapshot);
        required = _trace_requirements(self, ability);
        decision.dependencies = tuple(sorted(required));
        effects = TraceEffects();
        if point is not None {
            if point < 0
                or point >= len(self.events)
                or self.events[point].kind not in ('assign', 'scalar_update', 'visit')
                or current_type is None {
                raise ValueError(
                    'Current handler checkpoint requires a completed assignment or visit and current node type'
                );
            }
            event = self.events[point];
            _trace_merge_effects(effects, _trace_effects(self, event.next_id));
            handlers = _trace_entry_handlers(self, current_type, effects);
            if event.ability not in handlers {
                effects.unknown = True;
            } else {
                for name in handlers[handlers.index(event.ability) + 1:] {
                    _trace_merge_effects(
                        effects, _trace_effects(self, self.entries[name])
                    );
                }
            }
            _trace_node_effects(self, current_type, effects);
        }
        for item in pending[:target_index] {
            for name in _trace_entry_handlers(self, item.node_type, effects) {
                _trace_merge_effects(effects, _trace_effects(self, self.entries[name]));
            }
            _trace_node_effects(self, item.node_type, effects);
        }
        target_handlers = _trace_entry_handlers(
            self, pending[target_index].node_type, effects
        );
        if ability not in target_handlers {
            effects.unknown = True;
            decision.reasons.append(
                'Target handler is not resolved for the queued node'
            );
        } else {
            for name in target_handlers[:target_handlers.index(ability)] {
                _trace_merge_effects(effects, _trace_effects(self, self.entries[name]));
            }
        }
        _trace_field_effects(
            self,
            required
                | effects.writes
                | _trace_effects(self, self.entries[ability]).writes,
            effects
        );
        decision.intervening_writes = tuple(sorted(effects.writes));
        decision.stable = not effects.unknown and not bool(required & effects.writes);
        decision.execution_preserved = not effects.unknown and not effects.may_cancel;
        if effects.unknown {
            decision.reasons.append(
                'An intervening effect or queue operation is unresolved'
            );
        }
        if required & effects.writes {
            decision.reasons.append(
                'Intervening handlers may write: '
                    + ', '.join(sorted(required & effects.writes))
            );
        }
        if effects.may_cancel {
            decision.reasons.append(
                'Target execution may be cancelled; path prediction is conditional on execution'
            );
        }
        if decision.stable {
            decision.prediction = self.predict_handler(ability, values);
            decision.path_determined = decision.prediction.complete;
            decision.reasons.extend(decision.prediction.unresolved);
        }
        return decision;
    }

    def predict_after(
        point: int,
        snapshot: dict[str, any],
        isolated: bool = False,
        max_steps: int = 1000
    ) -> TracePrediction {
        result = TracePrediction();
        if not isolated {
            result.unresolved.append(
                'Prediction requires an isolated, single-target visit transition'
            );
            return result;
        }
        if point < 0
            or point >= len(self.events)
            or self.events[point].kind not in ('assign', 'scalar_update', 'visit') {
            raise ValueError('Checkpoint must identify a completed assignment event');
        }

        values: dict[str, any] = {};
        for (key, value) in snapshot.items() {
            if type(value) not in (bool, int, float, str, type(None)) {
                raise ValueError('Snapshot values must be primitive scalars');
            }
            values[key] = value;
        }
        current = self.events[point].next_id;
        for step in range(max_steps) {
            if current == -1 {
                result.complete = True;
                return result;
            }
            event = self.events[current];
            if event.kind in ('barrier', 'cancel', 'append') {
                result.unresolved.append(
                    'Unsupported effect at ' + event.ability + ':' + str(event.line)
                );
                return result;
            }
            try {
                if event.kind in ('assign', 'scalar_update') {
                    if event.kind == 'scalar_update'
                        and type(values.get(event.writes)) not in (int, float) {
                        raise ValueError(
                            'Augmented receiver is not a known numeric scalar'
                        );
                    }
                    values[event.writes] = _trace_eval(
                        event.expression, values, event.ability
                    );
                } elif event.kind == 'output' {
                    output = _trace_eval(event.expression, values, event.ability);
                    if type(output) not in (bool, int, float, str, type(None)) {
                        raise ValueError('Output value has unresolved effects');
                    }
                } elif event.kind == 'branch' {
                    choice = bool(_trace_eval(event.expression, values, event.ability));
                    result.branches.append({'event': event.id, 'taken': choice});
                    current = event.true_id if choice else event.false_id;
                    continue;
                } elif event.kind == 'visit' {
                    if len(event.targets) != 1 {
                        result.unresolved.append(
                            'Visit target type is not uniquely resolved'
                        );
                        return result;
                    }
                    tail = event.next_id;
                    seen: set[int] = set();
                    while tail != -1
                        and tail not in seen
                        and self.events[tail].kind in ('join', 'exit') {
                        seen.add(tail);
                        tail = self.events[tail].next_id;
                    }
                    if tail != -1 {
                        result.unresolved.append(
                            'Source continuation can change state before visit dispatch'
                        );
                        return result;
                    }
                    result.visits.append(
                        {
                            'event': event.id,
                            'from_ability': event.ability,
                            'target_type': event.targets[0]
                        }
                    );
                    handlers = self.dispatch.get(event.id, []);
                    if len(handlers) > 1 {
                        result.unresolved.append(
                            'Multiple event handlers require scheduler ordering analysis'
                        );
                        return result;
                    }
                    if handlers {
                        current = self.entries[handlers[0]];
                        continue;
                    }
                    current = -1;
                    continue;
                }
            } except (KeyError, ValueError, TypeError, ArithmeticError) as error {
                result.unresolved.append(str(error));
                return result;
            }
            current = event.next_id;
        }
        result.unresolved.append('Prediction step budget exhausted');
        return result;
    }
}

def _trace_text(ast_node: any) -> str {
    if isinstance(ast_node, uni.Token) {
        return ast_node.value;
    }
    return ' '.join(_trace_text(child) for child in ast_node.kid);
}

def _trace_key(name: str, ability: str) -> str {
    if name.startswith('self.') {
        return name;
    }
    if name.startswith('here.') {
        return ability + '::' + name;
    }
    return ability + '::' + name;
}

def _trace_attribute(ast_node: any) -> str {
    if isinstance(ast_node, pa.Name) {
        return ast_node.id;
    }
    if isinstance(ast_node, pa.Attribute) {
        return _trace_attribute(ast_node.value) + '.' + ast_node.attr;
    }
    raise ValueError('Unsupported attribute receiver');
}

def _trace_expr(ast_node: any, ability: str) -> tuple[str, tuple[str, ...]] {
    text = _trace_text(ast_node);
    tree = pa.parse(text, mode='eval').body;
    reads: set[str] = set();
    _trace_check(tree, ability, reads);
    return (text, tuple(sorted(reads)));
}

def _trace_check(ast_node: any, ability: str, reads: set[str]) {
    if isinstance(ast_node, pa.Constant) {
        if type(ast_node.value) not in (bool, int, float, str, type(None)) {
            raise ValueError('Unsupported constant');
        }
    } elif isinstance(ast_node, (pa.Name, pa.Attribute)) {
        name = _trace_attribute(ast_node);
        if '.' in name
            and (name.count('.') != 1 or not name.startswith(('self.', 'here.'))) {
            raise ValueError('Unknown field alias');
        }
        reads.add(_trace_key(name, ability));
    } elif isinstance(ast_node, pa.BinOp)
        and type(ast_node.op).__name__
            in ('Add', 'Sub', 'Mult', 'Div', 'FloorDiv', 'Mod') {
        _trace_check(ast_node.left, ability, reads);
        _trace_check(ast_node.right, ability, reads);
    } elif isinstance(ast_node, pa.UnaryOp)
        and type(ast_node.op).__name__ in ('Not', 'USub', 'UAdd') {
        _trace_check(ast_node.operand, ability, reads);
    } elif isinstance(ast_node, pa.BoolOp) {
        for value in ast_node.values {
            _trace_check(value, ability, reads);
        }
    } elif isinstance(ast_node, pa.Compare)
        and all(
            type(op).__name__ in ('Eq', 'NotEq', 'Lt', 'LtE', 'Gt', 'GtE')
            for op in ast_node.ops
        ) {
        _trace_check(ast_node.left, ability, reads);
        for value in ast_node.comparators {
            _trace_check(value, ability, reads);
        }
    } else {
        raise ValueError('Expression has unknown effects');
    }
}

def _trace_eval(text: str, values: dict[str, any], ability: str) -> any {
    return _trace_value(pa.parse(text, mode='eval').body, values, ability);
}

def _trace_value(ast_node: any, values: dict[str, any], ability: str) -> any {
    if isinstance(ast_node, pa.Constant) {
        return ast_node.value;
    }
    if isinstance(ast_node, (pa.Name, pa.Attribute)) {
        key = _trace_key(_trace_attribute(ast_node), ability);
        if values.get(key + '::unsafe', False) {
            raise ValueError('Observed unsafe scalar field: ' + key);
        }
        return values[key];
    }
    if isinstance(ast_node, pa.BinOp) {
        functions = {
            'Add': ops.add,
            'Sub': ops.sub,
            'Mult': ops.mul,
            'Div': ops.truediv,
            'FloorDiv': ops.floordiv,
            'Mod': ops.mod
        };
        return functions[type(ast_node.op).__name__](
            _trace_value(ast_node.left, values, ability),
            _trace_value(ast_node.right, values, ability)
        );
    }
    if isinstance(ast_node, pa.UnaryOp) {
        value = _trace_value(ast_node.operand, values, ability);
        if isinstance(ast_node.op, pa.Not) {
            return not value;
        }
        return -value if isinstance(ast_node.op, pa.USub) else +value;
    }
    if isinstance(ast_node, pa.BoolOp) {
        for item in ast_node.values {
            value = _trace_value(item, values, ability);
            if isinstance(ast_node.op, pa.And) and not value {
                return value;
            }
            if isinstance(ast_node.op, pa.Or) and value {
                return value;
            }
        }
        return value;
    }
    if isinstance(ast_node, pa.Compare) {
        functions = {
            'Eq': ops.eq,
            'NotEq': ops.ne,
            'Lt': ops.lt,
            'LtE': ops.le,
            'Gt': ops.gt,
            'GtE': ops.ge
        };
        left = _trace_value(ast_node.left, values, ability);
        for (op, right_node) in zip(ast_node.ops, ast_node.comparators) {
            right = _trace_value(right_node, values, ability);
            if not functions[type(op).__name__](left, right) {
                return False;
            }
            left = right;
        }
        return True;
    }
    raise ValueError('Unsupported prediction expression');
}

obj DependencyBuilder {
    has graph: WalkerDependencyGraph;

    def event(
        kind: str,
        ability: str,
        ast_node: any,
        expression: str = '',
        reads: tuple[str, ...] = (),
        writes: str = ''
    ) -> TraceEvent {
        event = TraceEvent(
            id=len(self.graph.events),
            kind=kind,
            ability=ability,
            line=ast_node.loc.first_line,
            column=getattr(ast_node.loc, 'col_start', 0),
            expression=expression,
            reads=reads,
            writes=writes
        );
        self.graph.events.append(event);
        return event;
    }

    def block(
        body: any, ability: str, env: dict[str, int], controls: list[tuple[int, str]]
    ) -> tuple[int, int, dict[str, int]] {
        first = -1;
        last = -1;
        for statement in body {
            event = self.statement(statement, ability, env, controls);
            if first == -1 {
                first = event[0];
            }
            if last != -1 {
                self.graph.events[last].next_id = event[0];
            }
            last = event[1];
            env = event[2];
        }
        return (first, last, env);
    }

    def inputs(
        event: TraceEvent, env: dict[str, int], controls: list[tuple[int, str]]
    ) {
        for key in event.reads {
            if key not in env {
                source = self.event(
                    'input', event.ability, event_node_stub(event.line)
                );
                source.writes = key;
                env[key] = source.id;
            }
            self.graph.edges.append(TraceDependency(env[key], event.id, 'data', key));
        }
        for (source, label) in controls {
            self.graph.edges.append(
                TraceDependency(source, event.id, 'control', label)
            );
        }
    }

    def statement(
        ast_node: any,
        ability: str,
        env: dict[str, int],
        controls: list[tuple[int, str]]
    ) -> tuple[int, int, dict[str, int]] {
        try {
            call = pa.parse(
                _trace_text(ast_node).strip().rstrip(';'), mode='eval'
            ).body;
            if isinstance(call, pa.Call)
                and isinstance(call.func, pa.Attribute)
                and call.func.attr == 'append'
                and len(call.args) == 1
                and not call.keywords {
                receiver = _trace_attribute(call.func.value);
                if receiver.startswith('self.') and receiver.count('.') == 1 {
                    append_reads: set[str] = set();
                    _trace_check(call.args[0], ability, append_reads);
                    event = self.event(
                        'append',
                        ability,
                        ast_node,
                        pa.unparse(call.args[0]),
                        tuple(sorted(append_reads)),
                        receiver
                    );
                    self.inputs(event, env, controls);
                    return (event.id, event.id, env);
                }
            }
        } except (ValueError, SyntaxError) { }
        if isinstance(ast_node, uni.Assignment)
            and len(ast_node.target) == 1
            and ast_node.value is not None {
            try {
                (text, reads) = _trace_expr(ast_node.value, ability);
                name = _trace_attribute(
                    pa.parse(_trace_text(ast_node.target[0]), mode='eval').body
                );
                if '.' in name
                    and not (name.startswith('self.') and name.count('.') == 1) {
                    raise ValueError(
                        'Node and aliased writes require memory-effect analysis'
                    );
                }
                kind = 'assign';
                if ast_node.aug_op is not None {
                    op = ast_node.aug_op.value;
                    if op not in ('+=', '-=', '*=', '/=', '//=', '%=') {
                        raise ValueError('Unsupported augmented assignment');
                    }
                    kind = 'scalar_update';
                    text = name + ' ' + op[:-1] + ' (' + text + ')';
                    update_reads: set[str] = set(reads);
                    update_reads.add(_trace_key(name, ability));
                    reads = tuple(sorted(update_reads));
                }
                event = self.event(
                    kind, ability, ast_node, text, reads, _trace_key(name, ability)
                );
                self.inputs(event, env, controls);
                env[event.writes] = event.id;
                return (event.id, event.id, env);
            } except (ValueError, SyntaxError) { }
        }
        if isinstance(ast_node, uni.ReportStmt) {
            try {
                (text, reads) = _trace_expr(ast_node.expr, ability);

                leaf = pa.parse(text, mode='eval').body;
                if not isinstance(leaf, (pa.Constant, pa.Name, pa.Attribute)) {
                    raise ValueError('Output expression requires evaluation');
                }
                event = self.event('output', ability, ast_node, text, reads);
                self.inputs(event, env, controls);
                return (event.id, event.id, env);
            } except (ValueError, SyntaxError) { }
        }
        if isinstance(ast_node, uni.IfStmt) {
            try {
                (text, reads) = _trace_expr(ast_node.condition, ability);
            } except (ValueError, SyntaxError) {
                event = self.event('barrier', ability, ast_node);
                return (event.id, event.id, env);
            }
            event = self.event('branch', ability, ast_node, text, reads);
            self.inputs(event, env, controls);
            (yes_start, yes_end, yes_env) = self.block(
                ast_node.body, ability, dict(env), controls + [(event.id, 'true')]
            );
            other = ast_node.else_body;
            if isinstance(other, uni.ElseIf) {
                (no_start, no_end, no_env) = self.statement(
                    other, ability, dict(env), controls + [(event.id, 'false')]
                );
            } else {
                (no_start, no_end, no_env) = self.block(
                    other.body if other is not None else [],
                    ability,
                    dict(env),
                    controls + [(event.id, 'false')]
                );
            }
            join = self.event('join', ability, ast_node);
            event.true_id = yes_start if yes_start != -1 else join.id;
            event.false_id = no_start if no_start != -1 else join.id;
            for end in [yes_end, no_end] {
                if end != -1 {
                    self.graph.events[end].next_id = join.id;
                }
            }
            for key in set(yes_env) | set(no_env) {
                left = yes_env.get(key, -1);
                right = no_env.get(key, -1);
                if left == right {
                    env[key] = left;
                } else {
                    phi = self.event('phi', ability, ast_node, writes=key);
                    for (source, label) in [(left, 'true'), (right, 'false')] {
                        if source != -1 {
                            self.graph.edges.append(
                                TraceDependency(source, phi.id, 'data', label)
                            );
                        }
                    }
                    self.graph.edges.append(
                        TraceDependency(event.id, phi.id, 'control', 'merge')
                    );
                    env[key] = phi.id;
                }
            }
            return (event.id, join.id, env);
        }
        if isinstance(ast_node, uni.DisengageStmt) {
            event = self.event('cancel', ability, ast_node);
            self.inputs(event, env, controls);
            return (event.id, event.id, env);
        }
        if isinstance(ast_node, uni.VisitStmt) and ast_node.else_body is None {
            trailers = ast_node.target.get_all_sub_nodes(uni.EdgeRefTrailer);
            if isinstance(ast_node.target, uni.EdgeRefTrailer) {
                trailers = [ast_node.target];
            }
            targets: list[str] = [];
            safe = isinstance(ast_node.target, uni.EdgeRefTrailer)
                and len(trailers) == 1
                and ast_node.insert_loc is None;
            for trailer in trailers {
                chain = JacTTGGenerator._extract_chains_from_trailer(ast_node, trailer);

                hop = -1;
                for item in trailer.chain {
                    if isinstance(item, uni.EdgeOpRef) {
                        hop += 1;
                        if item.filter_cond is not None {
                            filter_type = item.filter_cond.f_type;
                            if filter_type is not None {
                                if isinstance(filter_type, uni.Name)
                                    and hop < len(chain) {
                                    chain[hop] = (
                                        chain[hop][0] or filter_type.value,
                                        chain[hop][1],
                                        chain[hop][2]
                                    );
                                } else {
                                    safe = False;
                                }
                            }
                        }
                    }
                    if isinstance(item, uni.FilterCompr) and item.f_type is not None {
                        if isinstance(item.f_type, uni.Name)
                            and 0 <= hop < len(chain) {
                            chain[hop] = (
                                chain[hop][0],
                                chain[hop][1] or item.f_type.value,
                                chain[hop][2]
                            );
                        } else {
                            safe = False;
                        }
                    }
                }
                safe = safe and bool(chain) and hop + 1 == len(chain);
                for item in trailer.get_all_sub_nodes(uni.FilterCompr) {
                    if item.compares {
                        safe = False;
                    }
                }
                if chain and chain[-1][1] is not None {
                    targets.append(str(chain[-1][1]));
                }
            }
            event = self.event('visit' if safe else 'barrier', ability, ast_node);
            event.targets = tuple(targets);
            if safe {
                event.hop_chain = tuple(chain);
                event.origin = JacTTGGenerator._edge_ref_explicit_origin_name(
                    trailers[0]
                )
                    or 'here';
            }
            event.definitions = dict(env);
            self.inputs(event, env, controls);
            return (event.id, event.id, env);
        }
        event = self.event('barrier', ability, ast_node);
        self.inputs(event, env, controls);
        return (event.id, event.id, env);
    }
}

obj TraceLocation {
    has first_line: int;
}

obj TraceSource {
    has loc: TraceLocation;
}

def event_node_stub(line: int) -> TraceSource {
    return TraceSource(TraceLocation(line));
}

def analyze_walker_dependencies(walker_type: type) -> WalkerDependencyGraph {
    arch = JacTTGGenerator._find_walker_ast_node(walker_type);
    if arch is None {
        raise ValueError('Walker source AST is unavailable');
    }
    graph = analyze_walker_ast(arch);
    graph.runtime_walker = walker_type;
    return graph;
}

def analyze_walker_ast(arch: uni.Archetype) -> WalkerDependencyGraph {
    graph = WalkerDependencyGraph(walker_name=arch.name.value);
    builder = DependencyBuilder(graph);
    for ability in arch.get_all_sub_nodes(uni.Ability) {
        if not isinstance(ability.signature, uni.EventSignature) {
            continue;
        }
        name = ability.py_resolve_name();
        start_event = builder.event('entry', name, ability);
        graph.entries[name] = start_event.id;
        types = ability.event_trigger_type_names();
        if not types and isinstance(ability.signature.arch_tag_info, uni.Name) {
            types = [ability.signature.arch_tag_info.value];
        }

        if ability.signature.event.value != 'entry' or not types {
            barrier = builder.event('barrier', name, ability);
            start_event.next_id = barrier.id;
            if not types {
                graph.handlers.setdefault('*', []).append(name);
            }
        } else {
            body = ability.body;
            if isinstance(body, uni.ImplDef) {
                body = body.body;
            }
            if not isinstance(body, list) {
                barrier = builder.event('barrier', name, ability);
                start_event.next_id = barrier.id;
            } else {
                (first, last, env) = builder.block(body, name, {}, []);
                exit_event = builder.event('exit', name, ability);
                start_event.next_id = first if first != -1 else exit_event.id;
                if last != -1 {
                    graph.events[last].next_id = exit_event.id;
                }
            }
        }
        for target in types or [] {
            graph.handlers.setdefault(target, []).append(name);
        }
    }
    for event in list(graph.events) {
        if event.kind != 'visit' {
            continue;
        }
        handlers: list[str] = list(graph.handlers.get('*', []));
        for target in event.targets {
            handlers.extend(graph.handlers.get(target, []));
        }
        graph.dispatch[event.id] = handlers;
        for name in handlers {
            graph.edges.append(
                TraceDependency(
                    event.id,
                    graph.entries[name],
                    'dispatch',
                    ','.join(event.targets),
                    event.id
                )
            );
            for read in graph.events {
                if read.ability != name {
                    continue;
                }
                for key in read.reads {
                    if key.startswith('self.')
                        and key in event.definitions
                        and any(
                            e.target == read.id
                                and e.label == key
                                and e.kind == 'data'
                                and graph.events[e.source].kind == 'input'
                            for e in list(graph.edges)
                        ) {
                        graph.edges.append(
                            TraceDependency(
                                event.definitions[key], read.id, 'state', key, event.id
                            )
                        );
                    }
                }
            }
        }
    }
    for event in graph.events {
        for target in [event.next_id, event.true_id, event.false_id] {
            if target != -1 {
                graph.edges.append(TraceDependency(event.id, target, 'order'));
            }
        }
    }
    return graph;
}


def _trace_safe_storage(arch_type: type) -> bool {
    import from types { GetSetDescriptorType, MemberDescriptorType }
    for base in arch_type.__mro__ {
        descriptor = vars(base).get('__dict__');
        if descriptor is None {
            continue;
        }
        if type(descriptor) not in (GetSetDescriptorType, MemberDescriptorType) {
            return False;
        }
        if descriptor.__name__ != '__dict__' {
            return False;
        }
    }
    return True;
}

def _trace_snapshot(snapshot: dict[str, any]) -> dict[str, any] {
    values: dict[str, any] = {};
    for (key, value) in snapshot.items() {
        if type(value) not in (bool, int, float, str, type(None)) {
            raise ValueError('Snapshot values must be primitive scalars');
        }
        values[key] = value;
    }
    return values;
}

def _trace_requirements(graph: WalkerDependencyGraph, ability: str) -> set[str] {
    if ability not in graph.entries {
        raise ValueError('Unknown target ability');
    }
    work = [
        e.id
        for e in graph.events
        if e.ability == ability and e.kind in ('branch', 'visit')
    ];
    seen: set[int] = set();
    required: set[str] = set();
    while work {
        current = work.pop();
        if current in seen {
            continue;
        }
        seen.add(current);
        event = graph.events[current];
        if event.kind == 'input' {
            required.add(event.writes);
        }
        for edge in graph.dependencies(current) {
            if edge.kind in ('data', 'control')
                and graph.events[edge.source].ability == ability {
                work.append(edge.source);
            }
        }
    }
    return required;
}

def _trace_effects(graph: WalkerDependencyGraph, start: int) -> TraceEffects {
    result = TraceEffects();
    work = [start];
    seen: set[int] = set();
    while work {
        current = work.pop();
        if current == -1 or current in seen {
            continue;
        }
        seen.add(current);
        event = graph.events[current];
        if event.writes.startswith('self.')
            and event.kind in ('assign', 'scalar_update') {
            result.writes.add(event.writes);
        }

        if event.kind in ('barrier', 'append', 'output') {
            result.unknown = True;
        }
        if event.kind == 'cancel' {
            result.may_cancel = True;
        }
        work.extend([event.next_id, event.true_id, event.false_id]);
    }
    return result;
}

def _trace_merge_effects(target: TraceEffects, source: TraceEffects) {
    target.writes |= source.writes;
    target.unknown = target.unknown or source.unknown;
    target.may_cancel = target.may_cancel or source.may_cancel;
}

def _trace_entry_handlers(
    graph: WalkerDependencyGraph, node_type: type, effects: TraceEffects
) -> list[str] {
    if graph.runtime_walker is None {
        effects.unknown = True;
        return [];
    }
    result: list[str] = [];

    for callback in getattr(graph.runtime_walker, '_jac_entry_funcs_', []) {
        trigger = callback.trigger;
        if trigger is None {
            continue;
        }
        try {
            matches = issubclass(node_type, trigger);
        } except TypeError {
            effects.unknown = True;
            continue;
        }
        if matches {
            if callback.name not in graph.entries
                or callback.func
                    is not getattr(graph.runtime_walker, callback.name, None) {
                effects.unknown = True;
            } else {
                result.append(callback.name);
            }
        }
    }
    return result;
}

def _trace_node_effects(
    graph: WalkerDependencyGraph, node_type: type, effects: TraceEffects
) {
    for callback in getattr(node_type, '_jac_entry_funcs_', []) {
        trigger = callback.trigger;
        try {
            if trigger is None
                or (
                    graph.runtime_walker is not None
                    and issubclass(graph.runtime_walker, trigger)
                ) {
                effects.unknown = True;
            }
        } except TypeError {
            effects.unknown = True;
        }
    }
}

def pending_trace_queue -> list[PendingTraceNode] {
    import from jaclang.runtime.osp_kernel { _current_scope }
    import from jaclang.runtime.archetype { NodeAnchor }
    scope = _current_scope();
    if scope is None {
        raise ValueError('No active walker scope');
    }
    result: list[PendingTraceNode] = [];
    for anchor in scope.next[scope.next_head:] {
        if anchor in scope.ignores {
            continue;
        }
        if not isinstance(anchor, NodeAnchor) {
            raise ValueError('Queue contains an unsupported non-node anchor');
        }
        result.append(
            PendingTraceNode(node_type=type(anchor.archetype), identity=str(anchor.id))
        );
    }
    return result;
}

def decide_live_pending(
    graph: WalkerDependencyGraph, point: int, target_index: int, ability: str
) -> QueueTraceDecision {
    import from jaclang.runtime.osp_kernel { _current_scope }
    import from jaclang.runtime.archetype { NodeAnchor, Archetype }
    scope = _current_scope();
    if scope is None or not scope.path or not isinstance(scope.path[-1], NodeAnchor) {
        raise ValueError('Checkpoint requires an active node handler');
    }
    if type(scope.wlk) is not graph.runtime_walker {
        raise ValueError('Dependency graph does not match the running walker');
    }
    if type(scope.wlk).__getattribute__ is not Archetype.__getattribute__
        or not _trace_safe_storage(type(scope.wlk)) {
        return QueueTraceDecision(
            reasons=['Walker dictionary storage has unknown effects']
        );
    }
    values: dict[str, any] = {};
    for (name, value) in vars(scope.wlk).items() {
        if type(value) in (bool, int, float, str, type(None)) {
            values['self.' + name] = value;
        }
    }
    decision = graph.decide_pending(
        pending_trace_queue(),
        target_index,
        ability,
        values,
        point=point,
        current_type=type(scope.path[-1].archetype)
    );
    if scope.disengaged {
        decision.execution_preserved = False;
        decision.reasons.append('Walker has already disengaged');
    }
    return decision;
}


def _trace_field_effects(
    graph: WalkerDependencyGraph, keys: set[str], effects: TraceEffects
) {
    import from jaclang.runtime.archetype { Archetype }
    if graph.runtime_walker is None {
        effects.unknown = True;
        return;
    }
    if not _trace_safe_storage(graph.runtime_walker) {
        effects.unknown = True;
    }
    if getattr(graph.runtime_walker, '__setattr__') is not Archetype.__setattr__ {
        effects.unknown = True;
    }
    if getattr(graph.runtime_walker, '__getattribute__')
        is not Archetype.__getattribute__ {
        effects.unknown = True;
    }
    for key in keys {
        if not key.startswith('self.') {
            continue;
        }
        for base in graph.runtime_walker.__mro__ {
            descriptor = vars(base).get(key[5:]);
            if any('__get__' in vars(owner) for owner in type(descriptor).__mro__) {
                effects.unknown = True;
            }
        }
    }
}


def compile_checkpoint_plan(arch: uni.Archetype) -> dict {
    graph = analyze_walker_ast(arch);
    candidates = [
        name
        for name in graph.entries
        if any(
            e.ability == name and e.kind in ('branch', 'visit') for e in graph.events
        )
    ];
    needed: set[str] = set();
    for name in candidates {
        needed.update(_trace_requirements(graph, name));
    }
    points = [
        e.id
        for e in graph.events
        if e.kind == 'visit'
            or (
                e.kind in ('assign', 'scalar_update')
                and e.writes.startswith('self.')
                and e.writes in needed
            )
    ];
    return {
        'version': 2,
        'walker_name': graph.walker_name,
        'entries': graph.entries,
        'handlers': graph.handlers,
        'dispatch': {str(k): v for (k, v) in graph.dispatch.items()},
        'candidates': candidates,
        'points': points,
        'events': [
            {
                'id': e.id,
                'kind': e.kind,
                'ability': e.ability,
                'line': e.line,
                'column': e.column,
                'expression': e.expression,
                'writes': e.writes,
                'reads': e.reads,
                'targets': e.targets,
                'hop_chain': e.hop_chain,
                'origin': e.origin,
                'next_id': e.next_id,
                'true_id': e.true_id,
                'false_id': e.false_id,
                'definitions': e.definitions
            } for e in graph.events
        ],
        'edges': [
            {
                'source': e.source,
                'target': e.target,
                'kind': e.kind,
                'label': e.label,
                'context': e.context
            } for e in graph.edges
        ]
    };
}

def checkpoint_graph(spec: dict, walker_type: type) -> WalkerDependencyGraph {
    if spec['version'] not in (1, 2) {
        raise ValueError('Unsupported dependency checkpoint plan');
    }
    graph = WalkerDependencyGraph(
        walker_name=spec['walker_name'], runtime_walker=walker_type
    );
    for item in spec['events'] {
        fields = dict(item);
        fields['reads'] = tuple(fields['reads']);
        fields['targets'] = tuple(fields['targets']);
        fields['hop_chain'] = tuple(tuple(hop) for hop in fields.get('hop_chain', []));
        graph.events.append(TraceEvent(**fields));
    }
    graph.edges = [TraceDependency(**item) for item in spec['edges']];
    graph.entries = dict(spec['entries']);
    graph.handlers = dict(spec['handlers']);
    graph.dispatch = {int(k): v for (k, v) in spec['dispatch'].items()};
    return graph;
}
