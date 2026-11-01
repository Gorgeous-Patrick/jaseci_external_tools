"""Presentation-only English report, outside the immutable153 capture closure."""
import argparse,hashlib,json,statistics,textwrap,os
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
E=ROOT/'project-notes/measurements/ttg-next-performance-20261101'
MODES=('off','baseline850','next')
LABEL={'off':'Off (9282)','baseline850':'TTG+ 85026d','next':'TTG+ 9282'}
CASES=('linked_list32','linked_list1000','littlex','issue_desk','knowledge_map','jdrive')
TITLE={'linked_list32':'LinkedList · 32','linked_list1000':'LinkedList · 1,000','littlex':'LittleX','issue_desk':'IssueDesk','knowledge_map':'KnowledgeMap','jdrive':'JDrive'}
COLOR={'off':'#6f8193','baseline850':'#db9651','next':'#176fa1'}
def ref(p):return dict(path=str(p.resolve()),sha256=hashlib.sha256(p.read_bytes()).hexdigest())
def read(p):return json.loads(p.read_text())
def load_ref(p):
 d=read(p);assert d['passed'];return d

def render(out,diagnostic=None):
 sources={k:E/v for k,v in dict(export='export-v1/results.json',export_seal='export-v1/artifacts.json',
    cpu='cpu-summary-v1.json',attribution='attribution-v1/results.json',coverage='coverage-v1.json',
    littlex='littlex-mechanism-v1.json',cpu_qualifications='cpu-presentation-qualifications-v1.json',lifecycle='formal-v1-stopped-capacity-v1.json').items()}
 sources['native']=E.parent/'ttg-next-20261101/accepted-native-mechanisms-v1.json'
 sources['cpu_review']=E.parent/'ttg-next-review-20261101/cpu-summary-v1-review.json'
 sources['raw_review']=E.parent/'ttg-next-review-20261101/formal72-publication-data-review.json'
 data={k:load_ref(p) for k,p in sources.items()}
 for r in data['export_seal']['outputs']:assert ref(Path(r['path']))==r
 export=data['export'];assert export['sample_counts']==dict(all=72,excluded_warmups=18,measured=54,cells=18,n_per_cell=3)
 rows={(r['case_id'],r['config_id']):r for r in export['rows']};assert len(rows)==18 and all(r['n']==3 for r in rows.values())
 if diagnostic:
  sources['diagnostic']=diagnostic;data['diagnostic']=load_ref(diagnostic)
 out.mkdir(parents=True,exist_ok=False);os.environ.setdefault('MPLCONFIGDIR',str(out/'mpl-cache'))
 import matplotlib;matplotlib.use('Agg')
 import matplotlib.pyplot as plt
 from matplotlib.backends.backend_pdf import PdfPages
 from matplotlib.patches import FancyBboxPatch,FancyArrowPatch,Circle
 plt.rcParams.update({'font.family':'DejaVu Sans','figure.facecolor':'white','savefig.facecolor':'white','text.color':'#183044','axes.spines.top':False,'axes.spines.right':False})
 inputs=dict(passed=True,source=ref(Path(__file__)),inputs={k:ref(p) for k,p in sources.items()},
  rows=export['rows'],cpu_modules=data['cpu']['modules'],
  definitions='Times in ms from accepted nanoseconds/1e6. Medians and ranges copied from accepted n = 3 statistics. CPU construction is separate microbench; source-backed interpretations labelled. Renderer does not reaggregate primary raw data.',
  CPU_scope_qualifications=['Runtime blocks contain100 calls; compiler blocks contain1 actual compile. Both have3 repeated blocks per regime.',
    'LittleX collect batch events 4/5 are an actual emitted but declared microbenchmark shape; primary9282 load_feed selects root linear only. This microbenchmark does not establish deployed LittleX CPU savings.',
    'frontier_origins counts bound seed/demand origins; one seed can recursively expand 1,000 steps. Primary cross-queued-origin width is one.'])
 page_no=0;report=['# TTG+: queued continuations and compiler-emitted SQL','',
  'Five existing applications, six fixtures, 72 fresh workflows: 18 excluded warmups and54 measured trials (n = 3 in all 18 cells).',
  'Primary DB metrics: actual PgWire sendall to ReadyForQuery protocol completion wall, summed intervals and their union, all-role SQL/data/control counts.','']
 pending=[];layout_records=[]
 def wrap_pixels(text,renderer,properties,width):
  output=[]
  for paragraph in text.split('\n'):
   words=paragraph.split();line=''
   if not words:output.append('');continue
   for word in words:
    candidate=(line+' '+word).strip()
    if line and renderer.get_text_width_height_descent(candidate,properties,False)[0]>width:
     output.append(line);line=word
    else:line=candidate
   output.append(line)
  return '\n'.join(output)
 def page(title,subtitle=''):
  f=plt.figure(figsize=(16,9));f._title=title;f._tables=[]
  f.text(.055,.92,title,size=28,weight='bold',ha='left')
  if subtitle:f.text(.055,.865,subtitle,size=15,color='#526d82')
  return f
 def save(pdf,f,regime='primary n = 3 fresh workflows | seed 42'):
  pending.append((f,regime))
 def lines(f,items,x=.065,y=.76,size=20,gap=.12):
  for item in items:f.text(x,y,item,size=size,va='top',linespacing=1.45);y-=gap
 def box(ax,x,y,w,h,text,face='#edf4fa',size=16):
  ax.add_patch(FancyBboxPatch((x,y),w,h,boxstyle='round,pad=0.012',facecolor=face,edgecolor='#96afc2'))
  props=matplotlib.font_manager.FontProperties(family='DejaVu Sans',size=size)
  width=w*ax.get_position().width*ax.figure.bbox.width*.92
  text=wrap_pixels(text,ax.figure.canvas.get_renderer(),props,width)
  ax.text(x+w/2,y+h/2,text,ha='center',va='center',size=size)
 def arrow(ax,a,b):ax.add_patch(FancyArrowPatch(a,b,arrowstyle='-|>',mutation_scale=19,color='#397b9f',lw=1.8))
 def table(f,headers,body,area=(.055,.18,.89,.61),font=14,widths=None):
  ax=f.add_axes(area);ax.axis('off');widths=widths or [1/len(headers)]*len(headers)
  renderer=f.canvas.get_renderer();wrapped=[]
  for i,row in enumerate([headers]+body):
   props=matplotlib.font_manager.FontProperties(family='DejaVu Sans',size=font,weight='bold' if i==0 else 'normal')
   wrapped.append([wrap_pixels(str(v),renderer,props,area[2]*f.bbox.width*widths[j]*.88) for j,v in enumerate(row)])
  weights=[max(v.count('\n')+1 for v in row)+.65 for row in wrapped];weight=sum(weights)
  t=ax.table(cellText=wrapped[1:],colLabels=wrapped[0],loc='center',cellLoc='left',colLoc='left',colWidths=widths)
  t.auto_set_font_size(False);t.set_fontsize(font)
  for (i,j),c in t.get_celld().items():
   c.set_height(.90*weights[i]/weight);c.set_edgecolor('#d3dfe7');c.PAD=.04
   if i==0:c.set_facecolor('#dcebf5');c.set_text_props(weight='bold')
   else:c.set_facecolor('#f5f9fc' if i%2 else 'white')
  f._tables.append(t);return t
 def finish(pdf):
  nonlocal page_no
  order=['TTG+','Research problem:','At B:','Compile once:','One emitted template,','Four-origin capability',
    'Why these existing','Complete fixed','All SQL','Native Traverse:','LL1000:','Matched recursive',
    'Controlled ANALYZE','Why ANALYZE','LittleX:','LittleX limiter:','One bound seed/',
    'Domain cases:','Construction-only','Selection and binding','Compilation and artifact','SQL generation:',
    'Real process','Measurement and lifecycle','What to improve','Reproducible evidence']
  assert len(pending)==len(order)
  ordered=[]
  for prefix in order:
   found=[p for p in pending if (p[0]._title==prefix if prefix=='TTG+' else p[0]._title.startswith(prefix))]
   assert len(found)==1,(prefix,[p[0]._title for p in found]);ordered.extend(found)
  for f,regime in ordered:
   page_no+=1
   f.canvas.draw();renderer=f.canvas.get_renderer();W,H=f.bbox.width,f.bbox.height
   for i,t in enumerate(f.texts):
    bbox=t.get_window_extent(renderer)
    available=(.942-t.get_position()[0])*W
    if i==0:
     assert t.get_horizontalalignment()=='left'
     if bbox.width>available:t.set_fontsize(max(24,t.get_fontsize()*available/bbox.width))
    else:
     oldtop=bbox.y1/H
     t.set_text(wrap_pixels(t.get_text(),renderer,t.get_fontproperties(),available))
     t.set_verticalalignment('top');t.set_y(oldtop)
   f.canvas.draw();renderer=f.canvas.get_renderer();checks=[]
   for i,t in enumerate(f.texts):
    b=t.get_window_extent(renderer);checks.append(dict(kind='figure',text=t.get_text(),bounds=[b.x0/W,b.y0/H,b.x1/W,b.y1/H]))
   for table_obj in f._tables:
    for cell in table_obj.get_celld().values():
     b=cell.get_text().get_window_extent(renderer);c=cell.get_window_extent(renderer)
     assert b.x0>=c.x0-1 and b.x1<=c.x1+1 and b.y0>=c.y0-1 and b.y1<=c.y1+1,('Table text outside cell',f._title,cell.get_text().get_text())
     checks.append(dict(kind='table',text=cell.get_text().get_text(),bounds=[b.x0/W,b.y0/H,b.x1/W,b.y1/H]))
   for q in checks:
    x0,y0,x1,y1=q['bounds'];assert x0>=.045 and x1<=.945 and y0>=.060 and y1<=.98,(f._title,q)
   # Explicit figure-text overlap checks; table axes are checked cell-by-cell.
   boxes=[(t,t.get_window_extent(renderer)) for t in f.texts]
   for i,(a,ab) in enumerate(boxes):
    for b,bb in boxes[i+1:]:
     overlap_x=min(ab.x1,bb.x1)-max(ab.x0,bb.x0);overlap_y=min(ab.y1,bb.y1)-max(ab.y0,bb.y0)
     assert overlap_x<=1 or overlap_y<=1,('Figure text overlap',f._title,a.get_text(),b.get_text())
   layout_records.append(dict(page=page_no,title=f._title,passed=True,text_checks=checks))
   f.text(.055,.033,'TTG+ | 85026d → 9282e246 | '+regime,size=10,color='#526d82');f.text(.95,.033,str(page_no),ha='right',size=10)
   pdf.savefig(f);f.savefig(out/f'slide-{page_no:02d}.png',dpi=105);plt.close(f)
 def ts(v):return f"{v['median']/1e6:.3f}\n[{v['min']/1e6:.3f}, {v['max']/1e6:.3f}]"
 def micro_label(item):return 'LinkedList / linear' if item['case']=='linked_list32' else 'LittleX / collect batch'
 def module_label(item):return 'LinkedList module' if item['case']=='linked_list32' else 'LittleX module'
 def cmedian(case,mode,field):return rows[(case,mode)][field]['median']
 with PdfPages(out/'ttg-next-performance.pdf',metadata={'Title':'TTG+ — queued continuation and compiled SQL evaluation','Author':'TTG research'}) as pdf:
  f=page('TTG+','Construction savings are clear; DB results depend on the workload and eligible region.')
  lines(f,['Five existing applications · six fixed fixtures · all 18 cells with n = 3',
   'LinkedList removes per-hop SQL versus Off; both TTG+ versions use16 per Traverse.',
   'New versus850: workflow medians vary; LittleX, IssueDesk and KnowledgeMap remain slower than Off.',
   'Construction microbench: ~1.5–1.8ms AST → ~4.7–7.0µs warm select/bind CPU.',
   'One bound seed/demand origin per template query; four-origin batching is a separate native test.'],size=20,gap=.115)
  save(pdf,f)
  f=page('Research problem: repeated runtime work','Graph traversal interleaves path discovery, payload loading and application state.')
  lines(f,['Native visit requests the next ordered graph path, then materializes its target payloads.',
    'Repeated hops can repeat SQL dispatches; runtime SQL AST construction adds client CPU work.',
    'Future graph accesses depend on program position, guards, carried state and the pending FIFO queue.',
    'TTG+ combines queued continuation analysis, batched path SQL and compiler-emitted typed templates.'],size=21,gap=.145)
  save(pdf,f)
  f=page('Complete fixed selection: DB protocol time','Whole-workflow median and [min, max] ms; all counts are fresh workflows, n = 3 per cell.')
  body=[[TITLE[c]]+[ts(rows[(c,m)]['protocol_sum_ns']) for m in MODES] for c in CASES]
  table(f,['Fixture','Off (9282)','TTG+ 85026d','TTG+ 9282'],body,font=15)
  f.text(.065,.095,'All 72 observed protocol sums equal interval unions. Timing includes actual data and transaction-control SQL.',size=15)
  save(pdf,f)
  f=page('All SQL is counted: data + control = TOTAL','Whole workflow; every count is identical across its three measured repeats.')
  body=[]
  for c in CASES:
   values=[]
   for m in MODES:
    r=rows[(c,m)];values.append(f"{int(r['sql_data']['median'])} + {int(r['sql_control']['median'])} = {int(r['sql_dispatches']['median'])}")
   body.append([TITLE[c]]+values)
  table(f,['Fixture','Off','85026d','9282'],body,font=16)
  f.text(.065,.095,'Foreground, child payload reads, path discovery, identity/catalog and transaction completion are retained.',size=15)
  save(pdf,f)
  f=page('Why these existing applications','The selection was fixed before timing; unsupported and slower cells are retained.')
  table(f,['Application','Native behavior and exercised oracle'],[
   ['LinkedList32 /1000','Traverse + Sum + Find(head/middle/tail/missing); exact order/count/state'],
   ['LittleX original','Feed / search / likes / follow / create; feed order, authorship, graph and restart'],
   ['IssueDesk','Engineer then issue visits; assignees/blockers/comments; mutations + cycle rejection'],
   ['KnowledgeMap','Shared-topic graph, a↔b links and explicit seen guard; publish/review/revise + denials'],
   ['JDrive','Folder depth/path dictionaries and trashed predicate; tree/trash/mkdir/persistence']],font=14,widths=[.25,.75])
  f.text(.065,.105,'Existing accepted Seed 42 fixtures, original native workflows and independent correctness oracles.',size=14)
  save(pdf,f)
  f=page('At B: continue the known FIFO queue and carry state','A has already queued B, C, D, E. Hook B observes self.i=0 and pending=[C,D,E].')
  ax=f.add_axes([.055,.30,.58,.49]);ax.set(xlim=(0,1),ylim=(0,1));ax.axis('off')
  box(ax,.45,.82,.13,.14,'A');
  for j,name in enumerate('BCDE'):
   x=.08+j*.23;box(ax,x,.49,.15,.19,name+'\ni='+str(j+1),size=17);arrow(ax,(.515,.82),(x+.075,.69));box(ax,x,.10,.15,.18,str([1,12,22,32][j]),'#e6f2eb',size=17);arrow(ax,(x+.075,.49),(x+.075,.28))
  for j,label in enumerate(('Left','Right','Right','Right')):ax.text(.09+j*.23,.37,label,size=13)
  f.text(.64,.74,'can branch with FrontierBranch entry {\n  self.i += 1;\n  if self.i == 1 {\n    visit [->:FrontierLeft:->\n           [?:FrontierLeaf]];\n  } else {\n    visit [->:FrontierRight:->\n           [?:FrontierLeaf]];\n  }\n}',family='DejaVu Sans Mono',size=15,va='top',linespacing=1.40)
  f.text(.065,.18,'Prediction carries scalar state in FIFO order; native abilities and the native queue retain their execution order.',size=17)
  f.text(.065,.115,'Graph uses short node names; code uses FrontierWalk native syntax. Reports [1,12,22,32] and final i = 4 match.',size=15)
  save(pdf,f,'separate accepted native mechanism test')
  f=page('Four-origin capability and the disengage assumption','Prediction assumes queued nodes trigger; native execution and cancellation remain authoritative.')
  table(f,['Accepted native case','Baseline','Next','Native result'],[
   ['Four-origin FrontierWalk','8 submitted\n8 promoted','8 submitted\n8 promoted','B,C,D,E; i=4\nreports1,12,22,32'],
   ['FrontierCancel','5 submitted\n5 promoted / 0 unused','7 submitted\n5 promoted / 2 unused','entered[0,1]\nreports[] unchanged']],area=(.055,.36,.89,.37),font=16)
  f.text(.065,.25,'The cancelled case demonstrates two extra predicted descendant payloads in this identity-bound fixture.',size=18)
  f.text(.065,.16,'Queued parent endpoints were already demanded by native visit evaluation. Ability entry and payload demand are distinct.',size=17)
  save(pdf,f,'accepted native functional integration')
  f=page('Compile once: emit SQL, then hydrate/select/bind','SQL AST generation moves into the actual Jac compiler emitter for covered emitted regions.')
  ax=f.add_axes([.055,.33,.89,.44]);ax.set(xlim=(0,1),ylim=(0,1));ax.axis('off')
  labels=['Jac emitter\ncompile_templates(events)','Serialized SQL + fixed params\n+ typed runtime slots','Graph load\nhydrate descriptors','Hook → select region\n→ bind typed values']
  for j,label in enumerate(labels):
   x=.01+j*.25;box(ax,x,.45,.22,.34,label,size=15)
   if j<3:arrow(ax,(x+.22,.62),(x+.25,.62))
  f.text(.065,.28,'Runtime slots: origins per site, actor UUID/text, row limit; linear regions also bind source type/module and depth.',size=17)
  f.text(.065,.18,'Bound SQL → unchanged PgWire boundary → ordered per-origin path cache + merged process payload loading.',size=18)
  f.text(.065,.105,'Covered primary paths report template_queries > 0 / legacy_fusion_calls = 0. Ordinary fallback still constructs its own queries.',size=15)
  save(pdf,f)
  f=page('One emitted template, many runtime origins','Simplified SQL shape; actual SQL and exact fingerprints are retained in the sealed evidence.')
  f.text(.065,.76,'SELECT slot, origin_order, target_id, arity\nFROM unnest(:origins_1::uuid[]) WITH ORDINALITY AS seed\nLEFT JOIN LATERAL (native ordered Post → Tweet path) ON TRUE\nUNION ALL\nSELECT ... FROM unnest(:origins_2::uuid[]) ...\nORDER BY slot, depth, ord\nLIMIT :row_limit;',size=18,family='DejaVu Sans Mono',va='top',linespacing=1.65)
  f.text(.065,.29,'Linear form uses a recursive origin_id/depth CTE, continuing only while actual arity == 1 and type/module match.',size=18)
  f.text(.065,.19,'The analyzer supplies permitted program transitions; SQL checks graph cardinality. Ordered and empty results seed native path cache.',size=17)
  f.text(.065,.105,'9282 also changes the emitted type-membership predicate to uncorrelated IN. This is a version/package comparison.',size=15)
  save(pdf,f)
  f=page('Construction-only thread CPU: AST versus templates','Construction microbenchmark: 100 calls/block × 3 blocks; 10 excluded AST/warm priming calls.')
  body=[]
  for item in data['cpu']['modules']:
   b=item['runtime']['baseline850']['groups'];n=item['runtime']['next']['groups']
   def us(s):return f"{s['median']:.3f}\n[{s['min']:.3f}, {s['max']:.3f}]"
   body.append([micro_label(item),us(b['dynamic_AST']['thread_cpu_us_per_call']),us(n['cold_hydrate_only']['thread_cpu_us_per_call']),us(n['warm_select_bind_unprofiled']['thread_cpu_us_per_call'])])
  table(f,['Module/shape','850 AST µs/call','9282 cold hydrate µs','9282 warm select+bind µs'],body,area=(.055,.40,.89,.36),font=16)
  f.text(.065,.29,'AST build count: 100/block for dynamic construction; 0 for hydration/selection/binding. Same-thread clock controls passed.',size=17)
  f.text(.065,.19,'Cold hydration covers the selected walker bundle. Inputs bind actual emitted sites and fixture IDs with declared common2048 limits.',size=16)
  f.text(.065,.105,'Declared LittleX collect-batch microbenchmark; the primary 9282 feed uses root linear.',size=15)
  save(pdf,f,'separate DB-free construction diagnostic; n = 3 blocks')
  f=page('Selection and binding are measured separately','Runtime only: 100 calls/block × 3 blocks; compiler measurements use 1 compile/block.')
  body=[]
  for item in data['cpu']['modules']:
   n=item['runtime']['next']['groups']
   values=[]
   for method in ('warm_select_unprofiled','warm_bind_unprofiled','warm_select_bind_unprofiled'):
    s=n[method]['thread_cpu_us_per_call'];values.append(f"{s['median']:.3f}\n[{s['min']:.3f}, {s['max']:.3f}]")
   body.append([micro_label(item)]+values)
  table(f,['Declared emitted shape','Select µs/call','Bind µs/call','Select +bind µs/call'],body,area=(.055,.39,.89,.38),font=16)
  f.text(.065,.28,'Separate select/bind counters use opt-in timers; unprofiled blocks retain native clocks disabled.',size=17)
  f.text(.065,.18,'Cold selected-walker hydration is separate; copying/spec validation/artifact metadata stay outside measured blocks.',size=16)
  f.text(.065,.105,'LL uses a covered linear shape. LittleX uses declared collect events 4/5; primary9282 selects only root linear.',size=15)
  save(pdf,f,'separate same-thread CPU construction diagnostic')
  f=page('Compilation and artifact growth are part of the tradeoff','First compiler calls include lazy initialization; full CPU vectors and controls are preserved.')
  body=[]
  for item in data['cpu']['modules']:
   b=item['compiler']['baseline850'];n=item['compiler']['next'];bg=b['groups']['same_program_unprofiled']['thread_cpu_ms'];ng=n['groups']['same_program_unprofiled']['thread_cpu_ms']
   body.append([module_label(item),f"{bg['median']:.1f} [{bg['min']:.1f}, {bg['max']:.1f}]\n{ng['median']:.1f} [{ng['min']:.1f}, {ng['max']:.1f}]",str(b['generated_artifacts']['py']['bytes'])+' → '+str(n['generated_artifacts']['py']['bytes']),str(b['generated_artifacts']['py_bytecode']['bytes'])+' → '+str(n['generated_artifacts']['py_bytecode']['bytes'])])
  table(f,['Module','Same-program CPU ms\n850 /9282','Generated Python bytes','Bytecode bytes'],body,area=(.055,.39,.89,.38),font=15)
  f.text(.065,.27,'Same-program runs follow one excluded compile; n = 3. First fresh-program CPU: LL ≈ 3.9/3.8s; LittleX ≈ 4.6/4.5s (850/9282).',size=16)
  f.text(.065,.17,'All fresh/same-program, wall/thread CPU, emitted SQL bytes and opt-in generation counters remain in the editable data.',size=16)
  f.text(.065,.105,'Full compiler vectors retain initialization and dispersion; generated Python and bytecode artifacts are larger.',size=15)
  save(pdf,f,'separate actual compiler/emitter diagnostic')
  f=page('SQL generation: measured cost and size','Actual emitter generation timers; separate profiled and unprofiled controls.')
  body=[]
  for item in data['cpu']['modules']:
   counters=item['compiler']['next']['groups']['same_program_profiled']['generation_counters']
   vals=[c['generation_thread_cpu_ns']/1e6 for c in counters]
   body.append([module_label(item),str(counters[0]['generation_calls']),f"{statistics.median(vals):.3f}\n[{min(vals):.3f}, {max(vals):.3f}]",str(counters[0]['emitted_sql_bytes']),str(counters[0]['emitted_artifact_bytes'])])
  table(f,['Module','Generation calls','Generation thread CPU ms','SQL bytes','Bundle bytes'],body,area=(.055,.39,.89,.38),font=15)
  f.text(.065,.27,'Counts include all walker checkpoint emission in the compiled module; bundles include catalog, batch, linear and native descriptors.',size=16)
  f.text(.065,.17,'SQL generation occurs during compilation; emitted descriptors, generated Python and bytecode sizes are measured.',size=17)
  save(pdf,f,'actual compiler generation instrumentation; n = 3 profiled compile controls')
  f=page('Native Traverse: SQL reduction is already present in850','TOTAL includes path discovery, payload reads, identity/catalog and controls; all n = 3 counts constant.')
  body=[]
  for c,n in [('linked_list32',32),('linked_list1000',1000)]:
   for m in MODES:
    r=rows[(c,m)];t=r['Traverse'];path=n if m=='off' else 1;payload=n+3 if m=='off' else 5;controls=7 if m=='off' else 8
    body.append([TITLE[c]+' /'+LABEL[m],ts(t['protocol_sum_ns']).replace('\n',' '),str(path),str(payload),str(controls),str(int(t['sql_dispatches']['median']))])
  table(f,['Fixture /mode','Protocol ms median [range]','Path','Payload','Control','TOTAL'],body,font=12.5,widths=[.24,.32,.10,.11,.11,.12])
  f.text(.065,.105,'Every row also has1 identity and 1 catalog query. Fused path counts 1; Off ordinary paths32/1000. Exact visited32/1000.',size=15)
  save(pdf,f)
  f=page('LL1000: the recursive SQL interval carries the variation','Same 1,000 returned rows /161,806 DataRow payload bytes; one recursive call per Traverse.')
  ax=f.add_axes([.09,.33,.49,.43])
  for j,m in enumerate(('baseline850','next')):
   selected=[s for s in data['attribution']['samples'] if s['case_id']=='linked_list1000' and s['config_id']==m]
   vals=[s['RPCs'][0]['categories']['fused_recursive']['protocol_sum_ns']/1e6 for s in selected]
   ax.scatter([j-.12,j,j+.12],vals,s=75,color=COLOR[m]);ax.plot([j-.16,j+.16],[statistics.median(vals)]*2,color=COLOR[m],lw=2)
   ax.text(j,.5,' / '.join(f'{v:.2f}' for v in vals),ha='center',size=11)
  ax.set(xticks=[0,1],xticklabels=['85026d','9282'],ylabel='Single recursive call protocol ms',ylim=(0,65))
  f.text(.64,.72,'850:55.257 /18.580 /18.421 ms\n9282:55.135 /53.809 /18.901 ms',size=19,va='top',linespacing=1.7)
  f.text(.64,.50,'Payload 5 calls stay around 10.6–11.1 ms.\nBoth versions have slow and fast samples.\nPrimary per-run plans/statistics\nare unavailable.',size=17,va='top',linespacing=1.6)
  f.text(.065,.13,'Workflow medians: 3,337.873 ms Off → 2,360.957 ms (850) → 2,310.506 ms (9282); Traverse medians differ in the opposite direction.',size=15)
  save(pdf,f)
  if diagnostic:
   diag=data['diagnostic'];assert diag['primary_performance'] is False and len(diag['recapture'])==len(diag['controlled_statistics'])==2
   f=page('Matched recursive SQL: accepted native recaptures','Two full six-operation workflows; exact captured SQL/Bind/state and original 1,000-row completion.')
   body=[]
   for case in diag['recapture']:
    assert case['actual_original_rows']==1000 and case['state_isolation']=='serializable'
    ps=case['plans'];body.append([LABEL[case['config_id']], ' / '.join(f"{p['planning_ms']:.3f}" for p in ps),' / '.join(f"{p['execution_ms']:.3f}" for p in ps),str(ps[0]['root_buffers']['Shared Hit Blocks'])])
   table(f,['Version','Planning ms: first / repeat','Execution ms: first / repeat','Root shared hits'],body,area=(.055,.39,.89,.38),font=16)
   f.text(.065,.29,'Serializable transactions; statistics rows = 0 and reltuples = −1. Census and EXPLAIN warm buffers.',size=16)
   f.text(.065,.19,'Shared reads = 0; spills = 0; JIT absent. Root buffer counters are direct inclusive values.',size=16)
   f.text(.065,.105,'Diagnostic EXPLAIN: first/repeat measurements, separate from the primary n = 3 protocol samples.',size=15)
   save(pdf,f,'separate exact-Bind native recaptures; first/repeat')
   f=page('Controlled ANALYZE changes the plan and execution cost','Restored captured relevant state, original DDL/indexes/settings and exact Bind; same ordered 1,000-row result.')
   body=[]
   for case in diag['controlled_statistics']:
    assert case['exact_bind_verified']
    for ph in case['phases']:
     assert ph['ordered_result_verified'] and ph['census_verified']
     ps=ph['plans'];body.append([LABEL[case['config_id']], 'After ANALYZE' if ph['analyzed'] else 'Before ANALYZE',
       ' / '.join(f"{p['planning_ms']:.3f}" for p in ps),' / '.join(f"{p['execution_ms']:.3f}" for p in ps),str(ps[0]['root_buffers']['Shared Hit Blocks'])])
   table(f,['Version','Statistics regime','Planning ms first/repeat','Execution ms first/repeat','Shared hits'],body,font=14,widths=[.18,.21,.23,.24,.14])
   f.text(.065,.16,'Before: reltuples = −1 for anchors/types. After: anchors = 2,005, graph_types = 4. Shared reads = 0.',size=16)
   f.text(.065,.095,'Controlled restored fixtures establish statistics sensitivity. Primary per-run plans/statistics are unavailable.',size=14.5)
   save(pdf,f,'controlled SQL-only before/after ANALYZE; first/repeat')
   f=page('Why ANALYZE helps in the controlled fixture','Measured operator change at two path-evaluation sites in the controlled restored fixture.')
   ax=f.add_axes([.055,.31,.89,.45]);ax.set(xlim=(0,1),ylim=(0,1));ax.axis('off')
   box(ax,.02,.41,.42,.42,'Before: BitmapAnd\nkind-only index + BitmapOr(src,dst)\n1,000 kind rows × 1,000 loops\nat each of two sites',size=17)
   arrow(ax,(.45,.62),(.55,.62))
   box(ax,.56,.41,.42,.42,'After: BitmapOr(src,dst)\nkind-only bitmap work removed\nendpoint anchors_pkey remains\nshared hits 20,126 → 16,126',face='#e8f3ec',size=17)
   f.text(.065,.27,'Execution falls from about 48–50 ms to 13.4–13.7 ms on both restored versions; JIT is absent in all 12 diagnostic plans.',size=17)
   f.text(.065,.17,'Controlled restored fixture: captured relevant columns, original defaults for unused columns, fresh heap, warm buffers.',size=15.5)
   f.text(.065,.095,'Next work: explicit statistics regimes, cost admission and database prepared-statement reuse. Primary per-run statistics unavailable.',size=15)
   save(pdf,f,'separate matched SQL-plan evidence; all original ordered results verified')
  f=page('LittleX: four feed requests add four data calls in9282','Each feed:850 has 2 fused queries;9282 has 1 fused root query +2 ordinary collect paths.')
  table(f,['Whole workflow','Off','85026d','9282'],[
   ['Protocol ms median',*[f"{rows[('littlex',m)]['protocol_sum_ns']['median']/1e6:.3f}" for m in MODES]],
   ['Data +control =TOTAL','90 +63 =153','78 +69 =147','82 +69 =151'],
   ['Per feed path discovery','3 ordinary','1 root +1 batch','1 root +2 ordinary'],
   ['Per feed payload reads','6','4','4']],font=16)
  f.text(.065,.14,'The four extra calls are path discovery; payload reads remain four per feed. Native outputs, order and final graph match.',size=17)
  save(pdf,f)
  f=page('LittleX limiter: one frontier attempt per continuation invocation','Source-backed interpretation, joined to compact counters, emitted event IDs and actual SQL sequence.')
  f.text(.065,.76,'frontier_attempted = []\nresolve(active, event):\n  if cached_path: return cached_path\n  if graph.sql_templates and not frontier_attempted:\n    frontier_attempted.append(True)\n    resolve_frontier(...)\n  if path_missing: resolve_ttg_path(...)',family='DejaVu Sans Mono',size=18,va='top',linespacing=1.55)
  f.text(.63,.76,'Event 1: Root → Profile\n  consumes the one attempt\n\nEvents 4/5: collect visits\n  ordinary fallback and reuse cache\n\nLater hooks return reused paths\n  before another frontier attempt',size=18,va='top',linespacing=1.55)
  f.text(.065,.225,'Recorded: template query 1, linear region 1, fallback resolver 2 and reached collect events 4/5; source-backed control interpretation.',size=16)
  f.text(.065,.145,'Gather 277 is a real tail barrier after both visits. It is insufficient to explain the missing current-ability batch.',size=16)
  f.text(.065,.085,'Proposed, untested: retry distinct proven regions/activations with path reuse/dedup; preserve guard and native semantics.',size=15)
  save(pdf,f)
  f=page('One bound seed/demand origin per template query','Fixed application queries use one bound seed/demand origin; a separate native integration binds four.')
  body=[]
  for c in CASES:
   s=next(s for s in data['coverage']['samples'] if s['case_id']==c and s['config_id']=='next' and s['repeat']==0);n=s['counts']
   body.append([TITLE[c],str(n.get('fusion.template_queries',0)),str(n.get('fusion.frontier_origins',0)),str(n.get('submitted_count',0)),str(n.get('promoted_count',0))])
  table(f,['Fixture','Template SQL','Bound seed/demand origins','Submitted','Promoted'],body,font=15)
  f.text(.065,.17,'One seed recursively covers 1,000 LinkedList steps. Cross-queued-origin demand width remains one in the fixed applications.',size=15)
  f.text(.065,.105,'Workflow counts are constant across n = 3; submission/promotion totals sum native per-scope ID sets.',size=15)
  save(pdf,f)
  f=page('Domain cases: reached barriers and controls remain visible','Actual compact checkpoint counts bind reached source locations and outcomes.')
  table(f,['Application','Observed evidence','Measured result'],[
   ['IssueDesk','9 template queries;14 submitted/promoted\nproject:98, engineer:104, issue:109 barriers reached','561SQL vs557 Off\n159.419ms vs139.440ms'],
   ['KnowledgeMap','4 templates;9 submitted/promoted\narticle:52 / article:171 and start:165 barriers','301SQL vs298 Off\n79.167ms vs72.712 ms'],
   ['JDrive','0 template queries /0 submissions\nwalk:45 /walk:48 /run:41 barriers reached','156SQL in all modes\n46.648ms vs48.053ms Off']],font=14)
  f.text(.065,.16,'Mutations, nested spawns, cycles/private views and restart/persistence were retained in independent stored replay and physical state checks.',size=16)
  save(pdf,f)
  f=page('Real process readers; zero observed SQL interval overlap','A child process existing is insufficient: actual PgWire calls and distinct backend PIDs are recorded.')
  sample=next(s for s in data['attribution']['samples'] if s['case_id']=='linked_list1000' and s['config_id']=='next' and s['repeat']==0)
  calls=sample['RPCs'][0]['Traverse_call_intervals'];parents=sorted({c['client_process_pid'] for c in calls if c['role']=='foreground'});children=sorted({c['client_process_pid'] for c in calls if c['role']!='foreground'})
  lines(f,[f'LL1000 representative Traverse: foreground PID {parents}; child PID {children}.',
   '14 foreground SQL +2 child SQL; actual separate PostgreSQL backends.',
   'All 72 protocol sums equal interval unions; observed SQL overlap = 0.',
   'Python 3.14 has the GIL enabled; actual child SQL executes on independent PostgreSQL backends.',
   'Startup/readiness and IPC remain in the natural workflow; DB totals cover only their actual SQL calls.'],size=19,gap=.115)
  save(pdf,f)
  f=page('Measurement and lifecycle','Primary clock: driver/socket sendall to ReadyForQuery, including response/row-decoding progress.')
  lines(f,['Clock immediately before real sendall → receipt of ReadyForQuery Z; row decoding/progress included.',
   'Parameter encoding/compiler/model work stays outside that interval; outer driver-call times retained separately.',
   'C CommandComplete, D rows/bytes, actual command cycles and SQL fingerprints retained; controls count.',
   'Fresh per-trial DB; identical seeded actions; one profile reset after setup; Always/process 1; limit 2048/steps 32768.',
   'OS/PG buffers warmed by seed/verification; SQL statement logging off; WAL min 32 / max 64 MB.'],size=18,gap=.12)
  save(pdf,f)
  f=page('What to improve next','Proposals are untested improvements, selected from measured limits rather than assumed speedups.')
  lines(f,['Region-aware retry/dedup: remove the single-attempt LittleX limitation while preserving native cache reuse.',
   'Admission by opportunity and cost: wider eligible origins matter; current application queries observe width1.',
   'Deferred roadmap: cost-model admission and database prepared-statement reuse, evaluated against workload selectivity.',
   'Artifact budget: consider deduplicated descriptors, lazy region hydration and selective template emission.',
   'Retain guard/identity/oracle checks and intentional overfetch accounting; evaluate existing workflows without dropping regressions.'],size=19,gap=.12)
  save(pdf,f)
  f=page('Reproducible evidence and exact completed inventory','72/72 primary workflows; 18/18 native correctness cases; five existing applications.')
  lines(f,['Runtime versions85026d and9282e246; primary Off uses9282. Same process 1/2048/32768 settings.',
   '54 measured +18 excluded warmups; all 18 n = 3 cells, complete CSV/JSON, sealed SQL/HTTP/events and semantic proofs.',
   'Independent audit:142,488 driver records /3,184 sealed files; all request/count/interval/export statistics match.',
   'Actual compiler output/artifacts and separate CPU controls; native four-origin/cancel evidence; source-bound LittleX explanation.',
   'Editable renderer + figure inputs + report/source hashes. Primary and diagnostic evidence remain separately identified.'],size=18,gap=.12)
  save(pdf,f)
  finish(pdf)
 report+=['| Fixture | Mode | Protocol median ms | Range ms | TOTAL SQL | Data | Control |','|---|---|---:|---|---:|---:|---:|']
 for c in CASES:
  for m in MODES:
   r=rows[(c,m)];v=r['protocol_sum_ns'];report.append(f"|{TITLE[c]}|{LABEL[m]}|{v['median']/1e6:.6f}|{v['min']/1e6:.6f}–{v['max']/1e6:.6f}|{r['sql_dispatches']['median']}|{r['sql_data']['median']}|{r['sql_control']['median']}|")
 report+=['','All 72 observed protocol sums equal unions. SQL includes all foreground/background and transaction-control calls.',
  'The fixed application workloads observe one bound seed/demand origin per template query (not total recursive expansion); the four-origin native fixture is separate functional evidence.',
  'Construction microbenchmark results, compiler initialization, full ranges and artifact growth are retained separately.',
  'See figure-inputs.json for exact source/evidence references and complete statistics.']
 (out/'layout-checks.json').write_text(json.dumps(dict(passed=True,pages=layout_records,right_limit=.945,checks='All figure text bounds and pair overlap; every table cell text contained by its cell.'),indent=2)+'\n')
 (out/'report.md').write_text('\n'.join(report)+'\n');(out/'figure-inputs.json').write_text(json.dumps(inputs,indent=2)+'\n')
 outputs=[ref(p) for p in sorted(out.glob('*')) if p.is_file()]
 manifest=dict(passed=True,page_count=page_no,renderer=ref(Path(__file__)),inputs={k:ref(p) for k,p in sources.items()},outputs=outputs,
  scope='Presentation-only; no primary capture/numeric source changed.')
 (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n');print(json.dumps(dict(page_count=page_no,PDF=ref(out/'ttg-next-performance.pdf'),manifest=ref(out/'manifest.json'))))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--diagnostic',type=Path);a=p.parse_args();render(a.output.resolve(),a.diagnostic)
