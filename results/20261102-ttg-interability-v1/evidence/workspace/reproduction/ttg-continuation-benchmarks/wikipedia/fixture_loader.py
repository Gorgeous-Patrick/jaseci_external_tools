"""Actual native fixture construction and typed Knows edge-property access."""
import json
from pathlib import Path
from jaclang import JacRuntimeInterface as Jac


def seed_graph(directory: str,node_types: dict,edge_types: dict) -> dict:
    graph=json.loads((Path(directory)/'graph.json').read_text());objects={}
    for row in graph['nodes']:
        obj=node_types[row['type']](**row['fields']);Jac.save(obj)
        objects[row['id']]=obj;Jac.connect(Jac.root(),obj)
    for row in graph['edges']:
        edge=edge_types[row['type']](**row.get('fields',{}))
        Jac.connect(objects[row['source']],objects[row['target']],edge)
    if Jac.get_context().diagnostics:raise AssertionError('Fixture import permission diagnostics')
    return {name:Jac.object_ref(obj) for name,obj in objects.items()}


def friendship_dates(person: object) -> dict:
    result={}
    for edge in person.__jac__.edges:
        if type(edge.archetype).__name__!='Knows':continue
        other=edge.target if edge.source.id==person.__jac__.id else edge.source
        result[Jac.object_ref(other.archetype)]=edge.archetype.creation_date
    return result


def remove_node(node: object) -> None:
    Jac.destroy(node)
