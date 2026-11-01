"""Tiny DB-free source-contract witnesses; not a native/Jac execution claim."""
import json
import sqlite3


class ActualTarget:
    pass


class ActualLink:
    pass


TargetAlias = ActualTarget
LinkAlias = ActualLink

# Exactly the distinction at source-v1 compile_templates: source Name tokens
# become dummy class names, while continuation_type resolves the real alias.
dummy = (type('LinkAlias', (object,), {}), type('TargetAlias', (object,), {}))
real = (LinkAlias, TargetAlias)
assert tuple(t.__name__ for t in dummy) == ('LinkAlias', 'TargetAlias')
assert tuple(t.__name__ for t in real) == ('ActualLink', 'ActualTarget')
db = sqlite3.connect(':memory:')
db.executescript('''
CREATE TABLE nodes(id TEXT, arch_type TEXT);
CREATE TABLE edges(id TEXT, src TEXT, dst TEXT, arch_type TEXT);
CREATE TABLE graph_types(type_name TEXT, ancestor TEXT);
INSERT INTO nodes VALUES ('B','ActualTarget');
INSERT INTO edges VALUES ('e1','A','B','ActualLink');
INSERT INTO graph_types VALUES ('ActualTarget','ActualTarget'),('ActualLink','ActualLink');
''')
sql = '''SELECT n.id,e.id FROM edges e JOIN nodes n ON n.id=e.dst
WHERE e.src=?
AND (e.arch_type=? OR e.arch_type IN (SELECT type_name FROM graph_types WHERE ancestor=?))
AND (n.arch_type=? OR n.arch_type IN (SELECT type_name FROM graph_types WHERE ancestor=?))'''


def select(types):
    edge, node = (t.__name__ for t in types)
    return db.execute(sql, ('A', edge, edge, node, node)).fetchall()


assert select(real) == [('B', 'e1')]
assert select(dummy) == []

# Minimal FIFO witness: source-v1's caller uses the hook's initial [B,C] even
# after the outer interpreter is already at B and supplies suffix [C].
assert ['B'] + ['B', 'C'] == ['B', 'B', 'C']
assert ['B'] + ['C'] == ['B', 'C']

# Minimal path-depth witness: semantic key has the full path and no actual upto.
shape = ('edge_AB', 'edge_BC')
full_key = ('ttg_compiled_pairs_v1', ('A',), shape, None)
cache = {full_key: ((('C', 'eBC'),), ())}
requested_upto = 1
assert cache[full_key][0] != (('B', 'eAB'),)
assert requested_upto != len(shape)  # repaired lookup must decline this hit
print(json.dumps({'alias_native': select(real), 'alias_emitted': select(dummy),
                  'stale_pending': ['B', 'B', 'C'], 'correct_pending': ['B', 'C'],
                  'prefix1_expected': 'B', 'full_key_wrong_result': cache[full_key][0][0][0],
                  'scope': 'independent tiny source-contract examples; no Jac/native/PG execution'}))
