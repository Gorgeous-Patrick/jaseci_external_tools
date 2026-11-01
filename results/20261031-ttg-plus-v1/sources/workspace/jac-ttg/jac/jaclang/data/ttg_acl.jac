import sys;
import from types { ModuleType }
import from jaclang.runtime.archetype { Archetype, NodeArchetype }

glob _STANDARD_ACCESS: any = vars(Archetype).get('__jac_access__');


def standard_node_access(node_type: any) -> bool {
    if type(node_type) is not type or not issubclass(node_type, NodeArchetype) {
        return False;
    }
    for base in node_type.__mro__ {
        if '__jac_access__' in vars(base) {
            return _STANDARD_ACCESS is not None
                and vars(base)['__jac_access__'] is _STANDARD_ACCESS;
        }
    }
    return False;
}


def catalog_node_type(name: any, module_name: any) -> any {
    import from jaclang.runtime.runtime { JacRuntime }
    if type(name) is not str
        or not name
        or type(module_name) is not str
        or not module_name {
        return None;
    }
    module = JacRuntime.loaded_modules.get(module_name);
    if module is None {
        module = sys.modules.get(module_name);
    }

    if type(module) is not ModuleType {
        return None;
    }
    resolved = vars(module).get(name);
    if resolved is None or type(resolved) is not type {
        return None;
    }
    declared_module = vars(resolved).get('__module__');
    if type(resolved.__name__) is not str
        or resolved.__name__ != name
        or type(declared_module) is not str
        or declared_module != module_name {
        return None;
    }
    return resolved;
}


def standard_catalog_access(mem: any) -> bool {
    import from jaclang.data.store { TxnIsolation }
    import from jaclang.runtime.ttg_sql { compile_acl_type_catalog }
    if mem is None or mem.store is None {
        return False;
    }
    with mem._lock {
        mem.read_barrier();
        if mem.store.txn_isolation()
            not in (TxnIsolation.SERIALIZABLE, TxnIsolation.SNAPSHOT_READ_ONLY) {
            return False;
        }
        key = ('ttg_standard_acl_catalog', 1);
        cached = mem.query_cache_get(key);
        if cached is not None {
            if not cached['approved'] {
                return False;
            }
            return all(
                catalog_node_type(name, module_name) is node_type
                    and standard_node_access(node_type)
                for (name, module_name, node_type) in cached['types']
            );
        }
        compiled = compile_acl_type_catalog();
        rows = mem.store.rows(compiled.sql, compiled.params);
        approved = True;
        types: list = [];
        for (name, module_name) in rows {
            resolved = catalog_node_type(name, module_name);
            if resolved is None or not standard_node_access(resolved) {
                approved = False;
                break;
            }
            types.append((name, module_name, resolved));
        }
        mem.query_cache_put(key, {'approved': approved, 'types': types});
        return approved;
    }
}
