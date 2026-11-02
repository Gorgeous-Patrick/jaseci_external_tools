from pathlib import Path
import json,hashlib
R=Path('/home/baichuan/jaseci');D=R/'project-notes/measurements/ttg-interability-diagnostics-20261102';run=D/'recapture-v1'
def ref(p):return {'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
def read(p):return json.loads(p.read_text())
assert read(run/'result.json')['passed'];life=read(run/'lifecycle.json');assert life['services_stopped'] and life['pg_ctl_status']==3 and not life['pidfile'] and not life['retained_databases']
rows=[];modes=[]
for mode in ('baseline9282','interability'):
 p=run/f'cases/finite_list1000-{mode}-diagnostic/diagnostic-acceptance.json';a=read(p);cr=a['capture'];cp=Path(cr['path']);assert ref(cp)==cr;c=read(cp)
 assert a['passed'] and a['full_workflow_oracle_passed'];assert a['actual_call']['data_rows']==1000 and a['actual_call']['error'] is None
 assert c['state']['context'][0][3]=='serializable';assert c['state']['statistics']==c['state']['statistics_after_explain']
 ps=[]
 for p2 in c['explain']['repetitions']:
  full=p2['full_plan'][0];root=full['Plan'];assert full['Execution Time']==p2['execution_ms'] and full['Planning Time']==p2['planning_ms'];assert root['Actual Rows']==1000
  ps.append({'planning_ms':p2['planning_ms'],'execution_ms':p2['execution_ms'],'shared_hits':root['Shared Hit Blocks'],'shared_reads':root['Shared Read Blocks'],'temp_written_blocks':root['Temp Written Blocks']})
 rows.append([mode,f"{ps[0]['planning_ms']:.3f} / {ps[1]['planning_ms']:.3f}",f"{ps[0]['execution_ms']:.3f} / {ps[1]['execution_ms']:.3f}",str(ps[0]['shared_hits']),str(ps[0]['temp_written_blocks'])])
 modes.append({'mode':mode,'acceptance':ref(p),'capture':cr,'plans':ps,'state_context':c['state']['context'],'relations':c['state']['relations'],'settings':c['state']['settings']})
x={'passed':True,'scope':'Matched native recapture; SERIALIZABLE, explicit pre-workflow ANALYZE, same-connection first/repeat EXPLAIN. Census warms buffers; separate from primary n=3.','headers':['Mode','Planning first/repeat ms','Execution first/repeat ms','Shared hits','Temp writes (blocks)'],'widths':[.16,.24,.26,.17,.17],'rows':rows,'modes':modes,'result':ref(run/'result.json'),'lifecycle':ref(run/'lifecycle.json'),'script':ref(Path(__file__)),'review_status':'Main source/result/plan binding checked; independent diagnostic reviewer stopped at usage limit before final report. Primary48 and HTTP/startup independent reviews remain complete.','observations':['Both selected original queries completed with 1000 rows and full native/restart/physical acceptance.','New recursive tuple carries phase and a growing seen UUID array; ANY membership guards cycles. Baseline recursive tuple carries origin and depth only.','New plan performs two additional source-anchor PK checks per origin: 1000 loops each, 3000 hits each, explaining the observed extra6000 shared hits structurally.','New CTE Scan reports985 temporary written blocks at work_mem4096kB; baseline reports0. Ancestor counters are inclusive and must not be summed.','No disk shared reads in either diagnostic. These plans locate additional validation/state/spill work; no isolated attribution of milliseconds to a single feature was measured.'],'next_steps':['Evaluate narrower recursive state or alternative exact cycle/completeness validation under explicit semantic proofs.','Retain cycle/fanout/overflow/ACL tests; do not simply remove guards.','Evaluate persistent reader reuse and cold-start-aware admission separately.']}
(D/'summary-v1.json').write_text(json.dumps(x,indent=2)+'\n');print(json.dumps(ref(D/'summary-v1.json')))
