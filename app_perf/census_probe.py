#!/usr/bin/env python3
"""Persist two native nodes and one edge solely to verify actual kind encodings."""
import argparse
import json
from pathlib import Path
from types import SimpleNamespace
import jaclang
from jaclang.runtime.archetype import Root, GenericEdge, EdgeAnchor
from jaclang.server.session import Session
from jaclang.data.store import ConnInfo, PgStore

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--port', type=int, required=True)
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
left, right = Root().__jac__, Root().__jac__
edge = EdgeAnchor(archetype=GenericEdge(), source=left, target=right, is_undirected=False)
owner = SimpleNamespace(_version_seen={})
rows = [Session._serialize(owner, anchor) for anchor in (left, right, edge)]
store = PgStore(ConnInfo(host='127.0.0.1', port=args.port, user='ttgperf', database='postgres'), auto_schema=True)
try:
    store.begin()
    store.upsert(rows)
    store.commit()
    ids = [str(row.id) for row in rows]
    actual = store.rows('SELECT kind, count(*) FROM anchors WHERE id=ANY(CAST(:ids AS uuid[])) GROUP BY kind ORDER BY kind', {'ids': ids})
    topology = store.rows('SELECT kind, src::text, dst::text FROM anchors WHERE id=CAST(:id AS uuid)', {'id': str(rows[2].id)})
    assert actual == [('EdgeAnchor', 1), ('NodeAnchor', 2)], actual
    assert topology == [('EdgeAnchor', str(left.id), str(right.id))], topology
    args.output.write_text(json.dumps(dict(passed=True, purpose='Dedicated native persisted fixture, not an application',
        actual_kind_counts=actual, actual_edge_topology=topology,
        native_node_kind='NodeAnchor', native_edge_kind='EdgeAnchor', node_ids=ids[:2], edge_id=ids[2]), indent=2) + '\n')
finally:
    store.close()
