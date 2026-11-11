import json
from pathlib import Path
from collections import Counter
from jaclang.runtime.ttg_access_graph import analyze_source
from jaclang.compiler.frontend.parser.frontend import parse
from jaclang.compiler.frontend import unitree as u
root=Path('/home/baichuan/jaseci')
base=root/'reproduction/ttg-app-performance/suite-final-20261030-v1'
out=root/'project-notes/measurements/ttg-access-visit-20261110'
summary={}
for name,path,impl in [('littlex',base/'originals/littlex/server.jac',None),('jdrive',base/'originals/jdrive/server.jac',base/'originals/jdrive/server.impl.jac'),('recipe_pantry',base/'app_suite/apps/recipe_pantry/server.jac',None)]:
 sources=[(path.read_text(),str(path))]+([(impl.read_text(),str(impl))] if impl else [])
 g=analyze_source(*sources[0],annexes=sources[1:])
 (out/(name+'-graph-v2.json')).write_text(json.dumps(g,indent=2)+'\n')
 actual=Counter((n['kind'],n['file'],n['line'],n['column']) for n in g['nodes'] if n['kind'] in ['Access','Visit'])
 expected=Counter()
 def walk(n):
  if isinstance(n,u.EdgeRefTrailer):expected[('Access',n.loc.mod_path,n.loc.first_line,n.loc.col_start)]+=1
  if isinstance(n,u.VisitStmt):expected[('Visit',n.loc.mod_path,n.loc.first_line,n.loc.col_start)]+=1
  for child in n.kid:walk(child)
 for source,filename in sources:
  ast,failed=parse(source,filename);assert not failed;walk(ast)
 summary[name]={'accesses':sum(n['kind']=='Access' for n in g['nodes']),'visits':sum(n['kind']=='Visit' for n in g['nodes']),'missing':[list(k)+[v] for k,v in (expected-actual).items()],'extra':[list(k)+[v] for k,v in (actual-expected).items()],'unmatched_implementations':g['unmatched_implementations']}
print(json.dumps(summary,indent=2))
(out/'app-inventory-v2.json').write_text(json.dumps(summary,indent=2)+'\n')
