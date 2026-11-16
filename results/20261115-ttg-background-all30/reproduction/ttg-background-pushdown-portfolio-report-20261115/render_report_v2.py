"""All30 English portfolio report. Accepted derived inputs only; no runtime/raw replay.
Deck primitives reused from the accepted restoration renderer.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import statistics
import importlib.util
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
        path=self.output/'ttg-background-pushdown-all30.pdf'
        violations=[]
        with self.PdfPages(path) as pdf:
            for i,f in enumerate(self.pages,1):
                footer=self.text(f,.055,.045,'TTG • '+self.data.get('recorded_date','2026-11-15')+' • '+f._kind,10,width=.82,color=MUTED)
                footer._is_footer=True
                number=self.text(f,.94,.045,str(i),10,width=.03,color=MUTED)
                number._is_footer=True
                f.canvas.draw();renderer=f.canvas.get_renderer();W,H=f.bbox.width,f.bbox.height
                checks=[]
                for t in f._tracked:
                    b=t.get_window_extent(renderer);bounds=[b.x0/W,b.y0/H,b.x1/W,b.y1/H]
                    if bounds[0]<.035 or bounds[2]>.965 or bounds[1]<.018 or bounds[3]>.95:
                        violations.append(dict(page=i,kind='slide bounds',text=t.get_text(),bounds=bounds))
                    if not getattr(t,'_is_footer',False) and bounds[1] < .06:
                        violations.append(dict(page=i,kind='footer band',text=t.get_text(),bounds=bounds))
                    if hasattr(t,'_cell_bounds'):
                        x0,y0,x1,y1=t._cell_bounds
                        if bounds[0]<x0-.002 or bounds[2]>x1+.002 or bounds[1]<y0-.003 or bounds[3]>y1+.003:
                            violations.append(dict(page=i,kind='table cell',text=t.get_text(),bounds=bounds))
                    checks.append(dict(text=t.get_text(),bounds=bounds))
                self.checks.append(dict(page=i,title=f._title,passed=not any(v['page']==i for v in violations),footer_exclusion_passed=not any(v['page']==i and v['kind']=='footer band' for v in violations),text=checks))
                pdf.savefig(f)
                if self.previews:f.savefig(self.output/f'slide-{i:02}.png',dpi=100)
                self.plt.close(f)
        if violations:
            (self.output/'layout-violations.json').write_text(json.dumps(violations,indent=2)+'\n')
            raise ValueError(f'{len(violations)} layout violations; see layout-violations.json')
        return path


def stat(data, app, policy, key):
    cell = next(c for c in data['cells'] if c['app'] == app and c['policy'] == policy)
    return cell['metrics'][key]


def mini(deck, figure, x, y, w, h, text, color='#14877c', size=11):
    figure.add_artist(deck.Box((x,y),w,h,boxstyle='round,pad=.006',
        transform=figure.transFigure,facecolor='white',edgecolor=color,linewidth=1.3))
    deck.text(figure,x+.009,y+h-.009,text,size,width=w-.018,color=INK)


def region(deck, figure, x, y, w, h, label):
    figure.add_artist(deck.Box((x,y),w,h,boxstyle='round,pad=.012',
        transform=figure.transFigure,facecolor='#eef7f3',edgecolor='#14877c',
        linewidth=1.7,linestyle='--'))
    deck.text(figure,x+.009,y+h-.012,label,12,width=w-.018,color='#14877c',weight='bold')


def ability(deck, figure, x, y, name, access, guard, visit):
    w,h=.235,.245
    figure.add_artist(deck.Box((x,y),w,h,boxstyle='round,pad=.007',
        transform=figure.transFigure,facecolor=PALE,edgecolor=NAVY,linewidth=1.6))
    deck.text(figure,x+.012,y+h-.012,name,15,width=w-.024,weight='bold',color=NAVY)
    for dy,text in ((.135,access),(.077,guard),(.019,visit)):
        mini(deck,figure,x+.013,y+dy,w-.026,.044,text,size=10)
    deck.arrow(figure,(x+.115,y+.133),(x+.115,y+.124))
    deck.arrow(figure,(x+.115,y+.075),(x+.115,y+.066))


def method_pages(deck, data, method):
    p=deck.page('From local dependencies to cross-ability regions',
        'General vision: concrete Jac A→B and A→C. This branched composition is illustrative, not a new supported certificate.',
        kind='Illustrative method; implemented examples follow')
    region(deck,p,.065,.19,.87,.59,'Candidate SQL region across ability-local Access / Visit subgraphs — illustrative')
    ability(deck,p,.382,.48,'A: entry ability','Access: origin + field','Guard: local predicate','Visit: append B, C')
    ability(deck,p,.10,.215,'B: entry ability','Access: B.fields','Guard: local predicate','Visit: B successors')
    ability(deck,p,.665,.215,'C: entry ability','Access: C.fields','Guard: local predicate','Visit: C successors')
    deck.arrow(p,(.408,.48),(.22,.465));deck.arrow(p,(.59,.48),(.78,.465))
    deck.text(p,.07,.165,'Solid inter-node arrows: Jac graph / Visit dispatch. Small internal arrows: ability-local data/control dependence. Region entry follows available external bindings; unknown effects form a boundary.',13,width=.86)
    deck.text(p,.07,.105,'General runtime composition and arbitrary latest-dependency placement remain future work. Bounded heterogeneous composition already has prior functional evidence (next page).',11,width=.86)

    p=deck.page('Prior implemented certificate: different ability definitions',
        'RegionA → RegionB → RegionC, typed finite chain. Prior native mechanism evidence, not a current all30 timing sample.',
        kind='Prior functional evidence • addd3a4 • method artifact 8922f473')
    region(deck,p,.06,.36,.88,.39,'Actual finite / unrolled SQL region across three distinct entry abilities')
    ability(deck,p,.08,.39,'RegionA entry','Access: origin / dispatch','Typed path: RegionAB','Visit: RegionB')
    ability(deck,p,.383,.39,'RegionB entry','Access: here.active','SQL: ordinary bool guard','Visit: RegionC if true')
    ability(deck,p,.685,.39,'RegionC entry','Access: terminal identity','SQL: type / row proof','No further certified Visit')
    deck.arrow(p,(.321,.51),(.375,.51));deck.arrow(p,(.624,.51),(.676,.51))
    deck.text(p,.07,.325,'Native-only lane outside green: output / report handlers execute unchanged; no report code is compiled into SQL.',13,width=.86)
    deck.text(p,.07,.285,'True guard: one region query, two cached paths, native report [17]. False guard: one region query, one cached path, no report. Native pair consumers requery zero store.rows after test completion.',17,width=.86)
    deck.text(p,.07,.175,'Exact typed dispatch + one supported Visit per ability; Boolean guard stays SQL-internal. Origin, dispatch and actor/ACL are external bindings. Shared thresholds / opaque effects are rejected, not solved generally.',15,width=.86)
    deck.text(p,.07,.12,'Source: method-inputs-v1.json 8922f473; actual guard SQL 9112d09d; native review 4d30896b. These functional records do not measure current worker latency or current payload service.',11,width=.86)

    p=deck.page('Current implemented certificate: JDrive Folder tree',
        'Same Folder.walk definition across multiple node activations; typed Contains→Folder and trashed=False remain in SQL.',
        kind='Current restored background mechanism • actual JDrive source')
    region(deck,p,.065,.315,.87,.44,'Implemented recursive output-tree certificate: complete typed child paths across activations')
    ability(deck,p,.085,.365,'Folder A: walk','Access: here / child.name','Contains→Folder; not trashed','Visit: visible children')
    ability(deck,p,.385,.365,'Folder B: walk','Access: here / child.name','Contains→Folder; not trashed','Visit: visible children')
    ability(deck,p,.685,.365,'Folder C: walk','Access: here / child.name','Contains→Folder; not trashed','Visit: visible children')
    deck.arrow(p,(.325,.485),(.377,.485));deck.arrow(p,(.625,.485),(.677,.485))
    deck.text(p,.075,.285,'A→B→C illustrates a descendant path inside the actual branched tree. This is homogeneous recurrence, distinct from the prior heterogeneous finite certificate.',14,width=.85)
    deck.text(p,.075,.19,'Native lane outside SQL: self.entries, depth/path bookkeeping, final sort/report and original Visit execution. Certified output effects do not select a different typed child predicate.',17,width=.85)
    deck.text(p,.075,.12,'Source: originals/jdrive/server.jac:103–111; server.impl.jac:44–68. Restoration native review 7012e912; depth7 actual queries/counters in accepted export 38e58fcd.',11,width=.85)

    p=deck.page('Foreground capture → private SQL → native cache',
        'No plan_continuation or old foreground Access resolver in the new path. Original business execution remains native.',
        kind='Implemented execution and safety boundaries')
    stages=[('1  Owner eligibility','Typed effect / dispatch proof; check single-flight and coverage before repeated ownership scans.'),
            ('2  Immutable capture','Origin, actor and primitive bindings; lazy exported native snapshot. Export is counted SQL setup.'),
            ('3  Bounded worker','Select / bind emitted SQL; private unpooled connection + compatible snapshot transaction.'),
            ('4  Complete row proof','Order, duplicates, terminal empties, predicates, ACL, closure, cycles and resource completeness.'),
            ('5  Owner publication','Mailbox checks request / epoch / capacity; atomic path + payload caches. Native consumers may reuse.')]
    for i,(title,body) in enumerate(stages):
        y=.69-i*.112
        deck.text(p,.065,y,title,18,weight='bold',color=NAVY,width=.29)
        deck.text(p,.36,y,body,15,width=.565)
        if i<4:deck.arrow(p,(.18,y-.065),(.18,y-.095))
    deck.text(p,.065,.12,'Dirty writes, expired/cancelled leases, unsupported effects and late results decline or fall back. Expected cancelled imports remain in SQL totals; unexpected errors are visible. No production Future wait is added.',12,width=.87)

    p=deck.page('Cost/admission: Always here, adaptive decisions later',
        'This comparison exercises eligible Always policies, not a trained learned-cost decision.',kind='Current policy versus unimplemented roadmap')
    deck.card(p,.065,.45,.40,.31,'Implemented now','Static eligibility, bounded queue, single-flight/coverage, transaction safety and cancellation. Always attempts eligible work; it does not guarantee completion or timely service.')
    deck.card(p,.535,.45,.40,.31,'Adaptive admission: future','Expected avoided blocking reads must outweigh setup, planning/binding, dispatch, transfer and wasted work. Include cold readiness, snapshot cost and transaction lifetime.')
    deck.text(p,.08,.345,'Conceptual decision: expected useful latency avoided > extra setup + scheduling + SQL + transfer + wasted work.',20,width=.84,color=NAVY,weight='bold')
    deck.text(p,.08,.225,'No fitted coefficients or causal CPU split are inferred from this study. Shared/overlapping wall intervals cannot be subtracted to recover CPU. DB prepared-plan reuse is separate, unimplemented work.',17,width=.84)
    deck.text(p,.08,.135,'Many small workflows may not amortize the observed extra SQL/job setup: interpretation supported by counts, not a measured CPU cause or a tested adaptive policy.',14,width=.84)



def sibling_page(deck):
    p=deck.page('Sibling dependence: output state ≠ future-access control',
        'Proven absence, exposed MAY dependence and unknown/unsupported are distinct outcomes.',kind='Semantic boundary; not a new generic effect analyzer')
    deck.card(p,.065,.47,.40,.29,'Output-only example','Appending a result or maintaining an output path can be independent of future visit selection under a checked certificate. JDrive still has shared output state.')
    deck.card(p,.535,.47,.40,.29,'Access-affecting witness','Queue [B,C], self.i=0. B: self.i += 1. C: if self.i == 1 visit X else Y. B changes C’s future access; identical entry snapshots are unsound.',color='#b76b31')
    deck.table(p,['Static outcome','Meaning'],[
        ['Proven absence','A bounded summary/certificate establishes no access-affecting shared dependence.'],
        ['MAY dependence','A write can reach a sibling’s guard / target / early exit / visible database effect.'],
        ['Unknown / unsupported','Opaque helper, alias or external effect blocks proof. Not theoretical impossibility.']],
        widths=[.23,.77],area=(.065,.15,.87,.25),size=14)
    deck.text(p,.065,.12,'Preserve FIFO, append-tail Visit order, duplicates and native disengage. Total visited count is not graph depth or proof of a chain. No general shared-threshold/latest-definition solver is claimed.',12,width=.87)


def overview_pages(deck, data):
    cells={(c['app'],c['policy']):c for c in data['cells']}
    winners=[a['label'] for a in data['apps'] if stat(data,a['app'],'restored','HTTP_response_sum_ms')['median'] < stat(data,a['app'],'off','HTTP_response_sum_ms')['median']]
    p=deck.page('Static background SQL: broad coverage, narrow wins',
        'One LinkedList microbenchmark + 29 applications; four policies, five fresh measured workflows per cell.',kind='All30 portfolio • 120 n5 cells')
    deck.card(p,.065,.47,.40,.29,f"{len(winners)} / 30 lower HTTP medians",', '.join(winners)+' beat Off in this fixed matrix. The remaining entries are retained as regressions.')
    deck.card(p,.535,.47,.40,.29,'720 primary workflows','120 excluded warmups + 600 measured workflows. 120 correctness identities: 108 fresh + 12 explicit bridge carry; no timing carry.')
    deck.text(p,.07,.35,'Large-scale result: JDrive depth7 (4,374 initial nodes). Most portfolio initial graphs are deliberately small; this is broad coverage, not 30 large-scale validations.',21,width=.86,color=NAVY,weight='bold')
    deck.text(p,.07,.20,'The new mode captures immutable parameters and enqueues static SQL work on GIL-off threads. It does not run the old continuation simulation; unsupported behavior remains native.',17,width=.86)
    deck.text(p,.07,.12,'Four modes: Off / Old Conservative / Previous Background / Restored Background. Successful correctness, static eligibility, actual activation and latency benefit are separate claims.',12,width=.86)

    p=deck.page('Benchmark breadth, scale and measurement boundary',
        'Most graphs start small; operations can add nodes/edges. Initial size is not visited count or final size.',kind='Fixed selection and experimental method')
    small=[]
    for a in data['apps']:
        f=a['selected_initial_fixture'];n=f.get('nodes',f.get('initial_node_count'))
        if a['app']!='jdrive':small.append(n)
    deck.table(p,['Fixed scope','Actual meaning'],[
        ['30 entries','Original LinkedList32 microbenchmark + 29 registered applications; no favorable-case pruning.'],
        ['Main JDrive scale','Depth7: 4,374 initial nodes / 4,373 edges; seven business HTTP actions.'],
        ['Other initial graphs',f"Source-declared initial node range {min(small)}–{max(small)}; workflow mutations may grow the graph."],
        ['Per policy / app','One excluded warmup + five fresh measured workflows; exact fixture/order/oracle shared.'],
        ['Correctness identities','4 depth7 + 12 explicitly carried bridge + 104 fresh portfolio = 120.'],
        ['Timing quantity','Sum of instrumented business HTTP response wall, ending at response read completion.'],
        ['SQL quantity','All-role data / control / TOTAL, including snapshot and worker transaction setup.']],
        widths=[.25,.75],area=(.065,.205,.87,.56),size=14)
    deck.text(p,.065,.135,'Post-response Future drain is separate. Runtime/config/source IDs are policy-specific; old immutable 711d controls remain explicit. Original business/state/restart/GIL/backend gates are retained.',13,width=.87)
    deck.text(p,.065,.12,'Primary captures retain SQL text and frontend frame metadata, not original Bind values or raw packet payloads. No parameter-equivalence claim follows from these records.',11,width=.87)


def evidence_pages(deck,data,purpose):
    from portfolio_pages_v2 import POLICIES, LABELS
    p=deck.page('Results overview: retain every regression',
        'Ratio = Restored Background HTTP median / Off HTTP median; below 1 means lower observed time.',kind='All30 measured n5 medians; no pooled cross-scale data')
    ax=p.add_axes([.235,.24,.69,.53])
    ratios=[stat(data,a['app'],'restored','HTTP_response_sum_ms')['median']/stat(data,a['app'],'off','HTTP_response_sum_ms')['median'] for a in data['apps']]
    ax.barh(range(30),ratios,color=['#14877c' if r<1 else '#b8824d' for r in ratios])
    ax.set_yticks(range(30),[a['label'] for a in data['apps']],fontsize=8.5);ax.invert_yaxis()
    ax.axvline(1,color=NAVY,linewidth=1);ax.set_xlabel('HTTP time ratio (Restored / Off)',fontsize=12);ax.grid(axis='x',alpha=.15)
    deck.text(p,.07,.12,'Table pages retain all five-value ranges and literal counts. Source-based support does not establish activation; zero tree jobs are not zero graph access or zero total prefetch work.',11,width=.86)

    p=deck.page('JDrive depth7: restored tree execution is observed',
        'Same seven business HTTP actions; fresh n5. Old Conservative still has fewer SQL calls.',kind='Current portfolio main JDrive entry; not an extra application')
    rows=[]
    for mode in POLICIES:
        rows.append([LABELS[mode]]+[str(int(stat(data,'jdrive',mode,k)['median'])) for k in ('recursive_SQL','pool_jobs','tree_jobs','data_SQL','control_SQL','total_SQL')])
    deck.table(p,['Policy','Recursive SQL','New pool jobs','Tree jobs','Data','Control','TOTAL'],rows,
        widths=[.25,.14,.14,.12,.11,.12,.12],area=(.065,.435,.87,.30),size=14)
    deck.text(p,.07,.375,'Restored, every measured workflow: 3 recursive queries, 5 pool jobs, 3 tree jobs/publications, 1,600 summed published cache-origin paths. Publication is not unique nodes or demonstrated timely service.',17,width=.86)
    deck.text(p,.07,.235,'The restored worker reuses the existing typed predicate-aware output-tree certificate. Previous Background lacked this recursive capability; that is a capability regression, not an inherent cost of asynchrony.',17,width=.86)
    deck.text(p,.07,.13,'Counts establish actual SQL work and remaining overhead; these records do not isolate late completion from other cache behavior. CPU phases and total CPU were not measured in this portfolio.',13,width=.86)

    if purpose:
        p=deck.page('Slow cases: measured extra work, limited causality',
            'Three largest absolute Restored-minus-Off workflow HTTP differences; examples selected after retaining the full matrix.',kind='Audited saved-derivative explanation • n5')
        rows=[]
        labels={a['app']:a['label'] for a in data['apps']}
        for ex in purpose['examples']:
            app=ex['app']
            for mode in ('off','restored'):
                rows.append([labels[app] if mode=='off' else '',LABELS[mode]]+[
                    f"{stat(data,app,mode,'HTTP_response_sum_ms')['median']:.3f}"]+[
                    str(int(stat(data,app,mode,k)['median'])) for k in ('data_SQL','control_SQL','total_SQL','pool_jobs')])
        deck.table(p,['Workflow','Policy','HTTP ms','Data','Control','TOTAL','New jobs'],rows,
            widths=[.19,.22,.13,.11,.11,.11,.13],area=(.065,.32,.87,.43),size=13)
        deck.text(p,.07,.255,'Extra snapshot/worker transactions and reads are observed; many small workflows may not amortize them. This is a counts-supported interpretation, not measured CPU causality or an isolated latency decomposition.',16,width=.86)
        deck.text(p,.07,.12,'Column medians need not add: data + control = TOTAL in each actual trial. Jobs and explicit cancelled:true event flags have different scopes; zero explicit flags would not mean no cancellations.',12,width=.86)

    p=deck.page('Support, activation and acceleration are separate',
        'All fixed applications remain, including native fallbacks, empty initial opportunities and slower results.',kind='Boundaries and negative outcomes')
    deck.bullets(p,[('Support is bounded','Typed/static tree and finite paths have explicit effect, dispatch, predicate and completeness requirements. Opaque helpers, writes, shared access-affecting state and unknown behavior stay native.'),
                    ('Zero output-tree jobs is a result','The bridge’s non-JDrive cases and all remaining portfolio stages have zero measured tree jobs. This does not prove that every prefetch path is inactive or theoretically impossible.'),
                    ('Small initial fixtures are deliberate','BuildRelease starts with one Release and no Build. Read/CRUD workflows, graph growth, helper calls and empty paths remain in the operation/oracle set.'),
                    ('Failure provenance is not hidden','B1-v1 failed independent replay mapping before acceptance. The repaired fresh B1-v2 is used; failed v1 is preserved separately and never pooled.')],gap=.158)

    sibling_page(deck)

    p=deck.page('Next steps and reproducible evidence',
        'No new profiling, SQL variant or feature experiment was added to complete this report.',kind='Scoped interpretation and roadmap')
    deck.bullets(p,[('Keep semantic boundaries','Expand only with exact per-ability/helper effects and native cache/ACL/snapshot proofs. General alias/external-effect and latest-definition composition remain future work.'),
                    ('Reduce observed extra work safely','Investigate extra foreground reads, repeated small-job setup, cancellation and region reuse. Publication counters alone do not establish timely service or usefulness.'),
                    ('Admission should include real costs','Future admission can account for transaction/setup, scheduling, transfer and wasted work. Always was used here; learned policy and prepared-plan reuse were not evaluated.'),
                    ('Evidence remains portable and versioned','Six accepted stage exports/audits feed all120 cells. Preserve 12 correctness carries, failed B1 provenance and three lossless relocation maps; restore raw evidence before accessing relocated paths.')],gap=.158)
    deck.text(p,.07,.12,'Inputs d0c17bb5 • input mapping 29a7a1e8 • purpose cb2b1d16 / mapping c5411822 • prior functional method 8922f473. Full paths/hashes and per-trial references are in figure inputs.',11,width=.86)


def render(input_path, purpose_path, output, previews):
    from portfolio_pages_v2 import add_portfolio_pages
    data=json.loads(Path(input_path).read_text())
    if ref(input_path)['sha256']!='d0c17bb51dc73aa4a724edf38234c6d14e034ff730be7f77860d2ff5ed0c003e':
        raise ValueError('Unexpected all30 input revision')
    purpose=json.loads(Path(purpose_path).read_text()) if purpose_path else None
    if purpose and ref(purpose_path)['sha256']!='cb2b1d16fc75c24b3c00295bdc6650ff8125377c81833dec263453b1bee1803e':
        raise ValueError('Unexpected purpose revision')
    if not data['passed'] or data['counts']!={'entries':30,'cells':120,'primary':720,'excluded_warmups':120,'measured':600,'n':5,'correctness_identities':120,'fresh_correctness':108,'carried_correctness':12}:
        raise ValueError('Final portfolio scope mismatch')
    method_path=Path(__file__).resolve().parents[2]/'project-notes/measurements/ttg-interability-20261101/method-inputs-v1.json'
    method=json.loads(method_path.read_text())
    if ref(method_path)['sha256']!='8922f473d720128b7808259ec4e4c536cb30b0741cb2f08dad333393d021b28b':
        raise ValueError('Prior method artifact drift')
    output=Path(output);output.mkdir(parents=True,exist_ok=False)
    data['recorded_date']='2026-11-15'
    deck=Deck(output,data,previews)
    overview_pages(deck,data)
    # Put method/cost/sibling pages before the full result matrix, never behind it.
    method_pages(deck,data,method)
    add_portfolio_pages(deck,data)
    evidence_pages(deck,data,purpose)
    pdf=deck.save()
    figure={'accepted_input':ref(input_path),'purpose':ref(purpose_path) if purpose else None,
            'prior_functional_method':ref(method_path),'data':data,'purpose_data':purpose,
            'method_data':method,'renderer':ref(__file__),'page_builder':ref(Path(__file__).with_name('portfolio_pages_v2.py'))}
    (output/'figure-inputs.json').write_text(json.dumps(figure,indent=2)+'\n')
    (output/'layout-checks.json').write_text(json.dumps({'passed':True,'pages':deck.checks},indent=2)+'\n')
    outputs=[ref(p) for p in sorted(output.iterdir()) if p.is_file()]
    manifest={'passed':True,'pages':len(deck.pages),'pdf':ref(pdf),'renderer':ref(__file__),
              'page_builder':ref(Path(__file__).with_name('portfolio_pages_v2.py')),'input':ref(input_path),
              'purpose':ref(purpose_path) if purpose else None,'prior_method':ref(method_path),
              'matplotlib_version':deck.matplotlib_version,'outputs':outputs}
    (output/'report-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps({'pdf':ref(pdf),'pages':len(deck.pages),'manifest':ref(output/'report-manifest.json')}))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--input',required=True)
    parser.add_argument('--purpose');parser.add_argument('--output',required=True)
    parser.add_argument('--previews',action='store_true');args=parser.parse_args()
    render(args.input,args.purpose,args.output,args.previews)

