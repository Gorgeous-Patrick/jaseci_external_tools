"""Narrow metadata validation: only the observed LL1000 three-mode exclusion."""
import hashlib,json
from pathlib import Path
MODES=('off','aggressive','conservative')
STATUS=('correctness_only','failed_isolation_gate','not_run_after_first_failure')
def read(p):return json.loads(Path(p).read_text())
def ref(p):
 p=Path(p).resolve();return dict(path=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest())
def checked(value):
 p=Path(value['path']);assert ref(p)==value,'Lineage input changed';return p
def validate_lineage(plan,stage,original_schedule):
 assert plan['kind']=='ttg-expanded-performance-20261112-v2-lineage'
 assert stage in ('extend-n5','precision'),'Only the exact remaining stages are authorized'
 line=plan['lineage'];old=read(checked(line['original_plan']))
 assert old['kind']=='ttg-expanded-performance-20261112-v1'
 assert plan['sources']==old['sources'] and plan['runtimes']==old['runtimes']
 assert plan['configs']==old['configs'] and plan['seed']==old['seed'] and plan['regime']==old['regime']
 assert plan['apps']==old['apps'] and plan['app_snapshot']==old['app_snapshot']
 exclusions=[dict(case_id='linked_list-1000',config_id=mode,status=status) for mode,status in zip(MODES,STATUS)]
 assert line['excluded_cells']==exclusions,'Any other case/mode deletion is forbidden'
 assert original_schedule==old['stages'][stage]
 selected=[r for r in original_schedule if r['case_id']!='linked_list-1000']
 assert plan['stages'][stage]==selected,'Order,trial IDs,seed/repeats or another cell changed'
 assert len(selected)==(114 if stage=='extend-n5' else 57)
 proof=read(checked(line['failed_stage_preservation']))
 assert proof['passed'] and proof['source_postcheck']['passed'] and not proof['source_postcheck']['mismatches']
 assert proof['source_manifest']==plan['sources'] and proof['pg_status']==3 and not proof['postmaster_pid_exists']
 assert len(proof['retained_databases'])==1 and proof['retained_databases'][0]==proof['failed_database']['database']
 assert proof['report_inventory']==exclusions
 failed=read(checked(line['failed_index']))
 assert failed['status']=='failed' and not failed['passed'] and len(failed['rows'])==31
 assert proof['index']==line['failed_index'] and failed['plan']==line['original_plan']
 assert [dict((k,r[k]) for k in wanted) for r,wanted in zip(failed['rows'],old['stages']['larger'][:31])]==old['stages']['larger'][:31]
 assert all(r['passed'] for r in failed['rows'])
 assert line['preserved_larger_timing_prefix_rows']==30
 assert line['correctness_only_extra_row']==failed['rows'][30]['trial_id']
 assert ref(Path(__file__))==plan['lineage_validator']
 return old
