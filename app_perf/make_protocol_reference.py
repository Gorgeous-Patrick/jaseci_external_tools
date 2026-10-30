#!/usr/bin/env python3
"""Create a disclosed SQL-only boundary-reference overlay; never used by apps."""
import difflib
import hashlib
import json
from pathlib import Path
import shutil

OWN = Path(__file__).resolve().parent
source = OWN / 'runtime-5f94eb62d-v2'
target = OWN / 'runtime-protocol-reference-v2-5f94eb62d'
target.mkdir(exist_ok=False)
shutil.copytree(source / 'jac', target / 'jac', ignore=shutil.ignore_patterns('__pycache__', '.jac'))
relative = Path('jac/jaclang/data/impl/pgwire.impl.jac')
path = target / relative
old = path.read_text()
new = "import time as _perf_boundary_time;\nglob _perf_boundary_records: list = [];\n" + old
begin = new.index('        sock.sendall(\n', new.index('impl PgWireConnection.run('))
end = new.index('        oids: list[int]', begin)
frame = new[begin:end].replace('        sock.sendall(\n', '        _perf_boundary_frame = (\n', 1)
replacement = frame + '        _perf_boundary_send_ns = _perf_boundary_time.perf_counter_ns();\n        sock.sendall(_perf_boundary_frame);\n\n'
new = new[:begin] + replacement + new[end:]
new = new.replace("            if mtype == 'Z' {\n", "            if mtype == 'Z' {\n                _perf_boundary_ready_ns = _perf_boundary_time.perf_counter_ns();\n                _perf_boundary_records.append((sql, _perf_boundary_send_ns, _perf_boundary_ready_ns));\n")
assert new.count('_perf_boundary_send_ns =') == 1 and new.count('_perf_boundary_ready_ns =') == 1
path.chmod(0o644)
path.write_text(new)
path.chmod(0o444)
patch = ''.join(difflib.unified_diff(old.splitlines(True), new.splitlines(True), fromfile=str(relative), tofile=str(relative)))
(target / 'boundary-reference.patch').write_text(patch)
(target / 'overlay.json').write_text(json.dumps(dict(purpose='SQL-only minimally intrusive protocol-clock reference, not application runtime',
    base_manifest_sha256=hashlib.sha256((source / 'snapshot.json').read_bytes()).hexdigest(),
    patched_file=str(relative), original_sha256=hashlib.sha256(old.encode()).hexdigest(),
    overlay_sha256=hashlib.sha256(new.encode()).hexdigest(), patch=patch), indent=2) + '\n')
print(target)
