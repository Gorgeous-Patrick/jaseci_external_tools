"""Editable English interability report; presentation only, outside capture172."""
import argparse,hashlib,json,os,textwrap
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
E=ROOT/'project-notes/measurements/ttg-interability-performance-20261101'
MODES=('off','baseline9282','interability')
LABEL={'off':'Off','baseline9282':'9282','interability':'Interability'}
CASES=('finite_list32','finite_list1000','guard_chain','littlex')
TITLE={'finite_list32':'LinkedList32','finite_list1000':'LinkedList1,000','guard_chain':'A→B→C','littlex':'LittleX'}
def ref(p):
 p=Path(p).resolve();return dict(path=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest())
def read(p):return json.loads(Path(p).read_text())
def render(out,diagnostic):
 out=Path(out).resolve();assert not out.exists();out.mkdir(parents=True)
 paths=dict(numeric=E/'export-v2/results.json',analysis=E/'analysis-v1/results.json',
  method=E.parent/'ttg-interability-20261101/method-inputs-v1.json',
  cost=E.parent/'ttg-interability-main-20261101/existing-cost-model-v1.json',
  inventory=ROOT/'project-notes/ttg-sibling-dependency-audit.json',
  raw_review=E.parent/'ttg-interability-review-20261101/formal48-raw-audit/summary.json',
  HTTP_review=E.parent/'ttg-interability-review-20261101/http-startup-analysis-review.json',
  diagnostic=Path(diagnostic).resolve(),AB_source=Path(__file__).parent/'apps/region_chain/server.jac',
  LL_source=Path(__file__).parent/'apps/linked_list/main.jac',
  diagram_source=ROOT/'project-notes/visualizations/ttg-ability-dependencies/figure_cross_ability_final.py')
 data={k:read(p) for k,p in paths.items() if not k.endswith('_source')}
 assert data['numeric']['sample_counts']==dict(all=48,excluded_warmups=12,measured=36,cells=12,n_per_cell=3)
 assert data['analysis']['passed'] and data['raw_review']['passed']
 assert data['diagnostic']['passed'] and data['inventory']['coverage']['unique_cases']==91
 rows={(r['case_id'],r['config_id']):r for r in data['numeric']['rows']}
 analysis={(r['case_id'],r['config_id']):r for r in data['analysis']['rows']}
 assert len(rows)==len(analysis)==12
 os.environ.setdefault('MPLCONFIGDIR',str(out/'mpl-cache'))
 import matplotlib;matplotlib.use('Agg')
 import matplotlib.pyplot as plt
 from matplotlib.backends.backend_pdf import PdfPages
 from matplotlib.patches import FancyBboxPatch,FancyArrowPatch
 from matplotlib.font_manager import FontProperties
 plt.rcParams.update({'figure.max_open_warning':0,'font.family':'DejaVu Sans','figure.facecolor':'white','savefig.facecolor':'white','text.color':'#183044'})
 pages=[];layouts=[];report=[]
 def wrap(value,renderer,properties,width):
  result=[]
  for paragraph in str(value).split('\n'):
   line=''
   for word in paragraph.split():
    candidate=(line+' '+word).strip()
    if line and renderer.get_text_width_height_descent(candidate,properties,False)[0]>width:
     result.append(line);line=word
    else:line=candidate
   result.append(line)
  return '\n'.join(result)
 def page(title,subtitle=''):
  f=plt.figure(figsize=(16,9));f._title=title;f._tables=[]
  f.text(.055,.92,title,size=28,weight='bold',ha='left')
  if subtitle:f.text(.055,.858,subtitle,size=15,color='#526d82')
  pages.append(f);return f
 def text(f,value,x=.065,y=.765,size=20):
  return f.text(x,y,value,size=size,va='top',linespacing=1.35)
 def bullets(f,items,y=.76,gap=.125,size=20):
  for value in items:text(f,value,y=y,size=size);y-=gap
 def code(f,value,area=(.065,.22,.52,.55),size=15):
  ax=f.add_axes(area);ax.axis('off');ax.set_facecolor('#f3f7fa')
  ax.text(.02,.97,value,ha='left',va='top',family='DejaVu Sans Mono',fontsize=size,linespacing=1.3)
  return ax
 def table(f,headers,body,area=(.055,.19,.89,.60),font=15,widths=None):
  ax=f.add_axes(area);ax.axis('off');widths=widths or [1/len(headers)]*len(headers)
  renderer=f.canvas.get_renderer();wrapped=[]
  for i,row in enumerate([headers]+body):
   prop=FontProperties(family='DejaVu Sans',size=font,weight='bold' if i==0 else 'normal')
   wrapped.append([wrap(v,renderer,prop,area[2]*f.bbox.width*widths[j]*.88) for j,v in enumerate(row)])
  weights=[max(v.count('\n')+1 for v in row)+.7 for row in wrapped];total=sum(weights)
  t=ax.table(cellText=wrapped[1:],colLabels=wrapped[0],loc='center',cellLoc='left',colLoc='left',colWidths=widths)
  t.auto_set_font_size(False);t.set_fontsize(font)
  for (i,j),cell in t.get_celld().items():
   cell.set_height(.94*weights[i]/total);cell.PAD=.045;cell.set_edgecolor('#d3dfe7')
   cell.set_facecolor('#dcebf5' if i==0 else ('#f4f8fb' if i%2 else 'white'))
   if i==0:cell.set_text_props(weight='bold')
  f._tables.append(t);return t
 def graph(f,labels,guards=None,area=(.61,.34,.31,.32)):
  ax=f.add_axes(area);ax.axis('off');n=len(labels)
  for i,label in enumerate(labels):
   x=.04+i*.94/max(1,n-1);ax.add_patch(FancyBboxPatch((x-.08,.42),.16,.22,boxstyle='round,pad=.01',facecolor='#e3f0f8',edgecolor='#397b9f'))
   ax.text(x,.53,label,ha='center',va='center',size=19)
   if i<n-1:
    nx=.04+(i+1)*.94/max(1,n-1);ax.add_patch(FancyArrowPatch((x+.085,.53),(nx-.085,.53),arrowstyle='-|>',mutation_scale=18,color='#397b9f'))
  if guards:ax.text(.5,.18,guards,ha='center',va='center',size=14)
  ax.set_xlim(-.1,1.12);ax.set_ylim(0,1)
 def ts(item,ns=False):
  scale=1e6 if ns else 1
  return f"{item['median']/scale:,.3f}\n[{item['min']/scale:,.3f}, {item['max']/scale:,.3f}]"
 def counter(case,mode,name):return analysis[case,mode]['work'][name]['median']

 f=page('Interability Dependency Graphs','Research method first: focus on regions without sibling-dependent future access.')
 bullets(f,['1. New method: compose ability dependency graphs and identify SQL-compilable regions.',
  '2. Cost model: briefly explain how a prefetch decision estimates benefit and cost.',
  '3. Benchmark set: the full 30-app + 61-operation inventory, followed by the small validation results.',
  '4. Sibling dependency: what changes future access, what can be proved, and what remains outside the first kernel.'],gap=.145,size=21)
 f=page('A concrete typed A→B→C traversal','Actual primary fixture; report/count statements retained in native execution.')
 source=paths['AB_source'].read_text();snippet=source[source.index('    can a'):source.index('    can c')]
 code(f,snippet,size=15);graph(f,['A','B','C'],'B.active controls B→C')
 text(f,'True: reports[10,20,30], visited3\nFalse: reports[10,20], visited2',x=.61,y=.29,size=18)
 f=page('Separate output state from future access','Local effect summaries feed the typed dispatch graph.')
 table(f,['Ability','Output effect','Future-access effect'],[
  ['a / A','visited+=1; report10','Typed AB visit to B'],
  ['b / B','visited+=1; report20','Read ordinary Boolean B.active; conditionally visit typed C'],
  ['c / C','visited+=1; report30','No further visit']],widths=[.18,.31,.51])
 text(f,'Here visited is total output state. It never controls a visit or cancellation in this fixture.',y=.145,size=16)
 f=page('Compose at compile time','Implemented finite kernel: exact typed dispatch, supported guard and explicit boundary.')
 graph(f,['a(A)','b(B)','c(C)'],'A→B ; B.active ⇒ B→C',area=(.09,.45,.80,.30))
 table(f,['Artifact','Recorded content'],[
  ['Local summary','source_type, visit, guard/guard_fields, dispatch, output effects'],
  ['Region certificate','checkpoint; dispatch_edges; external_dependencies; compiled SQL template'],
  ['Native method evidence','entry:0; dispatch edges1→3 and6→9 in accepted RegionGuard fixture'],
  ['External bindings','Origin identity, exact runtime dispatch and actor/ACL context']],area=(.065,.15,.87,.31),font=15,widths=[.25,.75])
 f=page('A dependency graph across ability boundaries','Solid access dependencies compose; output-only state stays outside access selection.')
 ax=f.add_axes((.06,.30,.88,.46));ax.axis('off')
 nodes={'a':(.10,.75,'A entry\ntyped visit B'),'read':(.40,.75,'B entry\nread B.active'),'if':(.66,.75,'Boolean guard'),'visit':(.88,.75,'typed visit C'),'out':(.40,.18,'visited += 1\nreport value')}
 for key,(x,y,label) in nodes.items():
  ax.add_patch(FancyBboxPatch((x-.08,y-.12),.16,.24,boxstyle='round,pad=.015',facecolor='#e3f0f8' if key!='out' else '#edf0f2',edgecolor='#397b9f'))
  ax.text(x,y,label,ha='center',va='center',size=16)
 for a,b in [('a','read'),('read','if'),('if','visit')]:
  x,y,_=nodes[a];u,v,_=nodes[b];ax.add_patch(FancyArrowPatch((x+.085,y),(u-.085,v),arrowstyle='-|>',mutation_scale=18,color='#397b9f'))
 ax.set_xlim(-.02,1.02);ax.set_ylim(-.03,1)
 text(f,'Origin and actor are ready at A entry. B.active is a node-local SQL input: it need not be known in Python before querying B. No output counter feeds the guard.',y=.23,size=19)
 # The requested nested Jac graph, drawn as editable vector shapes.
 import importlib.util
 spec=importlib.util.spec_from_file_location('nested_ability_figure',paths['diagram_source'])
 module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
 nested=module.build_figure();nested._title='One SQL region crossing Jac ability boundaries'
 nested._tables=[];nested._custom_footer=True;pages.append(nested)
 f=page('Move the supported guard inside SQL','Conceptual lowering of the finite example; actual SQL also validates types, ACL and arity.')
 code(f,'WITH b AS (\n  SELECT target_B FROM typed_AB(origin)\n), c AS (\n  SELECT target_C FROM b\n  JOIN typed_BC(b.id) ON b.active = TRUE\n)\nSELECT path_pair FROM b\nUNION ALL SELECT path_pair FROM c;',area=(.065,.35,.57,.42),size=18)
 text(f,'SQL boundary includes:\nA→B lookup\nB.active Boolean test\nconditional B→C lookup',x=.66,y=.73,size=18)
 text(f,'Malformed Boolean, fanout, cycle or incomplete result ⇒ decline static publication and retain native execution. A false guard publishes no invented B→C path.',y=.23,size=18)
 f=page('The SQL validates the second visit','Compiler proof and actual graph validation have different jobs.')
 table(f,['Compiler supplies','SQL/runtime validates'],[
  ['A typed AB→B dispatch and B typed BC→C dispatch','Actual identities, types/modules and immediate arity≤1'],
  ['B.active is a supported SQL-internal Boolean guard','JSON kind is Boolean; malformed values reject the static result'],
  ['No intervening unsupported write/helper/cancellation','Actual order, cycle/history and resource-completion checks'],
  ['Finite or homogeneous region artifact','Complete validated rows before atomic native-cache publication']],font=16,widths=[.48,.52])
 text(f,'Finite A→B→C uses unrolled CTE stages. Homogeneous Item→Item uses recursive lowering.',y=.145,size=15)
 f=page('Existing checkpoint → query → ordered native cache','Runtime selects/binds an emitted artifact; native ability dispatch stays in charge.')
 bullets(f,['At entry, bind origin/actor and check exact dispatch against the compiled certificate.',
  'Execute the selected SQL, validate the complete result, then publish typed native path pairs.',
  'Guard true: cache A→B and B→C; B entry reuses its published path.',
  'Guard false: cache A→B only; native B runs and does not visit C.',
  'Opaque helpers, writes, cancellation and unsupported guards form conservative boundaries.'],gap=.115)
 f=page('Finite LinkedList: a disclosed source variant','Original cutoff-bearing benchmark remains preserved separately.')
 code(f,'can visit_item with Item entry {\n    self.visited += 1;\n    report here.value;\n    visit [->:Next:->[?:Item]];\n}',area=(.065,.37,.57,.38),size=18)
 text(f,'Two changes only:\n1. Remove Traverse cutoff.\n2. Type the target as Item.',x=.66,y=.72,size=18)
 text(f,'Fixture proof: all Item nodes, at most one successor, correct incoming counts, full ordered reachability and acyclicity. visited remains a TOTAL, not a depth.',y=.25,size=19)
 f=page('Fixed primary scope and analyzed-statistics regime','Seed42 · process1 · limit2048 · steps32768 · fresh equivalent DB/server per workflow.')
 table(f,['Fixture','Actual measured actions'],[
  ['LinkedList32 /1,000','One full native Traverse per trial; Sum/Find source remains unchanged and is not invoked'],
  ['Typed A→B→C','One native RegionChain, B.active=true; false tested separately in all three modes'],
  ['Original LittleX','Unchanged nine primary RPCs; setup and six excluded steady views retain their own scopes']],font=15,widths=[.26,.74])
 text(f,'ANALYZE anchors + graph_types once after setup/views, before reset/first primary clock. WAL32/64MB. Twelve primary +3 false correctness cases;12 excluded warmups +36 measured trials.',y=.13,size=16)
 f=page('Actual DB protocol time','Median[min,max]ms, n=3. Every primary summed interval equals its interval union.')
 table(f,['Fixture']+[LABEL[m] for m in MODES],[[TITLE[c]]+[ts(rows[c,m]['protocol_sum_ns'],True) for m in MODES] for c in CASES],font=16)
 f=page('Actual primary HTTP response wall','Median[min,max]ms, n=3; client start through full response-body completion.')
 table(f,['Fixture']+[LABEL[m] for m in MODES],[[TITLE[c]]+[ts(analysis[c,m]['HTTP_response_sum_ms']) for m in MODES] for c in CASES],font=15)
 text(f,'LL/AB each have one request. LittleX sums nine response intervals. Explicit drain and client gaps remain separate; these are instrumented runs.',y=.145,size=15)
 f=page('Every SQL call is counted','Actual data + controls = TOTAL, identical across all three measured repeats.')
 table(f,['Fixture']+[LABEL[m] for m in MODES],[[TITLE[c]]+[f"{int(rows[c,m]['sql_data']['median'])} + {int(rows[c,m]['sql_control']['median'])} = {int(rows[c,m]['sql_dispatches']['median'])}" for m in MODES] for c in CASES],font=17)
 text(f,'Includes all foreground/background path, payload, identity/catalog and transaction-completion SQL.',y=.145,size=15)
 f=page('LL1,000: less interpreted continuation work','Recorded abstract work counters; all actual native visits remain1,000.')
 table(f,['Recorded quantity','9282','Interability'],[
  ['Continuation records',f"{counter('finite_list1000','baseline9282','continuation_count'):,.0f}",f"{counter('finite_list1000','interability','continuation_count'):,.0f}"],
  ['Abstract executions',f"{counter('finite_list1000','baseline9282','continuation_execution_count'):,.0f}",f"{counter('finite_list1000','interability','continuation_execution_count'):,.0f}"],
  ['Continuation path records',f"{counter('finite_list1000','baseline9282','continuation_path_count'):,.0f}",f"{counter('finite_list1000','interability','continuation_path_count'):,.0f}"],
  ['Native plans',f"{counter('finite_list1000','baseline9282','plan_count'):,.0f}",f"{counter('finite_list1000','interability','plan_count'):,.0f}"],
  ['Submitted / promoted payloads','999 /999','999 /999']],font=17,widths=[.48,.26,.26])
 text(f,'Static region selection bypasses the interpreter. These counters measure work quantity, not CPU time.',y=.145,size=15)
 f=page('Process readiness is a measured fixed wall cost','One native constructor clock covers imports/configuration through the ready handshake.')
 table(f,['Primary case','Unique child PIDs/trial','9282 startup sum ms','New startup sum ms'],[[TITLE[c],str(int(analysis[c,'interability']['startup_unique_count']['median'])),ts(analysis[c,'baseline9282']['startup_unique_sum_ms']),ts(analysis[c,'interability']['startup_unique_sum_ms'])] for c in CASES],font=15,widths=[.25,.19,.28,.28])
 text(f,'~190ms per PID; LittleX six PIDs total~1.14s versus~1.59s response wall. Timers exclude later lazy DB connect/load. No aligned critical-path percentage or CPU subtraction.',y=.145,size=15)
 f=page('Natural scope cleanup and process reuse','Source order explains the lifecycle; individual IPC/close durations were not retained.')
 bullets(f,['configured_dependency_prefetch wraps native spawn; finally joins its worker threads.',
  'The enclosing dependency scope closes ProcessReaders before spawn returns; Session.close also cleans a remaining pool.',
  'Recorded parent IPC workers: LL1 each; A→B→C2→1; LittleX6 each. Actual child SQL/backend identities are verified.',
  'All 48 trials show zero overlapping SQL protocol intervals on distinct backends.',
  'Proposed persistent readers need per-request transaction, actor, tracing and context reset.'],gap=.115)
 f=page('LittleX: Stage2 templates, a separate mechanism','Static interability region queries=0 in this workload.')
 table(f,['Measured quantity','9282','Interability'],[
  ['TOTAL SQL','151','147'],['Data /control SQL','82 /69','78 /69'],
  ['HTTP response-sum median ms',f"{analysis['littlex','baseline9282']['HTTP_response_sum_ms']['median']:.3f}",f"{analysis['littlex','interability']['HTTP_response_sum_ms']['median']:.3f}"],
  ['DB protocol median ms',f"{rows['littlex','baseline9282']['protocol_sum_ns']['median']/1e6:.3f}",f"{rows['littlex','interability']['protocol_sum_ns']['median']/1e6:.3f}"]],font=17)
 text(f,'Pure visit-prefix sites receive later frontier attempts using existing continuation/barrier logic. Stage2 is distinct from the new typed single-successor kernel.',y=.145,size=16)
 f=page('Matched recursive SQL diagnostic','Separate matched native diagnostic; primary n3 results stay unchanged.')
 diag=data['diagnostic']
 table(f,diag['headers'],diag['rows'],font=16,widths=diag.get('widths'))
 text(f,diag['scope'],y=.145,size=14)
 f=page('Why this recursive SQL does more work','Observed plan differences; no per-feature timing ablation was performed.')
 table(f,['Quantity / structure','9282','Interability'],[
  ['Recursive state','origin, depth','origin, phase, depth, growing seen UUID array'],
  ['Extra source-node PK validation','None','2 × 1,000 loops; 6,000 extra shared hits'],
  ['Root shared hits / reads','16,136 / 0','22,136 / 0'],
  ['CTE temporary written blocks','0','985 at work_mem 4 MB'],
  ['First / repeat execution ms','14.346 / 14.107','41.481 / 40.506']],font=16,widths=[.40,.25,.35])
 text(f,'Growing cycle history and extra validation are concrete optimization targets. Preserve cycle/completeness/ACL correctness; inclusive buffer counters are not additive.',y=.145,size=15)
 f=page('2 · Existing replaceable admission model','These mechanism comparisons fix Always/process admission.')
 text(f,'p × min(payload, opportunity) − resolve\n− (1−p) × payload × unused_weight − margin',y=.75,size=26)
 bullets(f,['p=(demanded+1)/(opportunities+2); feature estimate → decision → observation interface.',
  'Payload is dispatch-to-ready wall; opportunity is launch-to-demand, distinct from observed SQL overlap.',
  'Fused feedback is training_observed=false. Branch frequency is collected rather than used directly in this score.',
  'Future admission must include cold process readiness when launching a new reader. Prepared-plan reuse remains deferred.'],y=.52,gap=.11,size=18)
 apps=[c for c in data['inventory']['cases'] if c['family']=='apps']
 for start in (0,15):
  f=page(f'3 · Benchmark set: 30 apps · {start+1}–{start+15}','Source-audit inventory, one registered reader per app; current timing subset is separate.')
  body=[]
  for c in apps[start:start+15]:
   label='MAY: total-count cancellation' if c['case_id']=='app/linked_list' else 'NO under effect summaries'
   body.append([c['case_id'].split('/',1)[1],c['walker'],label])
  table(f,['Application','Registered reader','Future-access sibling result'],body,font=12.5,widths=[.26,.35,.39],area=(.055,.12,.89,.69))
 f=page('The additional 61 paper-operation identities','Existing selected inventory:22 TPC-H +29 SNB +5 TPC-C +5 Wikipedia.')
 body=[]
 for family in ('tpch','snb','tpcc','wikipedia'):
  cases=[c for c in data['inventory']['cases'] if c['family']==family]
  body.append([family.upper(),str(len(cases)),', '.join(c['case_id'].split('/',1)[1] for c in cases)])
 table(f,['Family','Count','Exact selected operation IDs'],body,font=15,widths=[.15,.10,.75])
 text(f,'These 91 source-audit identities are not91 measured performance cells. This round tests four fixtures /12 n3 cells.',y=.145,size=15)
 f=page('4 · Sibling dependence of future access','Shared output does not automatically imply interference between sibling visits.')
 table(f,['Witness','Static interpretation'],[
  ['self.total += here.value; visit fixed Next','Output-only reduction if total is never read to choose access'],
  ['if self.visited>=limit { disengage; }','MAY dependence: an earlier sibling can cancel later queued work; count is total, not depth'],
  ['seen guard before visit /graph read','MAY dependence: earlier visits can suppress a later access'],
  ['Opaque external helper /storage side effect','Requires an effect contract; unknown is not a theorem of impossibility']],font=16,widths=[.47,.53])
 f=page('What the 91-source audit establishes','Closed-world ordinary-field/effect reasoning; not an implemented universal analyzer.')
 bullets(f,['Registered readers:29 NO under explicit summaries; original cutoff-bearing LinkedList exposes MAY cancellation.',
  'Additional helpers/business walkers have their own seen guards, writes, queue and phase boundaries.',
  'TPC-H whole-operation view:16 NO,5 phase MAY, and Q20 conditional materialization dependence.',
  'Within a fixed TPC-H sibling stage, immutable join maps differ from feedback; phase/reduction dependencies can be relationally lowerable.',
  'Current unsupported syntax is separate from semantic dependence and from whether a static summary can prove it.'],gap=.115,size=19)
 f=page('Next improvements and larger-stage follow-up','Proposals are separate from the tested runtime and fixed-admission results.')
 bullets(f,['Use the matched-plan evidence to target recursive SQL costs while preserving certificate checks.',
  'Explore process reuse with explicit transaction/actor/context/tracing reset and cold-start-aware admission.',
  'Extend helper/effect summaries and dominated external guard bindings beyond the first typed kernel.',
  'Keep prepared-statement reuse and adaptive region admission as separate evaluated changes.',
  'Larger LittleX 50×20 / LL 2048 follow-up is paused at user request; no larger runs were started.'],gap=.115,size=19)
 f=page('Reproducible measured scope','All primary inputs, traces, semantic proofs, source versions and analysis remain bound.')
 bullets(f,['Runtime:9282 baseline versus clean addd3a4; Off uses the new runtime. Common process1/budgets and analyzed-statistics regime.',
  '15 native correctness cases, then48 fresh trials:12 excluded warmups and36 measured samples.',
  'Actual SQL sum/union/counts independently reaggregated; primary instrumented HTTP clocks audited.',
  'Compact native counters retain abstract work and startup observations without quadratic trace serialization.',
  'Editable renderer, figure inputs, source/analysis manifests and completed/excluded inventory accompany the PDF.'],gap=.115,size=19)

 # Additional explanation pages; final ordering follows the user's four-part brief.
 f=page('1 · From local dependencies to an interability region','Initial analysis target: future accesses do not depend on earlier siblings’ mutable state.')
 ax=f.add_axes((.06,.43,.88,.31));ax.axis('off')
 labels=['Per-ability\ndependency graph','Compose typed\ndispatch edges','Select supported\nSQL subgraph','Checkpoint after\nexternal inputs']
 for i,label in enumerate(labels):
  x=.015+i*.25
  ax.add_patch(FancyBboxPatch((x,.34),.215,.40,boxstyle='round,pad=.008',facecolor='#e3f0f8',edgecolor='#397b9f'))
  ax.text(x+.1075,.54,label,ha='center',va='center',fontsize=16)
  if i<3:ax.add_patch(FancyArrowPatch((x+.22,.54),(x+.244,.54),arrowstyle='-|>',mutation_scale=15,color='#397b9f'))
 text(f,'Dependencies include values, predicates, visit targets and effects. Output-only state may stay native when it cannot affect later access.',y=.34,size=20)
 text(f,'Implemented kernel: compile-time composition of known typed dispatch; runtime binds origin/actor and validates graph results. General runtime graph composition and arbitrary latest-dependency placement remain research work.',y=.22,size=17)
 f=page('A sibling write can change the later access','Conceptual A→{B,C} example, with B scheduled before C.')
 code(f,'B.entry:\n    self.threshold = B.value\n\nC.entry:\n    if C.value > self.threshold:\n        visit C.children',area=(.065,.33,.46,.42),size=19)
 ax=f.add_axes((.56,.31,.39,.45));ax.axis('off')
 for x,y,label in [(.24,.84,'B.value'),(.70,.84,'write threshold'),(.70,.48,'C predicate'),(.24,.48,'C.value'),(.70,.12,'visit C.children')]:
  ax.add_patch(FancyBboxPatch((x-.21,y-.10),.42,.20,boxstyle='round,pad=.01',facecolor='#f5f0eb',edgecolor='#a65b37'))
  ax.text(x,y,label,ha='center',va='center',fontsize=15)
 for x,y,u,v in [(.45,.84,.48,.84),(.70,.73,.70,.59),(.45,.48,.48,.48),(.70,.37,.70,.23)]:
  ax.add_patch(FancyArrowPatch((x,y),(u,v),arrowstyle='-|>',mutation_scale=17,color='#a65b37',linewidth=2))
 text(f,'The write in B is a dependency of C’s future visit. Keep this boundary until the required state transition and ordering can be represented soundly.',y=.20,size=20)
 f=page('Start with sibling-independent future access','First analyze and compose regions with proved sibling-independent future access.')
 table(f,['Analysis outcome','Initial treatment'],[
  ['Proved NO sibling feedback','Compose supported regions; keep original native queue/output semantics.'],
  ['MAY: shared state reaches a visit, guard or cancellation','Retain an explicit boundary. Later SQL lowering needs the correct state and ordering semantics.'],
  ['Unknown helper, descriptor or side effect','Require a bounded effect summary or fall back; unknown does not mean impossible.'],
  ['Output-only reduction','Allow it only after proving it cannot feed future accesses. Total visited is not recursion depth.']],font=16,widths=[.39,.61])
 text(f,'The small chain and guarded A→B→C validate the first typed kernel. The wider source audit guides extensions; it is not evidence of implementation coverage for all 91 cases.',y=.145,size=15)
 assert len(pages)==31
 # Method → cost model → full benchmark set and validation → sibling dependencies.
 groups=[('1 · METHOD',[0,28,1,2,3,4,5,6,7,8]),
         ('2 · COST MODEL',[20]),
         ('3 · BENCHMARK SET & VALIDATION',[21,22,23,9,10,11,12,13,14,15,16,17,18,19,26,27]),
         ('4 · SIBLING DEPENDENCY',[24,29,25,30])]
 original_pages=list(pages);pages=[];sections=[]
 for name,indices in groups:
  start=len(pages)+1
  for i in indices:
   original_pages[i]._section=name;pages.append(original_pages[i])
  sections.append(dict(title=name,first_page=start,last_page=len(pages)))
 assert len({id(f) for f in pages})==31
 # Reused accepted layout discipline: wrap to both margins and check cell bounds.
 with PdfPages(out/'ttg-interability-performance.pdf',metadata={'Title':'TTG+ — interability SQL regions','Author':'TTG research'}) as pdf:
  for number,f in enumerate(pages,1):
   f.canvas.draw();renderer=f.canvas.get_renderer();W,H=f.bbox.width,f.bbox.height
   for i,t in enumerate(f.texts):
    b=t.get_window_extent(renderer);available=(.942-t.get_position()[0])*W
    if i==0:
     if b.width>available:t.set_fontsize(max(23,t.get_fontsize()*available/b.width))
    else:
     top=b.y1/H;t.set_text(wrap(t.get_text(),renderer,t.get_fontproperties(),available));t.set_va('top');t.set_y(top)
   f.canvas.draw();renderer=f.canvas.get_renderer();checks=[]
   for t in f.texts:
    b=t.get_window_extent(renderer);checks.append(dict(text=t.get_text(),bounds=[b.x0/W,b.y0/H,b.x1/W,b.y1/H]))
   for obj in f._tables:
    for cell in obj.get_celld().values():
     b=cell.get_text().get_window_extent(renderer);c=cell.get_window_extent(renderer)
     assert b.x0>=c.x0-1 and b.x1<=c.x1+1 and b.y0>=c.y0-1 and b.y1<=c.y1+1,(f._title,cell.get_text().get_text())
     checks.append(dict(text=cell.get_text().get_text(),bounds=[b.x0/W,b.y0/H,b.x1/W,b.y1/H]))
   for q in checks:
    x0,y0,x1,y1=q['bounds'];assert x0>=.045 and x1<=.945 and y0>=.065 and y1<=.98,(f._title,q)
   boxes=[(t,t.get_window_extent(renderer)) for t in f.texts]
   for i,(a,ab) in enumerate(boxes):
    for b,bb in boxes[i+1:]:
     assert min(ab.x1,bb.x1)-max(ab.x0,bb.x0)<=1 or min(ab.y1,bb.y1)-max(ab.y0,bb.y0)<=1,(f._title,'text overlap')
   layouts.append(dict(page=number,title=f._title,checks=checks,passed=True))
   if not getattr(f,'_custom_footer',False):
    f.text(.055,.032,f'{f._section} | TTG+ | Evidence scope stated on each page',size=10,color='#526d82')
    f.text(.945,.032,str(number),ha='right',size=10)
   else:
    f.text(.975,.012,str(number),ha='right',size=10)
   pdf.savefig(f);f.savefig(out/f'slide-{number:02d}.png',dpi=105);plt.close(f)
   report.extend(['## '+f._title,'']+[q['text'] for q in checks]+[''])
 inputs=dict(passed=True,renderer=ref(Path(__file__)),inputs={k:ref(p) for k,p in paths.items()},
  numeric_rows=data['numeric']['rows'],analysis_rows=data['analysis']['rows'],diagnostic=data['diagnostic'],
  scope='Four fixtures,12 cells n3; measured LL is one Traverse, not the older multi-operation workflow. HTTP wall is separate from DB and CPU.',
  page_titles=[f._title for f in pages],sections=sections)
 (out/'figure-inputs.json').write_text(json.dumps(inputs,indent=2)+'\n')
 (out/'layout-checks.json').write_text(json.dumps(dict(passed=True,pages=layouts),indent=2)+'\n')
 (out/'report.md').write_text('\n'.join(report)+'\n')
 outputs=[ref(p) for p in sorted(out.iterdir()) if p.is_file()]
 manifest=dict(passed=True,pages=len(pages),renderer=ref(Path(__file__)),inputs=inputs['inputs'],outputs=outputs)
 (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
 print(json.dumps(dict(passed=True,pages=len(pages),PDF=ref(out/'ttg-interability-performance.pdf'),manifest=ref(out/'manifest.json'))))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--diagnostic',type=Path,required=True)
 a=p.parse_args();render(a.output,a.diagnostic)
