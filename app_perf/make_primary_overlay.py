#!/usr/bin/env python3
"""Disclosed experiment-only PRIMARY instrumentation. Never edits live source."""
import difflib
import hashlib
import json
from pathlib import Path
import shutil

OWN = Path(__file__).resolve().parent
source = OWN / 'runtime-5f94eb62d-v2'
target = OWN / 'runtime-primary-boundary-5f94eb62d-v1'
target.mkdir(exist_ok=False)
shutil.copytree(source, target, dirs_exist_ok=True, ignore=shutil.ignore_patterns('__pycache__', '.jac', 'snapshot.json'))
relative = Path('jac/jaclang/data/impl/pgwire.impl.jac')
path = target / relative
old = path.read_text()
begin = old.index('impl PgWireConnection.run(')
end = old.index('\n\nimpl PgWireConnection.close', begin)
before, body, after = old[:begin], old[begin:end], old[end:]
header = 'import time as _perf_clock;\nimport threading as _perf_threading;\nimport driver_probe as _perf_sink;\n'
metadata = '''    _perf_rid = _perf_sink.request_id();
    _perf_thread = _perf_threading.current_thread();
    _perf_role = getattr(_perf_thread, '_perf_role', 'foreground');
    _perf_c = 0;
    _perf_d = 0;
    _perf_send_ns: any = None;
    _perf_ready_ns: any = None;
    _perf_frame: any = None;
    _perf_sent = False;
    _perf_driver_start = _perf_clock.perf_counter_ns();
'''
body = body.replace("    assert not self._closed", metadata + "    assert not self._closed", 1)
frame_begin = body.index('        sock.sendall(\n')
frame_end = body.index('        oids: list[int]', frame_begin)
packet = body[frame_begin:frame_end].replace('        sock.sendall(\n', '        _perf_frame = (\n', 1)
body = body[:frame_begin] + packet + '''        _perf_send_ns = _perf_clock.perf_counter_ns();
        sock.sendall(_perf_frame);
        _perf_sent = True;

''' + body[frame_end:]
body = body.replace("            if mtype in ('1', '2', '3', 'C', 'n', 's') {\n", "            if mtype in ('1', '2', '3', 'C', 'n', 's') {\n                if mtype == 'C' { _perf_c += 1; }\n", 1)
body = body.replace("            if mtype == 'D' {\n", "            if mtype == 'D' {\n                _perf_d += 1;\n", 1)
body = body.replace("            if mtype == 'Z' {\n", "            if mtype == 'Z' {\n                _perf_ready_ns = _perf_clock.perf_counter_ns();\n", 1)
record = '''_perf_driver_end = _perf_clock.perf_counter_ns();
                _perf_sink.record_boundary(
                    sql, _perf_rid, _perf_role, _perf_thread.ident, id(self),
                    _perf_driver_start, _perf_send_ns, _perf_ready_ns, _perf_driver_end,
                    _perf_c, _perf_d, len(rows), ERROR, _perf_frame, _perf_sent
                );'''
body = body.replace('                return rows;', '                ' + record.replace('ERROR', 'None') + '\n                return rows;', 1)
error_record = record.replace('ERROR', 'f"{type(e).__name__}: {e}"')
error_record = '\n'.join(line[8:] if line.startswith('        ') else line for line in error_record.splitlines())
body = body.replace('        raise;\n', '        ' + error_record + '\n        raise;\n', 1)
new = header + before + body + after
assert body.count('_perf_sink.record_boundary(') == 2
path.chmod(0o644)
path.write_text(new)
patch = ''.join(difflib.unified_diff(old.splitlines(True), new.splitlines(True), fromfile=str(relative), tofile=str(relative)))
(target / 'primary-boundary.patch').write_text(patch)
files = {str(p.relative_to(target)): hashlib.sha256(p.read_bytes()).hexdigest()
         for p in sorted(target.rglob('*')) if p.is_file()}
manifest = dict(schema_version=1, kind='runtime_overlay', commit=json.loads((source / 'snapshot.json').read_text())['commit'],
    base_runtime_manifest_sha256=hashlib.sha256((source / 'snapshot.json').read_bytes()).hexdigest(),
    purpose='Experiment-only direct PgWire send-to-Z and driver clock/counters, same overlay for all4 policies',
    patch_file='primary-boundary.patch', modified_source=str(relative), files=files,
    unknown_metrics=['received_bytes', 'data_row_payload_bytes', 'recv_calls'],
    semantics='Natural close preserved; counters only in C/D branches; metadata appended after end clock')
(target / 'snapshot.json').write_text(json.dumps(manifest, indent=2) + '\n')
for p in target.rglob('*'):
    if p.is_file():
        p.chmod(0o444 | (p.stat().st_mode & 0o111))
print(target)
