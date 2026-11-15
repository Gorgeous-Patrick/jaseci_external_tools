"""Presentation only: accepted derived inputs, English slides, no runtime imports.

Prepared as source during timing. Execute only after complete accepted data and
quiet handoff; no rendering/testing has been performed by writing this file.
"""
import argparse
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import statistics
import sys

MODES = ('off', 'aggressive', 'conservative')
TERMINAL_OUTCOMES = ('resource_outcome','failed_isolation_gate','correctness_only','not_run','not_run_after_first_failure')
LABELS = {'off': 'Off', 'aggressive': 'Aggressive', 'conservative': 'Conservative'}
COLORS = {'off': '#758598', 'aggressive': '#d68b43', 'conservative': '#14877c'}
NAMES = {'jdrive':'JDrive','littlex':'LittleX','recipe_pantry':'RecipePantry','linked_list':'LinkedList',
         'issue_desk':'IssueDesk','stock_room':'StockRoom','clinic_queue':'ClinicQueue',
         'budget_ledger':'BudgetLedger','knowledge_map':'KnowledgeMap','course_path':'CoursePath',
         'approval_desk':'ApprovalDesk','library_loans':'LibraryLoans','event_seats':'EventSeats',
         'help_queue':'HelpQueue','delivery_route':'DeliveryRoute','volunteer_shift':'VolunteerShift',
         'incident_room':'IncidentRoom'}
TRAITS = {
 'jdrive':'Visible folder recursion; trashed branch pruning; list/trash/mkdir.',
 'littlex':'Feed Post/Follow paths; profile helper Access; like/follow/create.',
 'recipe_pantry':'Requirement joins; ownership helper; planned/cooked state; conserved inventory.',
 'linked_list':'Traverse total cutoff; Sum reduction; early/middle/missing Find.',
 'issue_desk':'Project branches; issue dependencies; assignment and close/reopen.',
 'stock_room':'Lot allocation; reserve/release/dispatch; conserved stock.',
 'clinic_queue':'Practitioner/slot branches; booking and cancellation.',
 'budget_ledger':'Envelope/category branches; conserved budget transfers.',
 'knowledge_map':'Revision helpers; shared seen-set link exploration.',
 'course_path':'Course/enrollment branches; prerequisite and completion rules.',
 'approval_desk':'Expense helper reads; line totals; approval routing and payment.',
 'library_loans':'Copy/hold graph reads; borrowing and queue updates.',
 'event_seats':'Seat/booking helpers; hold/confirm/cancel capacity.',
 'help_queue':'Ticket branches; clock/SLA evaluation and escalation writes.',
 'delivery_route':'Route/parcel branches; stop/load/delivery/retry state.',
 'volunteer_shift':'Shift capacity; signup, waitlist and cancellation.',
 'incident_room':'Reverse dependency trace; seen set; acknowledge/resolve.'}
NAVY, INK, MUTED, PALE = '#142c45', '#263c50', '#596f82', '#eff4f7'


def read(path):
    return json.loads(Path(path).read_text())


def reference(path):
    path = Path(path).resolve()
    return {'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def number(value, *, integer=False, positive=False):
    if type(value) not in ((int,) if integer else (int, float)) or not math.isfinite(value):
        raise ValueError('Expected a finite number of the declared type')
    if value < 0 or (positive and value <= 0):
        raise ValueError('Invalid negative/zero observation')
    return value


def vector(cell, field):
    return [row[field] for row in sorted(cell['trials'], key=lambda row: row['repeat'])]


def median(cell, field):
    return statistics.median(vector(cell, field))


def fmt(value):
    if value is None:
        return 'Not measured'
    if abs(value) >= 10000:
        return f'{value:,.0f}'
    if abs(value) >= 100:
        return f'{value:,.1f}'
    return f'{value:,.3f}'


def spread(values):
    return f'{fmt(statistics.median(values))}\n{fmt(min(values))}–{fmt(max(values))}'


def percent(numerator, denominator):
    return None if denominator == 0 else numerator / denominator


def pct(value):
    return 'N/A' if value is None else f'{100 * value:.1f}%'


def resolve_ref(value, root):
    path = Path(value['path'])
    path = path if path.is_absolute() else root / path
    if not path.is_file() or reference(path)['sha256'] != value['sha256']:
        raise ValueError('Required presentation input is missing or stale: ' + str(path))
    return path


def validate_document(data, root):
    """Validate small accepted metadata; do not scan primary archives/runtime trees."""
    if data.get('schema') != 'ttg-performance-report-v1' or data.get('status') != 'accepted_complete':
        raise ValueError('Complete accepted presentation input required')
    if data.get('timing_complete') is not True or data.get('timing_quiet') is not True:
        raise ValueError('Rendering is held until the timing window is complete and quiet')
    if set(data['modes']) != set(MODES) or len(data['modes']) != 3:
        raise ValueError('Exactly three declared policies required')
    if len(data['apps']) != 17 or len(set(data['apps'])) != 17:
        raise ValueError('The predeclared 17 applications must remain explicit')
    for value in data['evidence'].values():
        resolve_ref(value, root)
    resolve_ref(data['requirements'], root)
    fixtures = {f['case_id']: f for f in data['fixtures']}
    if len(fixtures) != len(data['fixtures']) or set(f['app'] for f in fixtures.values()) != set(data['apps']):
        raise ValueError('Duplicate fixture or missing fixed application')
    cells = {(c['case_id'], c['mode']): c for c in data['cells']}
    expected = {(key, mode) for key in fixtures for mode in MODES}
    if len(cells) != len(data['cells']) or set(cells) != expected:
        raise ValueError('Missing/extra/duplicate policy cells')
    for cell in cells.values():
        if cell['status'] in TERMINAL_OUTCOMES:
            if not cell.get('reason') or not cell.get('evidence'):
                raise ValueError('Terminal outcomes need reason and evidence; never zero-fill')
            if cell.get('trials'):
                raise ValueError('Correctness/failed/not-run records must not be passed off as primary timing trials')
            continue
        if cell['status'] != 'accepted' or len(cell['trials']) != 5:
            raise ValueError('Every accepted primary cell requires five measured workflows')
        if {r['repeat'] for r in cell['trials']} != set(range(5)):
            raise ValueError('Repeat IDs must be exactly 0–4')
        for row in cell['trials']:
            for field in ('http_response_ms', 'http_span_ms', 'db_protocol_sum_ms', 'db_protocol_union_ms'):
                number(row[field], positive=field.startswith('http_'))
            for field in ('data_sql', 'control_sql', 'business_http_requests'):
                number(row[field], integer=True, positive=field == 'business_http_requests')
            if row['db_protocol_union_ms'] > row['db_protocol_sum_ms'] + 0.00001:
                raise ValueError('SQL interval union exceeds summed intervals')
    pkeys=set()
    for cell in data.get('precision_cells', []):
        key=(cell['case_id'],cell['mode'])
        if key not in expected or key in pkeys:
            raise ValueError('Unknown/duplicate precision cell')
        pkeys.add(key)
        if cell['status'] != 'accepted':
            if cell['status'] not in TERMINAL_OUTCOMES or not cell.get('reason') or not cell.get('evidence'):
                raise ValueError('Terminal precision outcomes need an explicit reason and evidence')
            if cell.get('trials'):
                raise ValueError('A terminal precision outcome cannot invent diagnostic trials')
            continue
        if not cell['trials']:
            raise ValueError('An accepted diagnostic needs actual repetitions')
        if len({r['repeat'] for r in cell['trials']})!=len(cell['trials']):
            raise ValueError('Duplicate precision repeats')
        for row in cell['trials']:
            for name in ('prefetched_ids','demand_ids','prefetched_used_ids','promoted_ids','unused_ids'):
                number(row[name],integer=True)
            p,d,u=row['prefetched_ids'],row['demand_ids'],row['prefetched_used_ids']
            if u>min(p,d) or row['unused_ids'] != p-u:
                raise ValueError('Precision set arithmetic differs')
            if cell['mode']=='off' and p!=0:
                raise ValueError('Off must retain its actual zero-prefetch numerator')
            timely=row.get('timely_served_ids')
            if timely is not None and number(timely,integer=True)>d:
                raise ValueError('Timely service exceeds successful demand')
            filt=row.get('audited_filter_only_ids')
            lower=row.get('unnecessary_lower_bound')
            if filt is not None:
                number(filt,integer=True)
            if lower is not None:
                number(lower,integer=True)
                if not cell.get('necessity_audit'):
                    raise ValueError('Audited unnecessary-read count lacks scoped evidence')
                if row.get('filter_unused_disjoint') is True and filt is not None and lower!=row['unused_ids']+filt:
                    raise ValueError('Disjoint audited unnecessary count differs')
    if pkeys != expected:
        raise ValueError('Final precision inventory must cover every planned policy cell, including explicit resource outcomes')
    return fixtures,cells


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
        path=self.output/'ttg-performance-research.pdf'
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


def accepted(cell):
    return cell is not None and cell['status']=='accepted'


def outcome_label(cell):
    if cell is None:
        return 'Missing inventory'
    return {'resource_outcome':'Resource outcome','failed_isolation_gate':'Isolation gate failed',
            'correctness_only':'Correctness only','not_run':'Not run','not_run_after_first_failure':'Not run after failure'}.get(cell['status'],cell['status'])


def primary_small(data,fixtures):
    selected=[]
    for app in data['apps']:
        candidates=[f for f in fixtures.values() if f['app']==app and f['tier']=='small']
        if len(candidates)!=1:
            raise ValueError('Exactly one fixed small fixture per application required')
        selected.append(candidates[0])
    return selected


def precision_summary(cell):
    if cell is None or cell['status']!='accepted':
        return None
    result={}
    for field in ('prefetched_ids','demand_ids','prefetched_used_ids','promoted_ids','unused_ids'):
        result[field]=statistics.median([r[field] for r in cell['trials']])
    # Ratio of summed request-local counts across the declared diagnostic repeats.
    p=sum(r['prefetched_ids'] for r in cell['trials'])
    d=sum(r['demand_ids'] for r in cell['trials'])
    u=sum(r['prefetched_used_ids'] for r in cell['trials'])
    result.update(coverage=percent(u,d),usefulness=percent(u,p),n=len(cell['trials']))
    return result


def primary_tables(deck,small,cells):
    for start,end in ((0,9),(9,17)):
        f=deck.page('Primary HTTP: all fixed applications'+(' (1/2)' if start==0 else ' (2/2)'),
                    'Summed business-response wall, ms • median above min–max • all five fresh repeats retained')
        rows=[]
        for fixture in small[start:end]:
            group=[cells[fixture['case_id'],mode] for mode in MODES]
            off=median(group[0],'http_response_ms') if accepted(group[0]) else None
            values=[spread(vector(c,'http_response_ms')) if accepted(c) else outcome_label(c) for c in group]
            ratios='\n'.join(LABELS[m][0]+': '+f'{median(c,"http_response_ms")/off:.2f}×'
                             for m,c in zip(MODES[1:],group[1:]) if accepted(c) and off is not None)
            rows.append([NAMES[fixture['app']],*values,ratios or 'See outcome'])
        deck.table(f,['Application','Off','Aggressive','Conservative','Ratio to Off'],rows,
                   widths=[.20,.21,.21,.23,.15],size=13)
        deck.text(f,.06,.115,'Ratios use policy median / Off median. These are instrumented HTTP intervals, not setup or post-response drain.',13,color=MUTED)


def ratio_plot(deck,small,cells):
    f=deck.page('Five repeat dots reveal variation','Each dot = one measured response sum / that app’s Off median • diamonds = median ratio')
    ax=f.add_axes([.20,.16,.73,.60]);ys=[];labels=[]
    for i,fixture in enumerate(small):
        base=cells[fixture['case_id'],'off']
        if not accepted(base):continue
        baseline=median(base,'http_response_ms');ys.append(i);labels.append(NAMES[fixture['app']])
        for mode,offset in [('aggressive',-.15),('conservative',.15)]:
            cell=cells[fixture['case_id'],mode]
            if not accepted(cell):continue
            values=[v/baseline for v in vector(cell,'http_response_ms')];y=i+offset
            ax.plot([min(values),max(values)],[y,y],color=COLORS[mode],lw=1.5)
            ax.scatter(values,[y]*5,color=COLORS[mode],s=17,alpha=.65)
            ax.scatter([statistics.median(values)],[y],marker='D',s=28,color=COLORS[mode],label=LABELS[mode] if i==0 else None)
    ax.axvline(1,color=COLORS['off'],lw=1.2,ls='--');ax.set_xscale('log')
    ax.set_yticks(ys,labels,fontsize=12);ax.invert_yaxis();ax.set_xlabel('Response-wall ratio to Off; 1.0 is equal')
    ax.grid(axis='x',alpha=.18);ax.legend(frameon=False,loc='lower right',fontsize=12)


def sql_plot(deck,small,cells):
    f=deck.page('Data SQL per business HTTP request','Each point is one workflow ratio; control statements are reported separately')
    ax=f.add_axes([.20,.17,.72,.58])
    for i,fixture in enumerate(small):
        for mode,offset in zip(MODES,(-.22,0,.22)):
            cell=cells[fixture['case_id'],mode]
            if not accepted(cell):continue
            values=[r['data_sql']/r['business_http_requests'] for r in cell['trials']]
            y=i+offset;ax.plot([min(values),max(values)],[y,y],color=COLORS[mode])
            ax.scatter(values,[y]*5,color=COLORS[mode],s=13,alpha=.6)
            ax.scatter([statistics.median(values)],[y],color=COLORS[mode],marker='D',s=20,label=LABELS[mode] if i==0 else None)
    ax.set_yticks(range(len(small)),[NAMES[x['app']] for x in small],fontsize=12)
    ax.invert_yaxis();ax.set_xlabel('Data SQL / primary business HTTP requests');ax.grid(axis='x',alpha=.18)
    ax.legend(loc='lower right',frameon=False,fontsize=11)
    deck.text(f,.06,.105,'Full CSV also gives ratio of total SQL / total HTTP and control/all-role totals. A mean of per-request counts is a different statistic.',12,color=MUTED)


def sql_count_tables(deck,small,cells):
    for start,end in ((0,9),(9,17)):
        f=deck.page('Data and control SQL'+(' (1/2)' if start==0 else ' (2/2)'),
                    'Per-workflow medians over five repeats; each cell shows data / control, then all-role total')
        rows=[]
        for fixture in small[start:end]:
            values=[]
            for mode in MODES:
                cell=cells[fixture['case_id'],mode]
                if not accepted(cell):
                    values.append(outcome_label(cell))
                    continue
                total=statistics.median([r['data_sql']+r['control_sql'] for r in cell['trials']])
                values.append(f'{median(cell,"data_sql"):g} / {median(cell,"control_sql"):g}\nTotal {total:g}')
            rows.append([NAMES[fixture['app']],*values])
        deck.table(f,['Application','Off data / control','Aggressive data / control','Conservative data / control'],
                   rows,widths=[.22,.25,.26,.27],size=14)
        deck.text(f,.06,.105,'All roles and originating business requests are included. Complete repeat counts/ranges remain in the accepted export.',12,color=MUTED)


def scale_plot(deck,data,fixtures,cells):
    f=deck.page('Larger graphs: absolute costs and request work','All five repeats shown • connect only the same declared workflow and graph family')
    axes=f.subplots(2,2,gridspec_kw={'left':.08,'right':.95,'top':.74,'bottom':.16,'hspace':.60,'wspace':.28})
    for ax,app in zip(axes.flat,('jdrive','littlex','recipe_pantry','linked_list')):
        fs=sorted([x for x in fixtures.values() if x['app']==app],key=lambda x:x['scale_value'])
        for mode in MODES:
            families={}
            for fixture in fs:
                cell=cells[fixture['case_id'],mode]
                if not accepted(cell):continue
                x=fixture['scale_value'];values=vector(cell,'http_response_ms')
                ax.scatter([x]*5,values,color=COLORS[mode],s=16,alpha=.65)
                ax.errorbar([x],[statistics.median(values)],yerr=[[statistics.median(values)-min(values)],[max(values)-statistics.median(values)]],
                            color=COLORS[mode],marker='D',ms=4,capsize=3,label=LABELS[mode] if fixture==fs[0] else None)
                families.setdefault((fixture['scale_family'],fixture['workflow_id']),[]).append((x,statistics.median(values)))
            for observations in families.values():
                if len(observations)>1:
                    points=sorted(observations);ax.plot([v[0] for v in points],[v[1] for v in points],color=COLORS[mode],alpha=.55)
        ax.set_title(NAMES[app],fontsize=16);ax.set_xlabel(fs[0]['scale_unit'] if fs else 'Declared graph scale',fontsize=11)
        ax.set_ylabel('HTTP response sum, ms',fontsize=11);ax.grid(alpha=.15);ax.tick_params(labelsize=10)
        unmeasured=[x['label'] for x in fs if any(not accepted(cells[x['case_id'],m]) for m in MODES)]
        if unmeasured:
            ax.text(.03,.97,'Terminal outcome, not plotted: '+', '.join(unmeasured),transform=ax.transAxes,
                    fontsize=9,va='top',color=MUTED,wrap=True)
    deck.text(f,.06,.09,'A larger global LittleX population is not the same as a larger reachable feed. Source cutoff and prefetch budget remain explicit.',12,color=MUTED)


def precision_tables(deck,data,small):
    pcells={(c['case_id'],c['mode']):c for c in data.get('precision_cells',[])}
    sample_counts={len(c['trials']) for c in pcells.values() if c['status']=='accepted'}
    sample_note=(f'n = {next(iter(sample_counts))} independent precision workflow(s) per accepted cell'
                 if len(sample_counts)==1 else 'Independent precision repetitions; exact n retained per app/policy')
    for start,end in ((0,9),(9,17)):
        f=deck.page('Returned / demanded intersection'+(' (1/2)' if start==0 else ' (2/2)'),
                    sample_note+' • separate observer; not the primary n = 5 dataset',kind='Independent precision pass; sample count shown above')
        rows=[]
        for fixture in small[start:end]:
            stats={m:precision_summary(pcells.get((fixture['case_id'],m))) for m in MODES}
            def pair(field,ratio=False):
                return '\n'.join(('A ' if m=='aggressive' else 'C ')+(pct(stats[m][field]) if ratio else fmt(stats[m][field]))
                                 if stats[m] else ('A ' if m=='aggressive' else 'C ')+outcome_label(pcells.get((fixture['case_id'],m))) for m in MODES[1:])
            demands='/'.join(fmt(stats[m]['demand_ids']) if stats[m] else '—' for m in MODES)
            rows.append([NAMES[fixture['app']],demands,pair('coverage',True),pair('usefulness',True),pair('unused_ids')])
        deck.table(f,['Application','ALL-anchor D O/A/C','Overlap / D A/C','Overlap / P A/C','Unused IDs A/C'],rows,
                   widths=[.21,.23,.19,.20,.17],size=13)
        deck.text(f,.06,.108,'Operational Session demand, not business necessity. D varies by policy; intersection ignores timing. Full n1 count vectors retained.',12,color=MUTED)


def cpu_pages(deck,data):
    cpu=data.get('cpu_diagnostic')
    if not cpu:
        return
    for app in ('linked_list','recipe_pantry'):
        f=deck.page(NAMES[app]+': directly measured phase CPU',
                    'Separate n1 diagnostic per mode; two selected RPCs • all native and joint activation gates passed',
                    kind='Appendix • native-spawn-thread CPU only')
        rows=[]
        for mode in MODES:
            for r in sorted([x for x in cpu['rows'] if x['app']==app and x['mode']==mode],key=lambda x:x['ordinal']):
                phases=r['phases']
                interpreter=sum(x['exclusive_thread_CPU_ms'] for x in phases if x['name'].endswith('.plan_continuation'))
                sql=sum(x['exclusive_thread_CPU_ms'] for x in phases if '.compile_' in x['name'])
                wait=sum(x['inclusive_wall_ms'] for x in phases if x['name']=='native_prefetch_done.Event.wait')
                icalls=sum(x['calls'] for x in phases if x['name'].endswith('.plan_continuation'))
                scalls=sum(x['calls'] for x in phases if '.compile_' in x['name'])
                wcalls=sum(x['calls'] for x in phases if x['name']=='native_prefetch_done.Event.wait')
                def observed(value,calls):return fmt(value) if calls else '0 recorded calls'
                rows.append([LABELS[mode]+' / '+r['walker'],fmt(r['native_spawn_thread_CPU_ms']),
                             fmt(r['native_spawn_wall_ms']),observed(interpreter,icalls),observed(sql,scalls),observed(wait,wcalls)])
        deck.table(f,['Policy / RPC','Native thread CPU ms','Native span wall ms','Interpreter exclusive CPU','SQL builders exclusive CPU','Selected wait wall ms'],
                   rows,widths=[.25,.15,.15,.16,.16,.13],size=13,area=(.055,.28,.89,.48))
        deck.text(f,.065,.22,'Only direct exclusive CPU partitions are additive. Recursive inclusive phase values overlap and may exceed the outer span when summed.',15)
        deck.text(f,.065,.12,'Delegated planner/payload, event-loop and DB-server CPU are unmeasured. A lower Aggressive thread value is not total CPU saving; timer overhead is retained.',14,color=MUTED)


def node_precision_page(deck,data,small):
    f=deck.page('Node-only precision uses a different denominator',
                'Independent n1 pass • NodeAnchor/RootAnchor IDs only • operational demand still varies by policy',
                kind='Appendix • node-only versus all-anchor precision')
    pcells={(c['case_id'],c['mode']):c for c in data['precision_cells']}
    for start,end,area in [(0,9,(.055,.21,.435,.55)),(9,17,(.515,.21,.43,.55))]:
        rows=[]
        for fixture in small[start:end]:
            values=[]
            for mode in ('aggressive','conservative'):
                cell=pcells[fixture['case_id'],mode]
                if not accepted(cell):values.append(outcome_label(cell));continue
                trials=cell['trials'];d=sum(x['node_demand_ids'] for x in trials);p=sum(x['node_prefetched_ids'] for x in trials)
                overlap=sum(x['node_used_ids'] for x in trials)
                values.append(pct(percent(overlap,d))+' / '+pct(percent(overlap,p)))
            rows.append([NAMES[fixture['app']],*values])
        deck.table(f,['App','Agg. overlap/D /P','Cons. overlap/D /P'],rows,widths=[.38,.31,.31],area=area,size=11)
    deck.text(f,.065,.15,'The main precision table includes all anchor identities. This table excludes edges and retains roots. Neither is a minimum business-necessity oracle.',14)
    deck.text(f,.065,.085,'Promotion-backed service and return-before-demand-call subsets remain separate. Return callback timing is not an exact cache-insertion/readiness timestamp.',12,color=MUTED)


def build_deck(deck,data,fixtures,cells):
    small=primary_small(data,fixtures)
    measured=sum(len(c.get('trials',[])) for c in cells.values() if accepted(c))
    f=deck.page(data.get('title','TTG across 17 applications'),'Off / Aggressive / latest Conservative • real business workflows and declared graph scales')
    deck.card(f,.065,.43,.27,.30,'17 applications','Every fixed app remains visible, including zero activation and slower cases.',COLORS['off'])
    deck.card(f,.365,.43,.27,.30,'Five measured repeats',f'{measured} accepted measured workflows. 19 successful fixtures; 3 LL1000 terminal cells stay explicit.',COLORS['aggressive'])
    deck.card(f,.665,.43,.27,.30,'One accepted source','Shared latest standard-access runtime; actual GIL-off threads and identical per-fixture actions.',COLORS['conservative'])
    wins=[];successful=[]
    for fixture in fixtures.values():
        a=cells[fixture['case_id'],'off'];b=cells[fixture['case_id'],'conservative']
        if accepted(a) and accepted(b):
            successful.append(fixture)
            if median(b,'http_response_ms')<median(a,'http_response_ms'):
                wins.append((fixture,1-median(b,'http_response_ms')/median(a,'http_response_ms')))
    if len(wins)==1:
        fixture,gain=wins[0]
        message=f'Conservative HTTP median: {NAMES[fixture["app"]]} {fixture["label"]} improves {100*gain:.1f}%; the other {len(successful)-1} successful fixtures are slower than Off.'
    else:
        message=f'Conservative improves median HTTP in {len(wins)} of {len(successful)} successful fixtures; every result is retained.'
    deck.text(f,.065,.31,message,21,color=NAVY,weight='bold')
    deck.text(f,.065,.16,data['runtime']['identity'],15,color=MUTED)

    f=deck.page('JDrive: a real Folder ability and its region',
                'VisibleFolderTree.walk • frozen server.impl.jac:44–61 • source graph with internal Access/Visit dependencies',
                kind='Source-derived graph; accepted n5 caption')
    deck.card(f,.065,.40,.41,.35,'Folder node / walk ability',
        'A1: Access Contains → Folder [trashed == False]\nA1 → child id/name → depth/path output state\nA2: same Access → Visit children\nAppend current FolderTreeEntry',COLORS['conservative'])
    deck.card(f,.65,.55,.27,.20,'Visible child Folder','Predicate true → recursive Visit.\nSame typed read region continues.',COLORS['conservative'])
    deck.card(f,.65,.29,.27,.20,'Trashed child Folder','Predicate false → native query\nexcludes this branch.',COLORS['aggressive'])
    deck.arrow(f,(.48,.66),(.64,.66));deck.arrow(f,(.48,.51),(.64,.39))
    deck.text(f,.49,.73,'Contains',13,width=.14,color=MUTED)
    deck.text(f,.065,.28,'SQL discovery may reuse the typed predicate region; native depth/path bookkeeping and output execution remain native.',16,width=.52)
    jc=cells.get(('jdrive-depth5','conservative'));jo=cells.get(('jdrive-depth5','off'))
    if accepted(jc) and accepted(jo):
        deck.text(f,.065,.13,f'Accepted depth5: HTTP median {median(jc,"http_response_ms"):.3f} ms Conservative / {median(jo,"http_response_ms"):.3f} ms Off; data SQL {median(jc,"data_sql"):g} / {median(jo,"data_sql"):g}.',16,color=NAVY)

    f=deck.page('Jac graph with embedded ability dependencies','LittleX source example • typed Post and Follow paths; native response helper remains visible',kind='Source-derived diagram; activation separately bound')
    deck.card(f,.065,.47,.24,.27,'Root node / run','Access: Root → Profile\nVisit: enqueue Profile\nOrigin and actor binding',COLORS['off'])
    deck.card(f,.37,.43,.28,.35,'Profile / collect','Access + Visit:\nPost → Tweet\nFollow → Profile → Post → Tweet\nTwo ordered visit sites',COLORS['conservative'])
    deck.card(f,.72,.47,.22,.27,'Tweet / gather','here.to_view()\nRead payload fields\nAppend business response',COLORS['aggressive'])
    deck.arrow(f,(.312,.61),(.36,.61));deck.arrow(f,(.658,.61),(.71,.61))
    deck.text(f,.07,.30,'The region boundary follows supported Access/dispatch dependencies. It does not replace native ability execution.',18,width=.86)
    examples=data['mechanism'].get('examples',[])
    if examples:deck.text(f,.07,.20,examples[0]['explanation'],15,color=MUTED)
    if examples and examples[0].get('activation'):
        deck.text(f,.07,.115,examples[0]['activation'],13,color=NAVY)

    f=deck.page('One analysis for ordinary and condition-call Access','RecipePantry: actual object binding, short-circuit ownership and requirement reads',kind='Source-derived mechanism')
    deck.card(f,.065,.48,.27,.25,'Bind','meal = jobj(meal_id)\nLookupById Access\nActual native object/identity')
    deck.card(f,.365,.48,.27,.25,'Ownership','isinstance + jid membership\n[root-->] is real demand\nShort-circuit guard retained')
    deck.card(f,.665,.48,.27,.25,'Requirements','RecipeRef → Recipe\nNeeds → Requirement\nIngredientRef → Ingredient')
    deck.arrow(f,(.338,.61),(.355,.61));deck.arrow(f,(.638,.61),(.655,.61))
    deck.text(f,.07,.34,'Native branch/body hooks resume with actual local bindings after unresolved effects. Planning does not execute arbitrary user predicates.',19,width=.86)
    deck.text(f,.07,.19,data['runtime']['contract'],16,color=MUTED)

    f=deck.page('Three policies on the same declared contract','Always is admission; conservative describes which future demand is eligible',kind='Configuration and source provenance')
    deck.table(f,['Mode','Configuration','Operational distinction'],data['runtime']['policies'],
               widths=[.18,.32,.50],size=16,area=(.06,.32,.88,.44))
    deck.text(f,.065,.22,data['runtime']['flags'],17)
    deck.text(f,.065,.12,'Unknown effects, unsupported control or failed proof remain native boundaries. A partial prefix does not imply whole-app support.',15,color=MUTED)

    f=deck.page('The same business workflow under every policy','Fresh fixture and authenticated actor • identical ordered requests • independent expected results')
    for i,(title,body) in enumerate([('Setup','Create fresh DB; import exact graph; register actors; excluded state checks.'),
                                    ('Measured requests','Each RPC has a fresh Session. Keep reads, mutations and negative paths.'),
                                    ('Acceptance','Response/state oracle; restart; exact physical graph and owned cleanup.')]):
        deck.card(f,.07+i*.305,.45,.255,.29,title,body,COLORS[MODES[i]])
        if i<2:deck.arrow(f,(.33+i*.305,.60),(.363+i*.305,.60))
    deck.text(f,.07,.30,data['runtime']['profile_reset'],17)
    deck.text(f,.07,.19,'Responses finish before explicit drain. Setup, steady checks, restart and drain are excluded or separately labeled.',16,color=MUTED)

    for start,end in ((0,9),(9,17)):
        f=deck.page('Why these fixed applications'+(' (1/2)' if start==0 else ' (2/2)'),
                    'Actual domain sources and complete business scenarios; no favorable-case replacement',kind='Source and workload coverage')
        deck.table(f,['Application','Access / dependency / business traits'],
                   [[NAMES[a],TRAITS[a]] for a in data['apps'][start:end]],widths=[.23,.77],size=14)
        deck.text(f,.06,.10,'Seen-set traversal, SLA writes, routing, early return and unknown helper effects remain useful partial/unsupported controls.',12,color=MUTED)

    f=deck.page('Graph size and distribution are explicit inputs','Initial domain graph dimensions; reachable requests and scale family accompany each point',kind='Fixture provenance')
    scale_rows=[]
    for fixture in fixtures.values():
        if fixture['app'] in ('jdrive','littlex','recipe_pantry','linked_list'):
            scale_rows.append([NAMES[fixture['app']]+' / '+fixture['label'],str(fixture['dimensions']),fixture['distribution']])
    deck.table(f,['Fixture','Initial dimensions','Distribution / reachability'],scale_rows,widths=[.26,.34,.40],size=12)
    deck.text(f,.06,.10,'No larger-graph label is inferred from repeated sessions. Distinct workflow families are not connected into a scale curve.',12,color=MUTED)

    f=deck.page('Experimental regime and provenance','Versioned fixture, actions, runtime and instrumentation define a comparable cell',kind='Accepted protocol')
    deck.bullets(f,[('Native/thread configuration',data['runtime']['gil']),
                    ('Warmup, cache and statistics',data['runtime']['warmup']+' '+data['runtime']['cache_regime']+' '+data['runtime']['statistics']),
                    ('Repetitions and session lifetime',data['runtime']['sessions']+' Five fresh measured workflows; descriptive dots, medians and ranges. No n=5 p95 claim.')],gap=.19)

    f=deck.page('Read the clocks as different measurements','DB protocol intervals and HTTP response wall are not an additive CPU decomposition',kind='Measurement definitions')
    deck.card(f,.065,.46,.27,.29,'HTTP response wall','Request start → complete body read. Sum and workflow span reported; explicit post-response drain separate.',COLORS['off'])
    deck.card(f,.365,.46,.27,.29,'DB protocol wall','Actual sendall → ReadyForQuery. Count all roles and controls; sum, union and overlap separately.',COLORS['aggressive'])
    deck.card(f,.665,.46,.27,.29,'Precision pass','Session demand and prefetch-return observations. Extra wrappers run separately from primary timing.',COLORS['conservative'])
    deck.text(f,.065,.31,'A background statement remains attributed to its originating RPC when it completes late. Source timing boundaries remain unchanged.',18)
    deck.text(f,.065,.16,'HTTP minus DB is not CPU time. An executor label alone is not evidence of SQL overlap.',17,color=MUTED)

    primary_tables(deck,small,cells)
    ratio_plot(deck,small,cells)
    sql_plot(deck,small,cells)
    sql_count_tables(deck,small,cells)
    scale_plot(deck,data,fixtures,cells)

    f=deck.page('Scale validity and terminal outcomes','Bounds and concurrency/isolation gates remain distinct from native business values',kind='Accepted scale metadata')
    resource=[(fixtures[c['case_id']],c) for c in cells.values() if c['status'] in TERMINAL_OUTCOMES]
    rows=[[NAMES[x['app']]+' / '+x['label'],x['budget_note']] for x in fixtures.values()
          if x['app'] in ('jdrive','littlex','recipe_pantry','linked_list') and x['tier']=='larger']
    if resource:rows += [[x['label']+' / '+c['mode'],outcome_label(c)+': '+c['reason']] for x,c in resource]
    if not rows:rows=[['Accepted scales','See complete fixture parameter manifest and recorded resource outcomes.']]
    deck.table(f,['Fixture / outcome','Bound and interpretation'],rows,widths=[.30,.70],size=14)
    deck.text(f,.06,.105,'LinkedList visited is total activations, never automatically SQL depth. A valid 2,048-ID cap is disclosed on larger graphs.',12,color=MUTED)

    f=deck.page('Operational coverage and promotion-backed service','Independent precision trace; n = 1 per successful cell, separate from primary n = 5',kind='Precision definitions; sample counts are dataset-specific')
    deck.card(f,.065,.44,.27,.30,'Coverage','|P ∩ D| / |D|\nForeground demand returned by prefetch.\nD includes roots and memory hits.',COLORS['off'])
    deck.card(f,.365,.44,.27,.30,'Returned-demand fraction','|P ∩ D| / |P|\nTiming-agnostic intersection.\nAn Access need not Visit.',COLORS['conservative'])
    deck.card(f,.665,.44,.27,.30,'Promotion-backed service','Actual raw promotion in a successful demand call. Return-before-call subset is separate; not exact readiness.',COLORS['aggressive'])
    deck.text(f,.065,.31,'P = unique returned payload IDs; D = successful foreground Session demand, excluding planning. D is policy-dependent; this is not business necessity.',17)
    deck.text(f,.065,.16,'Repeated deliveries, late returns and unused IDs remain absolute counts. This is not a PostgreSQL cache-hit metric.',16,color=MUTED)
    precision_tables(deck,data,small)

    f=deck.page('Unnecessary reads need an actual necessity audit','Unused payload and excluded-query candidates are different measured classes',kind='Precision / source-validated necessity audit')
    items=data['findings'].get('unnecessary_audit',[])
    if items:
        deck.bullets(f,[(x['title'],x['observation']+' '+x['scope']) for x in items[:3]],gap=.19)
    else:
        deck.bullets(f,[('Unused is directly observable','A returned ID outside actual foreground demand is an observed unused payload.'),
                        ('Filtered candidates need source validation','Confirm the exact explicit predicate and graph state; prove disjointness before adding candidate counts.'),
                        ('ID-only access is still demand','The ownership helper reads every root-neighbor ID. Projection can reduce bytes without relabeling those nodes as waste.')],gap=.19)
    deck.text(f,.06,.11,'Audited classes establish lower bounds. Zero confirmed is not complete proof; unmeasured remains null.',13,color=MUTED)

    f=deck.page('Measured slow paths and query work','Actual fingerprints or accepted matched plans explain selected costs; interpretation stays source-bound',kind='Separate attribution / matched diagnostic')
    findings=data['findings'].get('bottlenecks',[])
    if findings:
        qualified=[]
        for x in findings[:3]:
            walker='Traverse' if 'Traverse' in x['title'] else 'Sum' if 'Sum' in x['title'] else None
            measured=[r for r in data.get('cpu_diagnostic',{}).get('rows',[])
                      if r['app']=='linked_list' and r['mode']=='conservative' and r['walker']==walker]
            if measured:
                phase=next(p for p in measured[0]['phases'] if p['name'].endswith('.plan_continuation'))
                scope=(f'Separate n1 native-spawn-thread diagnostic: continuation planning exclusive CPU '
                       f'{phase["exclusive_thread_CPU_ms"]:.3f} ms, {phase["calls"]} calls. See appendix p31; delegated CPU unmeasured.')
            else:
                scope='Cause unmeasured: this request was not CPU-profiled. Primary HTTP/DB intervals do not identify CPU cost.'
            qualified.append((x['title'],x['observation']+' '+scope))
        deck.bullets(f,qualified,gap=.19)
    else:
        ranked=[]
        for fixture in small:
            off=cells[fixture['case_id'],'off'];cons=cells[fixture['case_id'],'conservative']
            if accepted(off) and accepted(cons):ranked.append((median(cons,'http_response_ms')/median(off,'http_response_ms'),fixture))
        ranked.sort(key=lambda x:x[0],reverse=True)
        deck.bullets(f,[(NAMES[x['app']]+': observed response ratio',f'Conservative / Off median = {v:.2f}×. Complete vectors and per-RPC SQL counts are retained; this primary observation is not a server-plan or CPU decomposition.') for v,x in ranked[:3]],gap=.19)

    f=deck.page('Scheduling, overlap and waits','Actual thread/backend and interval observations take precedence over an async label',kind='Accepted concurrency attribution')
    observations=data['findings'].get('concurrency',[])
    if observations:deck.bullets(f,[(x['title'],x['observation']+' '+x['scope']) for x in observations[:3]],gap=.19)
    else:
        deck.bullets(f,[('Thread execution','Use joined actual server/thread/backend records and GIL-off boundary assertions.'),
                        ('SQL overlap','Summed DB intervals and interval union are distinct. Overlap is measured, not inferred from a policy flag.'),
                        ('Waiting and critical path','A retained wait/readiness timer has its source boundary. Unmeasured parent IPC or CPU is not reconstructed from residual wall.')],gap=.19)

    f=deck.page('Correctness and persistent business state','Every policy uses the same fixture, actions and independent expected answers',kind='Accepted native / business / physical evidence')
    checks=data['correctness']['summaries']
    deck.bullets(f,[(x['title'],x['observation']) for x in checks[:3]],gap=.19)
    deck.text(f,.06,.11,'Negative paths are actual native dispatches; exact unchanged persisted state and typed/root graph links are verified.',13,color=MUTED)

    f=deck.page('Instrumentation and calibration scope','Primary timing and precision diagnostics have explicitly different capture regimes',kind='Instrumentation evidence')
    deck.bullets(f,[('Primary observer',data['runtime']['instrumentation']),
                    ('Calibration or qualification',data['runtime']['calibration']),
                    ('Evidence separation','Primary n=5 latency, separate precision, matched SQL/CPU diagnostics and proposed changes retain distinct source and capture identities.')],gap=.19)

    f=deck.page('Next steps follow the measured limitation','Current behavior, measured evidence and untested proposals are labeled separately',kind='Roadmap')
    deck.bullets(f,[
        ('Repeated continuation planning — proposed reduction',
         'LLsmoke records 67 planning calls per selected Traverse/Sum. Reuse analysis and regions while preserving guards, native order and cancellation.'),
        ('Shared Session barrier before reader clone — unresolved isolation',
         'Separate barrier/close lifetime before retesting the preserved LL1000 isolation gate. This study makes no runtime repair or validator relaxation.'),
        ('Admission — proposed; Always used in this comparison',
         'Cold/planning cost, control SQL, dispatch/wait and saved request work belong in profitability. The learned cost model was not exercised.'),
        ('Prepared plans and compatible Access fusion — roadmap',
         'Existing binding is not DB prepared-plan reuse. Evaluate query reuse and fusion separately with full business and persistence oracles.')],gap=.15)

    f=deck.page('Exact source and inclusion provenance','All runtime, fixtures, policies and capture stages are versioned',kind='Evidence inventory')
    deck.bullets(f,[(x['title'],x['observation']) for x in data['provenance']['summaries'][:3]],gap=.19)
    deck.text(f,.06,.105,'Historical publications provide context. Their numbers are not pooled into these new cells.',13,color=MUTED)

    f=deck.page('Reproduce and inspect the complete evidence','One final PDF with editable source, accepted vectors, portable mapping and original seals',kind='Reproduction')
    rows=[[x['title'],x['command']] for x in data['reproduction']['commands'][:4]]
    deck.table(f,['Action','Command / portable path'],rows,widths=[.25,.75],size=14,area=(.06,.26,.88,.48))
    deck.text(f,.065,.18,data['reproduction']['scope'],15,color=MUTED)
    cpu_pages(deck,data)
    node_precision_page(deck,data,small)
    return small


def write_tables(output,data,cells):
    """Export displayed arithmetic with complete vectors retained in figure inputs."""
    with (output/'primary-summary.csv').open('w',newline='') as stream:
        fields=['case_id','mode','status','n','HTTP_median_ms','HTTP_min_ms','HTTP_max_ms',
                'HTTP_span_median_ms','DB_sum_median_ms','DB_union_median_ms',
                'data_SQL_median','control_SQL_median','all_SQL_median',
                'data_SQL_per_HTTP_median','ratio_total_data_SQL_to_total_HTTP']
        fields.insert(-1,'data_SQL_per_HTTP_mean_of_trial_ratios')
        writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader()
        for key,cell in cells.items():
            row=dict(case_id=key[0],mode=key[1],status=cell['status'],n=len(cell.get('trials',[])))
            if accepted(cell):
                values=vector(cell,'http_response_ms')
                row.update(HTTP_median_ms=statistics.median(values),HTTP_min_ms=min(values),HTTP_max_ms=max(values),
                    HTTP_span_median_ms=median(cell,'http_span_ms'),DB_sum_median_ms=median(cell,'db_protocol_sum_ms'),
                    DB_union_median_ms=median(cell,'db_protocol_union_ms'),data_SQL_median=median(cell,'data_sql'),
                    control_SQL_median=median(cell,'control_sql'),
                    all_SQL_median=statistics.median([r['data_sql']+r['control_sql'] for r in cell['trials']]),
                    data_SQL_per_HTTP_median=statistics.median([r['data_sql']/r['business_http_requests'] for r in cell['trials']]),
                    data_SQL_per_HTTP_mean_of_trial_ratios=statistics.mean([r['data_sql']/r['business_http_requests'] for r in cell['trials']]),
                    ratio_total_data_SQL_to_total_HTTP=sum(vector(cell,'data_sql'))/sum(vector(cell,'business_http_requests')))
            writer.writerow(row)
    (output/'precision-counts.json').write_text(json.dumps(data.get('precision_cells',[]),indent=2)+'\n')


def render(data_path,output,previews=False):
    data_path=Path(data_path).resolve();output=Path(output).resolve()
    data=read(data_path);fixtures,cells=validate_document(data,data_path.parent)
    output.mkdir(parents=True,exist_ok=False)
    inputs=dict(schema='ttg-report-figure-inputs-v1',passed=True,source=reference(Path(__file__)),
                accepted_presentation_input=reference(data_path),data=data,
                transformations=['ms supplied by accepted export; no raw reaggregation',
                    'n5 median/min/max and repeat dots','ratio of medians to Off',
                    'per-trial data SQL/HTTP and separately ratio of totals',
                    'precision coverage/usefulness from declared summed local counts'])
    (output/'figure-inputs.json').write_text(json.dumps(inputs,indent=2)+'\n')
    deck=Deck(output,data,previews);build_deck(deck,data,fixtures,cells);pdf=deck.save()
    write_tables(output,data,cells)
    (output/'layout-checks.json').write_text(json.dumps(dict(passed=True,pages=deck.checks),indent=2)+'\n')
    manifest=dict(passed=True,stage='Rendered; main visual and independent numeric review required',
                  language='English',pages=len(deck.pages),source=reference(Path(__file__)),
                  environment=dict(python=sys.version,python_executable=sys.executable,matplotlib=deck.matplotlib_version),
                  input=reference(data_path),titles=[f._title for f in deck.pages],
                  outputs=[reference(p) for p in sorted(output.iterdir()) if p.is_file()])
    (output/'report-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps(dict(pdf=reference(pdf),pages=len(deck.pages),manifest=reference(output/'report-manifest.json'))))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--previews',action='store_true')
    args=parser.parse_args();render(args.data,args.output,args.previews)
