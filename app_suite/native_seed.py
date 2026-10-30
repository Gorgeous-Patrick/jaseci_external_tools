"""Test-only native corpus importer, loaded in an isolated application snapshot.

Objects are the application's actual Jac classes. Jac.save/connect create native
anchors and topology; the original source checkouts are never rewritten.
"""
from collections import Counter
from dataclasses import fields
from io import BytesIO
import json
import os
from pathlib import Path

from jaclang import JacRuntimeInterface as Jac
from jaclang.runtime.archetype import AccessLevel


def read_jsonl(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def import_graph(node_types, edge_types, roots, storage=None):
    directory = Path(os.environ['TTG_DATASET'])
    app = json.loads((directory / 'manifest.json').read_text())['app']
    rows = read_jsonl(directory / 'nodes.jsonl')
    edges = read_jsonl(directory / 'edges.jsonl')
    authors = {e['source']: e['target'] for e in edges if e['type'] == 'AuthoredBy'}
    context = Jac.get_context()
    caller = str(context.user_root.id)
    objects, mapping = {}, {}

    def owner(key):
        if app == 'littlex':
            return 'user:' + key.split(':')[1]
        if app == 'jacord':
            return key if key.startswith('user:') else authors.get(key, 'user:0')
        return 'user:0'

    try:
        for row in rows:
            context.set_user_root(roots[owner(row['id'])])
            values = dict(row['fields'])
            if row['type'] == 'File':
                payload = b'TTG corpus file content. ' * 3
                payload = payload[:64].ljust(64, b' ')
                key = 'corpus-' + row['id'].replace('/', '_').replace(':', '_')
                storage.upload(BytesIO(payload), key)
                assert storage.download(key) == payload, 'File bytes did not round-trip'
                values['blob_key'] = key
            obj = node_types[row['type']](**values)
            Jac.save(obj)
            if app == 'jacord':
                Jac.perm_grant(obj, AccessLevel.WRITE)
            elif app == 'littlex':
                Jac.perm_grant(obj, AccessLevel.WRITE if row['type'] == 'Tweet' else AccessLevel.CONNECT)
            objects[row['id']] = obj
            mapping[row['id']] = Jac.object_ref(obj)
        for key, root_id in roots.items():
            context.set_user_root(root_id)
            if app == 'jacord':
                Jac.perm_grant(Jac.root(), AccessLevel.WRITE)
            head = key if app in ('littlex', 'jacord') else ('drive:0' if app == 'jdrive' else 'item:0')
            Jac.connect(Jac.root(), objects[head], edge_types.get('Contains') if app == 'jdrive' else None)
        for edge in edges:
            context.set_user_root(roots[owner(edge['source'])])
            Jac.connect(objects[edge['source']], objects[edge['target']], edge_types[edge['type']])
        if context.diagnostics:
            raise AssertionError('Native graph import produced permission diagnostics: ' +
                                 '; '.join(d.message() for d in context.diagnostics))
        return mapping
    finally:
        context.set_user_root(caller)


def inspect_graph(mapping):
    """Read actual native nodes and stored typed edges after a process restart."""
    objects = {}
    for key, native_id in mapping.items():
        obj = Jac.get_object(native_id)
        assert obj is not None, f'Missing native object: {key}'
        objects[key] = {'type': type(obj).__name__,
                        'fields': {f.name: getattr(obj, f.name) for f in fields(obj)
                                   if not f.name.startswith('_')}}
    reverse = {str(value).replace('-', ''): key for key, value in mapping.items()}
    store = Jac.get_context().mem.store
    rows = store.rows("SELECT src::text, arch_type, dst::text FROM anchors WHERE kind = 'EdgeAnchor'", {})
    edges = []
    for source, kind, target in rows:
        source = reverse.get(str(source).replace('-', ''))
        target = reverse.get(str(target).replace('-', ''))
        if source is not None and target is not None:
            edges.append({'source': source, 'type': kind, 'target': target})
    return {'nodes': objects, 'edges': edges,
            'type_counts': dict(Counter(obj['type'] for obj in objects.values()))}
