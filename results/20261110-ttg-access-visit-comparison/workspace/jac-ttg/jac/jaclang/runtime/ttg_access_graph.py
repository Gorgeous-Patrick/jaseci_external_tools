"""Experimental, opt-in Access/Visit dependency graph over the real Jac AST.

This is an analysis artifact, not an execution plan. It does not change hooks,
SQL, queues or prefetch admission. Ordinary calls and unsupported constructs
remain explicit unknowns; absence of a local Visit is not an interprocedural
non-visit proof. Graph expressions are the only Access nodes in version 1.
"""

import argparse
import hashlib
import json
from pathlib import Path

from jaclang.compiler.frontend import unitree as u


def text(node):
    if node is None:
        return ""
    if isinstance(node, u.Token):
        return node.value
    return " ".join(text(child) for child in node.kid)


def children(node):
    return [c for c in node.kid if not isinstance(c, u.Token) or isinstance(c, u.Expr)]


class AccessGraphBuilder:
    def __init__(self):
        self.nodes = []
        self.edges = []
        self.functions = {}
        self.scope = ""
        self.controls = []
        self.unknowns = []

    def edge(self, source, target, kind, label=""):
        edge = dict(source=source, target=target, kind=kind, label=label)
        if edge not in self.edges:
            self.edges.append(edge)

    def node(self, kind, ast, **metadata):
        eid = len(self.nodes)
        self.nodes.append(dict(id=eid, kind=kind, function=self.scope,
                               file=ast.loc.mod_path,
                               line=ast.loc.first_line,
                               column=getattr(ast.loc, "col_start", 0),
                               syntax=text(ast), **metadata))
        for source, label in self.controls:
            self.edge(source, eid, "control", label)
        return eid

    def input(self, ast, env, name=None):
        name = name or text(ast)
        if name not in env:
            env[name] = self.node("Input", ast, name=name)
        return env[name]

    def unknown(self, ast, env, reason):
        # Unknown effects may read/mutate aliased locals. Preserve the boundary,
        # not an invented empty effect summary.
        eid = self.node("Unknown", ast, reason=reason)
        for name, source in env.items():
            self.edge(source, eid, "possible_effect", name)
        self.unknowns.append(eid)
        return eid

    def expression(self, ast, env):
        if isinstance(ast, (u.Name, u.SpecialVarRef)):
            return self.input(ast, env)
        if isinstance(ast, u.AtomUnit):
            return self.expression(ast.value, env)
        if isinstance(ast, u.EdgeRefTrailer):
            chain = ast.chain
            explicit = bool(chain and not isinstance(chain[0], (u.EdgeOpRef, u.FilterCompr)))
            origin = self.expression(chain[0], env) if explicit else self.input(ast, env, "here")
            predicates = []
            for item in chain:
                filters = [item] if isinstance(item, u.FilterCompr) else []
                if isinstance(item, u.EdgeOpRef) and item.filter_cond is not None:
                    filters.append(item.filter_cond)
                for filt in filters:
                    for comparison in (filt.compares or []):
                        # The LHS denotes a candidate property, not a local
                        # variable. RHS expressions supply external inputs.
                        if isinstance(comparison, u.CompareExpr):
                            for operand in comparison.rights:
                                predicates.append(self.expression(operand, env))
                        else:
                            predicates.append(self.unknown(comparison, env, "Compound graph predicate not modeled"))
            eid = self.node("Access", ast, access_kind="graph_query",
                            origin=self.nodes[origin]["syntax"],
                            edges_only=ast.edges_only, execution="conditional")
            self.edge(origin, eid, "data", "origin")
            for source in predicates:
                self.edge(source, eid, "data", "predicate input")
            return eid
        if isinstance(ast, u.FuncCall):
            target = self.expression(ast.target, env)
            args = [self.expression(arg, env) for arg in (ast.params or [])]
            eid = self.unknown(ast, env, "Call effects/return aliases require a callee summary")
            self.nodes[eid]["kind"] = "Call"
            self.edge(target, eid, "data", "callee")
            for source in args:
                self.edge(source, eid, "data", "argument")
            return eid
        if isinstance(ast, u.AtomTrailer):
            base = self.expression(ast.target, env)
            if ast.is_attr:
                eid = self.node("Compute", ast, operation="attribute read; not Access v1")
                self.edge(base, eid, "data", "receiver")
                return eid
            index = self.expression(ast.right, env)
            eid = self.node("Compute", ast, operation="subscript; possible identity selection")
            self.edge(base, eid, "value", "selected element")
            self.edge(index, eid, "data", "index")
            return eid
        if isinstance(ast, u.ListCompr):
            local = dict(env)
            old_controls = self.controls
            self.controls = list(old_controls)
            for clause in ast.compr:
                collection = self.expression(clause.collection, local)
                iteration = self.node("Iteration", clause, execution="zero or more")
                self.edge(collection, iteration, "data", "collection")
                self.controls.append((iteration, "each element"))
                binding = self.node("Assign", clause.target, name=text(clause.target))
                self.edge(collection, binding, "value", "element")
                local[text(clause.target)] = binding
                for condition in clause.conditional or []:
                    cond = self.expression(condition, local)
                    branch = self.node("Branch", condition)
                    self.edge(cond, branch, "data", "condition")
                    self.controls.append((branch, "true"))
            out = self.expression(ast.out_expr, local)
            self.controls = old_controls
            eid = self.node("Compute", ast, operation="comprehension result")
            self.edge(out, eid, "value", "output elements")
            return eid
        if isinstance(ast, u.Token):
            return self.node("Constant", ast)
        deps = [self.expression(c, env) for c in children(ast)]
        eid = self.node("Compute", ast, operation=type(ast).__name__)
        for source in deps:
            self.edge(source, eid, "data", "operand")
        return eid

    def block(self, statements, env):
        for ast in statements:
            if isinstance(ast, u.Assignment) and ast.value is not None:
                value = self.expression(ast.value, env)
                if len(ast.target) != 1 or not isinstance(ast.target[0], u.Name) or ast.aug_op:
                    eid = self.unknown(ast, env, "Aliased/augmented assignment not modeled")
                    self.edge(value, eid, "data", "assigned expression")
                    continue
                name = ast.target[0].value
                eid = self.node("Assign", ast, name=name)
                self.edge(value, eid, "value", name)
                env[name] = eid
            elif isinstance(ast, u.VisitStmt):
                value = self.expression(ast.target, env)
                eid = self.node("Visit", ast, operation="enqueue; not actual node entry")
                self.edge(value, eid, "value", "visit targets")
                if ast.insert_loc is not None or ast.else_body is not None:
                    self.unknown(ast, env, "Visit insertion/else semantics not modeled")
            elif isinstance(ast, u.IfStmt):
                condition = self.expression(ast.condition, env)
                eid = self.node("Branch", ast.condition)
                self.edge(condition, eid, "data", "condition")
                saved = self.controls
                self.controls = saved + [(eid, "true")]
                yes = self.block(ast.body, dict(env))
                self.controls = saved + [(eid, "false")]
                other = ast.else_body
                no = self.block([other] if isinstance(other, u.IfStmt) else
                                (other.body if other else []), dict(env))
                self.controls = saved
                for name in sorted(yes.keys() | no.keys()):
                    left, right = yes.get(name), no.get(name)
                    present = left if left is not None else right
                    if (left is None or right is None) and self.nodes[present]["kind"] == "Input":
                        # Reading an external input in only one branch does not
                        # conditionally define that input.
                        env[name] = present
                        continue
                    if left == right:
                        env[name] = left
                        continue
                    phi = self.node("Phi", ast.condition, name=name)
                    for source, label in [(left, "true"), (right, "false")]:
                        if source is None:
                            source = self.node("Input", ast.condition, name=name,
                                               unresolved="possibly unbound")
                        self.edge(source, phi, "value", label)
                    self.edge(eid, phi, "control", "merge")
                    env[name] = phi
            elif isinstance(ast, (u.ReportStmt, u.ReturnStmt)):
                value = self.expression(ast.expr, env) if ast.expr is not None else None
                eid = self.node("Report" if isinstance(ast, u.ReportStmt) else "Return", ast)
                if value is not None:
                    self.edge(value, eid, "value", "output")
                if isinstance(ast, u.ReturnStmt):
                    # Keep subsequent syntactic nodes, but never claim complete
                    # control-flow safety across early termination in this v1.
                    self.unknowns.append(eid)
            elif isinstance(ast, u.DisengageStmt):
                eid = self.node("Cancel", ast)
                self.unknowns.append(eid)
            elif isinstance(ast, u.InForStmt):
                collection = self.expression(ast.collection, env)
                iteration = self.node("Iteration", ast.collection, execution="zero or more")
                self.edge(collection, iteration, "data", "collection")
                saved = self.controls
                self.controls = saved + [(iteration, "each element")]
                local = dict(env)
                binding = self.node("Assign", ast.target, name=text(ast.target))
                self.edge(collection, binding, "value", "element")
                local[text(ast.target)] = binding
                after = self.block(ast.body, local)
                self.controls = saved
                boundary = self.unknown(ast, after, "Loop-carried state/else semantics not modeled")
                # Invalidate loop-written locals instead of falsely exporting
                # the last syntactic assignment as a definite reaching value.
                for name, value in after.items():
                    if env.get(name) != value:
                        env[name] = boundary
            elif isinstance(ast, u.ExprStmt):
                self.expression(ast.expr, env)
            else:
                # Scan expressions so accesses inside unsupported statements
                # remain visible, while explicitly withholding completeness.
                for child in children(ast):
                    self.expression(child, env)
                self.unknown(ast, env, "Statement/control effects not modeled")
        return env

    def function(self, ability, owner, implementation=None):
        self.scope = owner + "." + ability.py_resolve_name()
        if self.scope in self.functions:
            raise ValueError("Duplicate function scope: " + self.scope)
        self.controls = []
        self.unknowns = []
        start = self.node("Entry", ability.signature or ability)
        body = implementation.body if implementation is not None else ability.body
        if isinstance(body, u.ImplDef):
            body = body.body
        if not isinstance(body, list):
            self.unknown(ability, {}, "External/missing function body")
        else:
            self.block(body, {})
        self.functions[self.scope] = dict(entry=start, unknowns=list(self.unknowns),
                                         kind="ability" if isinstance(ability.signature, u.EventSignature) else "method")

    def result(self):
        successors = {}
        for edge in self.edges:
            if edge["kind"] == "value":
                successors.setdefault(edge["source"], []).append(edge["target"])
        for node in self.nodes:
            if node["kind"] != "Access":
                continue
            work = list(successors.get(node["id"], []))
            seen = set()
            while work:
                eid = work.pop()
                if eid in seen:
                    continue
                seen.add(eid)
                work.extend(successors.get(eid, []))
            targets = sorted(i for i in seen if self.nodes[i]["kind"] == "Visit")
            node["local_visit_targets"] = targets
            node["visit_flow"] = "may_reach_local_visit" if targets else "no_local_value_flow_to_visit"
            # Exported returns, calls, unsupported syntax and descriptors need
            # interprocedural/effect/type reasoning before any absence proof.
            node["global_nonvisit_proven"] = False
        return dict(version=1, kind="experimental_access_visit_graph",
                    execution_enabled=False, nodes=self.nodes, edges=self.edges,
                    functions=self.functions,
                    limitations=["Local syntactic value/control dependencies, not execution counts or SQL regions",
                                 "Call summaries, heap aliasing, descriptors, dispatch and queue execution are unresolved",
                                 "No local Visit flow does not prove absence of Visit through a caller/alias",
                                 "Only graph expressions are Access nodes; property reads and jobj are not Access v1"])


def analyze_access_visits(module):
    builder = AccessGraphBuilder()
    implementations = {}
    for item in module.body:
        if isinstance(item, u.ImplDef):
            key = module.name + "." + ".".join(text(part) for part in item.target)
            if key in implementations:
                raise ValueError("Duplicate implementation: " + key)
            implementations[key] = item
    def scan(items, owner):
        for item in items:
            if isinstance(item, u.Archetype) and isinstance(item.body, list):
                scan(item.body, owner + "." + item.name.value)
            elif isinstance(item, u.Ability):
                key = owner + "." + item.py_resolve_name()
                builder.function(item, owner, implementations.pop(key, None))
    scan(module.body, module.name)
    result = builder.result()
    result["unmatched_implementations"] = sorted(implementations)
    return result


def analyze_source(source, filename="access_visit.jac", annexes=()):
    from jaclang.compiler.frontend.parser.frontend import parse
    module, failed = parse(source, filename)
    if failed:
        raise ValueError("Jac parse failed: " + filename)
    from jaclang.compiler.passes.annex_weave import merge_annex_into
    source_refs = []
    for annex_source, annex_path in annexes:
        annex, failed = parse(annex_source, annex_path)
        if failed:
            raise ValueError("Jac parse failed: " + annex_path)
        merge_annex_into(module, annex)
        source_refs.append(dict(path=annex_path, sha256=hashlib.sha256(annex_source.encode()).hexdigest()))
    result = analyze_access_visits(module)
    result["source"] = dict(path=filename, sha256=hashlib.sha256(source.encode()).hexdigest())
    result["annexes"] = source_refs
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--impl", type=Path, action="append", default=[])
    args = parser.parse_args()
    result = analyze_source(args.source.read_text(), str(args.source.resolve()),
                            [(p.read_text(), str(p.resolve())) for p in args.impl])
    args.output.write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    main()
