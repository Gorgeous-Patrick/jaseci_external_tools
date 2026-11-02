"""Narrow export metadata regression after the actual48-case CLI completed."""
import ast,hashlib,importlib.util,inspect,json,sys
from pathlib import Path
ROOT=Path.cwd();OWN=ROOT/'reproduction/ttg-interability-performance'
E=ROOT/'project-notes/measurements/ttg-interability-performance-20261101'
sys.path.insert(0,str(OWN))
def read(p):return json.loads(p.read_text())
def ref(p):return dict(path=str(p.resolve()),sha256=hashlib.sha256(p.read_bytes()).hexdigest())
old=OWN/'ia_export.py';new=OWN/'ia_export_v2.py'
assert new.read_text()==old.read_text().replace("cache=plan['cache'],learning=plan['learning'],postgres=plan['postgres']", "regime=plan['regime'],postgres=plan['postgres']")
for name in ('dispersion','aggregate'):
 def function(p):return next(v for v in ast.parse(p.read_text()).body if isinstance(v,ast.FunctionDef) and v.name==name)
 assert ast.dump(function(old))==ast.dump(function(new))
spec=importlib.util.spec_from_file_location('_ia_actual_export_v2_regression',new)
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
assert Path(module.release.__code__.co_filename).resolve()==OWN/'ia_runner.py'
assert len(inspect.signature(module.release).parameters)==2
plan=read(E/'correctness-plan-v1/plan.json');results=read(E/'export-v2/results.json')
assert results['sample_counts']==dict(all=48,excluded_warmups=12,measured=36,cells=12,n_per_cell=3)
assert len(results['rows'])==12 and all(r['n']==3 for r in results['rows'])
assert results['definitions']['regime']==plan['regime'] and results['postprocessor']==ref(new)
assert results['sources']==plan['sources'] and results['index']==ref(E/'formal-v1/index.json')
assert (E/'export-v2.log').read_text().strip()==str(E/'export-v2/results.json')
for value in read(E/'export-v2/artifacts.json')['outputs']:assert ref(Path(value['path']))==value
candidate=read(E/'review-candidate-v1/manifest.json')
assert next(v['live'] for v in candidate['sources'] if v['live']['path']==str(old))==ref(old)
manifest=dict(passed=True,scope='One metadata expression changed; numeric aggregation, seal validation and capture unchanged',
 original_source=ref(old),source=ref(new),test_source=ref(Path(__file__)),actual_export_log=ref(E/'export-v2.log'),
 preserved_failed_export_log=ref(E/'export-v1.log'),plan=ref(E/'correctness-plan-v1/plan.json'),
 input=ref(E/'formal-v1/index.json'),lifecycle=ref(E/'formal-v1-lifecycle.json'),
 outputs=[ref(E/'export-v2'/n) for n in ('results.json','table.csv','artifacts.json')],
 exact_delta="cache=plan['cache'],learning=plan['learning'] -> regime=plan['regime']",
 actual_command='python3 -B reproduction/ttg-interability-performance/ia_export_v2.py --index project-notes/measurements/ttg-interability-performance-20261101/formal-v1/index.json --output project-notes/measurements/ttg-interability-performance-20261101/export-v2',
 validation='Actual complete CLI exit0; this fresh-process test checks source delta, unchanged numeric AST, exact release binding and actual12 n3 outputs. Independent raw arithmetic audit remains separate.')
p=E/'export-v2/postprocessor-manifest.json';p.write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps(dict(passed=True,manifest=ref(p),results=ref(E/'export-v2/results.json'),table=ref(E/'export-v2/table.csv'),index=ref(E/'formal-v1/index.json'))))
