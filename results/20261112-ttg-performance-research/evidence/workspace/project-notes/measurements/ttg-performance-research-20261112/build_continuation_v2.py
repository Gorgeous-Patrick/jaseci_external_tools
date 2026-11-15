"""Metadata-only continuation; preserve original indexes and controller sources."""
import copy,hashlib,json
from pathlib import Path
ROOT=Path.cwd();E=ROOT/'project-notes/measurements/ttg-performance-research-20261112'
OWN=ROOT/'reproduction/ttg-performance-research-20261112'
def ref(p):
 p=Path(p).resolve();return dict(path=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest())
old_path=E/'plan-v1/plan.json';old=json.loads(old_path.read_text());plan=copy.deepcopy(old)
proof_path=E/'larger-v1-failure-preservation.json';proof=json.loads(proof_path.read_text())
failed_path=E/'larger-v1/index.json';failed=json.loads(failed_path.read_text())
assert proof['passed'] and proof['source_postcheck']['passed'] and len(failed['rows'])==31
plan['kind']='ttg-expanded-performance-20261112-v2-lineage'
for stage in ('extend-n5','precision'):
 plan['stages'][stage]=[r for r in old['stages'][stage] if r['case_id']!='linked_list-1000']
assert len(plan['stages']['extend-n5'])==114 and len(plan['stages']['precision'])==57
plan['controller']=ref(OWN/'runner_v2.py');plan['lineage_validator']=ref(OWN/'lineage_v2.py')
plan['lineage']=dict(original_plan=ref(old_path),failed_index=ref(failed_path),
 failed_stage_preservation=ref(proof_path),excluded_cells=proof['report_inventory'],
 preserved_larger_timing_prefix_rows=30,correctness_only_extra_row=failed['rows'][30]['trial_id'],
 accepted_prefixes=[dict(index=ref(E/'first-v1/index.json'),start=0,end=45,status='complete'),
  dict(index=ref(E/'small-rest-v1/index.json'),start=0,end=210,status='complete'),
  dict(index=ref(failed_path),start=0,end=30,status='accepted_prefix_of_failed_stage')],
 invariant='No native runtime/observer/timer/GIL/oracle change. Only exact LL1000 fixture trio removed from remaining schedules; original trial IDs/order/repeats retained.',
 failure='Observed backend-isolation gate assertion; gate unchanged, no safe-pooling claim and no timing sample accepted for LL1000.')
plan['counts']=dict(apps=17,inventory_fixtures=20,comparison_fixtures=19,comparison_policy_cells=57,
 correctness=57,excluded_warmups=57,pilot_n3=171,primary_n5=285,comparison_total=399,
 retained_correctness_only_extra=1,new_n5_trials=114,precision_first_pass=57,terminal_inventory_cells=3)
plan['execution']='Only NEW controller runner_v2.py for extend-n5/precision after exact main release; all captured18 and source8d3 remain unchanged.'
out=E/'plan-v2';assert not out.exists();out.mkdir()
p=out/'plan.json';p.write_text(json.dumps(plan,indent=2)+'\n')
manifest=dict(passed=True,source=ref(Path(__file__)),plan=ref(p),controller=plan['controller'],
 lineage_validator=plan['lineage_validator'],original_sources=old['sources'],original_plan=ref(old_path),
 preservation=ref(proof_path),prefixes=plan['lineage']['accepted_prefixes'])
(out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps(dict(passed=True,plan=ref(p),manifest=ref(out/'manifest.json'),controller=plan['controller'],lineage_validator=plan['lineage_validator'])))
