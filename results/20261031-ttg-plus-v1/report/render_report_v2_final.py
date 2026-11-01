"""Presentation only: white/sans English mechanism and accepted nine-cell data."""
import argparse
import hashlib
import json
import os
from pathlib import Path

LABELS={'off':'Off','prefusion':'Repaired pre-fusion / process','ttg_plus':'TTG+ / process'}
TITLES={'linked_list32':'LinkedList · 32 nodes','linked_list1000':'LinkedList · 1,000 nodes','littlex':'LittleX · original workflow'}


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def ref(path):return dict(path=str(Path(path).resolve()),sha256=sha(path))
def checked(value):
    path=Path(value['path'])
    if sha(path)!=value['sha256']:raise ValueError('Report input hash mismatch: '+str(path))
    return path


def render(source,out,attribution=None,classification=None,linkedlist=None,diagnostics=None):
    source=source.resolve();out=out.resolve()
    seal=json.loads((source/'artifacts.json').read_text())
    if seal.get('passed') is not True:raise ValueError('Passed numerical export required')
    for value in seal['outputs']:checked(value)
    data=json.loads((source/'results.json').read_text())
    if data.get('passed') is not True or data['sample_counts']!=dict(all=36,excluded_warmups=9,measured=27,cells=9,n_per_cell=3):
        raise ValueError('Accepted exact36 TTG+ export required')
    if len(data['rows'])!=9 or any(r['n']!=3 for r in data['rows']):raise ValueError('All nine n3 cells required')
    plan=json.loads(checked(data['plan']).read_text());runtime=json.loads(checked(plan['runtime']).read_text())
    closure=json.loads(checked(data['sources']).read_text())
    for name,digest in closure['files'].items():
        if sha(name)!=digest:raise ValueError('Frozen numeric source changed: '+name)
    supplemental=None
    if attribution:
        supplemental=json.loads(attribution.read_text())
        if not supplemental['passed']:raise ValueError('Passed attribution required')
        checked(supplemental['source']);checked(supplemental['attribution'])
    classes=json.loads(classification.read_text()) if classification else None
    eligibility=json.loads(linkedlist.read_text()) if linkedlist else None
    if classes:
        if not classes['passed']:raise ValueError('Passed independent classification required')
        checked(classes['classification_source'])
        for row in classes['rows']:
            if row['n']!=3:raise ValueError('Classification must retain n3')
            for value in row['sample_audits']:checked(value)
    if eligibility:
        if not eligibility['passed']:raise ValueError('Passed LinkedList evidence required')
        checked(eligibility['source']);checked(eligibility['independent_raw_audit'])
        for value in eligibility['inputs']:checked(value)
    diagnostic=json.loads(diagnostics.read_text()) if diagnostics else None
    if diagnostic:
        if not diagnostic['passed'] or diagnostic['primary_measurement'] is not False or len(diagnostic['plans'])!=10:
            raise ValueError('Accepted separate ten-plan diagnostic required')
        for value in diagnostic['accepted_recaptures']:checked(value)
        for key in ('selection','source_binding','summarizer'):checked(diagnostic[key])
        for diagnostic_plan in diagnostic['plans']:
            checked(diagnostic_plan['capture'])
            if diagnostic_plan['context'][0][3]!='serializable':raise ValueError('Diagnostic isolation changed')
    out.mkdir(parents=True,exist_ok=False);os.environ.setdefault('MPLCONFIGDIR',str(out/'matplotlib-cache'))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_pdf import PdfPages
    from matplotlib.patches import FancyArrowPatch,FancyBboxPatch,Circle
    plt.rcParams.update({'font.family':'DejaVu Sans','figure.facecolor':'white','savefig.facecolor':'white',
        'text.color':'#17212d','axes.edgecolor':'#bac3cc'})
    inputs=dict(export=ref(source/'results.json'),plan=data['plan'],runtime=plan['runtime'],
        rows=data['rows'],ratios=data['ratios'],sanity=data['LinkedList_total_SQL_sanity'],
        conversion='Nanoseconds/1e6 to milliseconds; statistics copied from accepted export',SQL_examples=[])
    if attribution:inputs['supplemental_attribution']=ref(attribution)
    if classification:inputs['independent_SQL_classification']=ref(classification)
    if linkedlist:inputs['LinkedList_eligibility']=ref(linkedlist)
    if diagnostics:
        inputs['matched_diagnostic']=ref(diagnostics)
        inputs['diagnostic_comparisons']=diagnostic['comparisons']
        inputs['diagnostic_lifecycle']=ref(diagnostics.parent/'stopped-proof-v1.json')
    def mechanism_source(relative,anchor):
        path=Path(runtime['root'])/relative
        if sha(path)!=runtime['files'][relative]:raise ValueError('Mechanism source differs from tested runtime')
        text=path.read_text();position=text.index(anchor)
        return dict(**ref(path),line=text[:position].count('\n')+1,anchor=anchor)
    inputs['mechanism_sources']={
        'certificate':mechanism_source('jac/jaclang/runtime/ttg_fusion.jac','def certify_fused_region('),
        'recursive_SQL':mechanism_source('jac/jaclang/runtime/ttg_fusion_sql.jac','def compile_fused_region('),
        'ordered_cache':mechanism_source('jac/jaclang/runtime/ttg_fusion.jac','if not cache_ttg_paths(mem, staged)'),
    }
    app_root=Path(plan['app_snapshot']['path']).parent
    inputs['mechanism_sources']['native_LinkedList']=ref(app_root/'originals/linked_list/main.jac')
    inputs['mechanism_sources']['native_LittleX']=ref(app_root/'originals/littlex/server.jac')
    pages=0;report=['# TTG+: fused traversal SQL','',
        'Three workloads × three configurations × three measured fresh workflows, with nine excluded warmups.',
        'Primary: actual PgWire send-to-ReadyForQuery protocol completion wall; sum and interval union reported separately.',
        'SQL counts include all real foreground/background data, path and transaction-control dispatches.',
        'Runtime '+runtime['commit']+'; seed42; process workers1; prefetch_limit2048; common abstract-step budget32768.','']
    def page(title,subtitle=''):
        fig=plt.figure(figsize=(16,9));fig.text(.055,.91,title,size=29,weight='bold')
        if subtitle:fig.text(.055,.85,subtitle,size=15,color='#486077')
        return fig
    def save(pdf,fig):
        nonlocal pages
        pages+=1;regime=getattr(fig,'_ttg_regime','seed42 | primary n=3 fresh workflows')
        fig.text(.055,.035,'TTG+ | '+runtime['commit'][:10]+' | '+regime,size=10)
        fig.text(.95,.035,str(pages),ha='right',size=10)
        pdf.savefig(fig);fig.savefig(out/f'slide-{pages:02d}.png',dpi=110);plt.close(fig)
    def box(ax,x,y,w,h,text,color='#edf4fa',size=17):
        ax.add_patch(FancyBboxPatch((x,y),w,h,boxstyle='round,pad=0.012',facecolor=color,edgecolor='#9bb0c2'))
        ax.text(x+w/2,y+h/2,text,ha='center',va='center',size=size)
    def arrow(ax,x1,y1,x2,y2):ax.add_patch(FancyArrowPatch((x1,y1),(x2,y2),arrowstyle='-|>',mutation_scale=18,color='#477398',lw=2))
    with PdfPages(out/'ttg-plus-performance.pdf',metadata={'Title':'TTG+ — fused traversal SQL and measured DB calls','Author':'TTG research'}) as pdf:
        fig=page('TTG+','From native traversal continuations to fused SQL and ordered cache entries')
        for y,text in [(.69,'LinkedList32 · LinkedList1000 · original LittleX'),(.57,'Off · repaired pre-fusion process · TTG+ process'),
            (.43,'36 fresh workflow trials: 9 excluded warmups + 27 measured'),(.31,'Actual DB protocol time, total SQL, native correctness and process/backend intervals')]:
            fig.text(.07,y,text,size=24 if y>.5 else 21)
        save(pdf,fig)
        fig=page('The problem: native traversal crosses DB boundaries','The walker preserves application order; each demanded next step can require path and payload access.')
        code='walker Traverse {\n  has visited: int = 0;\n  can visit_item with Item entry {\n    self.visited += 1;\n    report here.value;\n    if self.visited >= 10000 { disengage; }\n    visit [->:Next:->];\n  }\n}'
        fig.text(.065,.68,code,size=18,family='DejaVu Sans Mono',va='top',linespacing=1.45)
        ax=fig.add_axes([.59,.35,.35,.32]);ax.set(xlim=(0,1),ylim=(0,1));ax.axis('off')
        for i in range(4):
            x=.1+i*.25;ax.add_patch(Circle((x,.6),.075,color='#e2eef8',ec='#477398'));ax.text(x,.6,str(i),ha='center',va='center',size=19)
            if i<3:arrow(ax,x+.08,.6,x+.17,.6)
        ax.text(.5,.27,'Item —Next→ Item —Next→ …',ha='center',size=17)
        fig.text(.59,.25,'Ordered reports and visited=N remain native correctness checks.',size=16,wrap=True)
        save(pdf,fig)
        fig=page('Mechanism: snapshot → certified region → native cache','Same repaired runtime; the explicit ttg_fused_sql switch selects the fused branch.')
        ax=fig.add_axes([.06,.18,.88,.58]);ax.set(xlim=(0,1),ylim=(0,1));ax.axis('off')
        labels=['Hook snapshot\nmaterialized state','Program position\nand guard transitions','Certified SQL\nregion','Ordered path cache\n+ batched payload']
        for i,label in enumerate(labels):
            x=.015+i*.25;box(ax,x,.44,.205,.30,label,size=17)
            if i<3:arrow(ax,x+.215,.59,x+.238,.59)
        ax.text(.5,.20,'Native execution consumes the cached path in its original order.\nUnsupported or unsafe tails retain their recorded fallback reason.',ha='center',size=19,linespacing=1.7)
        save(pdf,fig)
        fig=page('Why is a second visit guaranteed?','The analyzer supplies a conditional control-flow certificate; SQL checks the actual graph facts.')
        fig.text(.065,.745,'Same LinkedList, at the first visit hook',size=20,weight='bold')
        certificate=('origin = A : Item\nability/event = Traverse.visit_item / visit\nscalar snapshot: visited = 1\ncutoff: visited < 10000\npending FIFO = []\none known Item-entry handler\nrule: here --Next--> Item\nmax_origins encodes cutoff + budgets')
        fig.text(.065,.69,certificate,size=16,family='DejaVu Sans Mono',va='top',linespacing=1.55)
        ax=fig.add_axes([.60,.55,.33,.17]);ax.set(xlim=(0,1),ylim=(0,1));ax.axis('off')
        for i,label in enumerate(('A','B','C','D')):
            x=.1+i*.25;ax.add_patch(Circle((x,.55),.075,color='#e2eef8',ec='#477398'));ax.text(x,.55,label,ha='center',va='center',size=18)
            if i<3:arrow(ax,x+.08,.55,x+.17,.55)
        fig.text(.60,.535,'Illustrative four-node instance; measured sizes are 32 and 1,000.',size=12)
        fig.text(.60,.735,'Analyzer proof',size=20,weight='bold')
        fig.text(.60,.49,'After visit(A) returns one Item,\nFIFO dispatch enters that same ability at B.\nAt depth d, visited = 1 + d; the certified\nbound stays before disengage. SQL consumes\nthat bound, without interpreting Jac code.',size=17,va='top',linespacing=1.65)
        fig.text(.065,.235,'The code certificate does not assert that an edge exists. SQL must observe exactly one successor',size=18,weight='bold')
        fig.text(.065,.185,'of the exact certified runtime type/module before recursing. Zero or multiple successors stop linear expansion;',size=17)
        fig.text(.065,.135,'a nonempty pending FIFO also prevents this linear certificate. Native execution still handles the actual path.',size=17)
        save(pdf,fig)
        fig=page('Graph evidence in SQL → ordered native cache','Simplified from the final SQL AST contract; native edge/type/ACL/order predicates and bound parameters are abbreviated.')
        sql=('WITH RECURSIVE walk(origin_id, depth) AS (\n  VALUES (:origin, 0)\n  UNION ALL\n  SELECT m.target_id, w.depth + 1\n  FROM walk w, LATERAL native_path(w.origin_id) m\n  WHERE m.arity = 1\n    AND (m.arch_type, m.arch_module) = (:type, :module)\n    AND w.depth < :max_origins - 1\n)\nSELECT w.origin_id, w.depth, p.target_id, p.ord, p.arity\nFROM walk w LEFT JOIN LATERAL native_path(w.origin_id) p\n  ON TRUE\nORDER BY w.depth, p.ord;')
        fig.text(.06,.765,sql,size=13.5,family='DejaVu Sans Mono',va='top',linespacing=1.55)
        fig.text(.66,.76,'Per-origin ordered path cache',size=19,weight='bold')
        fig.text(.66,.70,'(A, Next) → [(B, edgeAB)]\n(B, Next) → [(C, edgeBC)]\n(C, Next) → [(D, edgeCD)]\n(D, Next) → []',size=15.5,family='DejaVu Sans Mono',va='top',linespacing=1.7)
        fig.text(.66,.485,'The empty terminal result is cached too.\nNative visit consumes its own path order.\nPayload IDs are merged for process loading.\nSQL discovers paths; the walker still runs.',size=16,va='top',linespacing=1.55)
        fig.text(.06,.25,'LittleX: two proven visits in the current collect ability',size=19,weight='bold')
        snippet=('collect(Profile):  visit Post → Tweet;\n                   visit Follow → Profile → Post → Tweet;\ngather(Tweet):     self.feed.append(here.to_view());')
        fig.text(.065,.205,snippet,size=14.5,family='DejaVu Sans Mono',va='top',linespacing=1.5)
        fig.text(.65,.23,'Both current-ability path rules can be batched.\nQueued gather runs later; to_view is a barrier\nfor proving further ability effects.',size=14.5,va='top',linespacing=1.65)
        save(pdf,fig)
        for case in ('linked_list32','linked_list1000','littlex'):
            rows=[r for r in data['rows'] if r['case_id']==case]
            fig=page(TITLES[case]+': DB time and total SQL','Median [minimum–maximum] across three independent measured fresh workflows')
            table=[]
            report+=['## '+TITLES[case],'','| Configuration | DB sum ms | DB union ms | SQL total/data/control/other |','|---|---:|---:|---:|']
            for row in rows:
                def time(key):
                    v=row[key];return f"{v['median']/1e6:.3f} [{v['min']/1e6:.3f}–{v['max']/1e6:.3f}]"
                counts='/'.join(f"{row[k]['median']:g}" for k in ('sql_dispatches','sql_data','sql_control','sql_other'))
                values=[LABELS[row['config_id']],time('protocol_sum_ns'),time('protocol_union_ns'),counts]
                table.append(values);report.append('| '+' | '.join(values)+' |')
            ax=fig.add_axes([.055,.40,.89,.32]);ax.axis('off')
            t=ax.table(cellText=table,colLabels=['Configuration','DB sum ms','DB union ms','Total/data/control/other SQL'],
                cellLoc='center',colWidths=[.27,.25,.25,.23],bbox=[0,0,1,1])
            t.auto_set_font_size(False);t.set_fontsize(14)
            for (r,c),cell in t.get_celld().items():
                cell.set_edgecolor('#d4dde5')
                if r==0:cell.set_facecolor('#e9f1f8');cell.set_text_props(weight='bold')
            fig.text(.065,.27,'Primary scope: business workflow. Setup, authentication, import, steady reads and verification are retained separately.',size=14)
            fig.text(.065,.19,'Sum adds all foreground/background DB calls. Union merges their actual protocol intervals.',size=16)
            save(pdf,fig);report.append('')
        fig=page('LinkedList: native Traverse counts and all-role SQL','One actual Traverse request per fresh workflow; full workflow also includes Sum and four Find operations.')
        values=[]
        for row in data['rows']:
            if 'Traverse' not in row:continue
            t=row['Traverse'];v=t['sql_dispatches']
            values.append([TITLES[row['case_id']],LABELS[row['config_id']],str(t['native_visited']),
                f"{v['median']:g} [{v['min']:g}–{v['max']:g}]",f"{t['sql_data']['median']:g}",f"{t['sql_control']['median']:g}"])
        ax=fig.add_axes([.055,.29,.89,.47]);ax.axis('off')
        t=ax.table(cellText=values,colLabels=['Workload','Configuration','Visited','Total SQL [range]','Data SQL','Control SQL'],
            colWidths=[.20,.28,.10,.18,.12,.12],cellLoc='center',bbox=[0,0,1,1]);t.auto_set_font_size(False);t.set_fontsize(13)
        for (r,c),cell in t.get_celld().items():
            cell.set_edgecolor('#d4dde5')
            if r==0:cell.set_facecolor('#e9f1f8');cell.set_text_props(weight='bold')
        fig.text(.06,.18,'Total counts retain path, payload and control SQL across foreground and background roles.',size=17)
        save(pdf,fig)
        fig=page('LinkedList: Traverse protocol time','Median [minimum–maximum] ms; the sum and union are equal in every measured Traverse sample.')
        values=[]
        for row in data['rows']:
            if 'Traverse' not in row:continue
            t=row['Traverse'];v=t['protocol_sum_ns']
            values.append([TITLES[row['case_id']],LABELS[row['config_id']],
                f"{v['median']/1e6:.3f} [{v['min']/1e6:.3f}–{v['max']/1e6:.3f}]",str(t['sql_dispatches']['median'])])
        ax=fig.add_axes([.055,.29,.89,.47]);ax.axis('off')
        t=ax.table(cellText=values,colLabels=['Workload','Configuration','DB sum = union ms','Total SQL'],
            colWidths=[.23,.30,.35,.12],cellLoc='center',bbox=[0,0,1,1]);t.auto_set_font_size(False);t.set_fontsize(14)
        for (r,c),cell in t.get_celld().items():
            cell.set_edgecolor('#d4dde5')
            if r==0:cell.set_facecolor('#e9f1f8');cell.set_text_props(weight='bold')
        fig.text(.065,.17,'Native ordered reports are 0…31 and 0…999, with visited=32 and visited=1,000 respectively.',size=17)
        save(pdf,fig)
        if classes:
            fig=page('LinkedList: both path and payload calls collapse','Actual Traverse SQL classifications; every value is identical in all three measured repeats.')
            values=[]
            for row in classes['rows']:
                cats=row['categories']
                for name,counts in cats.items():
                    if len(set(counts))!=1:raise ValueError('Update classification display for varying counts')
                values.append([row['case_id'].replace('linked_list','LL '),LABELS[row['config_id']],
                    cats['ordinary_path'][0],cats['fused_path'][0],cats['payload'][0],cats['control'][0],
                    cats['identity'][0]+cats['catalog'][0],row['TOTAL_SQL'][0]])
            ax=fig.add_axes([.05,.30,.90,.46]);ax.axis('off')
            table=ax.table(cellText=values,colLabels=['Size','Configuration','Ordinary\npath','Fused\npath','Payload','Control','Identity\n+ catalog','TOTAL'],
                colWidths=[.10,.29,.10,.10,.10,.10,.12,.09],cellLoc='center',bbox=[0,0,1,1]);table.auto_set_font_size(False);table.set_fontsize(13)
            for (r,c),cell in table.get_celld().items():
                cell.set_edgecolor('#d4dde5')
                if r==0:cell.set_facecolor('#e9f1f8');cell.set_text_props(weight='bold')
            fig.text(.065,.19,'Per-origin ordered path entries replace repeated path discovery; one process payload batch replaces repeated loads.',size=16)
            fig.text(.065,.12,'The totals include both roles, the type/module catalog proof, identity lookup and transaction controls.',size=16)
            save(pdf,fig)
            report+=['## Traverse SQL decomposition','',
                '| Size | Mode | Ordinary path | Fused path | Payload | Control | Identity + catalog | Total |',
                '|---|---|---:|---:|---:|---:|---:|---:|']
            report+=['| '+' | '.join(map(str,r))+' |' for r in values]+['']
        if eligibility:
            fig=page('Limited coalescing: Find keeps its data-dependent branch','LinkedList1,000 · actual SQL per operation; all three measured repeats have the same counts.')
            ops=eligibility['operations'];values=[]
            for name in ('Traverse','Sum','Find head','Find middle','Find tail','Find missing'):
                selected=[next(r for r in ops if r['case']=='linked_list1000' and r['config']==mode and r['operation']==name) for mode in ('off','prefusion','ttg_plus')]
                if any(len(set(r['SQL']))!=1 for r in selected):raise ValueError('Update operation display for varying counts')
                values.append([name]+[r['SQL'][0] for r in selected])
            ax=fig.add_axes([.06,.37,.52,.39]);ax.axis('off')
            table=ax.table(cellText=values,colLabels=['Native operation','Off','Pre-fusion','TTG+'],colWidths=[.40,.20,.20,.20],
                cellLoc='center',bbox=[0,0,1,1]);table.auto_set_font_size(False);table.set_fontsize(13)
            for (r,c),cell in table.get_celld().items():
                cell.set_edgecolor('#d4dde5')
                if r==0:cell.set_facecolor('#e9f1f8');cell.set_text_props(weight='bold')
            fig.text(.63,.73,'Native Find guard',size=21,weight='bold')
            fig.text(.63,.66,'if here.value == self.target {\n  self.found = True;\n  report here;\n  disengage;\n}\nvisit [->:Next:->];',size=15,family='DejaVu Sans Mono',va='top',linespacing=1.6)
            stops=[o for o in eligibility['compact_outcomes'] if o['case']=='linked_list1000' and o['config']=='ttg_plus' and o['request'] in ('2:8','2:9','2:10')]
            if len(stops)!=9 or not all("Unknown scalar fact: 'visit_item::here.value'" in o['stops'] for o in stops):raise ValueError('Find stop evidence missing')
            fig.text(.065,.26,"Observed planner stop: Unknown scalar fact: 'visit_item::here.value'",size=19,weight='bold')
            fig.text(.065,.19,'Middle/tail/missing Find issue 500/999/1,000 fused path queries, each caching one origin.',size=17)
            fig.text(.065,.13,'Traverse and Sum coalesce; these Find requests preserve per-step path and payload counts.',size=17)
            save(pdf,fig)
            report+=['## Branch-sensitive eligibility','',
                "The actual middle, tail and missing Find outcomes record `Unknown scalar fact: 'visit_item::here.value'`. Their fused-query counts are 500, 999 and 1,000. Each query caches one origin, retaining per-step path dispatch counts.",
                '', '| Operation (1,000 nodes) | Off SQL | Pre-fusion SQL | TTG+ SQL |','|---|---:|---:|---:|']
            report+=['| '+' | '.join(map(str,r))+' |' for r in values]+['']
        if supplemental:
            fig=page('LittleX: fewer calls, higher protocol contribution','Arithmetic means across all three accepted workflows; categories partition every primary SQL call.')
            values=[]
            for mode in supplemental['LittleX_mean_categories']:
                cats={c['category']:c for c in mode['categories']}
                values.append([LABELS[mode['config']]]+[f"{cats[k]['mean_SQL']:g} / {cats[k]['mean_protocol_ms']:.3f}" for k in ('Path discovery','Payload loading','Control','Other data')])
            ax=fig.add_axes([.05,.43,.90,.29]);ax.axis('off')
            table=ax.table(cellText=values,colLabels=['Configuration','Path SQL / ms','Payload SQL / ms','Control SQL / ms','Other SQL / ms'],
                colWidths=[.28,.18,.18,.18,.18],cellLoc='center',bbox=[0,0,1,1]);table.auto_set_font_size(False);table.set_fontsize(13)
            for (r,c),cell in table.get_celld().items():
                cell.set_edgecolor('#d4dde5')
                if r==0:cell.set_facecolor('#e9f1f8');cell.set_text_props(weight='bold')
            fig.text(.065,.32,'Payload fingerprint b0075df9: 108 returned rows and 70,163 protocol row-payload bytes',size=18,weight='bold')
            fig.text(.065,.265,'in every workflow in all three modes. TTG+ loads them in 44 calls, versus 52 off/pre-fusion.',size=17)
            fig.text(.065,.18,'Path discovery: native path SELECTs plus certified fused SQL. Controls include BEGIN, SET, COMMIT and DISCARD.',size=14)
            fig.text(.065,.12,'These contributions locate the measured cost; matched EXPLAIN diagnostics examine server planning/execution separately.',size=14)
            save(pdf,fig)
            fig=page('LittleX: the two fused SQL targets','Full SQL, source-bound fingerprints and per-request call references are retained in the attribution artifact.')
            y=.73
            for target in supplemental['targets']:
                fig.text(.065,y,target['label'].capitalize(),size=21,weight='bold');y-=.06
                fig.text(.08,y,f"{target['fingerprint'][:16]} · {target['calls_per_workflow'][0]} calls/workflow · {target['mean_protocol_ms_per_workflow']:.3f} ms mean DB sum",size=18);y-=.055
                fig.text(.08,y,'Requests: '+', '.join(sorted({r['path'].replace('/walker/','') for r in target['per_RPC']})),size=17);y-=.12
            fig.text(.065,.22,'The batched query covers two current collect paths; the recursive query also appears in get_profile and create_tweet.',size=15)
            fig.text(.065,.15,'Protocol timing includes transport and client decode progress. The separate diagnostic recaptures exact Bind values/state.',size=15)
            save(pdf,fig)
            fig=page('Actual process reader: separate PID, sequential SQL intervals','LittleX TTG+ · measured repeat0 · first load_feed; actual send-to-ReadyForQuery intervals.')
            timeline=supplemental['timeline'];calls=timeline['calls'];base=min(c['send_ns'] for c in calls)
            lanes=sorted({(c['role'],c['client_process_pid'],c['backend_pid']) for c in calls})
            colors={'foreground':'#337caa','background_prefetch':'#df8c32'}
            def intervals(ax):
                for c in calls:
                    lane=lanes.index((c['role'],c['client_process_pid'],c['backend_pid']))
                    ax.broken_barh([((c['send_ns']-base)/1e6,(c['ready_ns']-c['send_ns'])/1e6)],(lane-.22,.44),facecolors=colors[c['role']])
                    ax.plot((c['send_ns']-base)/1e6,lane,marker='|',ms=8,color=colors[c['role']],linestyle='none')
                ax.set_ylim(-.5,len(lanes)-.5);ax.grid(axis='x',alpha=.2)
            ax=fig.add_axes([.27,.49,.67,.24]);intervals(ax)
            ax.set_yticks(range(len(lanes)),[f"{'Child' if r!='foreground' else 'Foreground'} OS {p}\nPG backend {b}" for r,p,b in lanes],fontsize=13)
            ax.set_title('Overall RPC SQL timeline',fontsize=14)
            child=[c for c in calls if c['role']!='foreground'];first_child=min(c['send_ns'] for c in child)
            early_end=max(c['ready_ns'] for c in calls if c['ready_ns']<first_child)
            windows=[(0,(early_end-base)/1e6+.5,'Early foreground SQL'),
                ((first_child-base)/1e6-.5,(max(c['ready_ns'] for c in child)-base)/1e6+.5,'Child payload / completion SQL')]
            for x,(left,right,title) in zip((.15,.61),windows):
                zoom=fig.add_axes([x,.20,.33,.17]);intervals(zoom);zoom.set_xlim(left,right)
                zoom.set_yticks(range(len(lanes)),['Child' if r!='foreground' else 'FG '+str(b) for r,p,b in lanes],fontsize=10)
                zoom.set_title(title,fontsize=13);zoom.set_xlabel('ms from first SQL send (same origin)',fontsize=11)
            fig.text(.065,.105,'Bars preserve measured durations; ticks mark actual sends. Insets retain the overall timeline’s millisecond coordinates.',size=13)
            fig.text(.065,.065,'Real child SQL is observed; foreground/background DB intervals do not overlap in the measured workflows.',size=13)
            save(pdf,fig)
            report+=['## LittleX trace attribution','',
                'All nine measured workflows return 108 payload rows and 70,163 protocol row-payload bytes for fingerprint b0075df9. Off and pre-fusion issue 52 payload calls; TTG+ issues 44. These row counts do not identify distinct application IDs.',
                'The batched 3166e116 query contributes 9.680058 ms mean summed protocol time across four calls per workflow. Recursive d1067307 contributes 7.932784 ms across six calls. These are protocol contributions, not server-only or CPU timings.','']
        if diagnostic:
            fig=page('Matched LittleX diagnostic: planning and execution','One accepted recapture per mode; first and immediate repeated EXPLAIN are separate observations.')
            fig._ttg_regime='matched diagnostic | first / repeated EXPLAIN'
            values=[]
            for c in diagnostic['comparisons']:
                label='Root → Profile' if c['region']=='root_profile' else 'Collect: Post + Follow'
                run='First' if c['repetition']==0 else 'Repeat'
                for mode,p,e,hits in [('Native',c['native_planning_ms'],c['native_execution_ms'],c['native_root_shared_hits']),
                    ('Fused',c['fused_planning_ms'],c['fused_execution_ms'],c['fused_root_shared_hits'])]:
                    values.append([label,run,mode,f'{p:.3f}',f'{e:.3f}',str(int(c['native_rows'])),str(hits)])
            ax=fig.add_axes([.055,.29,.89,.48]);ax.axis('off')
            table=ax.table(cellText=values,colLabels=['Semantic region','Observation','SQL','Planning ms','Execution ms','Rows','Shared hits'],
                colWidths=[.27,.14,.10,.14,.14,.08,.13],cellLoc='center',bbox=[0,0,1,1]);table.auto_set_font_size(False);table.set_fontsize(13)
            for (r,c),cell in table.get_celld().items():
                cell.set_edgecolor('#d4dde5')
                if r==0:cell.set_facecolor('#e9f1f8');cell.set_text_props(weight='bold')
            fig.text(.065,.20,'Exact recapture Bind/state in the same SERIALIZABLE transaction; census and EXPLAIN warm the buffers.',size=15)
            fig.text(.065,.14,'Collect native values add two independent statement roots. These server-reported times are separate from primary n3 protocol wall.',size=14)
            save(pdf,fig)
            report+=['## Matched server-plan diagnostic','',
                'One off and one TTG+ full native workflow passed the same business/state/restart oracles. Five selected original SQL calls completed; ten EXPLAIN plans use their exact diagnostic Bind bytes in the same recorded SERIALIZABLE transaction. Census and repeated EXPLAIN warm the buffers. This diagnostic is separate from primary n3 protocol timing.',
                '', '| Region | Observation | SQL | Planning ms | Execution ms | Rows | Root shared hits |','|---|---|---|---:|---:|---:|---:|']
            report+=['| '+' | '.join(map(str,r))+' |' for r in values]+['']
            plans={p['target_id']:p for p in diagnostic['plans'] if p['repetition']==0}
            node_specs=[('Native Post','native-post','n1','anchors_pkey'),('Native Follow','native-follow','n2','anchors_pkey'),
                ('Fused batch / Post','fused-batch','_t4','idx_anchors_kind_type'),('Fused batch / Follow','fused-batch','_t17','idx_anchors_kind_type')]
            nodes=[];values=[]
            for label,target,alias,index in node_specs:
                plan=plans[target]
                candidates=[n for n in plan['executed_nodes'] if n.get('Alias')==alias and n.get('Index Name')==index]
                if len(candidates)!=1:raise ValueError('Matched diagnostic plan-node identity changed')
                n=candidates[0];nodes.append(dict(label=label,capture=plan['capture'],node=n))
                values.append([label,index,str(n['Actual Loops']),f"{n['Actual Rows']:g}",str(n['buffers']['Shared Hit Blocks'])])
            inputs['diagnostic_plan_nodes']=nodes
            fig=page('Measured plan difference: indexable target lookup','First EXPLAIN · matched collect region; plan rows are per-loop averages, distinct from returned SQL row totals.')
            fig._ttg_regime='matched diagnostic | first EXPLAIN plan nodes'
            ax=fig.add_axes([.055,.43,.89,.30]);ax.axis('off')
            table=ax.table(cellText=values,colLabels=['Plan node','Index','Loops','Rows / loop','Shared hits'],
                colWidths=[.29,.30,.12,.14,.15],cellLoc='center',bbox=[0,0,1,1]);table.auto_set_font_size(False);table.set_fontsize(14)
            for (r,c),cell in table.get_celld().items():
                cell.set_edgecolor('#d4dde5')
                if r==0:cell.set_facecolor('#e9f1f8');cell.set_text_props(weight='bold')
            fig.text(.065,.33,'Native target nodes use the primary-key condition id = CASE … . The selected fused nodes',size=17)
            fig.text(.065,.275,"use the kind/type index with Index Cond: kind = 'NodeAnchor'.",size=17)
            fig.text(.065,.20,'Collect statement-root shared hits: native pair 55; fused batch 320. Shared reads and temporary I/O are zero.',size=15)
            fig.text(.065,.14,'Node and parent buffer counters are inclusive. The table retains each reported counter without adding the tree.',size=14)
            save(pdf,fig)
            fig=page('Next work: preserve the proof, reduce small-region cost','Research hypotheses motivated by measured counts and plans; improvements have not been measured.')
            fig._ttg_regime='proposed experiments'
            items=[('Indexable target joins','Reshape the fused SQL AST so target ID equality can use the primary key;\nretain ACL, type/module, arity and native ordering checks.'),
                ('Eligibility and cost admission','Prefer fusion when the proven region coalesces enough path/payload calls.\nTest per-path execution for single-origin regions and unresolved Find guards.'),
                ('Planning reuse','Test prepared-plan reuse for repeated fused shapes; compare planning,\nexecution, total SQL and complete native correctness under the same regime.')]
            for y,(title,body) in zip((.72,.51,.30),items):
                fig.text(.065,y,title,size=22,weight='bold');fig.text(.08,y-.055,body,size=18,va='top',linespacing=1.6)
            save(pdf,fig)
            report+=['## Next experiments','',
                'Test an indexable target-ID join in the fused SQL AST while preserving ACL, exact type/module, cardinality and ordered cache semantics. Test admission that accounts for proven multi-origin savings and retains per-path execution for uneconomic single-origin regions. Test prepared-plan reuse with complete native correctness. These are proposed experiments; no improvement result is claimed.','']
        fig=page('Experimental regime and correctness','Same final repaired source; only the prefetch/fusion configuration differs.')
        lines=['Seed 42; one process reader; prefetch_limit=2048; common planner budget=32768.',
            'Nine excluded full-workflow warmups; three measured fresh workflows per cell; balanced policy order.',
            'Each workflow uses equivalent fresh data and fresh server state; one profile reset after setup.',
            'Always admission model; natural within-workflow caches; no cross-trial learning or cache carry.',
            'Native reports, ordering, Sum/Find, LittleX mutations, identities and final graph/restart checks pass.',
            'Reviewed direct driver boundary; native process cleanup and post-response late-call attribution.',
            'Actual client/PG backend PID intervals support process and overlap evidence; SQL logging is off.']
        for i,line in enumerate(lines):fig.text(.065,.73-i*.083,line,size=17)
        save(pdf,fig)
    (out/'figure-inputs.json').write_text(json.dumps(inputs,indent=2)+'\n')
    (out/'report.md').write_text('\n'.join(report)+'\n')
    manifest=dict(passed=True,pages=pages,renderer=ref(__file__),accepted_export=ref(source/'results.json'),
        inputs=ref(out/'figure-inputs.json'),outputs=[ref(p) for p in sorted(out.glob('*')) if p.is_file()])
    (out/'report-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(out/'ttg-plus-performance.pdf')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--export',dest='source',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--attribution',type=Path)
    parser.add_argument('--classification',type=Path);parser.add_argument('--linkedlist',type=Path);parser.add_argument('--diagnostics',type=Path)
    args=parser.parse_args();render(args.source,args.output,args.attribution,args.classification,args.linkedlist,args.diagnostics)
