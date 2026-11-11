"""Compile ordinary graph Access demands independently of Visit scheduling.

The existing continuation/region plan remains the Visit scheduling projection.
This projection adds graph reads in the current ability and statically resolved
ordinary calls. It never executes a user function, modifies a queue, or infers
a callee from its name alone. Unknown calls/effects end the admitted prefix.
"""
import ast
import copy
import json
import operator
from time import perf_counter
from uuid import UUID

from jaclang.compiler.frontend import unitree as u
from jaclang.runtime.ttg_access_graph import text, children


class Unresolved(ValueError):
    pass


def path(origin, node_type=None, hops=()):
    return dict(origin=origin, node_type=node_type, hops=list(hops))


class AccessCompiler:
    def __init__(self, arch):
        self.arch = arch
        self.module = arch.find_parent_of_type(u.Module)
        self.types = {}
        self.functions = {}
        self.methods = {}
        for item in self.module.body:
            if isinstance(item, u.Archetype):
                self.types[item.name.value] = item
                for method in item.get_methods():
                    self.methods[(item.name.value, method.py_resolve_name())] = method
            elif isinstance(item, u.Ability):
                self.functions[item.py_resolve_name()] = item
        self.demands = []
        self.rejections = []
        self.stack = []
        self.guards = []
        self.visit = False

    def reject(self, node, reason):
        self.rejections.append(dict(file=node.loc.mod_path, line=node.loc.first_line,
                                    reason=reason, calls=list(self.stack)))

    def scalar(self, node):
        """Serializable closed scalar grammar; evaluated only from safe facts."""
        try:
            value = ast.parse(text(node), mode='eval').body
        except SyntaxError as exc:
            raise Unresolved('Unsupported scalar syntax') from exc
        def lower(n):
            if isinstance(n, ast.Constant) and type(n.value) in (str, int, float, bool, type(None)):
                return ['constant', n.value]
            if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id in ('self', 'here'):
                return ['field', n.value.id, n.attr]
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == 'jid' and not n.keywords and len(n.args) == 1 and isinstance(n.args[0], ast.Name) and n.args[0].id in ('here', 'root') and 'jid' not in self.functions:
                return ['identity', n.args[0].id]
            if isinstance(n, ast.UnaryOp) and isinstance(n.op, ast.Not):
                return ['not', lower(n.operand)]
            if isinstance(n, ast.BoolOp):
                return ['and' if isinstance(n.op, ast.And) else 'or', *[lower(v) for v in n.values]]
            if isinstance(n, ast.Compare) and len(n.ops) == 1 and type(n.ops[0]) in (ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE):
                return ['compare', type(n.ops[0]).__name__, lower(n.left), lower(n.comparators[0])]
            raise Unresolved('Scalar depends on unresolved local/call/effect')
        return lower(value)

    def query(self, node, env):
        if node.edges_only or node.is_async:
            raise Unresolved('Edge-only/asynchronous Access not admitted')
        items = node.chain
        explicit = items and not isinstance(items[0], (u.EdgeOpRef, u.FilterCompr))
        base = self.expr(items[0], env) if explicit else env.get('here')
        if not base:
            raise Unresolved('Graph Access origin is unresolved')
        hops = copy.deepcopy(base['hops'])
        added = 0
        for item in items[1:] if explicit else items:
            if isinstance(item, u.EdgeOpRef):
                edge = None
                if item.filter_cond is not None:
                    if item.filter_cond.compares:
                        raise Unresolved('Edge predicates not admitted in Access v1')
                    if item.filter_cond.f_type is not None:
                        if not isinstance(item.filter_cond.f_type, u.Name):
                            raise Unresolved('Dynamic edge type')
                        edge = item.filter_cond.f_type.value
                # The enum's numeric values are the graph-query ABI.
                direction = int(item.edge_dir.value)
                hops.append(dict(edge=edge, node=None, direction=direction, predicates=[]))
                added += 1
            elif isinstance(item, u.FilterCompr) and added:
                if item.f_type is not None:
                    if not isinstance(item.f_type, u.Name):
                        raise Unresolved('Dynamic node type')
                    hops[-1]['node'] = item.f_type.value
                for predicate in item.compares:
                    if not isinstance(predicate, u.CompareExpr) or not isinstance(predicate.left, u.Name) or len(predicate.rights) != 1:
                        raise Unresolved('Unsupported graph predicate')
                    expr = self.scalar(predicate.rights[0])
                    if expr[0] != 'constant':
                        raise Unresolved('Only constant query predicates admitted initially')
                    op = predicate.ops[0].value
                    if op not in ('==', '!=', '<', '<=', '>', '>='):
                        raise Unresolved('Unsupported predicate operator')
                    hops[-1]['predicates'].append([predicate.left.value, op, expr[1]])
            else:
                raise Unresolved('Graph query target constraint is unresolved')
        if not added:
            raise Unresolved('Graph query has no supported hop')
        result = path(base['origin'], hops[-1]['node'], hops)
        if base.get('singletons'):
            result['singletons'] = list(base['singletons'])
        demand = dict(kind='Access', id=len(self.demands), path=result,
                      guards=copy.deepcopy(self.guards), calls=list(self.stack),
                      file=node.loc.mod_path, line=node.loc.first_line,
                      column=node.loc.col_start,
                      scheduling='visit_projection' if self.visit else 'ordinary_access')
        self.demands.append(demand)
        return result

    def expr(self, node, env):
        if node is None:
            return None
        if isinstance(node, (u.Name, u.SpecialVarRef)):
            return env.get(text(node))
        if isinstance(node, u.AtomUnit):
            return self.expr(node.value, env)
        if isinstance(node, u.EdgeRefTrailer):
            return self.query(node, env)
        if isinstance(node, u.AtomTrailer):
            base = self.expr(node.target, env)
            if not node.is_attr:
                # Choosing index zero is only projected when the full path is
                # singleton at runtime. Never substitute all rows for [0].
                if base and text(node.right).replace(' ', '') == '[0]':
                    base = copy.deepcopy(base)
                    base.setdefault('singletons', []).append(len(base['hops']))
                    return base
                self.expr(node.right, env)
            return None
        if isinstance(node, u.ListCompr):
            local = dict(env)
            for clause in node.compr:
                value = self.expr(clause.collection, local)
                if not isinstance(clause.target, u.Name) or clause.conditional:
                    raise Unresolved('Conditional/destructuring comprehension')
                local[clause.target.value] = value
            self.expr(node.out_expr, local)
            return None
        if isinstance(node, u.FuncCall):
            return self.call(node, env)
        # Connections/deletions are graph effects, not ordinary expressions.
        if isinstance(node, (u.ConnectOp, u.DisconnectOp)):
            raise Unresolved('Graph mutation boundary')
        for child in children(node):
            self.expr(child, env)
        return None

    def call(self, call, env):
        target = call.target
        callee = None
        receiver = None
        name = text(target)
        if isinstance(target, u.Name):
            callee = self.functions.get(target.value)
            # Arguments are evaluated before the call, even at an unknown call.
            arguments = [self.expr(p.value if isinstance(p, u.KWPair) else p, env) for p in call.params or []]
            if callee is None:
                declared = self.types.get(target.value)
                data_constructor = declared is not None and declared.arch_type.value == 'obj' and not declared.get_methods() and not declared.base_classes
                if target.value in ('jid', 'len', 'sum', 'max', 'min', 'sorted', 'isinstance', 'cast') or data_constructor:
                    return None
                raise Unresolved('Unresolved call: ' + name)
        elif isinstance(target, u.AtomTrailer) and target.is_attr and isinstance(target.right, u.Name):
            receiver = self.expr(target.target, env)
            arguments = [self.expr(p.value if isinstance(p, u.KWPair) else p, env) for p in call.params or []]
            if receiver and receiver.get('node_type'):
                callee = self.methods.get((receiver['node_type'], target.right.value))
            if callee is None:
                raise Unresolved('Unresolved receiver/method: ' + name)
        else:
            raise Unresolved('Dynamic callee')
        if not isinstance(callee.signature, u.FuncSignature) or any(isinstance(p, u.KWPair) for p in call.params or []):
            raise Unresolved('Callee signature/keyword binding not supported')
        params = list(callee.signature.get_parameters())
        if len(params) != len(arguments):
            raise Unresolved('Argument binding does not match declaration')
        if id(callee) in [item[0] for item in getattr(self, '_active_calls', [])]:
            raise Unresolved('Recursive ordinary call')
        local = {'root': env['root']}
        if receiver:
            local['self'] = receiver
            # Implicit graph origins inside a node method refer to its node.
            local['here'] = receiver
        for param, value in zip(params, arguments):
            local[param.name.value] = value
        previous = getattr(self, '_active_calls', [])
        self._active_calls = previous + [(id(callee), name)]
        self.stack.append(name)
        try:
            before = len(self.rejections)
            result = self.block(self.body(callee), local)
            if len(self.rejections) != before:
                raise Unresolved('Callee prefix ended at an unresolved effect: ' + name)
            return result
        finally:
            self.stack.pop()
            self._active_calls = previous

    @staticmethod
    def body(ability):
        body = ability.body
        if isinstance(body, u.ImplDef):
            body = body.body
        if not isinstance(body, list):
            raise Unresolved('Missing function body')
        return body

    def block(self, statements, env):
        for stmt in statements:
            try:
                if isinstance(stmt, u.Assignment):
                    value = self.expr(stmt.value, env)
                    if len(stmt.target) != 1 or not isinstance(stmt.target[0], u.Name) or stmt.aug_op:
                        raise Unresolved('Nonlocal/augmented write boundary')
                    env[stmt.target[0].value] = value
                elif isinstance(stmt, u.VisitStmt):
                    old = self.visit
                    self.visit = True
                    try:
                        self.expr(stmt.target, env)
                    finally:
                        self.visit = old
                    # Enqueue is represented separately; no simulated method
                    # call or invented Access for visit xs.
                elif isinstance(stmt, u.IfStmt):
                    if self.stack:
                        raise Unresolved('Callee guard receiver binding is not admitted yet')
                    condition = self.scalar(stmt.condition)
                    old = self.guards
                    self.guards = old + [[condition, True]]
                    self.block(stmt.body, dict(env))
                    self.guards = old + [[condition, False]]
                    other = stmt.else_body
                    if other is not None:
                        self.block([other] if isinstance(other, u.IfStmt) else other.body, dict(env))
                    self.guards = old
                    # No unproven reaching values after a branch merge.
                    raise Unresolved('Branch continuation requires a merged state')
                elif isinstance(stmt, (u.ReportStmt, u.ReturnStmt)):
                    value = self.expr(stmt.expr, env)
                    if isinstance(stmt, u.ReturnStmt):
                        return value
                elif isinstance(stmt, u.InForStmt):
                    value = self.expr(stmt.collection, env)
                    if not isinstance(stmt.target, u.Name) or stmt.else_body:
                        raise Unresolved('Destructured/else loop')
                    local = dict(env)
                    local[stmt.target.value] = value
                    self.block(stmt.body, local)
                    raise Unresolved('Loop continuation requires effect summary')
                elif isinstance(stmt, u.ExprStmt):
                    self.expr(stmt.expr, env)
                else:
                    raise Unresolved('Unsupported statement: ' + type(stmt).__name__)
            except Unresolved as exc:
                self.reject(stmt, str(exc))
                return None
        return None

    def compile(self):
        abilities = {}
        for ability in self.arch.get_methods():
            if not isinstance(ability.signature, u.EventSignature):
                continue
            names = ability.event_trigger_type_names() or []
            if not names and isinstance(ability.signature.arch_tag_info, u.Name):
                names = [ability.signature.arch_tag_info.value]
            if len(names) != 1:
                continue
            self.demands, self.rejections, self.stack, self.guards = [], [], [], []
            name = ability.py_resolve_name()
            env = {'here': path('here', names[0]), 'root': path('root', 'Root')}
            try:
                self.block(self.body(ability), env)
            except Unresolved as exc:
                self.reject(ability, str(exc))
            abilities[name] = dict(trigger=names[0], demands=self.demands,
                                   rejections=self.rejections)
        return dict(version=1, abilities=abilities,
                    contract='Access decides payload demand; Visit scheduling uses the existing continuation projection. Ordinary calls require a statically typed receiver or exact local function declaration; unsupported effects end the prefix.')


def compile_access_plan(arch):
    return AccessCompiler(arch).compile()


def scalar_value(spec, walker_facts, node_facts, origin, root):
    kind = spec[0]
    if kind == 'constant':
        return spec[1]
    if kind == 'field':
        facts = walker_facts if spec[1] == 'self' else node_facts
        if facts.get(spec[2] + '::unsafe') or spec[2] not in facts:
            raise Unresolved('Unavailable/unsafe scalar')
        value = facts[spec[2]]
        if type(value) not in (bool, int, float, str, type(None)):
            raise Unresolved('Nonprimitive scalar')
        return value
    if kind == 'identity':
        anchor = origin if spec[1] == 'here' else root
        if anchor is None:
            raise Unresolved('Missing identity')
        return anchor.id.hex
    if kind == 'not':
        return not scalar_value(spec[1], walker_facts, node_facts, origin, root)
    if kind in ('and', 'or'):
        for child in spec[1:]:
            value = scalar_value(child, walker_facts, node_facts, origin, root)
            if kind == 'and' and not value or kind == 'or' and value:
                return value
        return value
    if kind == 'compare':
        ops = {'Eq': operator.eq, 'NotEq': operator.ne, 'Lt': operator.lt,
               'LtE': operator.le, 'Gt': operator.gt, 'GtE': operator.ge}
        return ops[spec[1]](scalar_value(spec[2], walker_facts, node_facts, origin, root),
                            scalar_value(spec[3], walker_facts, node_facts, origin, root))
    raise Unresolved('Unknown scalar instruction')


def prefetch_accesses(state, graph, scope, point):
    """Resolve ordinary Access paths and dispatch payload; never enqueue nodes."""
    from jaclang.runtime.ttg_continuation import continuation_type, known_node_fields
    from jaclang.runtime.ttg_dependencies import _trace_safe_storage
    from jaclang.runtime.archetype import Archetype, NodeArchetype
    from jaclang.runtime.graph_query import GraphQuery, QHop, QPred
    from jaclang.data.query_planner import resolve_ttg_path, _topology_node_ids
    from jaclang.runtime.ttg_dependency_prefetch import dispatch_fused_payload, model_ability_key
    if not state.fused_sql or graph.events[point].kind != 'entry' or scope.disengaged:
        return
    ability = graph.events[point].ability
    program = graph.access_plan.get('abilities', {}).get(ability)
    if not program or not scope.path:
        return
    anchor = scope.path[-1]
    expected = continuation_type(scope.wlk, program['trigger'])
    if expected is None or type(anchor.archetype) is not expected:
        return
    if not _trace_safe_storage(type(scope.wlk)) or type(scope.wlk).__getattribute__ is not Archetype.__getattribute__:
        return
    if not _trace_safe_storage(expected) or expected.__getattribute__ is not NodeArchetype.__getattribute__:
        return
    mem = state.ctx.mem
    facts = known_node_fields(anchor.archetype)
    walker_facts = vars(scope.wlk)
    root = state.ctx.user_root
    ids = []
    seen_paths = set()
    with mem._raw_lock:
        excluded = set(mem.__mem__) | set(mem.__raw_mem__) | state.submitted | set(mem._deleted)
    limit = state.max_length - len(state.submitted)
    if limit <= 0:
        return
    for demand in program['demands']:
        if demand['scheduling'] != 'ordinary_access':
            continue
        try:
            if any(bool(scalar_value(g, walker_facts, facts, anchor, root)) != wanted for g, wanted in demand['guards']):
                state.fusion['access_guard_skips'] += 1
                continue
            spec = demand['path']
            origin = root if spec['origin'] == 'root' else anchor
            if origin is None or not spec['hops']:
                continue
            key = (origin.id, json.dumps(spec, sort_keys=True))
            if key in seen_paths:
                continue
            seen_paths.add(key)
            hops = []
            for hop in spec['hops']:
                edge = continuation_type(scope.wlk, hop['edge']) if hop['edge'] else None
                node = continuation_type(scope.wlk, hop['node']) if hop['node'] else None
                if hop['edge'] and edge is None or hop['node'] and node is None:
                    raise Unresolved('Unresolved Access type')
                hops.append(QHop(dir=hop['direction'], edge=edge, nd=node,
                                 preds=[QPred(field=f, op=o, value=v) for f, o, v in hop['predicates']]))
            query = GraphQuery([], hops=hops)
            if not any(hop['predicates'] for hop in spec['hops']):
                # Topology-only resolution does not materialize payload. Avoid
                # resolving already covered root/helper reads at every entry.
                cached_ids = _topology_node_ids(mem, [origin.id], query, len(hops))
                if cached_ids is not None and all(uid in excluded for uid in cached_ids):
                    state.fusion['access_cache_complete_skips'] += 1
                    continue
            for length in spec.get('singletons', []):
                rows = resolve_ttg_path(mem, GraphQuery([], hops=hops[:length]), origin.id, 1)
                if rows is None or len(rows) != 1:
                    raise Unresolved('Indexed Access prefix is not singleton')
            state.fusion['access_queries'] += 1
            rows = resolve_ttg_path(mem, query, origin.id, state.max_length)
            if rows is None:
                raise Unresolved('Access resolution declined')
            state.fusion['access_resolved_nodes'] += len(rows)
            for row in rows:
                uid = UUID(str(row[0]))
                if uid not in excluded and len(ids) < limit:
                    ids.append(uid)
                    excluded.add(uid)
        except (Unresolved, ValueError, TypeError, KeyError) as exc:
            state.fusion['access_declines'] += 1
            state.fusion['access_last_decline'] = str(exc)
    if not ids:
        return
    plan = dict(origin=str(anchor.id), ability=ability, visit_event=point,
                demand_kind='Access', hops=[], ids=[], status='resolved',
                decisions=[], demanded=False, decision_ms=0.0, queue_position=0,
                candidate_at=perf_counter(), resolved_nodes=len(ids),
                site_key=model_ability_key(state, graph, ability) + ':access',
                ability_key=model_ability_key(state, graph, ability))
    state.plans.append(plan)
    dispatch_fused_payload(state, {len(state.plans) - 1: ids})
    state.fusion['access_payload_ids'] += len(ids)
