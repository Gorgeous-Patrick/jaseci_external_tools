"""Short presentation only; reuse the accepted Nov12 slide primitives.

No Jac/runtime imports, benchmarks or trace replay. Render only accepted derived
inputs after stopped/quiet handoff. Frozen runtime/capture sources are untouched.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import statistics

NAVY, INK, MUTED, PALE = '#142c45', '#263c50', '#596f82', '#eff4f7'
MODES = ('off','aggressive','conservative','background')
LABELS = {'off':'Off','aggressive':'Aggressive','conservative':'Old Conservative','background':'Background SQL'}
COLORS = {'off':'#758598','aggressive':'#d68b43','conservative':'#14877c','background':'#6655aa'}
APPS = ('littlex','linked_list','jdrive','recipe_pantry')
NAMES = {'littlex':'LittleX','linked_list':'LinkedList 32','jdrive':'JDrive depth 5','recipe_pantry':'RecipePantry'}


def ref(path):
    path=Path(path).resolve()
    return {'path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}


def median(row,key):
    return row[key]['median']


class Deck:
    def __init__(self, output, data, previews=False):
        # Heavy plotting imports occur only inside the explicit final render.
        os.environ.setdefault('MPLCONFIGDIR', str(output/'mpl-cache'))
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        from matplotlib.backends.backend_pdf import PdfPages
        from matplotlib.patches import Rectangle, FancyBboxPatch, FancyArrowPatch
        from matplotlib.font_manager import FontProperties
        self.plt,self.PdfPages=plt,PdfPages
        self.matplotlib_version=matplotlib.__version__
        self.Rectangle,self.Box,self.Arrow=Rectangle,FancyBboxPatch,FancyArrowPatch
        self.Font=FontProperties
        plt.rcParams.update({'font.family':'DejaVu Sans','font.size':16,'pdf.fonttype':42,
            'text.color':INK,'axes.spines.top':False,'axes.spines.right':False})
        self.output,self.data,self.previews=output,data,previews
        self.pages=[]
        self.checks=[]

    def wrapped(self, figure, text, width, size, weight='normal'):
        renderer=figure.canvas.get_renderer()
        properties=self.Font(family='DejaVu Sans',size=size,weight=weight)
        available=width*figure.bbox.width
        result=[]
        for paragraph in str(text).split('\n'):
            current=''
            for word in paragraph.split():
                candidate=(current+' '+word).strip()
                measured=renderer.get_text_width_height_descent(candidate,properties,False)[0]
                if current and measured>available:
                    result.append(current);current=word
                else:
                    current=candidate
            result.append(current)
        return '\n'.join(result)

    def text(self,f,x,y,value,size=18,width=.88,color=INK,weight='normal',**kwargs):
        value=self.wrapped(f,value,width,size,weight)
        t=f.text(x,y,value,fontsize=size,color=color,weight=weight,va='top',**kwargs)
        f._tracked.append(t)
        return t

    def page(self,title,subtitle='',kind='Primary n = 5; fresh workflows'):
        f=self.plt.figure(figsize=(16,9),facecolor='white')
        f._tracked=[];f._title=title;f._kind=kind
        f.add_artist(self.Rectangle((0,.962),1,.038,transform=f.transFigure,facecolor=NAVY,edgecolor='none'))
        self.text(f,.055,.925,title,28,color=NAVY,weight='bold')
        if subtitle:self.text(f,.055,.845,subtitle,15,color=MUTED)
        self.pages.append(f)
        return f

    def bullets(self,f,items,y=.75,gap=.165):
        for title,body in items:
            self.text(f,.065,y,title,20,color=NAVY,weight='bold')
            self.text(f,.075,y-.053,body,17,width=.85)
            y-=gap

    def table(self,f,headers,rows,widths=None,area=(.055,.155,.89,.61),size=14):
        widths=widths or [1/len(headers)]*len(headers)
        matrix=[headers]+rows
        wrapped=[[self.wrapped(f,v,area[2]*widths[j]-.015,size,'bold' if i==0 else 'normal')
                  for j,v in enumerate(row)] for i,row in enumerate(matrix)]
        weights=[max(cell.count('\n')+1 for cell in row)+.8 for row in wrapped]
        total=sum(weights);top=area[1]+area[3]
        for i,row in enumerate(wrapped):
            height=area[3]*weights[i]/total;x=area[0]
            for j,value in enumerate(row):
                width=area[2]*widths[j]
                f.add_artist(self.Rectangle((x,top-height),width,height,transform=f.transFigure,
                    facecolor=NAVY if i==0 else (PALE if i%2 else 'white'),edgecolor='white'))
                t=self.text(f,x+.009,top-.012,value,size,width=width-.018,
                            color='white' if i==0 else INK,weight='bold' if i==0 else 'normal')
                t._cell_bounds=(x,top-height,x+width,top)
                x+=width
            top-=height

    def card(self,f,x,y,w,h,title,body,color='#14877c'):
        f.add_artist(self.Box((x,y),w,h,boxstyle='round,pad=.008',transform=f.transFigure,
                             facecolor=PALE,edgecolor=color,linewidth=1.4))
        self.text(f,x+.016,y+h-.02,title,19,width=w-.032,color=color,weight='bold')
        self.text(f,x+.016,y+h-.085,body,16,width=w-.032)

    def arrow(self,f,a,b,label=None):
        f.add_artist(self.Arrow(a,b,transform=f.transFigure,arrowstyle='-|>',mutation_scale=18,
                               linewidth=1.7,color=MUTED))
        if label:self.text(f,(a[0]+b[0])/2,(a[1]+b[1])/2,label,12,width=.14)

    def save(self):
        path=self.output/'ttg-background-pushdown.pdf'
        with self.PdfPages(path) as pdf:
            for i,f in enumerate(self.pages,1):
                self.text(f,.055,.045,'TTG • '+self.data['recorded_date']+' • '+f._kind,10,width=.82,color=MUTED)
                self.text(f,.94,.045,str(i),10,width=.03,color=MUTED)
                f.canvas.draw();renderer=f.canvas.get_renderer();W,H=f.bbox.width,f.bbox.height
                checks=[]
                for t in f._tracked:
                    b=t.get_window_extent(renderer);bounds=[b.x0/W,b.y0/H,b.x1/W,b.y1/H]
                    if bounds[0]<.035 or bounds[2]>.965 or bounds[1]<.018 or bounds[3]>.95:
                        raise ValueError(f'Page {i} text outside slide bounds: {t.get_text()}')
                    if hasattr(t,'_cell_bounds'):
                        x0,y0,x1,y1=t._cell_bounds
                        if bounds[0]<x0-.002 or bounds[2]>x1+.002 or bounds[1]<y0-.003 or bounds[3]>y1+.003:
                            raise ValueError(f'Page {i} table text outside cell: {t.get_text()}')
                    checks.append(dict(text=t.get_text(),bounds=bounds))
                self.checks.append(dict(page=i,title=f._title,passed=True,text=checks))
                pdf.savefig(f)
                if self.previews:f.savefig(self.output/f'slide-{i:02}.png',dpi=100)
                self.plt.close(f)
        return path


def build(deck, exported, example):
    cells={(r['app'],r['config_id']):r for r in exported['rows']}
    assert set(cells)=={(a,m) for a in APPS for m in MODES}
    for row in cells.values():
        assert row['n']==5
        assert all(row[k]['n']==5 and len(row[k]['values'])==5 for k in
            ('HTTP_response_sum_ms','data_SQL','control_SQL','total_SQL','business_requests'))
    def r(a,m): return cells[a,m]
    def med(a,m,k): return median(r(a,m),k)
    def f(v): return f'{v:,.3f}'
    gains={a:100*(1-med(a,'background','HTTP_response_sum_ms')/med(a,'off','HTTP_response_sum_ms')) for a in APPS}
    assert [a for a in APPS if gains[a]>0]==['linked_list']

    p=deck.page('Background SQL prefetch: four applications',
        'Four fixed policies on one frozen runtime • five measured fresh workflows per cell')
    deck.text(p,.065,.755,f'LinkedList HTTP time is {gains["linked_list"]:.1f}% lower than Off.',28,width=.85,color='#6655aa',weight='bold')
    deck.text(p,.065,.675,'Background HTTP time is higher than Off on the other three workloads. JDrive loses an existing recursive capability; this is not an inherent cost of asynchronous execution.',20,width=.85)
    deck.table(p,['Fixture','Off HTTP ms','Background ms','HTTP time vs Off'],[
        [NAMES[a],f(med(a,'off','HTTP_response_sum_ms')),f(med(a,'background','HTTP_response_sum_ms')),
         f'{abs(gains[a]):.1f}% '+('lower time' if gains[a]>0 else 'higher time')] for a in APPS],
        widths=[.28,.23,.23,.26],area=(.065,.19,.87,.36),size=17)
    deck.text(p,.065,.12,'80 measured workflows + 16 excluded warmups; a separate 16-case correctness tier passed. All four policies and all regressions are retained.',13,width=.85)

    p=deck.page('All 16 cells: literal SQL totals and HTTP counts',
        'Medians of five fresh workflows. Snapshot/worker-transaction setup and late SQL included; fixture/bootstrap/admin excluded.')
    deck.table(p,['Fixture','Policy','HTTP sum\nms','HTTP\nrequests','Data SQL','Control SQL','TOTAL SQL','Data / HTTP'],[
        [NAMES[a],LABELS[m],f(med(a,m,'HTTP_response_sum_ms')),
         f'{med(a,m,"business_requests"):.0f}',f'{med(a,m,"data_SQL"):.0f}',
         f'{med(a,m,"control_SQL"):.0f}',f'{med(a,m,"total_SQL"):.0f}',
         f'{med(a,m,"data_SQL_per_business_request"):.3f}'] for a in APPS for m in MODES],
        widths=[.15,.18,.13,.095,.095,.10,.095,.155],area=(.055,.13,.89,.64),size=12)
    deck.text(p,.06,.105,'HTTP = sum of instrumented response-read wall times. Component medians are reported independently; no percentile or CPU-saving claim.',11,width=.87)

    p=deck.page('Five observed HTTP values per policy',
        'Dots are separate fresh workflows; thick bars are medians. Each panel has its own linear millisecond axis.')
    for i,a in enumerate(APPS):
        ax=p.add_axes([.075+(i%2)*.47,.47-(i//2)*.32,.39,.245])
        for j,m in enumerate(MODES):
            vals=r(a,m)['HTTP_response_sum_ms']['values']
            ax.scatter([j+(k-2)*.045 for k in range(5)],vals,color=COLORS[m],s=24,zorder=3)
            ax.plot([j-.18,j+.18],[statistics.median(vals)]*2,color=COLORS[m],lw=3)
        ax.set_title(NAMES[a],fontsize=14,color=NAVY)
        ax.set_xticks(range(4),['Off','Aggressive','Old Cons.','Background'],fontsize=10)
        ax.tick_params(axis='y',labelsize=10);ax.set_ylabel('HTTP sum (ms)',fontsize=10)
        ax.set_ylim(bottom=0);ax.grid(axis='y',alpha=.2)

    p=deck.page('Static SQL goes to an independent worker',
        'Source mechanism; no runtime continuation simulation in the new path',kind='Source-bound mechanism')
    deck.card(p,.065,.55,.255,.22,'1  Native hook','Capture actual origin, actor, primitive scalars and native region identity. Unsupported cases remain native.')
    deck.card(p,.37,.55,.255,.22,'2  Bounded enqueue','Single-flight / coverage checks; enqueue immutable capture. No added foreground Future wait.')
    deck.card(p,.675,.55,.255,.22,'3  Private SQL worker','Select and bind compiler-emitted SQL. Use a fresh unpooled connection and imported snapshot.')
    deck.arrow(p,(.325,.66),(.36,.66));deck.arrow(p,(.63,.66),(.665,.66))
    deck.card(p,.22,.23,.255,.22,'4  Complete result','Run path SQL and payload load; rollback and physically close. Reuse threads, not connections.')
    deck.card(p,.535,.23,.255,.22,'5  Native mailbox','Validate live transaction epoch / cancellation, then publish complete ordered paths and payloads.')
    deck.arrow(p,(.80,.55),(.35,.45));deck.arrow(p,(.475,.34),(.535,.34))
    deck.text(p,.065,.13,'Native Visit order, scalar updates, cutoffs and disengage are unchanged. Snapshot export is a disclosed lazy foreground setup SQL statement.',14,width=.87)

    p=deck.page('JDrive: an explicit capability regression',
        'Audited repeat 0, first VisibleFolderTree request 2:6. These are one-RPC records, not n=5 medians.',kind='Measured records + source interpretation')
    by_mode={x['mode']:x for x in example['records']};old=by_mode['conservative'];bg=by_mode['background']
    items=[('Data SQL',old['SQL']['data'],bg['SQL']['data']),('Control SQL',old['SQL']['control'],bg['SQL']['control']),
           ('TOTAL SQL',old['SQL']['TOTAL'],bg['SQL']['TOTAL']),('Path / tree SQL',old['categories']['other_data'],bg['categories']['ordinary_path']),
           ('Payload SQL',old['categories']['payload'],bg['categories']['payload']),('Snapshot exports',0,bg['categories']['snapshot_export']),
           ('Snapshot imports',0,bg['categories']['snapshot_import']),('Worker PID queries',0,bg['categories']['worker_identity']),
           ('DB protocol sum ms',f(old['DB_sum_ms']),f(bg['DB_sum_ms'])),('Background jobs',old['jobs'],bg['jobs'])]
    deck.table(p,['Recorded item','Old Cons.','Background'],[[name,str(x),str(y)] for name,x,y in items],
        widths=[.50,.24,.26],area=(.055,.19,.49,.58),size=13)
    deck.text(p,.58,.76,'Why the SQL scope changed',21,width=.36,color=NAVY,weight='bold')
    deck.text(p,.58,.69,'Old Conservative uses an output-tree recursive certificate for typed Contains → Folder with trashed=False and private output bookkeeping.',17,width=.36)
    deck.text(p,.58,.49,'The new background recurrence rejects this output grammar and filtered hop. It emits finite native-hook paths and does not reuse that existing recursive certificate.',17,width=.36)
    deck.text(p,.58,.28,'34 jobs: 33 finished, 1 cancelled; 33 paths / 44 payloads published. Ordinary-path counts include foreground and background calls.',15,width=.36)
    deck.text(p,.06,.12,'Higher per-origin path/payload work and per-job setup are recorded. Their exact CPU or latency contributions were not isolated; asynchronous execution itself is not disproved.',12,width=.87)

    p=deck.page('HTTP wall and DB protocol wall answer different questions',
        'Median workflow values, n = 5. DB includes all roles and late calls through post-response drain.')
    deck.table(p,['Background workload','HTTP sum ms','DB sum ms','DB union ms','TOTAL SQL'],[
        [NAMES[a],f(med(a,'background','HTTP_response_sum_ms')),f(med(a,'background','DB_sum_ms')),
         f(med(a,'background','DB_union_ms')),f'{med(a,"background","total_SQL"):.0f}'] for a in APPS],
        widths=[.28,.18,.18,.18,.18],area=(.065,.41,.87,.35),size=17)
    deck.bullets(p,[('Clock boundaries','HTTP stops at response-read completion; JSON decoding and explicit Future drain are outside it. SQL totals retain late request-origin calls.'),
                    ('No residual CPU inference','Summed DB intervals may overlap. No new CPU profile or SQL-plan ablation was run for this report; HTTP minus DB is not CPU time.')],y=.33,gap=.12)

    p=deck.page('Snapshot safety and setup are included',
        'Source and correctness evidence; SQL accounting is unchanged',kind='Method and validated boundaries')
    deck.bullets(p,[
        ('One export per eligible clean transaction','Foreground exports its actual native snapshot lazily. Worker import uses matching isolation on an independent unpooled connection; native writes decline or invalidate speculation.'),
        ('Count literal statements and purpose separately','SELECT pg_export_snapshot and worker SELECT pg_backend_pid remain data SQL; SET SNAPSHOT remains control SQL. BEGIN, rollback and other controls remain in TOTAL.'),
        ('Pool scope and cancellation','Fresh server per workflow; threads may be reused within that workflow. The excluded fresh warmup does not warm a measured server. Late/queue-full/skipped jobs are not forced into publication.'),
        ('Accepted evidence','16 application correctness cases passed. Audit retained 19 cancelled-import errors across 96 captures: 16 measured, 3 warmup; 17 code 42704 and 2 code 55000, all linked to cancellation and cleanup.')],y=.755,gap=.158)

    p=deck.page('Next step: restore static recursive capability',
        'No production change or additional experiment was made after the frozen study.',kind='Untested next steps + provenance')
    deck.bullets(p,[
        ('Highest priority — UNIMPLEMENTED / UNTESTED','Reuse the existing typed, predicate-aware output-tree certificate in the background worker, preserving complete native cache results, ACLs and synchronized snapshots without an interpreter.'),
        ('Then measure admission and job reuse','Evaluate overlapping finite-region reuse and setup-aware admission with full native oracles. Always admission was used here; neither learned admission nor DB prepared-plan reuse was evaluated.'),
        ('Frozen provenance','Common tested working tree: 38 exact dirty/new paths over HEAD 96868; intentional dirty-30 baseline preserved. Final runtime 711df00a / proof bee8e8a9; raw audit d0d83247 and publication review 33374b3f.'),
        ('Reproduce the accepted scope','Use the frozen four-application/four-policy plan and export 2111f217. Sixteen n=5 cells; no historic sample carry. Figures and the renderer bind the accepted export, source explanation and scoped JDrive records.')],y=.755,gap=.158)


def render(inputs_path, output, previews=False):
    inputs=json.loads(Path(inputs_path).read_text())
    assert inputs['frozen'] and inputs['quiet']
    payloads={}
    for name,item in inputs['inputs'].items():
        assert ref(item['path'])['sha256']==item['sha256'], 'Input drift: '+name
        payloads[name]=json.loads(Path(item['path']).read_text())
    exported=payloads['export'];assert exported['passed']
    assert payloads['publication_review']['status'].startswith('PASS')
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=False)
    deck=Deck(output,{'recorded_date':'2026-11-15'},previews)
    build(deck,exported,payloads['jdrive_example']);pdf=deck.save()
    figure=dict(inputs=inputs,rows=exported['rows'],jdrive_example=payloads['jdrive_example'],
                source_findings=payloads['source_explanation']['findings'])
    (output/'figure-inputs.json').write_text(json.dumps(figure,indent=2)+'\n')
    (output/'layout-checks.json').write_text(json.dumps(deck.checks,indent=2)+'\n')
    files=[pdf,output/'figure-inputs.json',output/'layout-checks.json',*sorted(output.glob('slide-*.png'))]
    manifest=dict(passed=True,pages=len(deck.pages),PDF=ref(pdf),renderer=ref(__file__),
        input_manifest=ref(inputs_path),outputs=[ref(p) for p in files],
        matplotlib=deck.matplotlib_version,scope='Four apps x four policies, n5. No new experiments; one audited JDrive RPC explanation.')
    path=output/'report-manifest.json';path.write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps(dict(PDF=ref(pdf),pages=len(deck.pages),manifest=ref(path))))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--inputs',required=True)
    parser.add_argument('--output',required=True);parser.add_argument('--previews',action='store_true')
    args=parser.parse_args();render(args.inputs,args.output,args.previews)

