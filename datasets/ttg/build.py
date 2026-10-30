#!/usr/bin/env python3
"""Build a deterministic, portable four-application TTG workload corpus."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict, deque
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import random
import subprocess

APPS = ('linked_list', 'littlex', 'jacord', 'jdrive')
SCALES = {
    'smoke': dict(length=32, users=6, posts=4, channels=2, messages=8, depth=3),
    'small': dict(length=1000, users=50, posts=20, channels=5, messages=100, depth=5),
    'medium': dict(length=10000, users=500, posts=100, channels=10, messages=1000, depth=7),
}


def encoded(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False) + '\n').encode()


class Graph:
    def __init__(self):
        self.nodes = {}
        self.edges = []
        self.out = defaultdict(list)
        self.inc = defaultdict(list)

    def node(self, key, kind, **fields):
        if key in self.nodes:
            raise ValueError(f'duplicate node {key}')
        self.nodes[key] = dict(id=key, type=kind, fields=fields)
        return key

    def edge(self, source, kind, target):
        if source not in self.nodes or target not in self.nodes:
            raise ValueError('dangling edge')
        self.edges.append(dict(source=source, type=kind, target=target))
        self.out[source, kind].append(target)
        self.inc[target, kind].append(source)

    def adjacent(self, key, kind, incoming=False):
        return (self.inc if incoming else self.out)[key, kind]

    def walk(self, start, kind, incoming=False, visible=False):
        queue, seen, result = deque([start]), set(), []
        while queue:
            key = queue.popleft()
            if key in seen:
                continue
            seen.add(key)
            result.append(key)
            for child in self.adjacent(key, kind, incoming):
                if not visible or (self.nodes[child]['type'] == 'Folder' and not self.nodes[child]['fields']['trashed']):
                    queue.append(child)
        return result


def make_graph(app, config, rng):
    g = Graph()
    if app == 'linked_list':
        for i in range(config['length']):
            key = g.node(f'item:{i}', 'Item', value=i, index=i)
            if i:
                g.edge(f'item:{i-1}', 'Next', key)
    elif app == 'littlex':
        count = config['users']
        for i in range(count):
            g.node(f'user:{i}', 'Profile', username=f'user_{i:04}', bio=f'profile {i}', created_at='2026-01-01T00:00:00Z')
        for i in range(count):
            # A reproducible hot account plus local and random follow targets.
            targets = {0, (i+1) % count, rng.randrange(count)} - {i}
            for target in sorted(targets):
                g.edge(f'user:{i}', 'Follow', f'user:{target}')
            for p in range(config['posts']):
                key = g.node(f'post:{i}:{p}', 'Tweet', content=f'post {p} from user {i} #topic{p%4}', author_username=f'user_{i:04}', created_at=(datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=p)).isoformat(), likes=[], comments=[])
                g.edge(f'user:{i}', 'Post', key)
    elif app == 'jacord':
        for i in range(config['users']):
            g.node(f'user:{i}', 'User', username=f'user_{i:04}', display_name=f'User {i}', created_at='2026-01-01T00:00:00Z')
        ws = g.node('workspace:0', 'Workspace', name='Research', created_at='2026-01-01T00:00:00Z')
        for i in range(config['users']):
            g.edge(f'user:{i}', 'Member', ws)
        for c in range(config['channels']):
            channel = g.node(f'channel:{c}', 'Channel', name=f'channel-{c}', topic='TTG evaluation', created_at='2026-01-01T00:00:00Z')
            g.edge(ws, 'HasChannel', channel)
            for m in range(config['messages']):
                msg = g.node(f'message:{c}:{m}', 'Message', content=f'message {m}', created_at='2026-01-01T00:00:00Z')
                g.edge(msg, 'Posted', channel)
                g.edge(msg, 'AuthoredBy', f'user:{rng.randrange(config["users"])}')
                # Reproducible skew: most messages have no replies; some have chains.
                parent = msg
                for r in range(rng.choice([0, 0, 0, 1, 2, 5])):
                    reply = g.node(f'reply:{c}:{m}:{r}', 'Message', content=f'reply {r}', created_at='2026-01-01T00:00:00Z')
                    g.edge(reply, 'ReplyTo', parent)
                    g.edge(reply, 'AuthoredBy', f'user:{rng.randrange(config["users"])}')
                    parent = reply
    else:
        drive = g.node('drive:0', 'Drive', created_at='2026-01-01T00:00:00Z')
        root = g.node('folder:root', 'Folder', name='root', trashed=False, created_at='', updated_at='')
        g.edge(drive, 'Contains', root)
        current = [root]
        for depth in range(config['depth']):
            following = []
            for parent in current:
                for j in range(3):
                    key = f'{parent}/{j}'
                    # Always include a hidden root branch with populated descendants.
                    hidden = (depth == 0 and j == 2) or (depth > 0 and rng.random() < 0.2)
                    g.node(key, 'Folder', name=f'd{depth}-{j}', trashed=hidden, created_at='', updated_at='')
                    g.edge(parent, 'Contains', key)
                    following.append(key)
                file = g.node(f'{parent}/file', 'File', name='sample.txt', mime='text/plain', size=64, blob_key=f'{parent}/file', trashed=False, created_at='', updated_at='')
                g.edge(parent, 'Contains', file)
            current = following
    return g


def result(g, operation):
    """Reference logical results; native walker reports are normalized by adapters."""
    op, target = operation['op'], operation['target']
    if op == 'traverse':
        return g.walk(target, 'Next')[:10000]
    if op == 'sum':
        return sum(g.nodes[k]['fields']['value'] for k in g.walk(target, 'Next'))
    if op == 'find':
        return next((k for k in g.walk(target, 'Next') if g.nodes[k]['fields']['value'] == operation['value']), None)
    if op == 'feed':
        authors = [target] + g.adjacent(target, 'Follow')
        posts = {p for a in authors for p in g.adjacent(a, 'Post')}
        query = operation.get('search', '').lower().strip()
        return sorted(p for p in posts if query in g.nodes[p]['fields']['content'].lower())
    if op == 'like':
        likes = g.nodes[target]['fields']['likes']
        user = operation['username']
        likes.remove(user) if user in likes else likes.append(user)
        return sorted(likes)
    if op == 'follow':
        other = operation['other']
        if other not in g.adjacent(target, 'Follow'):
            g.edge(target, 'Follow', other)
        return sorted(g.adjacent(target, 'Follow'))
    if op == 'create_tweet':
        key = operation['new_id']
        g.node(key, 'Tweet', content=operation['content'], author_username=g.nodes[target]['fields']['username'], created_at='2026-01-01T01:00:00Z', likes=[], comments=[])
        g.edge(target, 'Post', key)
        return key
    if op == 'channel':
        found = set()
        for msg in g.adjacent(target, 'Posted', incoming=True):
            found.update(g.walk(msg, 'ReplyTo', incoming=True))
        return sorted(found)
    if op == 'post_reply':
        key = operation['new_id']
        g.node(key, 'Message', content=operation['content'], created_at='2026-01-01T01:00:00Z')
        g.edge(key, 'ReplyTo', target)
        g.edge(key, 'AuthoredBy', operation['author'])
        return key
    if op == 'tree':
        return sorted(g.walk(target, 'Contains', visible=True))
    if op == 'list_folder':
        return sorted(k for k in g.adjacent(target, 'Contains') if not g.nodes[k]['fields'].get('trashed', False))
    if op == 'trash':
        g.nodes[target]['fields']['trashed'] = True
        return True
    if op == 'mkdir':
        key = operation['new_id']
        g.node(key, 'Folder', name='new-folder', trashed=False, created_at='', updated_at='')
        g.edge(target, 'Contains', key)
        return key
    raise ValueError(f'unknown operation {op}')


def session(app, config, graph=None):
    if app == 'linked_list':
        return [dict(op=op, target='item:0', **kwargs) for op, kwargs in [('traverse', {}), ('sum', {}), ('find', {'value':0}), ('find', {'value':config['length']//2}), ('find', {'value':config['length']-1}), ('find', {'value':-1})]]
    if app == 'littlex':
        graph = graph or make_graph(app, config, random.Random(42))
        unfollowed = next(f'user:{i}' for i in range(1, config['users']) if f'user:{i}' not in graph.adjacent('user:0', 'Follow'))
        return [dict(op='feed', target='user:0'), dict(op='feed', target='user:0', search='#topic1'), dict(op='like', target='post:1:0', username='user_0000'), dict(op='like', target='post:1:0', username='user_0000'), dict(op='follow', target='user:0', other=unfollowed), dict(op='feed', target='user:0'), dict(op='create_tweet', target='user:0', new_id='post:session:0', content='session post #topic1'), dict(op='feed', target='user:0')]
    if app == 'jacord':
        return [dict(op='channel', target='channel:0'), dict(op='channel', target='channel:1'), dict(op='post_reply', target='message:0:0', new_id='reply:session:0', content='session reply', author='user:0'), dict(op='channel', target='channel:0')]
    return [dict(op='list_folder', target='folder:root'), dict(op='tree', target='folder:root'), dict(op='trash', target='folder:root/0'), dict(op='tree', target='folder:root'), dict(op='mkdir', target='folder:root', new_id='folder:session:0'), dict(op='list_folder', target='folder:root'), dict(op='tree', target='folder:root')]


def revision(path):
    def git(*args):
        p = subprocess.run(['git', '-C', str(path), *args], capture_output=True, text=True)
        if p.returncode:
            raise RuntimeError(f'cannot identify source checkout: {path}')
        return p.stdout.strip()
    return dict(commit=git('rev-parse', 'HEAD'), dirty=bool(git('status', '--porcelain')), path=str(path.resolve()))


def write_jsonl(path, records):
    with path.open('wb') as f:
        for row in records:
            f.write(encoded(row))


def build(output, app, scale, seed, source_root):
    config = SCALES[scale]
    g = make_graph(app, config, random.Random(seed))
    output.mkdir(parents=True, exist_ok=False)
    write_jsonl(output/'nodes.jsonl', g.nodes.values())
    write_jsonl(output/'edges.jsonl', g.edges)
    node_counts, edge_counts = dict(Counter(n['type'] for n in g.nodes.values())), dict(Counter(e['type'] for e in g.edges))
    operations = session(app, config, g)
    expected = []
    for i, operation in enumerate(operations):
        expected.append(dict(step=i, result=result(g, operation)))
    write_jsonl(output/'operations.jsonl', (dict(step=i, **op) for i, op in enumerate(operations)))
    write_jsonl(output/'expected.jsonl', expected)
    source_path = source_root / {'linked_list':'jaseci_external_tools', 'littlex':'jaseci_external_tools', 'jacord':'Jacord', 'jdrive':'JDrive'}[app]
    source = revision(source_path)
    # Snapshot actual source bytes as well as HEAD, since some checkouts are dirty.
    relfiles = {'linked_list':['linked_list/main.jac'], 'littlex':['littlex5/server.jac'], 'jacord':['server.jac','server.impl.jac'], 'jdrive':['server.jac','server.impl.jac']}[app]
    source['files'] = {p:hashlib.sha256((source_path/p).read_bytes()).hexdigest() for p in relfiles}
    manifest = dict(format_version=1, generator_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), app=app, scale=scale, seed=seed, distribution='synthetic', config=config, nodes_by_type=node_counts, edges_by_type=edge_counts, steps=len(operations), source=source, files={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(output.glob('*.jsonl'))}, native_import_status='pending', native_replay_status='pending', logical_id_policy='adapter maps logical IDs to runtime IDs; preserve edge insertion order')
    (output/'manifest.json').write_bytes(encoded(manifest))
    return manifest


def validate(path):
    manifest = json.loads((path/'manifest.json').read_text())
    for name, checksum in manifest['files'].items():
        if hashlib.sha256((path/name).read_bytes()).hexdigest() != checksum:
            raise ValueError(f'checksum mismatch: {name}')
    def rows(name):
        return [json.loads(line) for line in (path/name).read_text().splitlines()]
    g = Graph()
    for n in rows('nodes.jsonl'):
        g.node(n['id'], n['type'], **n['fields'])
    for e in rows('edges.jsonl'):
        g.edge(e['source'], e['type'], e['target'])
    if dict(Counter(n['type'] for n in g.nodes.values())) != manifest['nodes_by_type']:
        raise ValueError('node counts differ')
    if dict(Counter(e['type'] for e in g.edges)) != manifest['edges_by_type']:
        raise ValueError('edge counts differ')
    ops, answers = rows('operations.jsonl'), rows('expected.jsonl')
    if len(ops) != len(answers) or len(ops) != manifest['steps']:
        raise ValueError('operation count differs')
    for i, (op, expected) in enumerate(zip(ops, answers)):
        if op['step'] != i or expected['step'] != i or result(g, op) != expected['result']:
            raise ValueError(f'oracle mismatch at step {i}')
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    generate = sub.add_parser('build')
    generate.add_argument('--output', type=Path, required=True)
    generate.add_argument('--app', choices=(*APPS, 'all'), default='all')
    generate.add_argument('--scale', choices=SCALES, default='smoke')
    generate.add_argument('--seed', type=int, default=42)
    generate.add_argument('--source-root', type=Path, default=Path(__file__).resolve().parents[3])
    check = sub.add_parser('validate')
    check.add_argument('path', type=Path)
    args = parser.parse_args()
    if args.command == 'validate':
        manifests = sorted(args.path.glob('*/manifest.json'))
        paths = [m.parent for m in manifests] if manifests else [args.path]
        for path in paths:
            m = validate(path)
            print(f'{m["app"]}: logical replay passed ({m["steps"]} steps)')
    else:
        for app in APPS if args.app == 'all' else [args.app]:
            manifest = build(args.output/app, app, args.scale, args.seed, args.source_root)
            print(f'{app}: {sum(manifest["nodes_by_type"].values())} nodes, {sum(manifest["edges_by_type"].values())} edges')


if __name__ == '__main__':
    main()
