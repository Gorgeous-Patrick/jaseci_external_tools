"""Additive four-page restoration report, accepted derived inputs only.
Reuses the prior slide primitives; no Jac imports, raw replay or experiments.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import statistics
NAVY, INK, MUTED, PALE = '#142c45', '#263c50', '#596f82', '#eff4f7'
MODES=('off','conservative','background','restored')
LABELS={'off':'Off','conservative':'Old Conservative','background':'Previous Background','restored':'Restored Background'}
COLORS={'off':'#758598','conservative':'#14877c','background':'#d68b43','restored':'#6655aa'}

def ref(path):
    p=Path(path).resolve()
    return {'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}

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
        path=self.output/'ttg-background-pushdown-restoration.pdf'
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


def build(deck, data):
    export=data['export'];rows={r['config_id']:r for r in export['rows']}
    assert set(rows)==set(MODES) and all(r['n']==5 for r in rows.values())
    assert export['counts']=={'captured':24,'correctness':0,'excluded_warmups':4,'measured':20,'measured_cells':4}
    correct=data['correctness'];assert correct['passed'] and len(correct['rows'])==16
    assert all(row['passed'] for row in correct['rows'])
    assert data['publication']['status'].startswith('PASS')
    purpose={c['mode']:c for c in data['purpose']['cells']}
    med=lambda m,k:rows[m][k]['median']
    fmt=lambda v:f'{v:,.3f}'
    restored=med('restored','HTTP_response_sum_ms')
    reduction=100*(1-restored/med('conservative','HTTP_response_sum_ms'))

    p=deck.page('Recursive SQL capability restored in background',
        'An additive restoration: the existing typed, predicate-aware output-tree certificate is reused.',kind='Source mechanism and deterministic native proof')
    deck.card(p,.06,.53,.26,.23,'Existing certificate','Typed Contains → Folder; trashed=False. Native output bookkeeping, Visit order, ACL and predicate semantics are retained.')
    deck.card(p,.37,.53,.26,.23,'Private SQL worker','Select and bind the existing recursive SQL in its synchronized private snapshot transaction. No ability interpreter.')
    deck.card(p,.68,.53,.26,.23,'Complete native cache','Validate properties, order, arity, empties, closure and cycles. Owner rechecks epoch / cached fields, then publishes atomically.')
    deck.arrow(p,(.325,.64),(.36,.64));deck.arrow(p,(.635,.64),(.67,.64))
    deck.text(p,.065,.43,'Actual branched, three-level native proof',22,color=NAVY,weight='bold')
    deck.text(p,.065,.365,'One recursive query / private job / owner effect proof; six cached origin paths and five payloads. Full output equals Off and old CS, including the duplicate-edge variant.',19,width=.86)
    deck.text(p,.065,.245,'After test-only Future completion: actual owner _run sees no further path or payload SQL; native builder and old resolver/interpreter are forbidden. Eleven duplicate_skips are submission suppression, not cache hits.',16,width=.86)
    deck.text(p,.065,.12,'Production has no added Future wait. The existing ownership scan is an owner-thread cost, checked once per tree attempt after single-flight / coverage guards.',13,width=.86)

    p=deck.page('Fresh JDrive depth-five performance',
        f'Restored HTTP median {fmt(restored)} ms: {reduction:.1f}% lower than old CS despite more SQL. Five fresh measured workflows per policy.')
    table=[]
    for mode in MODES:
        stats=rows[mode]['HTTP_response_sum_ms']
        table.append([LABELS[mode],fmt(stats['median'])+'\n['+fmt(stats['min'])+'–'+fmt(stats['max'])+']',
            str(int(med(mode,'business_requests'))),str(int(med(mode,'data_SQL'))),
            str(int(med(mode,'control_SQL'))),str(int(med(mode,'total_SQL'))),
            fmt(med(mode,'data_SQL_per_business_request'))])
    deck.table(p,['Policy','HTTP sum ms\nmedian [range]','HTTP\nrequests','Data SQL','Control SQL','TOTAL SQL','Data / HTTP'],table,
               widths=[.22,.25,.09,.10,.11,.10,.13],area=(.055,.445,.89,.32),size=14)
    ax=p.add_axes([.095,.16,.81,.205])
    for i,mode in enumerate(MODES):
        values=rows[mode]['HTTP_response_sum_ms']['values']
        ax.scatter([i+(j-2)*.045 for j in range(5)],values,color=COLORS[mode],s=30,zorder=3)
        ax.plot([i-.18,i+.18],[statistics.median(values)]*2,color=COLORS[mode],lw=3)
    ax.set_xticks(range(4),['Off','Old Conservative','Previous Background','Restored Background'],fontsize=11)
    ax.set_ylabel('HTTP sum (ms)',fontsize=11);ax.tick_params(axis='y',labelsize=10)
    ax.set_ylim(bottom=0);ax.grid(axis='y',alpha=.2)
    deck.text(p,.06,.105,'Old CS and previous BG use immutable 711d controls; Off is disabled on the restored runtime. Four separate fresh warmups are excluded. No prior timing samples are pooled.',11,width=.88)

    p=deck.page('Actual activation and four-app correctness scope',
        'JDrive timing only: the other three applications have correctness results, not new performance measurements.')
    def interval(mode,key):
        s=rows[mode][key]
        return str(int(s['median'])) if s['min']==s['max'] else f"{int(s['median'])} [{int(s['min'])}–{int(s['max'])}]"
    deck.table(p,['Policy','Actual recursive SQL','New SQL-pool jobs','Of which tree jobs'],[
        [LABELS[m],interval(m,'recursive_SQL'),interval(m,'pool_jobs'),interval(m,'tree_jobs')] for m in MODES],
        widths=[.31,.23,.23,.23],area=(.065,.46,.87,.30),size=16)
    deck.text(p,.065,.415,'Restored, every measured workflow: 3 tree queries, 5 pool jobs, 3 tree proofs / publications and 261 summed published cache-origin paths. These are not unique nodes or timely cache hits.',15,width=.87)
    apps=[('littlex','LittleX smoke'),('linked_list','Original LinkedList 32'),('jdrive','JDrive depth 5'),('recipe_pantry','RecipePantry smoke')]
    statuses={(r['app'],r['config_id']):r['passed'] for r in correct['rows']}
    assert len(statuses)==16
    deck.table(p,['Correctness fixture','Off','Old CS','Previous BG','Restored BG'],[
        [name]+['PASS' if statuses[(app,m)] else 'FAIL' for m in MODES] for app,name in apps],
        widths=[.34,.14,.16,.18,.18],area=(.065,.115,.87,.23),size=13)
    deck.text(p,.065,.08,'Pool-job counts describe the new SQL pool, not legacy thread workers. Full business/state/restart/GIL/backend gates passed. No cancelled-import error occurred in the 24 captures.',10.5,width=.87)

    p=deck.page('Remaining SQL work: 196 restored versus 107 old CS',
        'Median all-role counts, n = 5. Setup remains included in the unchanged data / control / TOTAL classification.')
    def count(mode,key):return purpose[mode]['purposes'].get(key,{'median':0})['median']
    def setup(mode):return sum(count(mode,k) for k in ('snapshot_export','snapshot_import','worker_identity'))
    parts=[('Ordinary paths',count('conservative','ordinary_path'),count('restored','ordinary_path')),
           ('Payload reads',count('conservative','payload'),count('restored','payload')),
           ('Snapshot / worker identity setup',setup('conservative'),setup('restored')),
           ('Remaining controls',count('conservative','control'),count('restored','control')),
           ('Recursive tree SQL',count('conservative','output_tree_region'),count('restored','output_tree_region')),
           ('Identity + mutation',count('conservative','identity')+count('conservative','mutation'),count('restored','identity')+count('restored','mutation')),
           ('TOTAL',med('conservative','total_SQL'),med('restored','total_SQL'))]
    assert sum(y-x for _,x,y in parts[:-1])==89
    deck.table(p,['Measured purpose','Old CS','Restored','Change'],[
        [name,str(int(x)),str(int(y)),('+' if y>x else '')+str(int(y-x))] for name,x,y in parts],
        widths=[.49,.16,.18,.17],area=(.055,.285,.50,.48),size=13)
    deck.text(p,.60,.76,'Extra foreground reads remain',21,width=.34,color=NAVY,weight='bold')
    deck.text(p,.60,.685,'Foreground ordinary paths: 32 vs 4. Foreground payload reads: 59 vs 30. The three tree queries move from foreground to background.',17,width=.34)
    deck.text(p,.60,.475,'Records do not isolate late completion from other cache behavior. Publication is not demonstrated timely service; no CPU or per-phase attribution was measured.',17,width=.34)
    deck.text(p,.60,.31,'Next steps are untested: investigate remaining reads and setup-aware admission while preserving ACL, snapshot and cancellation rules.',15,width=.34)
    deck.text(p,.06,.195,'The +89 is +30 ordinary paths, +29 payload reads, +15 snapshot/worker-identity setup and +15 other controls. Restored repeat 3 has one extra path and payload query (TOTAL 198).',12,width=.88)
    deck.text(p,.06,.105,'Scope: 24 captures = 4 warmups + 20 measured; 16 separate correctness cases. Runtime 93ea9557 / b1153c21; export 485743ad; audit 8d9884bf; publication b24b8cce. Earlier report 534c768e remains unchanged.',10.5,width=.88)


def render(inputs_path, output, previews):
    inputs=json.loads(Path(inputs_path).read_text());assert inputs['frozen'] and inputs['quiet']
    data={}
    for name,item in inputs['inputs'].items():
        assert ref(item['path'])['sha256']==item['sha256'], 'Input drift: '+name
        data[name]=json.loads(Path(item['path']).read_text())
    assert data['export']['passed'] and data['purpose']['passed']
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=False)
    deck=Deck(output,{'recorded_date':'2026-11-15'},previews);build(deck,data);pdf=deck.save()
    figure=dict(inputs=inputs,rows=data['export']['rows'],
        purpose_medians={c['mode']:{k:v['median'] for k,v in c['purposes'].items()} for c in data['purpose']['cells']},
        correctness=[{k:r[k] for k in ('app','config_id','passed')} for r in data['correctness']['rows']],
        native_proof=data['runtime']['results'])
    (output/'figure-inputs.json').write_text(json.dumps(figure,indent=2)+'\n')
    (output/'layout-checks.json').write_text(json.dumps(deck.checks,indent=2)+'\n')
    files=[pdf,output/'figure-inputs.json',output/'layout-checks.json',*sorted(output.glob('slide-*.png'))]
    manifest=dict(passed=True,pages=len(deck.pages),PDF=ref(pdf),renderer=ref(__file__),
                  input_manifest=ref(inputs_path),outputs=[ref(p) for p in files],
                  scope='Fresh JDrive n5 only; four-app correctness; native test waits are not production waits.')
    p=output/'report-manifest.json';p.write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps(dict(PDF=ref(pdf),pages=len(deck.pages),manifest=ref(p))))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--inputs',required=True)
    parser.add_argument('--output',required=True);parser.add_argument('--previews',action='store_true')
    args=parser.parse_args();render(args.inputs,args.output,args.previews)

