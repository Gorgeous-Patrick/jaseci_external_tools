"""Corpus invariants and small, independently calculated logical outcomes."""
import copy
import json
from pathlib import Path
import random
import tempfile
import unittest

import build


class CorpusTests(unittest.TestCase):
    def test_reproducible_graphs_and_seed_variation(self):
        for app in build.APPS:
            with self.subTest(app=app):
                a = build.make_graph(app, build.SCALES['smoke'], random.Random(42))
                b = build.make_graph(app, build.SCALES['smoke'], random.Random(42))
                self.assertEqual(a.nodes, b.nodes)
                self.assertEqual(a.edges, b.edges)
                if app != 'linked_list':
                    c = build.make_graph(app, build.SCALES['smoke'], random.Random(43))
                    self.assertNotEqual((a.nodes, a.edges), (c.nodes, c.edges))

    def test_list_early_late_and_absent(self):
        g = build.make_graph('linked_list', build.SCALES['smoke'], random.Random(42))
        self.assertEqual(build.result(g, dict(op='sum', target='item:0')), 496)
        self.assertEqual(build.result(g, dict(op='find', target='item:0', value=16)), 'item:16')
        self.assertIsNone(build.result(g, dict(op='find', target='item:0', value=-1)))

    def test_hidden_parent_prunes_visible_descendants(self):
        g = build.Graph()
        for key, hidden in [('root', False), ('hidden', True), ('leaf', False), ('visible', False)]:
            g.node(key, 'Folder', trashed=hidden)
        g.edge('root', 'Contains', 'hidden')
        g.edge('hidden', 'Contains', 'leaf')
        g.edge('root', 'Contains', 'visible')
        self.assertEqual(build.result(g, dict(op='tree', target='root')), ['root', 'visible'])

    def test_reply_edges_are_incoming(self):
        g = build.Graph()
        g.node('channel', 'Channel')
        for key in ('message', 'reply', 'nested'):
            g.node(key, 'Message')
        g.edge('message', 'Posted', 'channel')
        g.edge('reply', 'ReplyTo', 'message')
        g.edge('nested', 'ReplyTo', 'reply')
        self.assertEqual(build.result(g, dict(op='channel', target='channel')), ['message', 'nested', 'reply'])

    def test_mutations_visible_to_subsequent_reads(self):
        for app in ('littlex', 'jacord', 'jdrive'):
            g = build.make_graph(app, build.SCALES['smoke'], random.Random(42))
            baseline = copy.deepcopy(g.nodes)
            for op in build.session(app, build.SCALES['smoke']):
                build.result(g, op)
            self.assertNotEqual(baseline, g.nodes) if app != 'littlex' else self.assertEqual(g.nodes['post:1:0']['fields']['likes'], [])

    def test_artifacts_validate_and_detect_corruption(self):
        root = Path(__file__).resolve().parents[3]
        with tempfile.TemporaryDirectory() as temp:
            for app in build.APPS:
                path = Path(temp)/app
                build.build(path, app, 'smoke', 42, root)
                build.validate(path)
                with (path/'nodes.jsonl').open('a') as f:
                    f.write('{}\n')
                with self.assertRaisesRegex(ValueError, 'checksum mismatch'):
                    build.validate(path)

    def test_duplicate_and_dangling_nodes_rejected(self):
        g = build.Graph()
        g.node('one', 'Item')
        with self.assertRaises(ValueError):
            g.node('one', 'Item')
        with self.assertRaises(ValueError):
            g.edge('one', 'Next', 'missing')

    def test_medium_timestamps_are_valid(self):
        g = build.make_graph('littlex', dict(build.SCALES['smoke'], posts=100), random.Random(42))
        from datetime import datetime
        for n in g.nodes.values():
            datetime.fromisoformat(n['fields']['created_at'])


if __name__ == '__main__':
    unittest.main()
