"""Bounded presentation mapping. Uses accepted derivatives; no primary raw reread."""
import hashlib,json,re,statistics
from pathlib import Path
ROOT=Path('/home/baichuan/jaseci')
E=ROOT/'project-notes/measurements/ttg-next-performance-20261101'
OWN=ROOT/'project-notes/measurements/ttg-next-review-20261101'
def load(p):return json.loads(Path(p).read_text())
def ref(p):
 p=Path(p);return dict(path=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest())
def norm(s):return re.sub(r'\s+','',s)
checks=[]
def check(name,value):
 assert value,name
 checks.append(name)
m=load(E/'report-final-v2/manifest.json');f=load(E/'report-final-v2/figure-inputs.json');v1=load(E/'report-final-v1/figure-inputs.json')
for name,r in m['inputs'].items():check('input_hash:'+name,ref(r['path'])==r)
for r in [m['renderer']]+m['outputs']:check('output_or_renderer_hash:'+Path(r['path']).name,ref(r['path'])==r)
check('exact_pdf',ref(E/'report-final-v2/ttg-next-performance.pdf')['sha256']=='aafcd4cc8b634abf3cb628ba19f3d0686bdc5f46b1e59f20ae8e0064caf0d3a0')
check('exact_manifest',ref(E/'report-final-v2/manifest.json')['sha256']=='fab57bf243e00ccd4e7d7a52774492f85533726f553b80ac80720d9957de24c9')
check('v2_figure_data_unchanged',all(f[k]==v1[k] for k in f if k!='source'))
export=load(E/'export-v1/results.json');cpu=load(E/'cpu-summary-v1.json');coverage=load(E/'coverage-v1.json');diag=load(m['inputs']['diagnostic']['path'])
check('18_exact_export_rows',len(f['rows'])==18 and f['rows']==export['rows'] and all(r['n']==3 for r in f['rows']))
check('2_exact_cpu_modules',len(f['cpu_modules'])==2 and f['cpu_modules']==cpu['modules'])
pages=(OWN/'report-final-v2-extracted.txt').read_text().split('\f');check('26_extracted_pages',len(pages)==27 and m['page_count']==26)
md=(E/'report-final-v2/report.md').read_text()
for r in export['rows']:
 v=r['protocol_sum_ns'];label=r['case_id']+'/'+r['config_id']
 for k in ('median','min','max'):
  check('workflow_pdf_'+label+'/'+k,f'{v[k]/1e6:.3f}' in pages[7])
  check('workflow_md_'+label+'/'+k,f'{v[k]/1e6:.6f}' in md)
 d,c,t=[r[k]['median'] for k in ('sql_data','sql_control','sql_dispatches')]
 check('SQL_pdf_'+label,norm(f'{d}+{c}={t}') in norm(pages[8]))
 if 'Traverse' in r:
  v=r['Traverse']['protocol_sum_ns']
  check('Traverse_pdf_'+label,norm(f"{v['median']/1e6:.3f} [{v['min']/1e6:.3f}, {v['max']/1e6:.3f}]") in norm(pages[9]))
for module in cpu['modules']:
 b=module['runtime']['baseline850']['groups'];n=module['runtime']['next']['groups']
 for group,pg in [(b['dynamic_AST'],18),(n['cold_hydrate_only'],18),(n['warm_select_bind_unprofiled'],18),(n['warm_select_unprofiled'],19),(n['warm_bind_unprofiled'],19),(n['warm_select_bind_unprofiled'],19)]:
  for k in ('median','min','max'):check('cpu_value_page'+str(pg+1),f"{group['thread_cpu_us_per_call'][k]:.3f}" in pages[pg])
 for version in ('baseline850','next'):
  c=module['compiler'][version]
  for k in ('median','min','max'):check('compiler_cpu_page21',f"{c['groups']['same_program_unprofiled']['thread_cpu_ms'][k]:.1f}" in pages[20])
  for key in ('py','py_bytecode'):check('artifact_bytes_page21',str(c['generated_artifacts'][key]['bytes']) in pages[20])
 counters=module['compiler']['next']['groups']['same_program_profiled']['generation_counters'];vals=[c['generation_thread_cpu_ns']/1e6 for c in counters]
 for v in (statistics.median(vals),min(vals),max(vals)):check('generation_cpu_page22',f'{v:.3f}' in pages[21])
 for k in ('generation_calls','emitted_sql_bytes','emitted_artifact_bytes'):check('generation_size_count_page22',str(counters[0][k]) in pages[21])
for case in diag['recapture']:
 for p in case['plans']:
  for k in ('planning_ms','execution_ms'):check('native_plan_page12',f"{p[k]:.3f}" in pages[11])
  check('native_buffer_page12',str(p['root_buffers']['Shared Hit Blocks']) in pages[11])
for case in diag['controlled_statistics']:
 for phase in case['phases']:
  for p in phase['plans']:
   for k in ('planning_ms','execution_ms'):check('controlled_plan_page13',f"{p[k]:.3f}" in pages[12])
   check('controlled_buffer_page13',str(p['root_buffers']['Shared Hit Blocks']) in pages[12])
for case in {s['case_id'] for s in coverage['samples']}:
 samples=[s for s in coverage['samples'] if s['case_id']==case and s['config_id']=='next'];check('coverage_n3:'+case,len(samples)==3)
 keys=['fusion.template_queries','fusion.frontier_origins','submitted_count','promoted_count']
 values=[[s['counts'].get(k,0) for k in keys] for s in samples];check('coverage_counts_n3_constant:'+case,values[0]==values[1]==values[2])
 check('coverage_page17:'+case,norm(' '.join(map(str,values[0]))) in norm(pages[16]))
for pg,phrases in {14:['151','147','four extra calls','payload reads remain four'],15:['Source-backed interpretation','fallback resolver 2','untested','Gather 277'],18:['selected walker bundle','primary 9282 feed uses root linear'],19:['100 calls/block','1 compile/block','primary9282 selects only root linear'],20:['lazy initialization','larger'],24:['untested','Deferred roadmap','prepared-statement reuse','without dropping regressions']}.items():
 for phrase in phrases:check('scope_page'+str(pg+1)+':'+phrase,norm(phrase) in norm(pages[pg]))
check('producer_layout_pass_26_pages',load(E/'report-final-v2/layout-checks.json')['passed'] is True and len(load(E/'report-final-v2/layout-checks.json')['pages'])==26)
check('title_proof_bound',ref(E/'final-v2-title-check.json')['sha256']=='15bded1569d82bf338b2d8d3b49a44882ec1e878dc7a926748f69bd2e625a7dd')
result=dict(passed=True,scope='Final-v2 presentation numeric mapping and exact hash rebind only. Prior primary/CPU/native/diagnostic reviews carry; no new raw audit, DB, timed rerun or independent visual acceptance.',manifest=ref(E/'report-final-v2/manifest.json'),PDF=ref(E/'report-final-v2/ttg-next-performance.pdf'),renderer=m['renderer'],figure_inputs=ref(E/'report-final-v2/figure-inputs.json'),packaging_inventory=ref(E/'packaging-inputs-final-v1.json'),accepted_inputs=m['inputs'],diagnostic_review=ref(OWN/'final-sql-diagnostic-review.json'),extracted_text=ref(OWN/'report-final-v2-extracted.txt'),audit_source=ref(OWN/'report-final-v2-numeric-audit.py'),checks=checks,findings=[],limitations=['Numeric mapping does not expand the scope of the accepted underlying reviews.','Main/P7 visual acceptance is reused.','n=3 observations and version comparisons do not isolate queue/IN causes or establish whole-application CPU savings.'])
(OWN/'report-final-v2-numeric-review.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(dict(passed=True,checks=len(checks),review=ref(OWN/'report-final-v2-numeric-review.json'))))
