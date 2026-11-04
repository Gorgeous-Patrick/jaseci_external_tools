"""Presentation only; accepted numbers are loaded, never recomputed from traces."""
import hashlib,json,os,textwrap
from pathlib import Path
E=Path(__file__).resolve().parent
def read(p):return json.loads(Path(p).read_text())
def ref(p):return dict(path=str(p),sha256=hashlib.sha256(Path(p).read_bytes()).hexdigest())
def main():
    data=read(E/'results.json');analysis=read(E/'interpretation.json');support=read(E/'support-source-v1.json')
    assert data['passed'] and analysis['passed'] and len(data['groups'])==15
    out=E/'slides-v1';assert not out.exists();out.mkdir();os.environ['MPLCONFIGDIR']=str(out/'mpl-cache')
    import matplotlib;matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_pdf import PdfPages
    from matplotlib.patches import FancyBboxPatch,FancyArrowPatch
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':14,'figure.facecolor':'white','savefig.facecolor':'white','text.color':'#17324d'})
    pages=[];texts=[];layout=[];blue='#1d5e91';orange='#c86724';green='#208369'
    names=lambda a: ''.join(w.title() for w in a.split('_'))
    def page(title,sub=''):
        f=plt.figure(figsize=(16,9));f.text(.055,.92,title,size=28,weight='bold');f.text(.055,.86,sub,size=14,color='#526b7e');pages.append(f);texts.append([title,sub]);return f
    def text(f,s,y=.76,size=21,width=103,x=.06):
        s='\n'.join(textwrap.fill(p,width=width,break_long_words=False) for p in str(s).split('\n'));f.text(x,y,s,size=size,va='top',linespacing=1.4);texts[-1].append(s)
    def bullets(f,items,y=.76,gap=.14,size=20):
        for i,s in enumerate(items):text(f,'• '+s,y-i*gap,size,100)
    def table(f,headers,rows,y=.16,h=.61,font=14,widths=None):
        ws=widths or [1/len(headers)]*len(headers)
        def fit(v,c):return '\n'.join(textwrap.fill(p,width=max(8,int(16*.89*72*ws[c]/(font*.56))-2),break_long_words=False) for p in str(v).split('\n'))
        wrapped=[[fit(v,c) for c,v in enumerate(row)] for row in rows]
        ax=f.add_axes([.055,y,.89,h]);ax.axis('off');tab=ax.table(cellText=wrapped,colLabels=[fit(v,c) for c,v in enumerate(headers)],cellLoc='left',colLoc='left',bbox=[0,0,1,1],colWidths=widths);tab.auto_set_font_size(False);tab.set_fontsize(font)
        for (r,c),cell in tab.get_celld().items():
            cell.set_edgecolor('#d9e3eb');cell.PAD=.05
            if r==0:cell.set_facecolor(blue);cell.get_text().set_color('white');cell.get_text().set_weight('bold')
            else:cell.set_facecolor('#f1f6fa' if r%2 else 'white')
        texts[-1].append(str(headers)+'\n'+'\n'.join(str(r) for r in rows));return tab
    apps=list(data['groups']);g=data['groups'];value=lambda a,m,k:g[a][m][k]['median']
    faster=[a for a in apps if value(a,'thread','HTTP_sum_ms')<value(a,'off','HTTP_sum_ms')]
    f=page('TTG across 15 applications','Current runtime f9a6d37b2 · GIL-off Python 3.14.6 · asynchronous thread prefetch')
    bullets(f,[f'15 fixed applications; 120 fresh workflows: 30 excluded validation warmups + 90 measured.',f'All correctness and GIL-off checks pass. HTTP median improves in {len(faster)}/15 selected workflows.', 'Compiler support, observed prefetch coverage and measured speedup are evaluated separately.','Every slower result is retained; targeted diagnostics explain observed costs.'],gap=.145)
    f=page('The question and the fixed experiment','Select by source structure before looking at speed; keep the complete business workflow')
    bullets(f,['Same runtime and source in off/thread; one worker, limit 2048, seed 42, fresh database per trial.','JDrive: 364 folders + 121 files. LittleX: 50 profiles + 1,000 tweets. Other 13: original seeded domain scenarios.','One uniform ANALYZE before primary/reset. Setup, steady checks and restart are retained but excluded.','Three measured repetitions per cell, rotated off/thread order. Report medians and ranges, not population estimates.'],gap=.145,size=19)
    f=page('From program dependencies to prefetched data','Native abilities still execute; compiler/runtime prediction changes fetching')
    labels=['Ability graph\nvalues + effects','Backward slice\nfuture accesses','Supported SQL\nregion/template','Resolve paths\nACL + ordering','Thread payload\nthen native use']
    for i,label in enumerate(labels):
        x=.05+i*.185;f.patches.append(FancyBboxPatch((x,.47),.16,.22,boxstyle='round,pad=.01',transform=f.transFigure,facecolor='#e8f2fa',edgecolor=blue));f.text(x+.08,.58,label,ha='center',va='center',size=18)
        if i<4:f.patches.append(FancyArrowPatch((x+.162,.58),(x+.183,.58),transform=f.transFigure,arrowstyle='-|>',mutation_scale=18,color=blue))
    text(f,'Output-only bookkeeping can be excluded from the access slice only with an effect contract. Unknown effects, access-dependent shared state and cancellation remain dependencies.',.32,20)
    f=page('Jac graph, with dependencies inside each node','Illustrative Folder A → Folder B / Folder C; same native walk ability at every Folder')
    f.patches.append(FancyBboxPatch((.065,.555),.87,.15,boxstyle='round,pad=.012',transform=f.transFigure,facecolor='#dff2e8',edgecolor=green,linestyle='--',linewidth=2))
    f.text(.50,.74,'SQL-compilable access slice across ability invocations',ha='center',size=17,color=green,weight='bold')
    for i,label in enumerate(['Folder A','Folder B','Folder C']):
        x=.055+i*.31
        f.patches.append(FancyBboxPatch((x,.38),.27,.32,boxstyle='round,pad=.01',transform=f.transFigure,facecolor='none',edgecolor=blue,linewidth=2))
        f.text(x+.135,.665,label+' · walk',ha='center',size=19,weight='bold')
        f.text(x+.135,.60,'here → Contains / Folder\ntrashed == False → visit',ha='center',va='center',size=15)
        f.text(x+.135,.455,'jid / depth / path\n→ entries + output maps',ha='center',va='center',size=15,color='#667788')
    f.patches.append(FancyArrowPatch((.325,.535),(.365,.535),transform=f.transFigure,arrowstyle='-|>',mutation_scale=18,color=blue))
    f.patches.append(FancyArrowPatch((.19,.38),(.81,.38),connectionstyle='arc3,rad=.23',transform=f.transFigure,arrowstyle='-|>',mutation_scale=18,color=blue))
    f.text(.5,.25,'Jac edges: A Contains B; A Contains C',ha='center',size=17,color=blue)
    text(f,'The green slice predicts accesses. Grey output dependencies remain in native execution; they do not control the visit predicate in this source.',.16,17,115)
    f=page('What “supported” means','Four separate observations; one cannot stand in for another')
    table(f,['Level','Evidence required'],[['Correctness','Native outputs, mutations, negative cases, restart and physical state agree'],['Predictable access','Typed path / supported predicate; output effects cannot alter later access'],['Active optimization','Actual region/template query, cache reuse and background SQL records'],['Performance benefit','All-role SQL + DB intervals + complete HTTP workflow improve']],font=18)
    f=page('Cost model: eligibility is only the first decision','This experiment uses AlwaysPrefetch to expose costs; it does not claim learned admission gains')
    bullets(f,['An eligible region predicts which accesses can be fetched. It does not guarantee that fetching them now is profitable.','A useful admission estimate compares saved foreground waits with added path SQL, payload work, runtime planning and executor setup.','Cache hits, region size, query shape and expected unused data must enter the estimate; actual concurrency should be measured.','The present off/Always-thread comparison provides evidence for admission thresholds. Prepared-statement reuse and adaptive admission remain follow-up work.'],gap=.145,size=19)
    f=page('Why these applications are useful tests','Structural candidates plus explicit partial-support controls')
    table(f,['Family','Selected applications','What it exercises'],[['Recursive tree','JDrive','Boolean-filtered tree, output maps, ordered cache'],['Cross-ability graph','LittleX','Profile/Post/Follow region; payload and mutation costs'],['Typed chains / branches','IssueDesk, StockRoom, ClinicQueue, BudgetLedger','Multiple visits and typed dispatch; helper boundaries'],['Typed branches + nested reads','LibraryLoans, HelpQueue, DeliveryRoute, VolunteerShift','Root/branch prefixes versus terminal helper/loop reads'],['Short prefix / output-heavy','ApprovalDesk, EventSeats, KnowledgeMap, CoursePath, IncidentRoom','Low opportunity and partial coverage retained']],font=14,widths=[.21,.38,.41])
    for start in range(0,15,5):
        subset=apps[start:start+5];f=page(f'Whole workflow results — {start+1} to {start+len(subset)}','Medians of n=3; milliseconds; SQL includes foreground, background and controls')
        rows=[]
        for a in subset:
            o=g[a]['off'];t=g[a]['thread'];rows.append([names(a),f"{o['HTTP_sum_ms']['median']:.2f} → {t['HTTP_sum_ms']['median']:.2f}",f"{t['HTTP_sum_ms']['median']/o['HTTP_sum_ms']['median']:.2f}×",f"{o['DB_sum_ms']['median']:.2f} → {t['DB_sum_ms']['median']:.2f}",f"{o['SQL']['median']} → {t['SQL']['median']}"])
        table(f,['Application','HTTP off → thread','Thread / off','DB off → thread','SQL off → thread'],rows,font=15,widths=[.20,.24,.15,.24,.17])
    f=page('SQL reduction is not a speedup guarantee','Each point is one application; medians, n=3 per mode')
    ax=f.add_axes([.21,.16,.72,.63]);ax.axvline(1,color='#888',linestyle='--')
    for i,a in enumerate(apps):
        x=value(a,'thread','SQL')/value(a,'off','SQL');y=value(a,'thread','HTTP_sum_ms')/value(a,'off','HTTP_sum_ms')
        ax.plot([x,y],[i,i],color='#c4d1db',linewidth=1.5)
        ax.scatter(x,i,color=blue,marker='s',s=35,label='SQL count' if i==0 else None)
        ax.scatter(y,i,color=orange,s=35,label='HTTP response sum' if i==0 else None)
    ax.set_yticks(range(len(apps)),[names(a) for a in apps],fontsize=11);ax.invert_yaxis();ax.set_xlabel('Ratio: thread / off (lower is better)');ax.grid(axis='x',alpha=.15);ax.legend(loc='lower right',fontsize=11)
    for start in (0,8):
        subset=apps[start:start+8];f=page('HTTP variability — '+str(start+1),'Observed minimum–maximum of three primary workflows; milliseconds')
        table(f,['Application','Off min–max','Thread min–max'],[[names(a),f"{min(g[a]['off']['HTTP_sum_ms']['values']):.2f}–{max(g[a]['off']['HTTP_sum_ms']['values']):.2f}",f"{min(g[a]['thread']['HTTP_sum_ms']['values']):.2f}–{max(g[a]['thread']['HTTP_sum_ms']['values']):.2f}"] for a in subset],font=15,widths=[.35,.325,.325])
    for start in (0,8):
        subset=apps[start:start+8];f=page('Reader-only results — '+str(start+1),'Sum of primary registered-reader calls within each workflow; no steady-read samples reused')
        table(f,['Application','Reader calls','Reader SQL off → thread','Reader HTTP ms off → thread'],[[names(a),str(value(a,'off','reader_requests')),f"{value(a,'off','reader_SQL')} → {value(a,'thread','reader_SQL')}",f"{value(a,'off','reader_HTTP_ms'):.2f} → {value(a,'thread','reader_HTTP_ms'):.2f}"] for a in subset],font=14,widths=[.24,.15,.29,.32])
    for start in (0,8):
        subset=apps[start:start+8];f=page('Observed optimization coverage — '+str(start+1),'Actual primary counters; cumulative demand counts are not distinct graph-node counts')
        table(f,['Application','Static queries','Templates','Cache reuses','Submitted / promoted'],[[names(a),str(analysis['coverage'][a]['region_queries']),str(analysis['coverage'][a]['template_queries']),str(analysis['coverage'][a]['region_reuses']),f"{analysis['coverage'][a]['submitted']} / {analysis['coverage'][a]['promoted']}"] for a in subset],font=14,widths=[.28,.17,.17,.17,.21])
    f=page('JDrive: a strong structural match','One homogeneous typed directory traversal, boolean predicate and private output state')
    bullets(f,['visit Contains → Folder(trashed == False) determines access; jid/depth/path bookkeeping constructs output.','The certificate permits the supported private output grammar while preserving every native report and visit.','Recursive discovery joins worktable → edge → target; ordered cache publication checks completeness and graph validity.',f"This run: SQL {value('jdrive','off','SQL')} → {value('jdrive','thread','SQL')}; HTTP {value('jdrive','off','HTTP_sum_ms'):.2f} → {value('jdrive','thread','HTTP_sum_ms'):.2f} ms."],gap=.14,size=19)
    for a in analysis['slowest'][:3]:
        f=page(names(a)+': where the extra time appears','Primary evidence identifies intervals and work; causal claims need separate diagnostics')
        detail=analysis['apps'][a]
        bullets(f,[f"HTTP {value(a,'off','HTTP_sum_ms'):.2f} → {value(a,'thread','HTTP_sum_ms'):.2f} ms; DB {value(a,'off','DB_sum_ms'):.2f} → {value(a,'thread','DB_sum_ms'):.2f} ms.",f"Data SQL {value(a,'off','data_SQL')} → {value(a,'thread','data_SQL')}; controls {value(a,'off','control_SQL')} → {value(a,'thread','control_SQL')}.",detail['observation'],detail['limitation']],gap=.145,size=19)
    diagnostics=read(E/'diagnostic-summary.json');assert diagnostics['passed']
    for section in diagnostics['slides']:
        f=page(section['title'],section['subtitle']);bullets(f,section['bullets'],gap=.145,size=19)
    f=page('Threads do not automatically hide latency','Actual client/backend/thread evidence, not an executor label')
    bullets(f,[analysis['overlap_summary'],'All actual SQL-boundary records assert Py_GIL_DISABLED == 1 and GIL disabled; background calls use real distinct threads and PostgreSQL backends.','HTTP sum ends after response reading; explicit drain is separate. DB sum and union are protocol wall times, not server CPU.','HTTP minus DB is not a CPU estimate. Native-worker CPU boundary timers and server plans are separate diagnostic samples.'],gap=.145,size=19)
    f=page('Why the remaining applications are not declared unsupported','15 unmeasured applications remain in the 30-app registry')
    unselected=[r['app'] for r in support['apps'] if not r['selected']]
    text(f,', '.join(names(a) for a in unselected),.76,20,105)
    bullets(f,['Typed root visits may be supported even when nested comprehensions or helper reads are not fused.','Seen/visited counters, sibling state that changes later access, dynamic calls, custom descriptors and writes require explicit contracts.','The prior 30-app sibling audit is conditional source analysis. It is not proof that the current compiler optimizes every reader.'],y=.53,gap=.15,size=19)
    f=page('Sibling dependency remains a real boundary','Output dependence and future-access dependence are different')
    bullets(f,['Safe candidate: append this node’s fields to a result list; the list never affects which nodes are visited next.','Access-dependent: increment a shared visited count, then disengage at a global node budget; sibling order changes future traversal.','A seen set used before visit or return can affect later access on diamonds/cycles. It cannot be treated as mere output bookkeeping.','Current backward slicing includes possible writers across abilities and retains unknown effects. Native semantics are not simplified for these tests.'],gap=.145,size=19)
    f=page('Next steps justified by the measurements','Proposals, not unmeasured speedup claims')
    bullets(f,analysis['next_steps'],gap=.145,size=19)
    f=page('Reproduce and interpret the evidence','All 15 applications and all negative performance outcomes are retained')
    bullets(f,['120 fresh workflows; 30 excluded validation warmups; 90 measured; 30 cells with n=3.','Each accepted database is independently replayed and physically checked before owned active-zero cleanup. Raw files, actual GIL records, source hashes and shutdown evidence are retained.','Whole-workflow and reader results include all foreground/background SQL and control statements. Synthetic seeded domain scenarios are small, not production scale.','Raw audit, exact vectors, source support map, diagnostic plans/profiles and editable renderer accompany this PDF.'],gap=.145,size=19)
    pdf=out/'ttg-15-app-performance.pdf'
    with PdfPages(pdf) as doc:
        for i,f in enumerate(pages,1):
            f.text(.055,.035,f'{i} / {len(pages)} · TTG portfolio · Primary n=3 unless labelled diagnostic',size=11,color='#526b7e')
            f.canvas.draw();ren=f.canvas.get_renderer();bad=[]
            for t in f.findobj(matplotlib.text.Text):
                if not t.get_visible() or not t.get_text():continue
                b=t.get_window_extent(ren)
                if b.width and (b.x0<0 or b.x1>f.bbox.width+1 or b.y0<0 or b.y1>f.bbox.height+1):bad.append(t.get_text())
            layout.append(dict(page=i,out_of_figure=bad));assert not bad,(i,bad)
            doc.savefig(f);f.savefig(out/f'slide-{i:02}.png',dpi=100);plt.close(f)
    (out/'report.md').write_text('\n\n'.join('\n\n'.join(t) for t in texts)+'\n')
    (out/'layout-checks.json').write_text(json.dumps(layout,indent=2)+'\n')
    inputs={str(p):ref(p) for p in (E/'results.json',E/'interpretation.json',E/'support-source-v1.json',E/'diagnostic-summary.json',E/'mechanism-source.json',Path(__file__))}
    (out/'manifest.json').write_text(json.dumps(dict(passed=True,pages=len(pages),inputs=inputs,outputs={p.name:ref(p) for p in out.iterdir() if p.is_file()}),indent=2)+'\n')
    print(pdf,len(pages),ref(pdf))
if __name__=='__main__':main()
