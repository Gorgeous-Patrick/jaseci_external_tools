import logging;
import sys;
import jaclang.compiler.frontend.unitree as uni;
import from uuid { UUID }

import from jaclang.compiler.frontend.constant { Tokens as Tok }
import from jaclang.runtime.archetype { NodeAnchor, NodeArchetype, VisitType }
import from jaclang.runtime.graph_query { QHop }
import from jaclang.runtime.ttg_sql {
    compile_specialized,
    compile_layered,
    compile_undirected_probe
}
import from jaclang.runtime.topology_index { TopologyIndex, ingest_topology_rows }

glob logger = logging.getLogger(__name__),
     _runtime_type_cache: dict[str, type] = {};

@classmethod
impl JacTTGGenerator._resolve_type_name(
    cls: type[JacTTGGenerator], ref: (type | str | None)
) -> (str | None) {
    if ref is None {
        return None;
    }
    if isinstance(ref, str) {
        return ref;
    }
    return ref.__name__;
}

@classmethod
impl JacTTGGenerator._runtime_type_for_name(
    cls: type[JacTTGGenerator], warch: any, name: (str | type | None)
) -> (type | None) {
    if name is None {
        return None;
    }
    if isinstance(name, `type) {
        return name;
    }
    key = str(name);
    if key in _runtime_type_cache {
        return _runtime_type_cache[key];
    }
    import from jaclang.runtime.runtime { JacRuntime }
    modules: list = [];
    wcls = `type(warch) if warch is not None else None;
    module_name = str(getattr(wcls, "__module__", "")) if wcls is not None else "";
    if module_name {
        modules.append(JacRuntime.loaded_modules.get(module_name));
        modules.append(sys.modules.get(module_name));
    }
    modules.extend(list(JacRuntime.loaded_modules.values()));
    for mod in modules {
        if mod is None {
            continue;
        }
        typ = getattr(mod, key, None);
        if isinstance(typ, `type) {
            _runtime_type_cache[key] = typ;
            return typ;
        }
    }
    fake = `type(key, (), {});
    _runtime_type_cache[key] = fake;
    return fake;
}

@classmethod
impl JacTTGGenerator._find_walker_ast_node(
    cls: type[JacTTGGenerator], warch_cls: type
) -> (uni.Archetype | None) {
    import from pathlib { Path }
    import from jaclang.runtime.runtime { JacRuntime }
    program = JacRuntime.get_program();
    module_name = warch_cls.__module__;
    class_name = warch_cls.__name__;
    py_module = JacRuntime.loaded_modules.get(module_name);
    if py_module is None {
        py_module = sys.modules.get(module_name);
    }
    if py_module is None {
        return None;
    }
    file_path = py_module?.__file__;
    if file_path is None {
        return None;
    }
    resolved = str(Path(str(file_path)).resolve());
    ast_module = program.find_module(resolved);
    if ast_module is None and resolved.endswith(".jac") {
        try {
            ast_module = program.compile(resolved, no_cgen=True, symtab_ir_only=True);
        } except Exception as e {
            logger.debug(f"TTG AST compile fallback failed for {resolved}: {e}");
            return None;
        }
    }
    if ast_module is None {
        return None;
    }
    for arch in ast_module.get_all_sub_nodes(uni.Archetype) {
        if (arch.arch_type.name == Tok.KW_WALKER and arch.name.value == class_name) {
            return arch;
        }
    }
    return None;
}

@classmethod
impl JacTTGGenerator._resolve_archetype(
    cls: type[JacTTGGenerator], scope_src: any, name: str
) -> (uni.Archetype | None) {
    import from typing { cast }
    scope = scope_src.find_parent_of_type(uni.UniScopeNode);
    if scope is None {
        return None;
    }
    result = scope.lookup(name);
    if result is None {
        return None;
    }
    return cast(uni.Archetype | None, result.decl.find_parent_of_type(uni.Archetype));
}

@classmethod
impl JacTTGGenerator._extract_edge_step(
    cls: type[JacTTGGenerator], scope: any, item: any
) -> tuple[str | None, str | None, int] {
    edge_type_name: (str | None) = None;
    node_filter_name: (str | None) = None;
    direction = 2;
    if isinstance(item, uni.EdgeOpRef) {
        fc = item?.filter_cond;
        if fc is not None {
            ft = fc?.f_type;
            if ft is not None {
                type_name: (str | None) = None;
                if isinstance(ft, uni.Name) {
                    type_name = ft.value;
                } else {
                    names = ft.get_all_sub_nodes(uni.Name);
                    if len(names) > 0 {
                        type_name = names[0].value;
                    }
                }
                if type_name is not None {
                    edge_arch = cls._resolve_archetype(scope, type_name);
                    if edge_arch is not None {
                        edge_type_name = edge_arch.name.value;
                    }
                }
            }
        }
        edge_dir = item?.edge_dir;
        try {
            direction = int(edge_dir.value);
        } except Exception {
            dir_name = getattr(edge_dir, 'name', '');
            if 'IN' in str(dir_name) {
                direction = 1;
            } elif 'ANY' in str(dir_name) {
                direction = 3;
            } else {
                direction = 2;
            }
        }
    } elif isinstance(item, uni.FilterCompr) {
        ft = item?.f_type;
        if ft is not None {
            type_name: (str | None) = None;
            if isinstance(ft, uni.Name) {
                type_name = ft.value;
            } else {
                names = ft.get_all_sub_nodes(uni.Name);
                if len(names) > 0 {
                    type_name = names[0].value;
                }
            }
            if type_name is not None {
                node_arch = cls._resolve_archetype(scope, type_name);
                if node_arch is not None {
                    node_filter_name = node_arch.name.value;
                }
            }
        }
    }
    return (edge_type_name, node_filter_name, direction);
}

@classmethod
impl JacTTGGenerator._edge_ref_explicit_origin_name(
    cls: type[JacTTGGenerator], trailer: any
) -> (str | None) {
    chain_items = getattr(trailer, 'chain', []);
    if len(chain_items) == 0 {
        return None;
    }
    first = chain_items[0];
    if isinstance(first, uni.EdgeOpRef) or isinstance(first, uni.FilterCompr) {
        return None;
    }
    return cls._ast_type_name(first);
}


@classmethod
impl JacTTGGenerator._edge_ref_origin_is_current(
    cls: type[JacTTGGenerator], trailer: any
) -> bool {
    origin_name = cls._edge_ref_explicit_origin_name(trailer);
    if origin_name is None or origin_name == "" {
        return True;
    }
    return origin_name in ("here", "self");
}


@classmethod
impl JacTTGGenerator._extract_chains_from_trailer(
    cls: type[JacTTGGenerator], scope: any, trailer: any
) -> list[tuple[str | None, str | None, int]] {
    import from typing { cast }
    edge_chain: list[tuple[str | None, str | None, int]] = [];
    origin_name = cls._edge_ref_explicit_origin_name(trailer);
    if (not cls._edge_ref_origin_is_current(trailer) and origin_name != "root") {
        logger.debug(f"TTG skips edge ref with non-current origin {origin_name!r}");
        return edge_chain;
    }
    chain_items = getattr(trailer, 'chain', []);
    for item in chain_items {
        step = cls._extract_edge_step(scope, item);
        if step[0] is not None or isinstance(item, uni.EdgeOpRef) {
            edge_chain.append(step);
        } elif step[1] is not None {
            if len(edge_chain) > 0 {
                prev: tuple[str | None, str | None, int] = edge_chain[-1];
                prev_dir: int = cast(int, prev[2]);
                edge_chain[-1] = (prev[0], step[1], prev_dir);
            }
        }
    }
    if len(edge_chain) == 0 {
        edge_refs = trailer.get_all_sub_nodes(uni.EdgeOpRef);
        for edge_ref in edge_refs {
            step = cls._extract_edge_step(scope, edge_ref);
            edge_chain.append(step);
        }
    }
    return edge_chain;
}

def _ttg_origin_name_for_visit(origin_name: (str | None)) -> str {
    return "root" if origin_name == "root" else "";
}


def _ttg_from_type_for_visit(
    origin_name: (str | None), default_type: (str | None)
) -> (str | None) {
    return "Root" if origin_name == "root" else default_type;
}


@classmethod
impl JacTTGGenerator._extract_refs_from_body(
    cls: type[JacTTGGenerator], body: any
) -> list[list[tuple[str | None, str | None, int]]] {
    result: list[list[tuple[str | None, str | None, int]]] = [];
    trailers = body.get_all_sub_nodes(uni.EdgeRefTrailer);
    for trailer in trailers {
        chain = cls._extract_chains_from_trailer(body, trailer);
        if len(chain) > 0 {
            result.append(chain);
        }
    }
    return result;
}

@classmethod
impl JacTTGGenerator._ability_sub_nodes(
    cls: type[JacTTGGenerator], ability: uni.Ability, node_type: type
) -> list {
    result = ability.get_all_sub_nodes(node_type);
    body = ability?.body;
    if isinstance(body, uni.ImplDef) {
        result.extend(body.get_all_sub_nodes(node_type));
    }
    return result;
}

@classmethod
impl JacTTGGenerator._ast_type_name(
    cls: type[JacTTGGenerator], expr: (uni.UniNode | None)
) -> (str | None) {
    if expr is None {
        return None;
    }
    if isinstance(expr, uni.Name) {
        return expr.value;
    }
    if isinstance(expr, uni.Token) {
        return expr.value;
    }
    if isinstance(expr, uni.BuiltinType) {
        return expr?.sym_name or str(getattr(expr, "value", ""));
    }
    if isinstance(expr, uni.AtomTrailer) {
        attrs = expr.as_attr_list;
        if attrs {
            last = attrs[-1];
            if isinstance(last, uni.Name) {
                return last.value;
            }
            if isinstance(last, uni.AstSymbolNode) {
                return last.sym_name;
            }
        }
    }
    return str(getattr(expr, "value", getattr(expr, "sym_name", "")));
}

@classmethod
impl JacTTGGenerator._call_target_symbol(
    cls: type[JacTTGGenerator], call: uni.FuncCall
) -> (uni.Symbol | None) {
    if isinstance(call.target, uni.Name) {
        sym = call.target.sym;
        if not sym and call.target.sym_tab {
            sym = call.target.sym_tab.lookup(call.target.sym_name, deep=True);
        }
        return sym;
    }
    if isinstance(call.target, uni.AtomTrailer) {
        attrs = call.target.as_attr_list;
        if attrs {
            last = attrs[-1];
            if isinstance(last, uni.AstSymbolNode) and last.sym {
                return last.sym;
            }
        }
    }
    return None;
}

@classmethod
impl JacTTGGenerator._resolve_called_ability(
    cls: type[JacTTGGenerator], call: uni.FuncCall
) -> (uni.Ability | None) {
    sym = cls._call_target_symbol(call);
    if sym and sym.defn {
        defn_node = sym.defn[0];
        if isinstance(defn_node, uni.Ability) {
            return defn_node;
        }
        if defn_node.parent and isinstance(defn_node.parent, uni.Ability) {
            return defn_node.parent;
        }
    }
    method_name: (str | None) = None;
    target = call.target;
    if isinstance(target, uni.AtomTrailer) {
        names = target.get_all_sub_nodes(uni.Name);
        if len(names) > 0 {
            method_name = names[-1].value;
        }
    } elif isinstance(target, uni.NameAtom) {
        method_name = target.sym_name;
    }
    if method_name is None {
        return None;
    }
    module = call.find_parent_of_type(uni.Module);
    if module is None {
        return None;
    }
    for arch in module.get_all_sub_nodes(uni.Archetype) {
        for method in arch.get_all_sub_nodes(uni.Ability) {
            if method.py_resolve_name() == method_name {
                return method;
            }
        }
    }
    return None;
}

@classmethod
impl JacTTGGenerator._single_param_node_type(
    cls: type[JacTTGGenerator], ability: uni.Ability
) -> (str | None) {
    if not isinstance(ability.signature, uni.FuncSignature) {
        return None;
    }
    params = ability.signature.get_parameters();
    if len(params) != 1 {
        return None;
    }
    tag = params[0].type_tag;
    if tag is None {
        return None;
    }
    type_name = cls._ast_type_name(tag.tag);
    if type_name is None {
        return None;
    }
    arch = cls._resolve_archetype(tag, type_name);
    if arch is None or arch.arch_type.name != Tok.KW_NODE {
        return None;
    }
    return arch.name.value;
}

@classmethod
impl JacTTGGenerator._trace_method_calls(
    cls: type[JacTTGGenerator],
    ability: uni.Ability,
    current_node_type: (str | None) = None,
    seen: (set[int] | None) = None
) -> list[VisitType] {
    result: list[VisitType] = [];
    if seen is None {
        seen = set();
    }
    func_calls = cls._ability_sub_nodes(ability, uni.FuncCall);
    for call_any in func_calls {
        if not isinstance(call_any, uni.FuncCall) {
            continue;
        }
        call: uni.FuncCall = call_any;
        callee = cls._resolve_called_ability(call);
        if callee is None or id(callee) in seen {
            continue;
        }
        seen.add(id(callee));
        owner_type: (str | None) = None;
        if callee.method_owner and isinstance(callee.method_owner, uni.Archetype) {
            owner_type = callee.method_owner.name.value;
        }
        if owner_type is None {
            param_owner_type = cls._single_param_node_type(callee);
            if param_owner_type is not None {
                owner_type = param_owner_type;
            }
        }
        if owner_type is None and current_node_type is not None {
            owner_type = current_node_type;
        }
        trailers = cls._ability_sub_nodes(callee, uni.EdgeRefTrailer);
        for trailer in trailers {
            chain = cls._extract_chains_from_trailer(callee, trailer);
            if len(chain) > 0 {
                origin_name = cls._edge_ref_explicit_origin_name(trailer);
                first_edge = chain[0][0] if len(chain) > 0 else None;
                result.append(
                    VisitType(
                        from_node_type=_ttg_from_type_for_visit(
                            origin_name, owner_type
                        ),
                        edge_type=first_edge,
                        edge_chain=chain if len(chain) > 0 else None,
                        is_visit=False,
                        origin_name=_ttg_origin_name_for_visit(origin_name)
                    )
                );
            }
        }
        result.extend(cls._trace_method_calls(callee, owner_type, seen));
    }
    return result;
}

@classmethod
impl JacTTGGenerator._extract_visits_from_ast(
    cls: type[JacTTGGenerator], warch: any
) -> list[VisitType] {
    warch_cls = `type(warch);
    cached_raw = warch_cls?.__jac_ttg_visits__;
    if isinstance(cached_raw, list) and len(cached_raw) > 0 {
        logger.info(
            f"[TTG-EXTRACT] cache HIT for {warch_cls.__name__}, "
            f"returning {len(cached_raw)} visits"
        );
        return cached_raw;
    }
    logger.info(f"[TTG-EXTRACT] cache MISS for {warch_cls.__name__}");
    ast_node = cls._find_walker_ast_node(warch_cls);
    if ast_node is None {
        return [];
    }
    result: list[VisitType] = [];
    abilities = ast_node.get_all_sub_nodes(uni.Ability);
    for ability in abilities {
        event_sigs = ability.get_all_sub_nodes(uni.EventSignature);
        if len(event_sigs) == 0 {
            continue;
        }
        node_type_name: (str | None) = None;
        node_type_names = event_sigs[0].get_all_sub_nodes(uni.Name);
        if len(node_type_names) > 0 {
            node_arch = cls._resolve_archetype(
                node_type_names[0], node_type_names[0].value
            );
            if node_arch is not None {
                node_type_name = node_arch.name.value;
            }
        }
        visit_stmts = cls._ability_sub_nodes(ability, uni.VisitStmt);
        for visit_stmt in visit_stmts {
            trailers = visit_stmt.get_all_sub_nodes(uni.EdgeRefTrailer);
            for trailer in trailers {
                chain = cls._extract_chains_from_trailer(visit_stmt, trailer);
                if len(chain) == 0 {
                    continue;
                }
                origin_name = cls._edge_ref_explicit_origin_name(trailer);
                first_edge = chain[0][0] if len(chain) > 0 else None;
                result.append(
                    VisitType(
                        from_node_type=_ttg_from_type_for_visit(
                            origin_name, node_type_name
                        ),
                        edge_type=first_edge,
                        edge_chain=chain if len(chain) > 0 else None,
                        origin_name=_ttg_origin_name_for_visit(origin_name)
                    )
                );
            }
        }
        visit_trailer_ids: set[int] = set();
        for vs in visit_stmts {
            for t in vs.get_all_sub_nodes(uni.EdgeRefTrailer) {
                visit_trailer_ids.add(id(t));
            }
        }
        all_trailers = cls._ability_sub_nodes(ability, uni.EdgeRefTrailer);
        for trailer in all_trailers {
            if id(trailer) in visit_trailer_ids {
                continue;
            }
            chain = cls._extract_chains_from_trailer(ability, trailer);
            if len(chain) > 0 {
                origin_name = cls._edge_ref_explicit_origin_name(trailer);
                first_edge = chain[0][0] if len(chain) > 0 else None;
                result.append(
                    VisitType(
                        from_node_type=_ttg_from_type_for_visit(
                            origin_name, node_type_name
                        ),
                        edge_type=first_edge,
                        edge_chain=chain if len(chain) > 0 else None,
                        is_visit=False,
                        origin_name=_ttg_origin_name_for_visit(origin_name)
                    )
                );
            }
        }
        result.extend(cls._trace_method_calls(ability, node_type_name));
    }
    setattr(warch_cls, "__jac_ttg_visits__", result);
    return result;
}

@classmethod
impl JacTTGGenerator._origin_for_id(
    cls: type[JacTTGGenerator], id: UUID
) -> NodeArchetype {
    raise RuntimeError("TTG query-planner fallback is disabled");
}

@classmethod
impl JacTTGGenerator._arch_types_for_ids(
    cls: type[JacTTGGenerator], mem: any, ids: list[UUID]
) -> dict[UUID, str] {
    raise RuntimeError("TTG extra arch-type lookup is disabled");
}

@classmethod
impl JacTTGGenerator._chain_to_hops(
    cls: type[JacTTGGenerator],
    warch: any,
    chain: list[tuple[str | None, str | None, int]]
) -> list[QHop] {
    raise RuntimeError("TTG query-planner fallback is disabled");
}

@classmethod
impl JacTTGGenerator._resolve_chain_ids(
    cls: type[JacTTGGenerator],
    mem: any,
    warch: any,
    origin_id: UUID,
    chain: list[tuple[str | None, str | None, int]],
    limit: int
) -> list[UUID] {
    raise RuntimeError("TTG query-planner fallback is disabled");
}


def _sql_visit_specs(
    cls: type[JacTTGGenerator], visits: list[VisitType]
) -> (list[dict] | None) {
    specs: list[dict] = [];
    for v in visits {
        if not isinstance(v, VisitType) {
            return None;
        }
        if v.edge_chain is not None {
            chain = v.edge_chain;
        } else {
            edge_name = cls._resolve_type_name(v.edge_type);
            chain = [(edge_name, None, 2)];
        }
        if not chain {
            return None;
        }
        normalized_chain: list[tuple[str | None, str | None, int]] = [];
        for hop in chain {
            try {
                direction = int(hop[2] or 2);
            } except Exception {
                return None;
            }
            if direction not in (1, 2, 3) {
                return None;
            }
            normalized_chain.append((hop[0], hop[1], direction));
        }
        specs.append(
            {
                "idx": len(specs),
                "from_type": cls._resolve_type_name(v.from_node_type),
                "chain": normalized_chain,
                "is_visit": bool(v.is_visit),
                "origin_name": str(getattr(v, "origin_name", "") or "")
            }
        );
    }
    return specs;
}


def _ttg_require_unlimited_fanout -> str {
    import os as _os;
    fanout_raw = _os.environ.get("JAC_TTG_SQL_FANOUT", "unlimited").strip().lower();
    if (
        fanout_raw
        and fanout_raw
            not in (
                "0",
                "none",
                "unlimited",
                "unbounded",
                "all",
                "false",
                "no",
                "off",

            )
    ) {
        try {
            if int(fanout_raw) > 0 {
                raise RuntimeError(
                    "TTG specialized set-based SQL does not support "
                    "fanout-limited planning"
                );
            }
        } except RuntimeError {
            raise;
        } except Exception {
            fanout_raw = "";
        }
    }
    return "unlimited";
}


def _ttg_specialized_max_chain_len(specs: list[dict]) -> int {
    max_chain_len = 1;
    for spec in specs {
        chain = spec.get("chain") or [];
        max_chain_len = max(max_chain_len, len(chain));
        for hop in chain {
            direction = int(hop[2] or 2);
            if direction not in (1, 2, 3) {
                raise RuntimeError(
                    "TTG specialized set-based SQL cannot lower direction "
                    f"{direction}"
                );
            }
        }
    }
    return max_chain_len;
}


def _ttg_as_bool(value: object) -> bool {
    if isinstance(value, bool) {
        return value;
    }
    return str(value).strip().lower() in ("true", "t", "1", "yes", "y");
}


def _ttg_idx_type_matches(
    idx: TopologyIndex, actual: (str | None), wanted: (str | None)
) -> bool {
    if wanted is None {
        return True;
    }
    if actual is None or not actual {
        return False;
    }
    if actual == wanted {
        return True;
    }
    ancestors: set[str] = idx.type_ancestors.get(actual, set());
    return wanted in ancestors;
}


def _ttg_idx_node_matches(
    idx: TopologyIndex, node_id: UUID, wanted: (str | None)
) -> bool {
    return _ttg_idx_type_matches(idx, idx.node_type(node_id), wanted);
}


def _ttg_parse_specialized_sql_result(
    rows: list[tuple], max_length: int, type_cache: (dict[UUID, str] | None) = None
) -> dict[str, object] {
    prefetch: list[UUID] = [];
    prefetch_seen: set[UUID] = set();
    topology_rows: list[tuple] = [];
    complete_hops: list[tuple[UUID, int]] = [];
    for r in rows {
        row_kind = int(str(r[0]));
        uid = UUID(str(r[2]));
        arch_type = str(r[3] or "unknown");
        if row_kind == 0 {
            if uid in prefetch_seen {
                continue;
            }
            if len(prefetch) >= max_length {
                continue;
            }
            prefetch_seen.add(uid);
            prefetch.append(uid);
            if type_cache is not None {
                type_cache[uid] = arch_type;
            }
            topology_rows.append(
                (0, r[2], arch_type, r[4], None, None, False, r[8], None)
            );
        } elif row_kind == 1 {
            if type_cache is not None and uid in prefetch_seen {
                type_cache[uid] = arch_type;
            }
            topology_rows.append(
                (0, r[2], arch_type, r[4], None, None, False, r[8], None)
            );
        } elif row_kind == 2 {
            topology_rows.append(
                (1, r[2], arch_type, None, r[5], r[6], r[7], r[8], r[9])
            );
        } elif row_kind == 3 {
            spec_idx = int(str(r[9]));
            complete_hops.append((uid, spec_idx));
        }
    }
    return {
        "prefetch_ids": prefetch,
        "topology_rows": topology_rows,
        "complete_hops": complete_hops
    };
}


def _ttg_complete_hops_by_spec(
    complete_hops: list[tuple[UUID, int]]
) -> dict[int, list[UUID]] {
    complete_by_spec: dict[int, list[UUID]] = {};
    for (origin_id, spec_idx) in complete_hops {
        complete_by_spec.setdefault(spec_idx, []).append(origin_id);
    }
    return complete_by_spec;
}


def _ttg_mark_single_hop_complete(
    idx: TopologyIndex, specs: list[dict], complete_hops: list[tuple[UUID, int]]
) -> tuple[int, int] {
    marked = 0;
    skipped_multihop = 0;
    complete_by_spec = _ttg_complete_hops_by_spec(complete_hops);
    for spec in specs {
        spec_idx = int(spec.get("idx", -1));
        chain = spec.get("chain") or [];
        if len(chain) != 1 {
            skipped_multihop += 1;
            continue;
        }
        origin_ids: list[UUID] = [];
        seen: set[UUID] = set();
        for uid in complete_by_spec.get(spec_idx, []) {
            if uid in seen {
                continue;
            }
            if not _ttg_idx_node_matches(idx, uid, spec.get("from_type")) {
                continue;
            }
            seen.add(uid);
            origin_ids.append(uid);
        }
        if not origin_ids {
            continue;
        }
        hop = chain[0];
        idx.mark_hops_loaded(origin_ids, hop[0], hop[1], int(hop[2] or 2));
        marked += len(origin_ids);
    }
    return (marked, skipped_multihop);
}


def _ttg_opt_complete_hops_enabled -> bool {
    import os as _os;
    raw = _os.environ.get("JAC_TTG_OPT_COMPLETE_HOPS", "").strip().lower();
    return raw not in ("0", "false", "no", "off");
}


def _ttg_prefetch_owner_roots_enabled -> bool {
    import os as _os;
    raw = _os.environ.get("JAC_TTG_PREFETCH_OWNER_ROOTS", "").strip().lower();
    return raw in ("1", "true", "yes", "on");
}


def _ttg_render_specialized_set_based_sql(
    specs: list[dict], params: dict[str, object]
) -> str {
    origins = [UUID(str(uid)) for uid in (params.get('origin_ids') or [])];
    compiled = compile_specialized(
        specs,
        origins,
        int(params['limit']),
        int(params.get('max_depth', params['limit'])),
        _ttg_prefetch_owner_roots_enabled(),
        _ttg_opt_complete_hops_enabled()
    );
    params.clear();
    params.update(compiled.params);
    return compiled.sql;
}

def _ttg_rows_with_explain(
    mem: any, sql: str, params: dict[str, object], label: str
) -> list[any] {
    import os as _os;
    explain_mode = _os.environ.get("JAC_TTG_SQL_EXPLAIN", "").strip().lower();
    if explain_mode in ("plan", "analyze", "true", "1", "on", "yes") {
        explain_options = "VERBOSE, FORMAT TEXT";
        if explain_mode in ("analyze", "true", "1", "on", "yes") {
            explain_options = "ANALYZE, BUFFERS, VERBOSE, SUMMARY, FORMAT TEXT";
        }
        explain_rows = mem.store.rows(f"EXPLAIN ({explain_options}) {sql}", params);
        explain_lines: list[str] = [];
        for r in explain_rows {
            explain_lines.append(str(r[0]));
        }
        logger.warning(f"[{label}-EXPLAIN]\n" + "\n".join(explain_lines));
        raise RuntimeError(f"{label} EXPLAIN requested");
    }
    return mem.store.rows(sql, params);
}


def _resolve_sql_visit_bfs_specialized_set_based(
    mem: any,
    origins: list[UUID],
    specs: list[dict],
    max_length: int,
    type_cache: (dict[UUID, str] | None) = None
) -> list[UUID] {
    import from typing { cast }
    fanout_desc = _ttg_require_unlimited_fanout();
    max_chain_len = _ttg_specialized_max_chain_len(specs);
    params: dict[str, object] = {
        "origin_ids": [str(i) for i in origins],
        "limit": int(max_length),
        "max_depth": int(max_length)
    };
    sql = _ttg_render_specialized_set_based_sql(specs, params);
    logger.info(
        f"[TTG-SQL-BFS-START] specs={len(specs)} origins={len(origins)} "
        f"fanout={fanout_desc} max_chain={max_chain_len} "
        f"limit={max_length} mode=set-based-specialized"
    );
    mem.read_barrier();
    try {
        rows = _ttg_rows_with_explain(mem, sql, params, "TTG-SQL-SPECIALIZED");
    } except Exception as e {
        logger.warning(f"TTG specialized set-based SQL BFS failed: {e}");
        raise;
    }
    parsed = _ttg_parse_specialized_sql_result(rows, max_length, type_cache);
    prefetch = cast(list[UUID], parsed["prefetch_ids"]);
    topology_rows = cast(list[tuple], parsed["topology_rows"]);
    complete_hop_keys = cast(list[tuple[UUID, int]], parsed["complete_hops"]);
    complete_hops = 0;
    skipped_complete_multihop = 0;
    try {
        idx = ingest_topology_rows(mem, topology_rows);
        (complete_hops, skipped_complete_multihop) = _ttg_mark_single_hop_complete(
            idx, specs, complete_hop_keys
        );
    } except Exception as e {
        logger.debug(f"TTG specialized SQL BFS topology ingest failed: {e}");
    }
    logger.info(
        f"[TTG-SQL-BFS] specs={len(specs)} origins={len(origins)} "
        f"prefetched={len(prefetch)} rows_returned={len(rows)} "
        f"topology_rows={len(topology_rows)} fanout={fanout_desc} "
        f"max_chain={max_chain_len} query_count=1 "
        f"complete_hops={complete_hops} "
        f"skipped_complete_multihop={skipped_complete_multihop} "
        "mode=set-based-specialized"
    );
    return prefetch;
}


def _resolve_sql_visit_bfs_budgeted(
    mem: any,
    origins: list[UUID],
    specs: list[dict],
    max_length: int,
    type_cache: (dict[UUID, str] | None) = None
) -> list[UUID] {
    return _resolve_sql_visit_bfs_specialized_set_based(
        mem, origins, specs, max_length, type_cache
    );
}


def _resolve_sql_visit_bfs_layered_budgeted(
    mem: any,
    origins: list[UUID],
    specs: list[dict],
    max_length: int,
    type_cache: (dict[UUID, str] | None) = None
) -> list[UUID] {
    import os as _os;
    fanout_raw = _os.environ.get("JAC_TTG_SQL_FANOUT", "unlimited").strip().lower();
    if (
        fanout_raw
        and fanout_raw
            not in (
                "0",
                "none",
                "unlimited",
                "unbounded",
                "all",
                "false",
                "no",
                "off",

            )
    ) {
        try {
            if int(fanout_raw) > 0 {
                raise RuntimeError(
                    "TTG layered SQL does not support fanout-limited planning"
                );
            }
        } except RuntimeError {
            raise;
        } except Exception {
            fanout_raw = "";
        }
    }
    max_chain_len = 1;
    directions: list[int] = [];
    for spec in specs {
        chain = spec.get('chain') or [];
        max_chain_len = max(max_chain_len, len(chain));
        for hop in chain {
            directions.append(int(hop[2] or 2));
        }
    }
    include_roots = _ttg_prefetch_owner_roots_enabled();
    mem.read_barrier();
    has_undirected = True;
    try {
        probe = compile_undirected_probe();
        undirected_rows = mem.store.rows(probe.sql, probe.params);
        has_undirected = bool(undirected_rows[0][0]) if undirected_rows else True;
    } except Exception as e {
        logger.debug(f'TTG layered SQL undirected-edge probe failed: {e}');
    }
    direction_mode = 'generic';
    if not has_undirected and all([d == 2 for d in directions]) {
        direction_mode = 'directed-out';
    } elif not has_undirected and all([d == 1 for d in directions]) {
        direction_mode = 'directed-in';
    }
    logger.info(
        f"[TTG-SQL-LAYERED-START] specs={len(specs)} origins={len(origins)} "
        f"fanout=unlimited max_chain={max_chain_len} limit={max_length} "
        f"direction_mode={direction_mode} has_undirected={has_undirected}"
    );
    explain_mode = _os.environ.get("JAC_TTG_SQL_EXPLAIN", "").strip().lower();
    prefetch: list[UUID] = [];
    prefetch_seen: set[UUID] = set();
    topology_rows: list[tuple] = [];
    frontier: list[UUID] = list(origins);
    expanded_seen: set[UUID] = set();
    depth = 0;
    query_count = 0;
    while (len(frontier) > 0 and len(prefetch) < max_length and depth < max_length) {
        remaining = max_length - len(prefetch);
        compiled = compile_layered(
            specs,
            list(frontier),
            list(prefetch_seen),
            int(remaining),
            has_undirected,
            include_roots
        );
        sql = compiled.sql;
        params = compiled.params;
        try {
            if explain_mode in ("plan", "analyze", "true", "1", "on", "yes") {
                explain_options = "VERBOSE, FORMAT TEXT";
                if explain_mode in ("analyze", "true", "1", "on", "yes") {
                    explain_options = "ANALYZE, BUFFERS, VERBOSE, SUMMARY, FORMAT TEXT";
                }
                explain_rows = mem.store.rows(
                    f"EXPLAIN ({explain_options}) {sql}", params
                );
                explain_lines: list[str] = [];
                for r in explain_rows {
                    explain_lines.append(str(r[0]));
                }
                logger.warning(
                    f"[TTG-SQL-LAYERED-EXPLAIN depth={depth}]\n"
                        + "\n".join(explain_lines)
                );
                raise RuntimeError("TTG layered SQL EXPLAIN requested");
            }
            rows = mem.store.rows(sql, params);
            query_count += 1;
        } except Exception as e {
            logger.warning(f"TTG layered SQL BFS failed at depth {depth}: {e}");
            raise;
        }
        next_frontier: list[UUID] = [];
        next_seen: set[UUID] = set();
        for r in rows {
            uid = UUID(str(r[1]));
            if uid in prefetch_seen {
                continue;
            }
            if len(prefetch) >= max_length {
                break;
            }
            prefetch_seen.add(uid);
            prefetch.append(uid);
            arch_type = str(r[2] or "unknown");
            if type_cache is not None {
                type_cache[uid] = arch_type;
            }
            topology_rows.append(
                (0, r[1], arch_type, r[3], None, None, False, r[4], None)
            );
            if bool(r[5]) and uid not in expanded_seen and uid not in next_seen {
                next_seen.add(uid);
                next_frontier.append(uid);
            }
        }
        for id in frontier {
            expanded_seen.add(id);
        }
        logger.info(
            f"[TTG-SQL-LAYERED] depth={depth} frontier={len(frontier)} "
            f"rows={len(rows)} next_frontier={len(next_frontier)} "
            f"prefetched={len(prefetch)} remaining={max_length - len(prefetch)}"
        );
        frontier = next_frontier;
        depth += 1;
    }
    try {
        ingest_topology_rows(mem, topology_rows);
    } except Exception as e {
        logger.debug(f"TTG layered SQL BFS topology ingest failed: {e}");
    }
    logger.info(
        f"[TTG-SQL-BFS] specs={len(specs)} origins={len(origins)} "
        f"prefetched={len(prefetch)} fanout=unlimited max_chain={max_chain_len} "
        f"query_count={query_count} mode=layered direction_mode={direction_mode}"
    );
    return prefetch;
}


def _resolve_sql_visit_bfs(
    cls: type[JacTTGGenerator],
    mem: any,
    origins: list[UUID],
    visits: list[VisitType],
    max_length: int,
    type_cache: (dict[UUID, str] | None) = None
) -> list[UUID] {
    if max_length <= 0 {
        return [];
    }
    if mem is None or mem?.store is None {
        raise RuntimeError("TTG SQL BFS requires a SQL-backed memory store");
    }
    if not origins {
        raise RuntimeError("TTG SQL BFS requires at least one origin");
    }
    specs = _sql_visit_specs(cls, visits);
    if specs is None {
        raise RuntimeError("TTG SQL BFS cannot lower this walker's visit graph to SQL");
    }
    if not specs {
        return [];
    }
    import os as _os;
    layered_raw = _os.environ.get("JAC_TTG_SQL_LAYERED", "").strip().lower();
    if layered_raw in ("1", "true", "yes", "on") {
        return _resolve_sql_visit_bfs_layered_budgeted(
            mem, origins, specs, max_length, type_cache
        );
    }
    return _resolve_sql_visit_bfs_budgeted(mem, origins, specs, max_length, type_cache);
}


def _finalize_ttg_prefetch(
    cls: type[JacTTGGenerator],
    prefetch: list[UUID],
    type_cache: dict[UUID, str],
    ast_ms: float,
    resolve_ms: float,
    resolve_calls: int,
    max_length: int
) -> list[UUID] {
    import os as _os;
    avg_resolve = resolve_ms / resolve_calls if resolve_calls > 0 else 0.0;
    missing_types = [
        id
        for id in prefetch
        if id not in type_cache
    ];
    if missing_types {
        logger.warning(
            "[TTG-COVERAGE] missing type metadata for "
            f"{len(missing_types)} prefetched ids"
        );
    }
    type_counts: dict[str, int] = {};
    for id in prefetch {
        tname = type_cache.get(id, "unknown");
        type_counts[tname] = type_counts.get(tname, 0) + 1;
    }
    logger.info(
        f"[TTG] ast_ms={ast_ms:.3f} resolve_chain_total_ms={resolve_ms:.3f} "
        f"resolve_calls={resolve_calls} avg_per_call_ms={avg_resolve:.4f} "
        f"prefetched={len(prefetch)}"
    );
    logger.info(
        f"[TTG-COVERAGE] prefetched_by_type={type_counts} " f"max_length={max_length}"
    );
    dump_path = _os.environ.get("JAC_PREFETCH_DUMP");
    if dump_path {
        try {
            import pathlib as _pathlib;
            p = _pathlib.Path(dump_path);
            p.parent.mkdir(parents=True, exist_ok=True);
            new_file = not p.exists();
            with p.open("a") as fh {
                if new_file {
                    fh.write("order,id,type\n");
                }
                for (idx, id) in enumerate(prefetch) {
                    fh.write(f"{idx},{id},{type_cache.get(id, 'unknown')}\n");
                }
            }
        } except Exception as e {
            logger.debug(f"[PREFETCH-DUMP] write failed: {e}");
        }
    }
    setattr(cls, "_last_resolve_ms", resolve_ms);
    return prefetch;
}


@classmethod
impl JacTTGGenerator.get_ttg_prefetch_list(
    cls: type[JacTTGGenerator],
    warch: any,
    start_anchor: NodeAnchor,
    mem: any = None,
    max_length: int = 200
) -> list[UUID] {
    import time as _time;
    if max_length <= 0 or start_anchor is None or start_anchor.id is None {
        return [];
    }
    if mem is None or mem?.store is None {
        raise RuntimeError("TTG prefetch requires a SQL-backed memory store");
    }
    t0 = _time.perf_counter();
    visits = cls._extract_visits_from_ast(warch);
    ast_ms = (_time.perf_counter() - t0) * 1000;
    logger.info(
        f"[TTG-DEBUG] extracted {len(visits)} visits: "
            + str(
                [
                    (
                        f"from={cls._resolve_type_name(v.from_node_type)}",
                        f"edge={cls._resolve_type_name(v.edge_type)}",
                        f"chain={v.edge_chain}",
                        f"is_visit={v.is_visit}",
                        f"origin={getattr(v, 'origin_name', '')}"
                    ) for v in visits
                ]
            )
    );
    start_id = start_anchor.id;
    type_cache: dict[UUID, str] = {};
    if start_anchor.archetype is not None {
        type_cache[start_id] = type(start_anchor.archetype).__name__;
    }
    origins: list[UUID] = [start_id];
    if any(str(getattr(v, "origin_name", "") or "") == "root" for v in visits) {
        try {
            import from jaclang.runtime.runtime { JacRuntimeInterface }
            ctx = JacRuntimeInterface.get_context();
            root_anchor = ctx?.user_root;
            root_id = root_anchor?.id;
            if root_id is not None and root_id not in origins {
                origins.append(root_id);
            }
            if (
                root_id is not None
                and root_anchor is not None
                and root_anchor.archetype is not None
            ) {
                type_cache[root_id] = type(root_anchor.archetype).__name__;
            }
        } except Exception as e {
            logger.debug(f"TTG could not add root origin: {e}");
        }
    }
    sql_start = _time.perf_counter();
    sql_prefetch = _resolve_sql_visit_bfs(
        cls, mem, origins, visits, max_length, type_cache
    );
    sql_ms = (_time.perf_counter() - sql_start) * 1000;
    return _finalize_ttg_prefetch(
        cls, sql_prefetch, type_cache, ast_ms, sql_ms, 1, max_length
    );
}

impl JacTTGGenerator.get_continuation_plan(
    cls: type[JacTTGGenerator],
    graph: any,
    current: dict,
    point: int,
    snapshot: dict,
    pending: list[dict],
    resolve: any,
    max_nodes: int = 200,
    max_steps: int = 32768,
    resolve_state: bool = False
) -> dict {
    import from jaclang.runtime.ttg_continuation { plan_continuation }
    return plan_continuation(
        graph,
        current,
        point,
        snapshot,
        pending,
        resolve,
        max_nodes,
        max_steps,
        resolve_state=resolve_state
    );
}
