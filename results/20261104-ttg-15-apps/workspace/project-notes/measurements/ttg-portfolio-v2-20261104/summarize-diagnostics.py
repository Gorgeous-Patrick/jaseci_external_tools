"""Bind direct CPU boundary records and matched SQL plans; no primary trace re-read."""
from pathlib import Path
import json,hashlib,collections,csv
E=Path(__file__).resolve().parent;R=E.parents[2]
def read(p):return json.loads(Path(p).read_text())
def ref(p):return dict(path=str(p),sha256=hashlib.sha256(Path(p).read_bytes()).hexdigest())
D=R/'project-notes/measurements/ttg-portfolio-diagnostics-v2-20261104';H=R/'project-notes/measurements/ttg-portfolio-cpu-hot-20261104';S=R/'project-notes/measurements/ttg-portfolio-sql-diagnostics-20261104'
primary=read(E/'results.json');profiles=[];inputs=[]
for parent,tag in [(D/'cpu-v2','first_reader'),(H/'run-v1','hot_walker')]:
 result=read(parent/'result.json');life=read(parent/'lifecycle.json');assert result['passed'] and life['services_stopped'] and life['pg_status']==3 and not life['pidfile'] and not life['retained_databases'];inputs.extend([ref(parent/'result.json'),ref(parent/'lifecycle.json'),ref(parent/'sources.json')])
 for row in result['rows']:
  for reference in row['profiles']:
   if tag=='first_reader':
    x=next(x for x in read(D/'direct-profiles.json')['profiles'] if x['original']==reference['path']);assert x['sha256']==reference['sha256'];r=x['record']
   else:
    p=Path(reference['path']);assert ref(p)==reference;r=read(p)
   assert r['passed'] and all(e['thread_id']==r['thread_id'] and e['cpu_ns']>=e['exclusive_cpu_ns']>=0 and e['wall_ns']>=e['cpu_ns'] for e in r['events'])
   assert sum(e['exclusive_cpu_ns'] for e in r['events'])==r['thread_cpu_ns']
   totals=collections.defaultdict(lambda:dict(calls=0,cpu_ms=0.,exclusive_cpu_ms=0.))
   for ev in r['events']:
    z=totals[ev['name']];z['calls']+=1;z['cpu_ms']+=ev['cpu_ns']/1e6;z['exclusive_cpu_ms']+=ev['exclusive_cpu_ns']/1e6
   profiles.append(dict(stage=tag,app=row['app'],mode=row['mode'],request=r['request'],native_cpu_ms=r['thread_cpu_ns']/1e6,native_wall_ms=r['wall_ns']/1e6,functions=dict(totals),source=reference))
aggregates={}
for x in profiles:
 k=x['stage']+'/'+x['app']+'/'+x['mode'];z=aggregates.setdefault(k,dict(requests=[],native_cpu_ms=0.,native_wall_ms=0.,functions={}))
 z['requests'].append(x['request']);z['native_cpu_ms']+=x['native_cpu_ms'];z['native_wall_ms']+=x['native_wall_ms']
 for name,v in x['functions'].items():
  q=z['functions'].setdefault(name,dict(calls=0,cpu_ms=0.,exclusive_cpu_ms=0.))
  for field in q:q[field]+=v[field]
controls=read(H/'gil-off-clock-controls.json');assert controls['passed'] and controls['Py_GIL_DISABLED']==1 and not controls['gil_enabled'];inputs.append(ref(H/'gil-off-clock-controls.json'))
assert len(profiles)==22
cpu=dict(passed=True,method='direct same-native-thread clock boundaries; nested exclusive times partition the measured native-spawn boundary',profiles=profiles,aggregates=aggregates,inputs=inputs,
 limits='Diagnostic n=1 per workflow; imports loaded before requests, instrumentation overhead included; no ability wrapping. Other thread/server CPU and HTTP auth/serialization outside spawn excluded. Do not subtract primary wall and DB. Earlier cProfile output rejected; not used.',archive_map=ref(D/'stopped-preservation-v1/manifest.json'))
(E/'cpu-boundaries.json').write_text(json.dumps(cpu,indent=2)+'\n')
sql=read(S/'summary.json');assert sql['passed'] and all(sql['same_logical_state_under_seq_uuid_bijection'].values())
def agg(stage,app,mode):return aggregates[stage+'/'+app+'/'+mode]
def fn(a,name):return a['functions'].get('jaclang.runtime.'+name,dict(calls=0,exclusive_cpu_ms=0))
help_t=agg('hot_walker','help_queue','thread');help_o=agg('hot_walker','help_queue','off');app_t=agg('hot_walker','approval_desk','thread');app_o=agg('hot_walker','approval_desk','off');lx=agg('first_reader','littlex','thread');lxo=agg('first_reader','littlex','off')
ht=fn(help_t,'ttg_continuation.plan_continuation');at=fn(app_t,'ttg_continuation.plan_continuation')
lxsql=[x for x in sql['rows'] if x['app']=='littlex'];thread=next(x for x in lxsql if x['mode']=='thread');off=[x for x in lxsql if x['mode']=='off']
comp=[]
for i in (0,1):
 comp.append(dict(occurrence=i,off_planning_ms=sum(x['plans'][i]['planning_ms'] for x in off),off_execution_ms=sum(x['plans'][i]['execution_ms'] for x in off),off_root_hits=sum(x['plans'][i]['root_hits'] for x in off),thread_planning_ms=thread['plans'][i]['planning_ms'],thread_execution_ms=thread['plans'][i]['execution_ms'],thread_root_hits=thread['plans'][i]['root_hits']))
slides=[
 dict(title='HelpQueue: expensive prediction, little saved work',subtitle='Matched diagnostic: all three EvaluateSLA requests; direct same-thread CPU timers',bullets=[
  f"Native-worker CPU sum: off {help_o['native_cpu_ms']:.2f} ms; thread {help_t['native_cpu_ms']:.2f} ms. Full original workflow and state checks pass.",
  f"plan_continuation alone: {ht['calls']} calls, {ht['exclusive_cpu_ms']:.2f} ms exclusive CPU. Nested timers are partitioned; inclusive recursive totals are not added.",
  'Primary EvaluateSLA stops at the ticket conditional/graph-read barrier. It still invokes continuation prediction and frontier resolution; only a short prefix is prefetched.',
  'This directly locates substantial extra runtime work. It does not apportion the entire primary HTTP difference or measure PostgreSQL CPU.']),
 dict(title='ApprovalDesk: the exit phase limits the region',subtitle='Matched diagnostic: all five SubmitExpense requests, including native rejection cases',bullets=[
  f"Native-worker CPU sum: off {app_o['native_cpu_ms']:.2f} ms; thread {app_t['native_cpu_ms']:.2f} ms. plan_continuation: {at['calls']} calls / {at['exclusive_cpu_ms']:.2f} ms exclusive CPU.",
  'LineItem values accumulate into self.total. Expense exit then chooses approval roles, traverses approvers and creates ApprovalStep nodes.',
  'Actual primary fallback says: Walker exit effects are outside the static region kernel. The line-item prefix can be fetched; the later routing/write phase remains procedural.',
  'Compiler eligibility for one prefix is insufficient for profitability. Avoid repeated planning at known unsupported boundaries; price planner CPU in admission.']),
 dict(title='LittleX: construction and execution still cost work',subtitle='First load_feed diagnostic; declared inputs and full native program unchanged',bullets=[
  f"Native-worker CPU: off {lxo['native_cpu_ms']:.2f} ms; thread {lx['native_cpu_ms']:.2f} ms. {fn(lx,'ttg_dependency_prefetch.record_model_event')['calls']} observed event hooks remain.",
  f"Named TTG runtime work totals {lx['native_cpu_ms']-lx['functions']['native_spawn']['exclusive_cpu_ms']:.2f} ms exclusive CPU. Static region resolution is attempted {fn(lx,'ttg_regions.resolve_interability_region')['calls']} times, including later cache/terminal checks.",
  'Primary workflow SQL falls 153 → 143, yet DB median rises 50.11 → 60.40 ms and HTTP 215.72 → 275.59 ms.',
  'The matched SQL plans on the next page show why fewer SELECTs need not mean less server work. These diagnostic timings are not primary n=3 measurements.']),
 dict(title='LittleX SQL: one complex query versus three simple paths',subtitle='Same logical state, actual Bind, uniform ANALYZE; census-warmed matched EXPLAIN',bullets=[
  f"First plans: off planning {comp[0]['off_planning_ms']:.3f} / execution {comp[0]['off_execution_ms']:.3f} ms total; thread {comp[0]['thread_planning_ms']:.3f} / {comp[0]['thread_execution_ms']:.3f} ms.",
  f"Immediate repeat: off {comp[1]['off_planning_ms']:.3f} / {comp[1]['off_execution_ms']:.3f} ms; thread {comp[1]['thread_planning_ms']:.3f} / {comp[1]['thread_execution_ms']:.3f} ms. Root shared hits {comp[1]['off_root_hits']} → {comp[1]['thread_root_hits']}; all physical reads zero.",
  'Compiled plan adds six WindowAgg nodes, ordering/CTE/aggregate machinery and an anchors Seq Scan (1,104 rows, 1 loop). Ordinary paths use endpoint primary-key lookups.',
  'The compiled result includes path/cache metadata and markers: 64 records versus 1 + 20 + 40 native path rows. This is not a claim of 64 distinct fetched nodes.']),
 dict(title='What these diagnostics establish',subtitle='Separate mechanisms; no single unexplained “thread overhead” label',bullets=[
  'Runtime: the direct continuation timers establish a large CPU cost in the two slowest procedural workflows, even with small graphs and compiler-emitted templates.',
  'Database: matched plans establish extra planning/execution and buffer work for the LittleX combined query in this controlled warm regime.',
  'Scheduling: all 90 primary samples have zero observed same-request foreground/background SQL overlap. Actual GIL-off threads do not guarantee hidden DB latency.',
  'Future experiments: skip known-no-benefit regions before runtime interpretation, reuse safe analysis facts, specialize SQL metadata/ACL work, then test cost-based admission. No proposed speedup is counted here.'])]
summary=dict(passed=True,cpu=ref(E/'cpu-boundaries.json'),sql=ref(S/'summary.json'),primary=ref(E/'results.json'),littlex_matched_sql=comp,slides=slides,invalid_profile_excluded=ref(R/'project-notes/measurements/ttg-portfolio-diagnostics-20261104/cpu-v1/profile-validity.json'))
(E/'diagnostic-summary.json').write_text(json.dumps(summary,indent=2)+'\n')
with (E/'table.csv').open('w') as f:
 w=csv.writer(f);w.writerow(['application','mode','n','HTTP_median_ms','HTTP_min_ms','HTTP_max_ms','DB_median_ms','SQL_median','data_SQL_median','control_SQL_median'])
 for app,modes in primary['groups'].items():
  for mode,g in modes.items():w.writerow([app,mode,g['HTTP_sum_ms']['n'],g['HTTP_sum_ms']['median'],g['HTTP_sum_ms']['min'],g['HTTP_sum_ms']['max'],g['DB_sum_ms']['median'],g['SQL']['median'],g['data_SQL']['median'],g['control_SQL']['median']])
print('Bound 22 direct CPU records, 8 SQL targets/16 plans, and primary CSV.')
