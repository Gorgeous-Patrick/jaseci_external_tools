#!/usr/bin/env python3
"""Compile/analyze diagnostic plans without executing app entries or walkers."""
import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
import jaclang
from jaclang.compiler.driver.program import JacProgram
from jaclang.compiler.frontend import unitree as uni
from jaclang.runtime.ttg_dependencies import compile_checkpoint_plan

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--preflight', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
args.preflight=args.preflight.resolve();args.output=args.output.resolve()
index = json.loads(args.preflight.read_text())
results = []
for case in index['cases']:
    if case['policy'] != 'none':
        continue
    source = Path(case['evidence']['path']).parent / 'server.jac'
    os.chdir(source.parent)
    sys.path.insert(0,str(source.parent))
    program = JacProgram()
    module = program.compile(str(source), no_cgen=True)
    assert not program.errors_had, str(program.errors_had)
    plans = []
    for arch in module.get_all_sub_nodes(uni.Archetype):
        if arch.arch_type.value != 'walker':
            continue
        plan = compile_checkpoint_plan(arch)
        locations = []
        nodes = [arch] + list(arch.get_all_sub_nodes(uni.UniNode))
        for event in plan['events']:
            if event['kind'] != 'barrier':
                continue
            possible = []
            for node in nodes:
                if node.loc.first_line == event['line'] and node.loc.col_start == event['column']:
                    path = Path(node.loc.mod_path)
                    text = path.read_text().splitlines() if path.is_file() else []
                    possible.append(dict(path=str(path), node_type=type(node).__name__, line=event['line'],
                        column=event['column'], source_excerpt=text[event['line']-1] if 0 < event['line'] <= len(text) else None))
            locations.append(dict(event_id=event['id'], ability=event['ability'], possible_source_locations=possible,
                interpretation='Compiler dependency-analysis barrier; source retained, no guessed dynamic demand'))
        plans.append(dict(plan=plan, barriers=locations,
            supported_typed_visits=sum(e['kind']=='visit' for e in plan['events']),
            barrier_count=sum(e['kind']=='barrier' for e in plan['events'])))
    results.append(dict(app=case['app'], source=str(source), source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(), walkers=plans))
    print(case['app'],len(plans),flush=True)
args.output.write_text(json.dumps(dict(scope='Static diagnostic compiler plans; not observed executions or performance results', apps=results), indent=2)+'\n')
