"""A bounded output-effect certificate for homogeneous, filtered traversals.

The native program is never rewritten.  The accepted entry grammar has one
unconditional trailing visit; preceding statements may compute private output,
but cannot mutate a node, enqueue, cancel, call an unknown helper or inspect
another ability's state.  Runtime contracts are separate from this syntax proof.
"""
import ast
import dis
import json
import re
import sys
from types import FunctionType
from uuid import UUID


def _text(node):
    from jaclang.runtime.ttg_dependencies import _trace_text
    return _trace_text(node)


def path_spec(node):
    from jaclang.compiler.frontend import unitree as u
    from jaclang.runtime.ttg import JacTTGGenerator
    if not isinstance(node, u.EdgeRefTrailer):
        raise ValueError('Not a direct graph path')
    if JacTTGGenerator._edge_ref_explicit_origin_name(node) not in (None, '', 'here'):
        raise ValueError('Non-current origin')
    chain = JacTTGGenerator._extract_chains_from_trailer(node, node)
    if len(chain) != 1:
        raise ValueError('Output tree requires one hop')
    edge, target, direction = chain[0]
    predicates = []
    for item in node.chain:
        if isinstance(item, u.EdgeOpRef) and item.filter_cond is not None:
            fc = item.filter_cond
            if fc.compares:
                raise ValueError('Edge predicate unsupported')
            if fc.f_type is not None:
                if not isinstance(fc.f_type, u.Name):
                    raise ValueError('Dynamic edge type')
                edge = edge or fc.f_type.value
        if isinstance(item, u.FilterCompr):
            if item.f_type is not None:
                if not isinstance(item.f_type, u.Name):
                    raise ValueError('Dynamic node type')
                target = target or item.f_type.value
            for predicate in item.compares:
                expr = ast.parse(_text(predicate), mode='eval').body
                if not (isinstance(expr, ast.Compare) and isinstance(expr.left, ast.Name)
                        and len(expr.ops) == len(expr.comparators) == 1
                        and isinstance(expr.ops[0], ast.Eq)
                        and isinstance(expr.comparators[0], ast.Constant)
                        and type(expr.comparators[0].value) is bool):
                    raise ValueError('Only exact boolean equality predicates')
                predicates.append([expr.left.id, '==', expr.comparators[0].value])
    if not edge or not target or direction not in (1, 2, 3):
        raise ValueError('Explicit typed hop required')
    return dict(hops=[[edge, target, direction]], predicates=predicates)


def compile_effect_certificate(arch):
    """Return syntactic access/output separation; unknown programs return None."""
    from jaclang.compiler.frontend import unitree as u
    entries = [a for a in arch.get_all_sub_nodes(u.Ability)
               if isinstance(a.signature, u.EventSignature) and a.signature.event.value == 'entry']
    if len(entries) != 1:
        return None
    ability = entries[0]
    types = ability.event_trigger_type_names() or []
    if not types and isinstance(ability.signature.arch_tag_info, u.Name):
        types = [ability.signature.arch_tag_info.value]
    if len(types) != 1:
        return None
    body = ability.body.body if isinstance(ability.body, u.ImplDef) else ability.body
    if not isinstance(body, list) or not body or not isinstance(body[-1], u.VisitStmt):
        return None
    visit = body[-1]
    if visit.else_body is not None or visit.insert_loc is not None:
        return None
    try:
        spec = path_spec(visit.target)
        if spec['hops'][0][1] != types[0]:
            return None
        node_fields = set(p[0] for p in spec['predicates'])
        self_fields = set()
        constructors = set()
        node_variables = {'here'}
        def expression(node):
            text = _text(node).strip().rstrip(";")
            tree = ast.parse(text, mode='eval').body
            for n in ast.walk(tree):
                if isinstance(n, (ast.Lambda, ast.ListComp, ast.DictComp, ast.SetComp,
                                  ast.GeneratorExp, ast.NamedExpr, ast.Await)):
                    raise ValueError('Unknown expression effects')
                if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name):
                    if n.value.id == 'self': self_fields.add(n.attr)
                    elif n.value.id in node_variables: node_fields.add(n.attr)
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id != 'jid':
                    constructors.add(n.func.id)
            return ast.unparse(tree)
        def statements(items, inside_loop=False, exiting=False):
            out = []
            for stmt in items:
                if not exiting and isinstance(stmt, u.Assignment) and len(stmt.target) == 1 and stmt.aug_op is None and stmt.value is not None:
                    left = expression(stmt.target[0]); right = expression(stmt.value)
                    out.append(dict(kind='assign', left=left, right=right))
                elif isinstance(stmt, u.IfStmt):
                    if stmt.else_body is not None:
                        raise ValueError('Output else branch unsupported')
                    out.append(dict(kind='if', condition=expression(stmt.condition), body=statements(stmt.body, inside_loop, exiting)))
                elif not exiting and isinstance(stmt, u.InForStmt) and not inside_loop:
                    loop_name = _text(stmt.target).strip()
                    if not isinstance(stmt.target, u.Name) or stmt.else_body is not None or path_spec(stmt.collection) != spec:
                        raise ValueError('Output loop differs from visit')
                    node_variables.add(loop_name)
                    out.append(dict(kind='for', target=loop_name, body=statements(stmt.body, True)))
                elif exiting and isinstance(stmt, u.ReportStmt):
                    out.append(dict(kind='report', value=expression(stmt.expr)))
                else:
                    text = _text(stmt).strip().rstrip(';')
                    if exiting:
                        text = re.sub(r'lambda\s*\(\s*(\w+)\s*:\s*\w+\s*\)\s*\{\s*\1\s*\.\s*(\w+)\s*;?\s*\}', r'lambda \1: \1.\2', text)
                        expr = ast.parse(text, mode='eval').body
                        if not (isinstance(expr, ast.Call) and isinstance(expr.func, ast.Attribute) and expr.func.attr == 'sort'
                            and isinstance(expr.func.value, ast.Attribute) and isinstance(expr.func.value.value, ast.Name)
                            and expr.func.value.value.id == 'self' and not expr.args and len(expr.keywords) == 1
                            and expr.keywords[0].arg == 'key' and isinstance(expr.keywords[0].value, ast.Lambda)):
                            raise ValueError('Unproved exit effects')
                        key = expr.keywords[0].value
                        if not (len(key.args.args) == 1 and isinstance(key.body, ast.Attribute) and isinstance(key.body.value, ast.Name)
                            and key.body.value.id == key.args.args[0].arg): raise ValueError('Unproved sort key')
                        self_fields.add(expr.func.value.attr)
                        out.append(dict(kind='sort', field=expr.func.value.attr, key=key.body.attr))
                        continue
                    expr = ast.parse(text, mode='eval').body
                    if not (isinstance(expr, ast.Call) and isinstance(expr.func, ast.Attribute)
                            and isinstance(expr.func.value, ast.Attribute)
                            and isinstance(expr.func.value.value, ast.Name)
                            and expr.func.value.value.id == 'self' and expr.func.attr == 'append'
                            and len(expr.args) == 1 and not expr.keywords):
                        raise ValueError('Statement has unproved effects')
                    self_fields.add(expr.func.value.attr)
                    out.append(dict(kind='append', field=expr.func.value.attr,
                                    value=expression(stmt).rstrip(';')))
            return out
        effects = statements(body[:-1])
        exits = []
        exit_abilities = []
        for other in arch.get_all_sub_nodes(u.Ability):
            if isinstance(other.signature, u.EventSignature) and other.signature.event.value == 'exit':
                exit_abilities.append(other.py_resolve_name())
                exit_body = other.body.body if isinstance(other.body, u.ImplDef) else other.body
                exits.extend(statements(exit_body, exiting=True))
        # Bare, existing pure chains use the older certificate.
        if not effects or not spec['predicates']:
            return None
        return dict(version=1, kind='output_tree', ability=ability.py_resolve_name(),
                    source_type=types[0], **spec, effects=effects, exits=exits, exit_abilities=exit_abilities,
                    node_fields=sorted(node_fields), self_fields=sorted(self_fields),
                    constructors=sorted(constructors), visit_line=visit.loc.first_line,
                    dependency_proof='Unconditional trailing visit has only origin/type/constant-predicate inputs; checked output grammar has no graph/queue writes. Runtime ownership, field and constructor contracts remain mandatory.')
    except (ValueError, SyntaxError, AttributeError, TypeError):
        return None


def _plain_init(cls, names):
    """Symbolically check the actual initializer; never construct a user object.

    All arguments are supplied. Default-factory branches are therefore skipped;
    the only allowed call is the framework's exact no-op postinit. This accepts
    generated Jac records without assuming every dataclass constructor is pure.
    """
    from jaclang.runtime.archetype import Archetype
    from jaclang.runtime.ttg_dependencies import _trace_safe_storage
    def raw_attr(owner, name):
        return next((vars(base)[name] for base in owner.__mro__ if name in vars(base)), None)
    if (type(cls) is not type or not issubclass(cls, Archetype)
            or not _trace_safe_storage(cls)
            or raw_attr(cls, '__new__') is not vars(object)['__new__']
            or raw_attr(cls, '__setattr__') is not vars(Archetype)['__setattr__']
            or raw_attr(cls, '__getattribute__') is not vars(object)['__getattribute__']
            or raw_attr(cls, '__post_init__') is not vars(Archetype)['__post_init__']):
        return False
    if any(name.startswith('_') for name in names): return False
    for name in names:
        if any(any('__set__' in vars(t) or '__get__' in vars(t)
                   for t in type(vars(base).get(name)).__mro__) for base in cls.__mro__):
            return False
    init = vars(cls).get('__init__')
    if type(init) is not FunctionType: return False
    instructions = list(dis.get_instructions(init))
    positions = {instruction.offset: i for i, instruction in enumerate(instructions)}
    environment = {'self': ('self',)} | {name: ('argument', name) for name in names}
    closure = dict(zip(init.__code__.co_freevars, init.__closure__ or ()))
    stack = []; stored = set(); index = 0
    try:
        for _ in range(1000):
            instruction = instructions[index]; index += 1
            op, arg = instruction.opname, instruction.argval
            if op in ('RESUME', 'COPY_FREE_VARS', 'NOP', 'CACHE', 'EXTENDED_ARG', 'NOT_TAKEN'): continue
            if op in ('LOAD_FAST', 'LOAD_FAST_BORROW'):
                stack.append(environment[arg])
            elif op in ('LOAD_FAST_LOAD_FAST', 'LOAD_FAST_BORROW_LOAD_FAST_BORROW'):
                stack.extend(environment[name] for name in arg)
            elif op == 'LOAD_CONST': stack.append(('constant', arg))
            elif op == 'LOAD_DEREF': stack.append(('closure', arg))
            elif op == 'IS_OP':
                right, left = stack.pop(), stack.pop()
                # Supplied application arguments cannot be dataclasses' sentinel.
                if not (left[0] == 'argument' and right[0] == 'closure'
                        and right[1].endswith('HAS_DEFAULT_FACTORY__')
                        and right[1] in closure): return False
                import dataclasses
                if closure[right[1]].cell_contents is not dataclasses._HAS_DEFAULT_FACTORY: return False
                stack.append(('constant', bool(arg)))
            elif op in ('POP_JUMP_IF_FALSE', 'POP_JUMP_FORWARD_IF_FALSE'):
                condition = stack.pop()
                if condition[0] != 'constant' or type(condition[1]) is not bool: return False
                if not condition[1]: index = positions[arg]
            elif op == 'JUMP_FORWARD': index = positions[arg]
            elif op == 'STORE_ATTR':
                receiver, value = stack.pop(), stack.pop()
                if receiver != ('self',) or value != ('argument', arg) or arg not in names: return False
                stored.add(arg)
            elif op in ('LOAD_ATTR', 'LOAD_METHOD'):
                if stack.pop() != ('self',) or arg != '__post_init__': return False
                stack.append(('postinit',))
            elif op == 'PRECALL':
                if arg != 0: return False
            elif op == 'CALL':
                if arg != 0 or stack.pop() != ('postinit',): return False
                stack.append(('constant', None))
            elif op == 'POP_TOP':
                if stack.pop() != ('constant', None): return False
            elif op == 'RETURN_VALUE':
                return stack.pop() == ('constant', None) and stored == set(names) and not stack
            elif op == 'RETURN_CONST': return arg is None and stored == set(names) and not stack
            else: return False
    except (IndexError, KeyError, TypeError): return False
    return False


def validate_effects(certificate, wlk, node_type, mem, scope, proof_roots=()):
    """Type/effect-check expressions without calling an application helper."""
    from jaclang.runtime.ttg_dependencies import _trace_safe_storage
    from jaclang.runtime.ttg_continuation import _plain_scalar_field
    from jaclang.runtime.archetype import NodeArchetype, Archetype
    from jaclang.runtime.runtime import JacPersistence
    if (not _trace_safe_storage(type(wlk)) or type(wlk).__getattribute__ is not object.__getattribute__
            or type(wlk).__setattr__ is not Archetype.__setattr__
            or node_type.__setattr__ is not Archetype.__setattr__):
        raise ValueError('Walker custom storage')
    namespace = vars(sys.modules[type(wlk).__module__])
    if namespace.get('jid') is not JacPersistence.object_ref:
        raise ValueError('Identity helper is shadowed')
    if next((vars(b)['__jac__'] for b in node_type.__mro__ if '__jac__' in vars(b)), None) is not vars(NodeArchetype)['__jac__']:
        raise ValueError('Node identity descriptor is custom')
    field_types = {}
    for name in certificate['node_fields']:
        for typ in (str, int, bool):
            if _plain_scalar_field(node_type, name, (typ, typ.__name__)):
                field_types[name] = typ
                break
        else:
            raise ValueError('Unproved ordinary node field: ' + name)
    for name, op, val in certificate['predicates']:
        if field_types[name] is not bool:
            raise ValueError('Predicate field is not bool')
    own = vars(wlk)
    types = {}
    containers = set()
    for name in certificate['self_fields']:
        if any(any('__set__' in vars(t) for t in type(vars(b).get(name)).__mro__) for b in type(wlk).__mro__):
            raise ValueError('Walker output field is a descriptor')
        value = own.get(name)
        if type(value) in (str, int, bool):
            types[name] = type(value)
        elif type(value) is dict:
            if any(type(k) is not str or type(v) not in (str, int) for k, v in value.items()):
                raise ValueError('Output map has custom keys/values')
            vtypes = {type(v) for v in value.values()}
            if len(vtypes) > 1: raise ValueError('Output map is heterogeneous')
            types[name] = ('map', next(iter(vtypes)) if vtypes else None)
            if id(value) in containers: raise ValueError('Output containers alias')
            containers.add(id(value))
        elif type(value) is list and not value:
            types[name] = ('list', None)
            if id(value) in containers: raise ValueError('Output containers alias')
            containers.add(id(value))
        else:
            raise ValueError('Unproved output field value: ' + name)
    # Graph/session/scope-owned objects must not share the output containers.
    # Inspect raw storage only; unknown storage fails closed, never calls getters.
    seen = set()
    work = list(mem.__mem__.values()) + [scope] + list(proof_roots)
    while work:
        value = work.pop()
        if id(value) in containers:
            raise ValueError('Output container aliases graph or queue state')
        if value is wlk or id(value) in seen:
            continue
        seen.add(id(value))
        if len(seen) > 50000: raise ValueError('Ownership scan budget')
        if type(value) is dict: work.extend(value.values())
        elif type(value) in (list, tuple, set): work.extend(value)
        elif value is None or type(value) in (str, int, bool, float, bytes, UUID, type) or callable(value): pass
        elif _trace_safe_storage(type(value)):
            try: work.extend(vars(value).values())
            except TypeError: pass
        else: raise ValueError('Unknown graph storage during ownership proof')
    env = {'here': ('node', node_type)}
    def infer(n):
        if isinstance(n, ast.Constant) and type(n.value) in (str, int, bool): return type(n.value)
        if isinstance(n, ast.Name): return env[n.id]
        if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name):
            if n.value.id == 'self': return types[n.attr]
            if env.get(n.value.id) == ('node', node_type): return field_types[n.attr]
        if isinstance(n, ast.UnaryOp) and isinstance(n.op, ast.Not):
            if infer(n.operand) not in (str, int, bool): raise ValueError('Custom truthiness')
            return bool
        if isinstance(n, ast.BinOp) and isinstance(n.op, ast.Add):
            left, right = infer(n.left), infer(n.right)
            if left is right and left in (int, str): return left
        if isinstance(n, ast.Compare) and len(n.ops) == len(n.comparators) == 1 and isinstance(n.ops[0], (ast.Eq, ast.NotEq)):
            if infer(n.left) in (str, int, bool) and infer(n.comparators[0]) in (str, int, bool): return bool
        if isinstance(n, ast.Call) and not n.keywords and isinstance(n.func, ast.Name) and n.func.id == 'jid' and len(n.args) == 1:
            if infer(n.args[0]) == ('node', node_type): return str
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == 'get' and len(n.args) == 2 and not n.keywords:
            receiver = infer(n.func.value); key, default = map(infer, n.args)
            if type(receiver) is tuple and receiver[0] == 'map' and key is str and default in (str, int) and receiver[1] in (None, default):
                return default
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and not n.args and n.keywords:
            cls = namespace.get(n.func.id)
            args = {kw.arg: infer(kw.value) for kw in n.keywords}
            if cls is None or None in args or any(t not in (int, str, bool) and not (type(t) is tuple and t[0] == 'list') for t in args.values()) or not _plain_init(cls, args):
                raise ValueError('Output constructor is not a plain scalar record')
            return ('record', cls)
        raise ValueError('Unproved output expression: ' + ast.dump(n))
    def check(items):
        for item in items:
            kind = item['kind']
            if kind == 'assign':
                left = ast.parse(item['left'], mode='eval').body
                typ = infer(ast.parse(item['right'], mode='eval').body)
                if isinstance(left, ast.Name): env[left.id] = typ
                elif isinstance(left, ast.Attribute) and isinstance(left.value, ast.Name) and left.value.id == 'self' and types[left.attr] is typ and typ in (str, int, bool): pass
                elif isinstance(left, ast.Subscript) and isinstance(left.value, ast.Attribute) and isinstance(left.value.value, ast.Name) and left.value.value.id == 'self':
                    before = types[left.value.attr]
                    if before[0] != 'map' or infer(left.slice) is not str or typ not in (str, int) or before[1] not in (None, typ):
                        raise ValueError('Output map assignment is unsafe')
                    types[left.value.attr] = ('map', typ)
                else: raise ValueError('Graph or aliased assignment')
            elif kind == 'if':
                if infer(ast.parse(item['condition'], mode='eval').body) not in (str, int, bool): raise ValueError('Custom output branch')
                previous = dict(env)
                check(item['body'])
                # Values introduced only in a conditional branch are not definite.
                env.clear(); env.update(previous)
            elif kind == 'for':
                env[item['target']] = ('node', node_type)
                previous = dict(env)
                check(item['body'])
                env.clear(); env.update(previous)
            elif kind == 'append':
                expr = ast.parse(item['value'], mode='eval').body
                typ = infer(expr.args[0])
                if types[item['field']][0] != 'list' or type(typ) is not tuple or typ[0] != 'record':
                    raise ValueError('Output append must target a private list of plain records')
                types[item['field']] = ('list', typ)
            elif kind == 'sort':
                item_type = types[item['field']][1]
                if type(item_type) is not tuple or item_type[0] != 'record': raise ValueError('Unproved sort list')
                record_type = item_type[1]
                if not _plain_scalar_field(record_type, item['key'], (str, 'str')): raise ValueError('Custom sort key')
            elif kind == 'report':
                infer(ast.parse(item['value'], mode='eval').body)
    check(certificate['effects'])
    check(certificate.get('exits', []))
    return {name: typ.__name__ for name, typ in field_types.items()}


def compile_tree_sql(certificate, gated):
    import jaclang.sql as q
    from jaclang.runtime.ttg_sql import _BuildColumns, _select, _all, _either, _cmp
    from jaclang.runtime.ttg_fusion_sql import _native_anchors, _fusion_match, _visibility
    cols = _BuildColumns()
    actor = dict(uuid=q.slot('actor_uuid', q.uuid_type()), text=q.slot('actor_text', q.text_type())) if gated else None
    walk = q.cte_ref([q.field('origin_id', q.uuid_type())])
    anchor = _select(None, [('origin_id', q.slot('origin', q.uuid_type()))])
    edge_type, target_type, direction = certificate['hops'][0]

    def hop(origin):
        # Same native one-hop endpoint, direction, ancestry and ACL semantics.
        # Keep target properties on this join: joining anchors again outside a
        # lateral path allowed PostgreSQL to repeat that path for every target.
        edge, node = _native_anchors(), _native_anchors()
        forward = _cmp(cols.col(edge, 'src'), origin)
        backward = _cmp(cols.col(edge, 'dst'), origin)
        if direction not in (1, 2, 3):
            raise ValueError('Unsupported native hop direction')
        direction_test = _either([forward, backward]) if direction == 3 else _either([
            backward if direction == 1 else forward,
            _all([cols.col(edge, 'undirected'), forward if direction == 1 else backward])])
        edge_test = _all([_cmp(cols.col(edge, 'kind'), q.text('EdgeAnchor')),
                          direction_test,
                          _fusion_match(cols, cols.col(edge, 'arch_type'), edge_type, True)])
        endpoint = q.case_nullable([(forward, cols.col(edge, 'dst'))], cols.col(edge, 'src'))
        node_test = _all([_cmp(cols.col(node, 'id'), endpoint),
                          _cmp(cols.col(node, 'kind'), q.text('NodeAnchor')),
                          _fusion_match(cols, cols.col(node, 'arch_type'), target_type, True),
                          _visibility(cols, node, actor)])
        return edge, node, edge_test, node_test

    edge, node, edge_test, node_test = hop(cols.col(walk, 'origin_id'))
    props = q.json_get(cols.col(node, 'props'), q.text('archetype'))
    terms = [_cmp(cols.col(node, 'arch_type'), q.text(certificate['source_type'])),
             _cmp(cols.col(node, 'arch_module'), q.slot('node_module', q.text_type()))]
    for name, op, value in certificate['predicates']:
        terms.extend([_cmp(q.json_kind(q.json_get(props, q.text(name))), q.text('boolean')),
                      _cmp(q.json_text(props, q.text(name)), q.text('true' if value else 'false'))])
    step = _select(walk, [('origin_id', cols.col(node, 'id'))],
                   joins=[q.inner_join(edge, edge_test), q.inner_join(node, node_test)],
                   predicate=_all(terms))
    # UNION deduplicates fetch origins only; native enqueue multiplicity remains.
    q.define_cte(walk, q.union(anchor, step), recursive=True)

    edge, node, edge_test, node_test = hop(cols.col(walk, 'origin_id'))
    order = [q.asc(cols.col(edge, 'seq')), q.asc(cols.col(edge, 'id'))]
    # Unfiltered candidate rows remain visible for the existing all-row proof.
    # In particular malformed predicate properties cannot silently become empty.
    paths = q.optional_source(_select(edge,
        [('target_id', cols.col(node, 'id')), ('edge_id', cols.col(edge, 'id')),
         ('arch_type', cols.col(node, 'arch_type')), ('arch_module', cols.col(node, 'arch_module')),
         ('ord', q.row_number(order_by=order)), ('arity', q.over(q.count())),
         ('target_props', cols.col(node, 'props'))],
        joins=[q.inner_join(node, node_test)], predicate=edge_test).as_source(lateral=True))
    source = _native_anchors()
    body = _select(walk,
        [('origin_id', cols.col(walk, 'origin_id'))] + cols.pick(paths, ['target_id','edge_id','arch_type','arch_module','ord','arity']) +
        [('source_props', cols.col(source, 'props')), ('target_props', cols.col(paths, 'target_props')),
         ('source_type', cols.col(source, 'arch_type')), ('source_module', cols.col(source, 'arch_module'))],
        joins=[q.inner_join(source, _cmp(cols.col(source, 'id'), cols.col(walk, 'origin_id'))),
               q.left_join(paths, q.boolean(True))])
    return q.compile_sql(q.ordered(body,
        [q.asc(q.output(q.field('origin_id',q.uuid_type()))), q.asc(q.output(q.field('ord',q.nullable(q.int64_type()))))],
        limit=q.slot('row_limit',q.int64_type())))


def compile_tree_templates(certificate):
    from jaclang.runtime.ttg_templates import sql_descriptor
    from jaclang.runtime.graph_query import GraphQuery,QHop,QPred
    from jaclang.data.sqlcompile import compile_query
    cert = dict(certificate, templates={}, native={})
    et, nt, direction = certificate['hops'][0]
    for gated in (False, True):
        mode = 'gated' if gated else 'open'
        cert['templates'][mode] = sql_descriptor(compile_tree_sql(certificate,gated))
        query = GraphQuery([], hops=[QHop(dir=direction, edge=type(et,(object,),{}), nd=type(nt,(object,),{}),
                                      preds=[QPred(field=f,op=o,value=v) for f,o,v in certificate['predicates']])]).visit()
        descriptors = {}
        for typed in (False,True):
            compiled=compile_query(query,1,acl_root=str(UUID(int=1)) if gated else None,include_type=typed)
            params=dict(compiled.params);params.pop('origin')
            slots=[['origin','text[]',False]]
            for name in list(params):
                if name.endswith('amu') or name.endswith('amt'):
                    params.pop(name);slots.append([name,'text',False])
            descriptors['typed' if typed else 'pairs']=dict(sql=compiled.sql,params=params,slots=slots,nonnegative_slots=[])
        cert['native'][mode]=descriptors
    return cert


def resolve_output_tree(mem, graph, wlk, scope, point, current, pending, user_root, max_rows, metrics, cache_token, cert):
    from jaclang.runtime.ttg_regions import region_coverage_key
    from jaclang.runtime.ttg_continuation import continuation_type
    from jaclang.runtime.ttg_frontier import template_type_matches
    from jaclang.runtime.ttg_dependencies import _trace_entry_handlers,_trace_node_effects,_trace_safe_storage,TraceEffects
    from jaclang.runtime.archetype import NodeArchetype,NodeAnchor
    from jaclang.runtime.graph_query import GraphQuery,QHop,QPred
    from jaclang.runtime.graph_walk import access_gated
    from jaclang.data.query_planner import _acl_pushdown_root
    from jaclang.runtime.ttg_templates import bind_template,publish_paths
    def decline(reason):
        metrics['region_fallbacks']=metrics.get('region_fallbacks',0)+1
        metrics['region_fallback_reason']=reason
        counts=metrics.setdefault('region_fallback_reasons',{});counts[reason]=counts.get(reason,0)+1
        return None
    source=continuation_type(wlk,cert['source_type']);et=continuation_type(wlk,cert['hops'][0][0])
    if source is None or et is None or not template_type_matches(source,cert['source_type']) or not template_type_matches(et,cert['hops'][0][0]):
        return decline('Output tree type binding is unresolved')
    if current['node_type'] is not source or not issubclass(source,NodeArchetype) or not _trace_safe_storage(source) or source.__getattribute__ is not NodeArchetype.__getattribute__:
        return decline('Output tree has custom node dispatch/storage')
    effects=TraceEffects();handlers=_trace_entry_handlers(graph,source,effects);_trace_node_effects(graph,source,effects)
    if effects.unknown or handlers != [cert['ability']]:
        return decline('Output tree entry effects differ')
    if sorted(cb.name for cb in type(wlk)._jac_exit_funcs_) != sorted(cert.get('exit_abilities', [])):
        return decline('Output tree exit dispatch differs')
    # Walker exits run after the queue is drained. Node entry/exit hooks are
    # covered by _trace_node_effects and must be absent for this certificate.
    query=GraphQuery([],hops=[QHop(dir=cert['hops'][0][2],edge=et,nd=source,
             preds=[QPred(field=f,op=o,value=v) for f,o,v in cert['predicates']])]).visit()
    with mem._lock:
        mem.read_barrier()
        actor=_acl_pushdown_root(query,1,mem)
        if access_gated() and actor is None:return decline('Output tree ACL is unproved')
        key=region_coverage_key(graph,scope,wlk,cert['ability'],current['id'],user_root,cache_token)
        if mem.query_cache_get(key) is not None:
            metrics['region_reuses']=metrics.get('region_reuses',0)+1
            return dict(paths=[],payload=[],reused=True,kind='output_tree')
        if pending or scope.ignores:return decline('Output tree has pending/ignored work')
        try: field_types=validate_effects(cert,wlk,source,mem,scope,[user_root])
        except (ValueError,KeyError,TypeError,AttributeError) as error:
            return decline('Output tree effect proof: '+str(error))
        values=dict(origin=UUID(str(current['id'])),row_limit=max_rows+1,node_module=source.__module__)
        if actor is not None:values.update(actor_uuid=UUID(actor),actor_text=actor)
        mode='gated' if actor is not None else 'open'
        compiled=bind_template(cert['templates'][mode],values)
        rows=mem.store.rows(compiled.sql,compiled.params)
        metrics['queries']+=1;metrics['region_queries']=metrics.get('region_queries',0)+1
        if not rows or len(rows)>max_rows:return decline('Output tree row budget/origin missing')
        expected_types={'str':str,'int':int,'bool':bool}
        def properties(raw):
            value=json.loads(raw) if type(raw) is str else raw
            props=value['archetype']
            if type(props) is not dict or any(type(props.get(name)) is not expected_types[typ] for name,typ in field_types.items()):
                raise ValueError('Malformed ordinary node property')
            return props
        groups={};arities={};unfiltered={}
        try:
            for row in rows:
                uid=UUID(str(row[0]));pairs=groups.setdefault(uid,[])
                if row[9]!=source.__name__ or row[10]!=source.__module__:raise ValueError('Source dispatch mismatch')
                properties(row[7])
                cached=mem.__mem__.get(uid)
                if cached is not None and cached.is_populated():
                    if type(cached) is not NodeAnchor or type(cached.archetype) is not source or vars(cached.archetype).get('__jac__') is not cached:
                        raise ValueError('Cached source storage mismatch')
                    if any(type(vars(cached.archetype).get(name)) is not expected_types[typ] for name,typ in field_types.items()):
                        raise ValueError('Cached node field differs from declaration')
                if row[1] is None:
                    if uid in arities or any(v is not None for v in row[2:7]):raise ValueError('Invalid empty marker')
                    arities[uid]=0;unfiltered[uid]=0
                    continue
                count=int(row[6]);order=unfiltered.get(uid,0)+1
                if count<=0 or int(row[5])!=order or arities.get(uid,count)!=count:raise ValueError('Incomplete path order')
                arities[uid]=count;unfiltered[uid]=order
                if row[3]!=source.__name__ or row[4]!=source.__module__:raise ValueError('Target dispatch mismatch')
                props=properties(row[8])
                if all(props[f] is v for f,o,v in cert['predicates']):
                    pairs.append((UUID(str(row[1])),UUID(str(row[2])),row[3],row[4]))
            if any(unfiltered[k]!=arities[k] for k in groups):raise ValueError('Truncated output path')
            origin=UUID(str(current['id']))
            expected={origin}|{p[0] for pairs in groups.values() for p in pairs}
            if set(groups)!=expected:raise ValueError('Tree closure missing or foreign origins')
            # Reject cycles without assuming depth == total visited count.
            grey=set();black=set();stack=[(origin,False)]
            while stack:
                uid,leaving=stack.pop()
                if leaving:grey.remove(uid);black.add(uid);continue
                if uid in grey:raise ValueError('Output tree cycle')
                if uid in black:continue
                grey.add(uid);stack.append((uid,True))
                stack.extend((p[0],False) for p in reversed(groups[uid]))
            if black != set(groups):raise ValueError('Disconnected tree origins')
        except (ValueError,TypeError,KeyError,IndexError) as error:
            return decline('Output tree row proof: '+str(error))
        staged=[(query,uid,pairs,cert['native'][mode]) for uid,pairs in groups.items()]
        if not publish_paths(mem,staged):return decline('Output tree atomic native cache publication failed')
        paths=[dict(event=point,origin=str(uid),ids=[str(p[0]) for p in pairs]) for uid,pairs in groups.items()]
        for uid in groups:mem.query_cache_put(region_coverage_key(graph,scope,wlk,cert['ability'],uid,user_root,cache_token),True)
        metrics['region_cache_paths']=metrics.get('region_cache_paths',0)+len(groups)
        metrics['cache_paths']+=len(groups);metrics['cache_empty_paths']+=sum(not p for p in groups.values())
        metrics['region_origins']=metrics.get('region_origins',0)+len(groups)
        metrics['regions'].append(dict(kind='output_tree',compiled=True,paths=paths,checkpoint=point))
        return dict(paths=paths,payload=[p for pairs in groups.values() for p in pairs],reused=False,kind='output_tree')
