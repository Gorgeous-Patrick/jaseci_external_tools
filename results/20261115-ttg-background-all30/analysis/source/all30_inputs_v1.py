"""Thin six-export adapter. Reads accepted JSON metadata only; no raw replay."""
import argparse,copy,csv,hashlib,json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
M=ROOT/'project-notes/measurements'
E=M/'ttg-background-pushdown-portfolio-performance-20261115'
PORTFOLIO=ROOT/'project-notes/ttg-background-pushdown-portfolio-plan-20261115.json'
POLICIES=('off','conservative','background','restored')
LABELS=dict(off='Off',conservative='Old Conservative',background='Previous Background',restored='Restored Background')
DATASETS=[
 ('depth7',M/'ttg-background-pushdown-large-performance-20261115/export-v1/results.json',M/'background-pushdown-large-review-20261115/primary24-raw-audit-v1/summary.json'),
 ('bridge',M/'ttg-background-pushdown-bridge-performance-20261115/export-v1/results.json',M/'background-pushdown-bridge-review-20261115/primary72-raw-audit-v1/summary.json')]
DATASETS += [(s,E/s/('export-v1' if s in ('A1','A2') else 'export-v2')/'results.json',
 M/'background-pushdown-portfolio-review-20261115'/f'{s}-primary{144 if s in ("A1","B1") else 168}-raw-audit-v1/summary.json') for s in ('A1','A2','B1','B2')]

def read(p):return json.loads(Path(p).read_text())
def ref(p):
 p=Path(p).resolve();return dict(path=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest())
def checked(r):
 assert ref(r['path'])==r,'Changed accepted metadata '+r['path'];return Path(r['path'])
def write(p,v):p.write_text(json.dumps(v,indent=2)+'\n')

def build(output):
 output=Path(output).resolve();assert not output.exists()
 portfolio=read(PORTFOLIO);apps=[];cells=[];samples=[];correct=[];datasets=[]
 for name,path,audit_path in DATASETS:
  value=read(path);audit=read(audit_path)
  assert value['passed'] and audit['passed'] and audit['quiet'] and audit['export']==ref(path)
  plan_path=checked(value['plan']);plan=read(plan_path)
  index=read(checked(audit['index']));life=read(checked(audit['lifecycle']))
  assert index['passed'] and index['status']=='complete' and index['source_after_passed']
  assert life['passed'] and life['pg_status']==3 and not life['retained_databases']
  if name=='bridge':
   carry_path=checked(value['correctness_carry']);carry=read(carry_path)
   assert carry['passed'] and carry['count']==12
   correct.extend(dict(dataset=name,carried=True,row=r['original_row'],carry=ref(carry_path)) for r in carry['records'])
  else:
   release=read(plan['formal_release']['path']);ci=read(checked(release['correctness_index']))
   assert ci['passed'] and ci['status']=='complete' and ci['source_after_passed']
   correct.extend(dict(dataset=name,carried=False,row=r,index=release['correctness_index']) for r in ci['rows'])
  audit_samples={r['trial_id']:r['audit'] for r in audit['samples']}
  for s in value['samples']:
   assert s['phase'] in ('excluded_warmup','measured')
   slim={k:copy.deepcopy(s[k]) for k in ('trial_id','case_id','app','scale','config_id','phase','repeat','references','GIL_proof','runtime','overlay','RPCs')}
   slim.update(dataset=name,source_export=ref(path),audit_derivative=audit_samples[s['trial_id']])
   samples.append(slim)
  for row in value['rows']:
   selected=sorted((s for s in value['samples'] if s['app']==row['app'] and s['config_id']==row['config_id'] and s['phase']=='measured'),key=lambda s:s['repeat'])
   assert row['n']==5 and [s['repeat'] for s in selected]==list(range(5))
   metrics={k:copy.deepcopy(v) for k,v in row.items() if isinstance(v,dict)}
   for key,stat in metrics.items():
    if key=='native_tree':continue
    assert stat['n']==5 and stat['values']==[s[key] for s in selected]
   cells.append(dict(app=row['app'],policy=row['config_id'],case_id=row['case_id'],scale=row['scale'],dataset=name,
    status=index['status'],timing_accepted=True,status_explanation='Five fresh measured workflows passed all frozen gates; excluded warmup remains separate.',
    metrics=metrics,source_export=ref(path),plan=value['plan'],source=plan['sources'],configuration=plan['configs'][row['config_id']],
    runtime=selected[0]['runtime'],overlay=selected[0]['overlay'],sample_ids=[s['trial_id'] for s in selected]))
  datasets.append(dict(dataset=name,export=ref(path),CSV=audit['CSV'],audit=ref(audit_path),index=audit['index'],
   lifecycle=audit['lifecycle'],plan=value['plan'],sources=plan['sources'],regime=plan['regime'],definitions=value['definitions'],
   counts=value['counts'],SQL_catalog=ref(audit_path.parent/'SQL-fingerprints.json')))
 assert len(samples)==720 and sum(s['phase']=='excluded_warmup' for s in samples)==120
 assert sum(s['phase']=='measured' for s in samples)==600
 assert len(correct)==120 and sum(r['carried'] for r in correct)==12
 assert len(cells)==120 and len({(c['app'],c['policy']) for c in cells})==120
 assert {(c['app'],c['policy'])for c in cells}=={(a['app'],p)for a in portfolio['entries']for p in POLICIES}
 size_path=M/'ttg-background-pushdown-large-performance-20261115/size-evidence-v1.json'
 size=next(r for r in read(size_path)['sizes'] if r['config']['depth']==7)
 for entry in portfolio['entries']:
  app=copy.deepcopy(entry);app['label']={'linked_list':'LinkedList','littlex':'LittleX','jdrive':'JDrive','jacord':'Jacord','recipe_pantry':'RecipePantry'}.get(app['app'],app['app'].replace('_',' ').title())
  app['source_declared_initial_fixture']=copy.deepcopy(entry['initial_fixture'])
  if app['app']=='jdrive':
   app['selected_initial_fixture']=size;app['fixture_source']=ref(size_path)
   counts=f"Depth7: {size['initial_node_count']} initial logical nodes / {size['initial_edges']} domain edges"
  else:
   app['selected_initial_fixture']=copy.deepcopy(entry['initial_fixture']);app['fixture_source']=ref(PORTFOLIO)
   counts=f"{entry['initial_fixture']['nodes']} source-declared initial logical nodes / {entry['initial_fixture']['domain_edges']} domain edges"
  selected=[c for c in cells if c['app']==app['app']]
  http=selected[0]['metrics']['business_requests'];assert all(c['metrics']['business_requests']['values']==http['values'] for c in selected)
  app['size_operations_support']=counts+f"; {http['median']:g} business HTTP; reader {app['registry_reader']}."
  app['fixture_count_scope']='Source-declared initial logical fixture counts; business mutations/final state remain in accepted proof references. No fixture reconciliation or new census.'
  changes=[]
  for c in selected:
   fields=[f"{k} {c['metrics'][key]['min']:g}–{c['metrics'][key]['max']:g}" for k,key in (('D','data_SQL'),('C','control_SQL'),('T','total_SQL')) if c['metrics'][key]['min']!=c['metrics'][key]['max']]
   if fields:changes.append(LABELS[c['policy']]+': '+', '.join(fields))
  app['count_range_or_status_note']='; '.join(changes) if changes else 'SQL counts constant across five samples in all four policies.'
  apps.append(app)
 lookup={(c['app'],c['policy']):c for c in cells};cells=[lookup[a['app'],p]for a in apps for p in POLICIES]
 relocations=[]
 for folder in (M/'ttg-background-pushdown-large-performance-20261115/depth7-cases-archive-v1',E/'audited-A1-A2-archive-v1',E/'audited-B1-v2-archive-v1'):
  verification=read(folder/'verification.json');assert verification['passed'] and verification['every_archive_member_SHA_matches'] and verification['every_original_file_SHA_unchanged']
  relocations.append(dict(verification=ref(folder/'verification.json'),restore_map=ref(folder/'restore-map.json'),members=ref(folder/'members.jsonl.gz'),archive=verification['archive'],scope='Original case/index references remain unchanged; explicit lossless restoration map resolves relocated bytes. No archive reread.'))
 failure=E/'B1/correctness-v1-failed-stopped.json';assert read(failure)['passed']
 value=dict(passed=True,kind='all30-accepted-portfolio-report-inputs-v1',all_stages_terminal=True,services_stopped=True,raw_audit_quiet=True,assembly_released=True,
  counts=dict(entries=30,cells=120,primary=720,excluded_warmups=120,measured=600,n=5,correctness_identities=120,fresh_correctness=108,carried_correctness=12),
  apps=apps,cells=cells,samples=samples,correctness=correct,datasets=datasets,portfolio=ref(PORTFOLIO),relocations=relocations,
  failed_attempt=dict(status='failed_harness_replay_mapping_v1',accepted_timing=False,evidence=ref(failure),scope='B1 v1 StopIteration before independent acceptance. Failed DB/output preserved; fresh repaired B1 v2 is the main matrix.'),
  separate_scale_appendix=dict(app='jdrive',scale='depth5',export=ref(M/'ttg-background-pushdown-restoration-performance-20261115/export-v1/results.json'),pooled=False),
  measurement_scope=dict(HTTP='Instrumented response-body wall; separate post-response Future drain; per-RPC start/end and wall values preserved in samples.',SQL='All-role lexical data/control/TOTAL includes snapshot/private-worker setup and late origin-attributed SQL. SQL text/frame metadata retained; original Bind values/raw packets not retained.',CPU='CPU components not measured in this study; no wall-minus-DB residual.',publication='Published paths are summed origins, not unique demand hits or timely service.',fixtures='Initial source counts verbatim; JDrive main entry explicitly depth7. Final-state evidence remains source-bound.'),source=ref(Path(__file__)))
 output.mkdir(parents=True);write(output/'inputs.json',value)
 with (output/'table.csv').open('w') as f:
  w=csv.writer(f);w.writerow(['app','policy','dataset','n','HTTP_ms_values','HTTP_ms_median','HTTP_ms_min','HTTP_ms_max','business_HTTP_values','data_SQL_values','control_SQL_values','TOTAL_SQL_values','data_per_HTTP_values'])
  for c in cells:
   x=c['metrics'];h=x['HTTP_response_sum_ms'];w.writerow([c['app'],c['policy'],c['dataset'],5,json.dumps(h['values']),h['median'],h['min'],h['max']]+[json.dumps(x[k]['values'])for k in ('business_requests','data_SQL','control_SQL','total_SQL','data_SQL_per_business_request')])
 write(output/'manifest.json',dict(passed=True,source=ref(Path(__file__)),outputs=[ref(output/'inputs.json'),ref(output/'table.csv')],accepted_exports=[d['export'] for d in datasets],audits=[d['audit']for d in datasets],scope='Thin accepted-metadata mapping only; no raw SQL/HTTP reread, new measurement, fixture audit or runtime import.'))
 print(json.dumps(dict(passed=True,inputs=ref(output/'inputs.json'),manifest=ref(output/'manifest.json'),counts=value['counts'])),flush=True)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args();build(a.output)
