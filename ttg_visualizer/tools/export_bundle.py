"""Export real compiler artifacts + sealed evidence, without executing an app.

Run with the Python version that produced the JIR (3.14 for the included case).
JIR/marshal is accepted only from a trusted LOCAL compiler cache, never uploads.
The browser accepts the resulting JSON data contract, never bytecode.
"""
from __future__ import annotations
import argparse
import dis
import gzip
import hashlib
import json
import marshal
import re
import struct
import sys
import types
from pathlib import Path


def sha(data):
    return hashlib.sha256(data).hexdigest()


def load_jsonl(path):
    opener = gzip.open if path.suffix == '.gz' else open
    with opener(path, 'rt') as f:
        for line, text in enumerate(f, 1):
            if text.strip():
                yield line, json.loads(text)


def read_jir(path):
    data = path.read_bytes()
    if data[:4] != b'JIR\0':
        raise ValueError('Not a Jac JIR artifact')
    py = struct.unpack_from('<H', data, 6)[0]
    if py != sys.version_info.major * 256 + sys.version_info.minor:
        raise ValueError(f'Use Python {py >> 8}.{py & 255} for this compiler artifact')
    pos = data.find(b'JIRX', 32)
    if pos < 0:
        raise ValueError('JIR has no compiled sections')
    pos += 4
    while pos + 5 <= len(data):
        kind, length = data[pos], struct.unpack_from('<I', data, pos + 1)[0]
        pos += 5
        if pos + length > len(data):
            raise ValueError('Truncated JIR section')
        if kind == 2:
            code = marshal.loads(data[pos:pos + length])
            if not isinstance(code, types.CodeType):
                raise ValueError('Expected compiler code object')
            return code
        if kind == 255:
            break
        pos += length
    raise ValueError('No Python bytecode section')


def compiler_records(code):
    """Read constants and actual hook callsites; do not execute code objects."""
    plans, hooks = {}, []
    def visit(c):
        for value in c.co_consts:
            if isinstance(value, types.CodeType):
                visit(value)
            elif isinstance(value, str) and value.startswith('{') and '"walker_name"' in value:
                spec = json.loads(value)
                if 'events' in spec:
                    name = spec['walker_name']
                    if name in plans and plans[name] != spec:
                        raise ValueError(f'Conflicting plans: {name}')
                    plans[name] = spec
        instructions = list(dis.get_instructions(c))
        for i, ins in enumerate(instructions):
            if ins.opname not in ('LOAD_GLOBAL', 'LOAD_ATTR') or ins.argval not in ('ttg_checkpoint', 'ttg_prefetch_observe'):
                continue
            # Emitted signature: hook(self, serialized_plan, point, __class__).
            tail = instructions[i + 1:i + 7]
            serialized = next((x.argval for x in tail if x.opname == 'LOAD_CONST' and isinstance(x.argval, str) and '"walker_name"' in x.argval), None)
            point = next((x.argval for x in tail if x.opname in ('LOAD_CONST', 'LOAD_SMALL_INT') and type(x.argval) is int), None)
            if serialized is None or point is None:
                raise ValueError('Unrecognized compiler hook ABI')
            spec = json.loads(serialized)
            hooks.append(dict(walker=spec['walker_name'], event=point,
                function=ins.argval, code_qualname=c.co_qualname,
                bytecode_offset=ins.offset, bytecode_line=ins.positions.lineno,
                evidence='compiled_bytecode_callsite'))
    visit(code)
    return plans, hooks


def source_location(event, sources, walker):
    """Annex bodies use impl line numbers; entry events use declarations.

    Existing TTG events lack filenames. Resolve only unambiguous ability impls;
    preserve the raw event and explicitly label this adapter resolution.
    """
    line = event['line']
    impls = []
    for name, source in sources.items():
        for i, text in enumerate(source['lines'], 1):
            if re.search(r'\bimpl\s+' + re.escape(walker + '.' + event['ability']) + r'\b', text):
                impls.append((name, i))
    declaration = next((name for name in sources if name.endswith('.jac') and not name.endswith('.impl.jac')), None)
    if event['kind'] in ('entry', 'exit'):
        return dict(file=declaration, line=line, resolution='compiler_declaration_position',
                    body_file=impls[0][0] if len(impls) == 1 else declaration,
                    body_line=impls[0][1] if len(impls) == 1 else line)
    if len(impls) == 1:
        name, start = impls[0]
        lines = sources[name]['lines']
        end = next((i for i, text in enumerate(lines, 1)
                    if i > start and re.match(r'\s*impl\s+', text)), len(lines) + 1)
        if start <= line < end:
            return dict(file=name, line=line, resolution='annex_ability_mapping')
    return dict(file=declaration, line=line, resolution='declaration_file_fallback')


def sql_descriptors(value, path=''):
    if isinstance(value, dict):
        if 'sql' in value and 'slots' in value:
            yield path, value
        else:
            for key, child in value.items():
                yield from sql_descriptors(child, path + '/' + str(key))
    elif isinstance(value, list):
        for i, child in enumerate(value):
            yield from sql_descriptors(child, path + '/' + str(i))


def export(case, jir, output, walker):
    seal = json.loads((case / 'artifacts.json').read_text())
    if seal.get('passed') is not True:
        raise ValueError('Case archive did not pass')
    refs = {}
    def verified(path):
        data = path.read_bytes()
        rel = str(path.relative_to(case))
        digest = sha(data)
        if seal['files'].get(rel) != digest:
            raise ValueError(f'Case source/evidence hash mismatch: {rel}')
        refs[rel] = dict(sha256=digest, bytes=len(data))
        return data
    summary = json.loads(verified(case / 'summary.json'))
    if summary.get('passed') is not True:
        raise ValueError('Case summary not passed')
    sources = {p.name: dict(text=verified(p).decode(), sha256=sha(p.read_bytes()))
               for p in case.glob('*.jac') if p.is_file()}
    for s in sources.values():
        s['lines'] = s['text'].splitlines()
    plans, hooks = compiler_records(read_jir(jir))
    if walker not in plans:
        raise ValueError(f'Walker absent in compiler artifact: {walker}')
    plan = plans[walker]
    events = [dict(e, location=source_location(e, sources, walker)) for e in plan['events']]
    hooks = [dict(h, id=f"hook-{h['event']}-{h['bytecode_offset']}",
                  placement='ability_entry' if plan['events'][h['event']]['kind'] == 'entry' else
                  ('before_statement' if h['function'] == 'ttg_prefetch_observe' else 'after_statement'))
             for h in hooks if h['walker'] == walker]
    regions = []
    for key, r in plan.get('interability_regions', {}).get('regions', {}).items():
        metadata = {k: v for k, v in r.items() if k not in ('templates', 'native', 'gated', 'open')}
        regions.append(dict(id='region-' + key, entry=int(key), metadata=metadata,
                            templates=[path for path, _ in sql_descriptors(r, '/interability_regions/regions/' + key)]))
    templates = [dict(id=path, sql=d['sql'], sql_sha256=sha(d['sql'].encode()),
                      params=d['params'], slots=d['slots'], nonnegative_slots=d.get('nonnegative_slots', []))
                 for path, d in sql_descriptors(plan)]
    dataset = json.loads(verified(case / 'fixture-canonical.json'))['dataset_files']
    def dataset_rows(name):
        p = case / 'dataset' / name
        b = p.read_bytes()
        if sha(b) != dataset[name]:
            raise ValueError('Fixture digest mismatch: ' + name)
        refs['dataset/' + name] = dict(sha256=sha(b), bytes=len(b))
        return [json.loads(l) for l in b.decode().splitlines() if l.strip()]
    nodes, edges = dataset_rows('nodes.jsonl'), dataset_rows('edges.jsonl')
    mapping = json.loads(verified(case / 'mapping-initial.json'))
    reverse = {v.replace('-', ''): k for k, v in mapping.items()}
    nodes = [dict(n, runtime_id=mapping.get(n['id'])) for n in nodes]
    verified(case / 'http-raw.jsonl')
    http_records = list(load_jsonl(case / 'http-raw.jsonl'))
    if summary['app'] == 'littlex':
        # Framework roots are absent from domain nodes.jsonl. Recover only
        # witnessed roots and actual root edges from the sealed seed census.
        imports = [r for _, r in http_records if r.get('path') == '/walker/SuiteImport']
        if len(imports) != 1:
            raise ValueError('Expected one sealed LittleX import')
        roots = imports[0]['output']['data']['result']['roots']
        witnessed = {str(v).replace('-', '') for _, r in http_records
                     if r.get('path') == '/walker/SuiteRoot'
                     for v in r['output']['data']['reports']}
        root_ids = {}
        for user, uid in roots.items():
            uid = uid.replace('-', '')
            if uid not in witnessed:
                raise ValueError('Root lacks a SuiteRoot witness')
            logical = 'root:' + user
            root_ids[uid] = logical
            nodes.append(dict(id=logical, type='Root', fields={}, runtime_id=uid,
                              evidence='SuiteRoot + SuiteImport roots'))
        census = json.loads(verified(case / 'fixture-raw.json'))
        for row in census:
            src, dst = str(row.get('src')).replace('-', ''), str(row.get('dst')).replace('-', '')
            if row['kind'] == 'EdgeAnchor' and src in root_ids and dst in reverse:
                edges.append(dict(source=root_ids[src], target=reverse[dst], type=row['arch_type'],
                                  undirected=row['undirected'], runtime_id=row['id'], evidence='fixture-raw.json'))
    requests = []
    for line, r in http_records:
        route = r.get('path', '').rstrip('/')
        if r.get('phase') != 'workflow' or not (route == '/walker/' + walker or route.startswith('/walker/' + walker + '/')):
            continue
        result = (r.get('output', {}).get('data') or {}).get('result') or {}
        # JDrive adapter: native depths is an observed traversal result, NOT SQL membership.
        visited = [reverse[x.replace('-', '')] for x in result.get('depths', {}) if x.replace('-', '') in reverse]
        requests.append(dict(id=r['request'], path=r['path'], phase=r['phase'],
                             visited=visited, evidence=dict(file='http-raw.jsonl', line=line),
                             native_visited_semantics=('Reported depths keys (JDrive adapter)' if summary['app'] == 'jdrive' else 'No complete per-node visit trace retained; feed output is not a visit log'), queries=[]))
    by_request = {r['id']: r for r in requests}
    for p in sorted(case.glob('*.calls.jsonl.gz')):
        verified(p)
        for line, q in load_jsonl(p):
            rid = q.get('origin_request_id')
            if rid not in by_request:
                continue
            sql = q.get('original_sql') or q['sql']
            normalized = sql.lstrip().upper()
            category = 'control' if normalized.startswith(('BEGIN', 'COMMIT', 'ROLLBACK', 'SAVEPOINT', 'RELEASE', 'DISCARD', 'SET ')) else 'data'
            matches = [t['id'] for t in templates if t['sql'] == sql]
            by_request[rid]['queries'].append(dict(id=f'{p.name}:{line}', sql=sql,
                sql_sha256=sha(sql.encode()), template_ids=matches, template_match='exact_sql_text' if matches else 'unmatched',
                role=q.get('role'), executor=q.get('actual_executor'), category=category,
                start_ns=q['send_ns'], end_ns=q['ready_ns'], duration_ms=(q['ready_ns'] - q['send_ns']) / 1e6,
                rows=q.get('returned_rows'), backend_pid=q.get('backend_pid'), thread_id=str(q.get('thread_id')),
                evidence=dict(file=p.name, line=line)))
    for r in requests:
        r['queries'].sort(key=lambda q: q['start_ns'])
        origin = min((q['start_ns'] for q in r['queries']), default=0)
        for q in r['queries']:
            q['start_ms'] = (q['start_ns'] - origin) / 1e6
            q['end_ms'] = (q['end_ns'] - origin) / 1e6
    bundle = dict(schema='jac.ttg.visualization', version=1, title=f'{summary["app"]} · {walker}',
        walker=walker, sources=sources, compiler=dict(plan=plan, events=events, edges=plan['edges'],
        hooks=hooks, regions=regions, templates=templates), graph=dict(nodes=nodes, edges=edges,
        state='Initial fixture before workflow mutations; not a per-request database snapshot'),
        requests=requests, provenance=dict(case=str(case), case_seal_sha256=sha((case/'artifacts.json').read_bytes()),
        compiler_artifact=dict(path=str(jir), sha256=sha(jir.read_bytes()),
            status='Local compiler cache; not included in original case seal. Constants read without execution.'),
        verified_files=refs), limitations=[
        'Hook callsites are compiler evidence; this capture has no per-hook firing log.',
        'SQL/template links use exact original SQL text, not inferred timing or fingerprints.',
        'Initial graph and native reported visits are separate; later request mutations are not replayed.',
        'A compiler output-tree certificate can accept a region rejected by the generic effect summary.',
        'An SQL region predicts access; output operations and native walker execution remain in Jac.'])
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(bundle, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(dict(output=str(output), bytes=output.stat().st_size, nodes=len(nodes),
        events=len(events), hooks=len(hooks), regions=len(regions), templates=len(templates), requests=len(requests))))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case', required=True, type=Path)
    parser.add_argument('--jir', required=True, type=Path)
    parser.add_argument('--walker', default='VisibleFolderTree')
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    export(args.case.resolve(), args.jir.resolve(), args.output, args.walker)
