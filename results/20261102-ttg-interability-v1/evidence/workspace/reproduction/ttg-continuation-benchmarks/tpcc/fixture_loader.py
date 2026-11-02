"""Retain warehouse ownership and the separate cross-root item catalog."""
import json
from pathlib import Path
from jaclang import JacRuntimeInterface as Jac
from jaclang.runtime.archetype import AccessLevel


def seed_graph(directory: str,catalog_root_jid: str,node_types: dict,edge_types: dict) -> dict:
    graph=json.loads((Path(directory)/'graph.json').read_text())
    context=Jac.get_context();owner=str(context.user_root.id);objects={}
    try:
        for row in graph['nodes']:
            context.set_user_root(catalog_root_jid if row['type']=='Item' else owner)
            obj=node_types[row['type']](**row['fields']);Jac.save(obj);objects[row['id']]=obj
            if row['type']=='Item':Jac.perm_grant(obj,AccessLevel.WRITE);Jac.connect(Jac.root(),obj)
            elif row['type']=='Warehouse':Jac.connect(Jac.root(),obj)
        context.set_user_root(owner)
        for row in graph['edges']:Jac.connect(objects[row['source']],objects[row['target']],edge_types.get(row['type']))
        if context.diagnostics:raise AssertionError('Cross-root fixture permission diagnostics')
        return {name:Jac.object_ref(obj) for name,obj in objects.items()}
    finally:context.set_user_root(owner)
