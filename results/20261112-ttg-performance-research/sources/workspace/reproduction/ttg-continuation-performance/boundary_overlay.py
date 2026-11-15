"""Build the disclosed direct PgWire/child observer in an OWNED snapshot only.

Pure transform functions can be tested without compiling/running any runtime.
The CLI requires a main-supplied tested immutable snapshot manifest. It never
copies or edits the mutable live runtime; target must be new and owned.
"""
import argparse
import difflib
import json
from pathlib import Path
import shutil
from evidence import checked_ref, read_json, sha256
from gate import check_tree, require

OWN=Path(__file__).resolve().parent
PGWIRE=Path('jac/jaclang/data/impl/pgwire.impl.jac')
PREFETCH=Path('jac/jaclang/runtime/prefetch.jac')
PROCESS=Path('jac/jaclang/runtime/ttg_process_reader.jac')


def once(text,old,new):
    if text.count(old)!=1: raise ValueError('Overlay source anchor changed: '+old[:90])
    return text.replace(old,new,1)


def imports(source,header):
    # Jac requires a module docstring to remain the first source element.
    if source.startswith(('"""', "'''")):
        delimiter=source[:3];end=source.find(delimiter,3)
        if end<0: raise ValueError('Unterminated module docstring')
        end+=3
        return source[:end]+'\n'+header+source[end:]
    return header+source


def pgwire(source):
    source=once(source,"        } elif mtype == 'K' {\n            continue;",
        "        } elif mtype == 'K' {\n            _perf_sink.connected(self, struct.unpack('!I', payload[:4])[0]);\n            continue;")
    begin=source.index('impl PgWireConnection.run(')
    end=source.index('\n\nimpl PgWireConnection.close',begin)
    before,body,after=source[:begin],source[begin:end],source[end:]
    body=once(body,"    assert not self._closed",'''    _perf_driver_start = _perf_clock.perf_counter_ns();
    _perf_origin = _perf_sink.binding();
    _perf_thread_id = _perf_threading.get_ident();
    _perf_c = 0;
    _perf_d = 0;
    _perf_d_bytes = 0;
    _perf_errors = 0;
    _perf_ready_count = 0;
    _perf_send_ns: any = None;
    _perf_ready_ns: any = None;
    _perf_frame: any = None;
    _perf_sent = False;
    assert not self._closed''')
    start=body.index('        sock.sendall(\n')
    end=body.index('        oids: list[int]',start)
    frame=body[start:end].replace('        sock.sendall(\n','        _perf_frame = (\n',1)
    body=body[:start]+frame+'''        _perf_send_ns = _perf_clock.perf_counter_ns();
        sock.sendall(_perf_frame);
        _perf_sent = True;

'''+body[end:]
    body=once(body,"            if mtype in ('1', '2', '3', 'C', 'n', 's') {\n",
        "            if mtype in ('1', '2', '3', 'C', 'n', 's') {\n                if mtype == 'C' { _perf_c += 1; }\n")
    body=once(body,"            if mtype == 'D' {\n",
        "            if mtype == 'D' {\n                _perf_d += 1;\n                _perf_d_bytes += len(payload);\n")
    body=once(body,"            if mtype == 'E' {\n",
        "            if mtype == 'E' {\n                _perf_errors += 1;\n")
    body=once(body,"            if mtype == 'Z' {\n",
        "            if mtype == 'Z' {\n                _perf_ready_ns = _perf_clock.perf_counter_ns();\n                _perf_ready_count += 1;\n")
    record='''_perf_driver_end = _perf_clock.perf_counter_ns();
_perf_sink.record_boundary(
    self, pos_sql, sql, _perf_origin, _perf_thread_id,
    _perf_driver_start, _perf_send_ns, _perf_ready_ns, _perf_driver_end,
    _perf_c, _perf_d, _perf_d_bytes, _perf_errors, _perf_ready_count,
    len(rows), ERROR, _perf_frame, _perf_sent
);'''
    normal='\n'.join('                '+line for line in record.replace('ERROR','None').splitlines())
    failure='\n'.join('        '+line for line in record.replace('ERROR','f"{type(e).__name__}: {e}"').splitlines())
    body=once(body,'                return rows;',normal+'\n                return rows;')
    body=once(body,'        raise;\n',failure+'\n        raise;\n')
    return imports(before+body+after,'import time as _perf_clock;\nimport threading as _perf_threading;\n'
        'import continuation_probe as _perf_sink;\n')


def prefetch(source):
    source=imports(source,'import continuation_probe as _perf_sink;\n')
    # Explicit launch sites only; no global Thread monkeypatch or added joins.
    source=once(source,'\n            thread.start();\n',
        "\n            _perf_sink.bind_worker_thread(thread, 'ipc_parent_thread');\n            thread.start();\n")
    source=once(source,'\n            t.start();\n',
        "\n            _perf_sink.bind_worker_thread(t, 'thread');\n            t.start();\n")
    source=once(source,'\n        t.start();\n',
        "\n        _perf_sink.bind_worker_thread(t, 'thread');\n        t.start();\n")
    return source


def process(source):
    source=imports(source,'import continuation_probe as _perf_sink;\nimport time as _perf_clock;\n')
    source=once(source,'            bufsize=1\n',
        '            bufsize=1,\n            env=_perf_sink.child_environment()\n')
    source=once(source,'        self.startup_ms = (perf_counter() - started) * 1000;\n',
        '''        self.startup_ms = (perf_counter() - started) * 1000;
        _perf_sink.event('process_reader_ready', child_process_pid=self.process.pid,
            startup_ms=self.startup_ms, startup_included=True);
''')
    start=source.index('    def load(ids:')
    end=source.index('\n    def close',start)
    before,body,after=source[:start],source[start:end],source[end:]
    body=once(body,'        with self.lock {\n',
        '        _perf_transfer_start = _perf_clock.perf_counter_ns();\n        with self.lock {\n')
    body=once(body,'            self.process.stdin.flush();\n',
        '            self.process.stdin.flush();\n            _perf_write_end = _perf_clock.perf_counter_ns();\n')
    body=once(body,'            line = self.process.stdout.readline();\n',
        '            line = self.process.stdout.readline();\n            _perf_response_line = _perf_clock.perf_counter_ns();\n')
    body=once(body,'            return rows;\n',
        '''            _perf_transfer_end = _perf_clock.perf_counter_ns();
            _perf_sink.event('process_reader_transfer', child_process_pid=self.process.pid,
                start_ns=_perf_transfer_start, write_end_ns=_perf_write_end,
                response_line_ns=_perf_response_line, end_ns=_perf_transfer_end,
                returned_rows=len(rows), response_wait_includes_child_work=True);
            return rows;
''')
    return before+body+after


def build(runtime_manifest,target):
    target=target.resolve()
    require(target.is_relative_to(OWN) and target!=OWN,'Overlay target must be a NEW owned snapshot directory')
    require(not target.exists(),'Overlay target already exists')
    base=check_tree(runtime_manifest)
    require(base.get('kind')=='runtime_snapshot' and base.get('immutable') is True,'Immutable runtime snapshot required')
    require(base.get('continuation_dispatch')=='runtime_hooks','Actual hook-driven continuation required')
    tests=read_json(checked_ref(base['test_evidence'],runtime_manifest.parent))
    require(tests.get('passed') is True,'Main-supplied tested runtime required')
    source=Path(base['root'])
    if not source.is_absolute(): source=runtime_manifest.parent/source
    require(source.resolve()!=Path('/home/baichuan/jaseci/jac-ttg'),'Mutable live runtime is forbidden')
    transformed={relative:transform((source/relative).read_text())
        for relative,transform in ((PGWIRE,pgwire),(PREFETCH,prefetch),(PROCESS,process))}
    # All anchors must validate before any target is created.
    output=target.parent/(target.name+'-overlay')
    require(not output.exists(),'Overlay metadata directory already exists')
    shutil.copytree(source,target,copy_function=shutil.copy2)
    patches=[]
    for relative,new in transformed.items():
        old=(source/relative).read_text()
        path=target/relative;path.chmod(0o644);path.write_text(new)
        patches.append(''.join(difflib.unified_diff(old.splitlines(True),new.splitlines(True),
            fromfile=str(relative),tofile=str(relative))))
    (target/'jac').chmod((target/'jac').stat().st_mode|0o200)
    shutil.copy2(OWN/'continuation_probe.py',target/'jac/continuation_probe.py')
    output.mkdir()
    patch=output/'boundary.patch';patch.write_text('\n'.join(patches))
    manifest=dict(kind='experiment_overlay',schema_version=1,root=str(target),
        base_runtime_manifest_sha256=sha256(runtime_manifest),same_for_all_configurations=True,
        patch=dict(path=str(patch),sha256=sha256(patch)),
        files={str(p.relative_to(target)):sha256(p) for p in sorted(target.rglob('*')) if p.is_file()},
        origins=[dict(path=str(OWN/'continuation_probe.py'),sha256=sha256(OWN/'continuation_probe.py'))],
        generator=dict(path=str(Path(__file__).resolve()),sha256=sha256(__file__)),
        semantics='Natural close and IPC payload untouched; child environment explicitly binds observation; counters only at C/D/E/Z branches',
        unvalidated_until='Final-runtime compilation, actual child SQL/CSV reconciliation, correctness and rotated overhead controls')
    (output/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    check_tree(output/'manifest.json')
    return output/'manifest.json'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-manifest',type=Path,required=True)
    parser.add_argument('--target',type=Path,required=True)
    args=parser.parse_args()
    print(build(args.runtime_manifest.resolve(),args.target))


if __name__=='__main__': main()
