#!/usr/bin/env python3
"""AST audit of every frozen app: only declared walker state sets become schema."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import jaclang
from jaclang.compiler.driver.program import JacProgram
from jaclang.compiler.frontend import unitree as uni

def tokens(node):
    return node.value if isinstance(node,uni.Token) else ' '.join(tokens(child) for child in node.kid)

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--suite',type=Path,required=True)
parser.add_argument('--output',type=Path,required=True)
args=parser.parse_args();root=args.suite.parent
registry=json.loads((root/'app_suite/registry.json').read_text())
original={'linked_list':['originals/linked_list/main.jac'],'littlex':['originals/littlex/server.jac'],
          'jacord':['originals/jacord/server.jac','originals/jacord/server.impl.jac'],
          'jdrive':['originals/jdrive/server.jac','originals/jdrive/server.impl.jac']}
schema={};inventory=[];state_fields=[];other_mentions=[]
for entry in registry['apps']:
    app=entry['app'];schema[app]={}
    paths=[root/name for name in original[app]] if app in original else sorted((root/'app_suite/apps'/app).glob('*.jac'))
    walkers=[]
    for path in paths:
        text=path.read_text();program=JacProgram();module=program.parse_str(text,str(path))
        assert not program.errors_had,str(program.errors_had)
        inventory.append({'app':app,'path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
        field_lines=set()
        for arch in module.get_all_sub_nodes(uni.Archetype):
            if arch.arch_type.value!='walker':continue
            walkers.append(arch.name.value)
            for field in arch.get_all_sub_nodes(uni.HasVar):
                owner=field.find_parent_of_type(uni.Archetype)
                if owner is not arch or field.type_tag is None:continue
                type_text=re.sub(r'\s+','',tokens(field.type_tag.tag))
                if not type_text.startswith('set['):continue
                assert type_text=='set[str]',('Unexpected declared set type requires explicit handling',app,arch.name.value,type_text)
                declaration={'element_type':'str','declared_type':type_text,'serialized_encoding':'python-set-repr',
                    'source':str(path),'source_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                    'line':field.loc.first_line,'column':field.loc.col_start,
                    'declaration_excerpt':text.splitlines()[field.loc.first_line-1],
                    'default':tokens(field.value) if field.value is not None else None}
                schema[app].setdefault(arch.name.value,{})[field.name.value]=declaration
                state_fields.append({'app':app,'walker':arch.name.value,'field':field.name.value,**declaration})
                field_lines.add(field.loc.first_line)
        for number,line in enumerate(text.splitlines(),1):
            if re.search(r'\bset\s*\[',line) and number not in field_lines:
                other_mentions.append({'app':app,'path':str(path),'line':number,'text':line,
                    'classification':'Local/parameter set annotation; not a declared walker state field'})
    print(app,len(walkers),len(schema[app]),flush=True)
assert len(schema)==30
result={'schema_version':1,'suite_manifest_sha256':hashlib.sha256(args.suite.read_bytes()).hexdigest(),
    'method':'Jac AST Archetype(walker) -> own HasVar.type_tag exactly set[str]; no regex ownership inference',
    'apps_scanned':30,'sources':inventory,'by_app':schema,'declared_state_sets':state_fields,
    'other_set_annotations':other_mentions,'no_apps_executed':True}
args.output.write_text(json.dumps(result,indent=2)+'\n');args.output.chmod(0o444)
print('Declared state sets:',[(r['app'],r['walker'],r['field']) for r in state_fields])
