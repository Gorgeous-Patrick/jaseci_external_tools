"""Export TTG facts from a trusted local Jac compilation, without running a walker.

Use --jir for an existing compiled module, or --source with the Jac Python
environment to compile a new module. Output is a portable compiler sidecar;
capture adapters can join this to a graph and request/SQL evidence bundle.
"""
import argparse
import hashlib
import json
import marshal
from pathlib import Path
from export_bundle import compiler_records, read_jir


def main():
    p = argparse.ArgumentParser(description=__doc__)
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument('--jir', type=Path)
    group.add_argument('--source', type=Path)
    p.add_argument('--output', required=True, type=Path)
    a = p.parse_args()
    source = (a.jir or a.source).resolve()
    before = source.read_bytes()
    if a.jir:
        code = read_jir(source)
    else:
        # Compiler only: do not Jac.import/spawn or execute the module body.
        from jaclang.compiler.driver.program import JacProgram
        program = JacProgram()
        ir = program.compile(file_path=str(source), use_str=before.decode())
        if program.errors_had:
            raise RuntimeError('\n'.join(map(str, program.errors_had)))
        code = marshal.loads(ir.gen.py_bytecode)
    plans, hooks = compiler_records(code)
    if source.read_bytes() != before:
        raise RuntimeError('Source changed during export')
    data = dict(schema='jac.ttg.compiler', version=1,
                source=dict(path=str(source), sha256=hashlib.sha256(before).hexdigest()),
                plans=plans, hooks=hooks)
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(data, indent=2) + '\n')
    print(f'{len(plans)} walkers, {len(hooks)} hook callsites → {a.output}')


if __name__ == '__main__':
    main()
