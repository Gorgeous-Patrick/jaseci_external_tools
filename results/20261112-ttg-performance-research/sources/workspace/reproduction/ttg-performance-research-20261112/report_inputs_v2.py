"""Thin final-report adapter OUTSIDE frozen18; run only after diagnostic quiet.

Reads accepted exports, small source/fixture metadata and audited derivatives.
Never imports Jac, scans SQL traces, runs app code or recomputes primary metrics.
Contract: reproduction/ttg-performance-research-report-20261112/CONTRACT.md.
"""
import argparse,hashlib,importlib.util,json
from collections import Counter,defaultdict
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
E=ROOT/'project-notes/measurements/ttg-performance-research-20261112'
R=E.with_name(E.name+'-review')/'matrix-raw-audit-v1'
REPORT=ROOT/'reproduction/ttg-performance-research-report-20261112'
MODES=('off','aggressive','conservative')
def read(p):return json.loads(Path(p).read_text())
def ref(p):
 p=Path(p).resolve();return dict(path=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest())
def checked(r):
 p=Path(r['path']);assert ref(p)==r,'Changed accepted input '+str(p);return p

def fixture_metadata(sample):
 """Initial fixture metadata only; trace files are never opened."""
 directory=checked(sample['references']['raw']).parent;seal=read(directory/'artifacts.json')
 def sealed(name):
  p=directory/name;assert ref(p)['sha256']==seal['files'][name];return p
 manifest=directory/'dataset/manifest.json'
 if manifest.is_file():
  p=sealed('dataset/manifest.json');v=read(p)
  return dict(nodes_by_type=v['nodes_by_type'],edges_by_type=v['edges_by_type'],parameters=v['config'],
   distribution=v['distribution'],source_refs=[ref(p)],basis='Generator manifest; accepted native/oracle/state proofs are separate.')
 p=sealed('fixture-canonical.json');rows=read(p);assert isinstance(rows,list)
 nodes=Counter(r['arch_type'] for r in rows if r['kind']=='NodeAnchor')
 edges=Counter(r['arch_type'] for r in rows if r['kind']=='EdgeAnchor')
 states=defaultdict(Counter)
 for r in rows:
  props=r.get('props',{}).get('archetype',{})
  for field in ('status','trashed','public','active','cooked'):
   if field in props:states[r['arch_type']+'.'+field][json.dumps(props[field],sort_keys=True)]+=1
 return dict(nodes_by_type=dict(nodes),edges_by_type=dict(edges),parameters={'fixture':'Unchanged native Seed and scenario'},
  distribution='Deterministic native Seed; fixed ordered mutations/errors',initial_state_histograms={k:dict(v) for k,v in states.items()},
  source_refs=[ref(p)],basis='Initial censused domain anchors, including typed/root links; user/system rows outside the declared census are not counted.')

def build(output,quiet=False):
 assert quiet,'Run only after explicit diagnostic quiet handoff'
 output=Path(output).resolve();assert not output.exists()
 primary_path=E/'export-n5-v2/results.json';precision_path=E/'export-precision-v2/results.json'
 primary=read(primary_path);precision=read(precision_path);plan_path=checked(primary['plan']);plan=read(plan_path)
 assert primary['passed'] and precision['passed'] and len(primary['rows'])==57 and len(precision['samples'])==57
 old=read(checked(plan['lineage']['original_plan']))
 map_path=REPORT/'accepted_export_adapter.py';spec=importlib.util.spec_from_file_location('nov12_report_primary_map',map_path)
 mapper=importlib.util.module_from_spec(spec);spec.loader.exec_module(mapper)
 mapped=mapper.map_accepted_export(primary);cells=mapped['cells'];assert all(c['n']==5 for c in cells)
 evidence=dict(primary=ref(primary_path),precision=ref(precision_path),primary_table=ref(E/'export-n5-v2/table.csv'),
  plan=ref(plan_path),original_sources=plan['sources'],runtime_clean=plan['runtimes']['clean'],runtime_overlay=plan['runtimes']['overlay'],
  fixture_snapshot=plan['app_snapshot'],runtime_identity=ref(ROOT/'project-notes/measurements/ttg-performance-research-20261112-runtime/runtime-identity-v1.json'),
  failure_preservation=plan['lineage']['failed_stage_preservation'],postprocessors=ref(E/'postprocessors-v2-manifest.json'),
  timing_stop=ref(E/'extend-n5-v2-stopped-capacity.json'),precision_stop=ref(E/'precision-v2-stopped-capacity.json'),
  actual_review=ref(R/'publication-review.json'),denominator_review=ref(R/'precision-denominator-review-v2.json'),
  analysis=ref(E/'analysis-v2/results.json'),analysis_manifest=ref(E/'analysis-v2/manifest.json'),
  primary_mapper=ref(map_path),adapter=ref(Path(__file__)))
 denominator=read(checked(evidence['denominator_review']));assert denominator['passed']
 opinion={(r['case_id'],r['config_id']):r for r in denominator['rows']}
 precision_cells=[]
 for p in precision['samples']:
  key=(p['case_id'],p['config_id']);node=opinion[key]
  trial=dict(repeat=p['repeat'],prefetched_ids=p['returned_unique'],demand_ids=p['successful_demand_unique'],
   prefetched_used_ids=p['returned_demand_intersection'],promoted_ids=p['raw_promotion_served_unique'],
   timely_served_ids=p['served_return_before_demand_call_unique'],unused_ids=p['unused_returned_unique'],
   delivery_rows=p['actual_row_deliveries'],repeated_delivery_rows=p['repeated_row_deliveries'],late_deliveries=p['already_materialized_late_deliveries'],
   observed_all_anchor_overlap_coverage=p['overlap_coverage'],observed_all_anchor_promotion_service_coverage=p['promotion_service_coverage'],
   returned_demand_fraction=p['returned_demand_fraction'],promotion_served_fraction=p['promotion_served_fraction'],
   node_prefetched_ids=node['returned_node_unique'],node_demand_ids=node['successful_demand_node_unique'],
   node_used_ids=node['observed_node_returned_demand_intersection'],observed_node_overlap_coverage=node['observed_node_overlap_coverage'],
   observed_node_promotion_service_coverage=node['observed_node_promotion_service_coverage'],
   observed_unused_node_lower_bound=node['confirmed_unused_node_prefetch_lower_bound'],
   audited_filter_only_ids=None,filter_unused_disjoint=None,unnecessary_lower_bound=None,
   uncovered_observed_demand=p['successful_demand_unique']-p['returned_demand_intersection'],references=p['references'])
  precision_cells.append(dict(case_id=p['case_id'],mode=p['config_id'],status='accepted',n=1,trials=[trial],
   evidence=[evidence['precision'],evidence['denominator_review']],denominator='Policy-dependent successful Session demand, request+actual Session-local unique IDs summed over workflow'))
 for c in cells:c['evidence']=[evidence['primary'],evidence['actual_review']]
 for row in plan['lineage']['excluded_cells']:
  status='not_run' if row['status']=='not_run_after_first_failure' else row['status']
  terminal=dict(case_id=row['case_id'],mode=row['config_id'],status=status,trials=[],
   reason={'off':'Native correctness accepted; no accepted timing repetitions before first-failure stop.',
    'aggressive':'Strict backend-isolation gate assertion failed; raw data and owned DB retained.',
    'conservative':'Not run after the aggressive first-failure stop.'}[row['config_id']],evidence=[evidence['failure_preservation']])
  cells.append(dict(terminal));precision_cells.append(dict(terminal))
 assert len(cells)==len(precision_cells)==60
 traits_path=ROOT/'project-notes/measurements/ttg-performance-research-20261112-runtime/fixture-feasibility-v1.json'
 traits=read(traits_path);traits={r['app']:r for r in traits['rows']};evidence['app_traits']=ref(traits_path)
 original_apps={r['app']:r for r in plan['apps']};apps=list(original_apps);assert len(apps)==17
 representatives={s['case_id']:s for s in primary['samples'] if s['phase']=='correctness' and s['config_id']=='off'}
 failed=read(checked(plan['lineage']['failed_index']));extra=failed['rows'][30]
 representatives['linked_list-1000']=dict(references=extra['result'])
 cases=list({r['case_id']:r for r in old['stages']['precision']}.values());fixtures=[]
 for case in cases:
  meta=fixture_metadata(representatives[case['case_id']]);count=sum(meta['nodes_by_type'].values())
  dimensions=', '.join(f'{n} {t}' for t,n in meta['nodes_by_type'].items())
  fixtures.append(dict(case_id=case['case_id'],app=case['app'],label=case['case_id'].removeprefix(case['app']+'-'),
   tier='small' if case['scale']=='smoke' else 'larger',workflow_id=case['app']+'-original-native-replay-steady3',
   scale_family='initial_domain_nodes',scale_value=count,scale_unit='initial domain nodes',dimensions=dimensions,
   distribution=meta['distribution'],fixture_metadata=meta,source_refs=original_apps[case['app']]['sources']+meta['source_refs'],
   oracle=traits[case['app']]['oracle'],budget_note='Thread workers1; payload limit2048; abstract step budget32768; HTTP timeout300s. Original application cutoffs remain unchanged.'))
 app_traits=[dict(app=a,characteristics=traits[a]['characteristics'],source=traits[a]['source'],sha256=traits[a]['sha256'],
  source_sites=traits[a]['source_sites'],read_walker=original_apps[a]['read_walker'],oracle=traits[a]['oracle']) for a in apps]
 analysis=read(checked(evidence['analysis']));assert analysis['passed']
 bottlenecks=[]
 for case,ordinal,title in [('linked_list-smoke',0,'LinkedList32 Traverse'),('linked_list-smoke',1,'LinkedList32 Sum'),('help_queue-smoke',6,'HelpQueue EvaluateSLA')]:
  rpc=next(r for r in analysis['RPCs'] if (r['case_id'],r['config_id'],r['ordinal'])==(case,'conservative',ordinal))
  bottlenecks.append(dict(title=title,observation=f"Conservative HTTP median delta versus Off: {rpc['HTTP_median_delta_vs_off_ms']:+.3f}ms; DB-call median delta: {rpc['DB_median_delta_vs_off_ms']:+.3f}ms.",
   scope='n5 primary response wall and all-role protocol intervals; separate CPU diagnostics establish any CPU attribution.',evidence=evidence['analysis']))
 runtime=dict(identity='Common frozen Nov11 unified Access runtime; clean39ab46b8 / DIRECT4deaf0ea.',
  policies=[['Off','prefetching=none','Native demand only'],['Aggressive','prefetching=ttg','Original TTG prediction/executor'],['Conservative','prefetching=ttg_dependency; fused=true','Latest unified Access proofs; Always admission']],
  contract='Access includes ordinary helpers, LookupById and guarded ownership reads. Successful Access is distinct from ability Visit/entry.',
  flags='Always; thread workers1; prefetch_limit2048; common32768 abstract steps; unchanged app cutoffs.',
  gil='Free-threaded CPython3.14.6; actual GIL-off assertions at server and foreground/background SQL boundaries.',
  statistics=plan['regime']['statistics']+'; WAL32/64MB; log_statement=none.',
  warmup='One excluded fresh workflow per cell; correctness cases separate.',
  sessions='Fresh DB/server per trial, fresh native Session per HTTP request; ordered business mutations/errors unchanged.',
  cache_regime='Compiler caches reused across fresh trials; OS/global caches are not flushed.',
  profile_reset=plan['regime']['profiles'],instrumentation='DIRECT sendall-to-ReadyForQuery protocol clocks; compact native outcome callbacks and in-memory GIL callbacks. HTTP timing is instrumented.',
  calibration='Reused reviewed driver boundary. No new uninstrumented HTTP or whole-program CPU equivalence measurement is claimed.')
 value=dict(schema='ttg-performance-report-v1',status='accepted_complete',timing_complete=True,timing_quiet=True,
  title='TTG across 17 applications',recorded_date='2026-11-12',study_id='ttg-performance-research-20261112',
  requirements=ref(E/'report-requirements.json'),evidence=evidence,apps=apps,modes=list(MODES),fixtures=fixtures,app_traits=app_traits,
  cells=cells,precision_cells=precision_cells,runtime=runtime,
  mechanism=dict(examples=[dict(title='LittleX original load_feed',source_ref=original_apps['littlex']['sources'][0],
   explanation='Root→Profile; then Post→Tweet and Follow→Profile→Post→Tweet. Native gather uses here.to_view; Access and Visit remain distinct.')]),
  findings=dict(bottlenecks=bottlenecks,concurrency=[],unnecessary_audit=[dict(title='Observed unused returned nodes',observation='The unused-node counts are observational lower bounds relative to recorded Session demand.',
   scope='All-anchor and node denominators are separate; demand itself varies by policy. Filter-only business necessity remains unmeasured.',evidence=evidence['denominator_review'])],next_steps=[]),
  precision_definitions=dict(**precision['definitions'],denominator='ALL-anchor operational successful Session demand is the default; node ratios are separately named. Demand is policy-dependent, not a business-necessity oracle.',
   promotion_label='promoted_ids means unique promotion-backed service inside successful demand calls, not every raw promotion or generic cache hit.',
   timely_label='timely_served_ids means payload-return callback before call start plus later actual promotion; callback is not exact cache-insertion time.'),
  correctness=dict(summaries=[dict(title='Paired native answers and state',observation='399 accepted comparison workflows across19 fixtures; independent full-response/scenario, typed physical graph and restart checks.'),
   dict(title='Original failure retained',observation='LL1000 Off correctness-only, Aggressive failed isolation gate, Conservative not run; no accepted timing or precision values.'),
   dict(title='Owned cleanup',observation='Completed DBs dropped only after semantic/source/seal/target and zero-session guards; failed LL1000 DB preserved.')]),
  provenance=dict(summaries=[dict(title='One effective runtime',observation=plan['provenance']),dict(title='Explicit prefix lineage',observation='Original n3 prefixes plus unchanged n5 extension; failed larger prefix30 only. Original indexes remain unchanged.'),dict(title='Separate capture regimes',observation='285 n5 primary measured workflows,57 excluded warmups,57 comparison correctness;57 n1 precision workflows. Full20fixture/60cell inventory retains3 terminal outcomes.')]),
  reproduction=dict(commands=[dict(title='Timing extension',command='runner_v2.py --plan plan-v2/plan.json --stage extend-n5 --output NEW --cluster NEW_OWNED'),
   dict(title='Precision pass',command='runner_v2.py --plan plan-v2/plan.json --stage precision --output NEW --cluster NEW_OWNED')],scope='Use the portable package path map and original accepted plan/source references; run only in an isolated owned DB window.'),
  counts=primary['counts'],excluded_samples=mapped['excluded_samples'])
 cpu_path=ROOT/'project-notes/measurements/ttg-performance-research-diagnostics-20261112/cpu-summary-v1.json'
 assert ref(cpu_path)['sha256']=='2d903dff593359aeb4b666b8273afd5de8267bb8deb488313547ee9ade504866'
 cpu=read(cpu_path);assert cpu['passed'] and not cpu['primary_measurement'] and cpu['diagnostic_n_per_app_mode']==1
 assert len(cpu['rows'])==cpu['selected_RPCs']==12
 expected_cpu={(app,mode,walker) for mode in MODES for app,walkers in [('linked_list',('Traverse','Sum')),('recipe_pantry',('ShoppingList','CookMeal'))] for walker in walkers}
 assert {(r['app'],r['mode'],r['walker']) for r in cpu['rows']}==expected_cpu
 evidence.update(cpu_summary=ref(cpu_path),cpu_source=cpu['source'],cpu_index=cpu['index'],cpu_lifecycle=cpu['lifecycle'],
  analysis_correction=ref(E/'analysis-v2/correction-verification.json'))
 value['cpu_diagnostic']=cpu
 value['precision_definitions']['demand']='Successful foreground Session.get/batch_get outside the recorded planning context. Operational demand is policy-dependent and differs from a business-necessity oracle.'
 value['runtime']['calibration']='Reviewed DIRECT driver boundary reused. Primary HTTP includes compact and GIL observer callbacks; precision and thread-CPU diagnostics have separate capture identities.'
 value['findings']['cpu_scope']=cpu['definitions']
 output.mkdir(parents=True);p=output/'report-inputs.json';p.write_text(json.dumps(value,indent=2)+'\n')
 (output/'manifest.json').write_text(json.dumps(dict(passed=True,adapter=ref(Path(__file__)),inputs=evidence,output=ref(p)),indent=2)+'\n')
 print(json.dumps(dict(passed=True,output=ref(p),cells=len(cells),precision_cells=len(precision_cells))))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--output',required=True,type=Path);p.add_argument('--quiet',action='store_true');a=p.parse_args();build(a.output,a.quiet)
