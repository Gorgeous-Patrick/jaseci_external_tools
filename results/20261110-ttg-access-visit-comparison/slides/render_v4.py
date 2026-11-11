"""Editable, English, data-bound slides. Presentation only; no benchmark run."""
import hashlib
import json
import os
import textwrap
from pathlib import Path
os.environ.setdefault('MPLCONFIGDIR','/tmp/ttg-access-slides-mpl')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch, Rectangle

HERE=Path(__file__).resolve().parent
D=json.loads((HERE/'slide-data.json').read_text()); assert D['passed']
G={(g['app'],g['mode']):g for g in D['groups']}
U=json.loads((HERE/'slide-data-v4.json').read_text()); assert U['passed']
C=U['current']
G['recipe_pantry','conservative']=dict(app='recipe_pantry',mode='conservative',n=3,prefetched=C['payload_objects'],covered=C['demanded_prefetch_objects'],demand=C['successful_demand_objects'],coverage=C['coverage'],unused=C['unused_payload_objects'],confirmed_filter_only=C['confirmed_filter_only'],confirmed_unnecessary_lower_bound=C['confirmed_unnecessary_lower_bound'],data_sql=C['sql_data'],control_sql=C['sql_control'])
OUT=HERE/'report-v4'; OUT.mkdir(exist_ok=True)
NAVY='#142c45'; INK='#263c50'; MUTED='#596f82'; AGG='#cf713c'; CONS='#14877c'; PALE='#eff4f7'; RED='#b34740'
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':18,'text.color':INK,'axes.labelcolor':INK,'pdf.fonttype':42})
pages=[]; labels=[]
def text(f,x,y,s,size=20,color=INK,weight='normal',**kw):
    return f.text(x,y,s,fontsize=size,color=color,weight=weight,va='top',**kw)
def page(title,subtitle):
    f=plt.figure(figsize=(16,9),facecolor='white'); pages.append(f);labels.append(title)
    f.add_artist(Rectangle((0,.962),1,.038,transform=f.transFigure,facecolor=NAVY,edgecolor='none'))
    text(f,.055,.915,title,29,NAVY,'bold');text(f,.055,.844,subtitle,16,MUTED)
    text(f,.055,.045,'TTG  /  Access & Visit  /  updated 2026-11-11  /  source-bound precision results',11,MUTED)
    text(f,.945,.045,f'{len(pages):02}',11,MUTED,ha='right')
    return f
def note(f,s,y=.13,size=16):text(f,.06,y,s,size,MUTED)
def box(f,x,y,w,h,title,body,color=CONS):
    f.add_artist(FancyBboxPatch((x,y),w,h,boxstyle='round,pad=.008',transform=f.transFigure,facecolor=PALE,edgecolor=color,linewidth=1.5))
    text(f,x+.018,y+h-.024,title,20,color,'bold')
    text(f,x+.018,y+h-.085,body,17)
def arrow(f,a,b,color=MUTED):
    f.add_artist(FancyArrowPatch(a,b,transform=f.transFigure,arrowstyle='-|>',mutation_scale=20,linewidth=2,color=color))
def table(f,headers,rows,widths=None,top=.73,rowh=.075,size=17):
    widths=widths or [1/len(headers)]*len(headers)
    x0=.06; full=.88
    for r,vals in enumerate([headers]+rows):
        y=top-r*rowh; x=x0
        for j,val in enumerate(vals):
            w=full*widths[j]
            f.add_artist(Rectangle((x,y-rowh),w,rowh,transform=f.transFigure,
                facecolor=NAVY if r==0 else ('#eff4f7' if r%2 else 'white'),edgecolor='white'))
            text(f,x+.012,y-.021,str(val),size,'white' if r==0 else INK,'bold' if r==0 else 'normal')
            x+=w
def bullet(f,y,title,body):
    text(f,.065,y,title,22,NAVY,'bold');text(f,.085,y-.056,body,18)
def pct(v):return f'{v*100:.2f}%'

apps=['jdrive','littlex','recipe_pantry']; names={'jdrive':'JDrive','littlex':'LittleX','recipe_pantry':'RecipePantry'}

f=page('Aggressive vs. Conservative TTG','Latest accepted results: Access coverage and unnecessary full-node fetches')
box(f,.065,.43,.27,.31,'JDrive','Aggressive: at least 832\nunnecessary full-node fetches.\nConservative: 0 confirmed\nin the audited classes.',AGG)
box(f,.365,.43,.27,.31,'LittleX','357 prefetched and used\nin both policies.\nAccess-only reads are\ncovered by Conservative.')
box(f,.665,.43,.27,.31,'RecipePantry',f"Conservative: {C['demanded_prefetch_objects']} / {C['successful_demand_objects']} covered\n{pct(C['coverage'])} demand coverage\n0 unused prefetches\n0 confirmed white reads")
text(f,.07,.32,'GIL-off threads  •  n = 3 per reported configuration  •  native results preserved',21,NAVY,'bold')
note(f,'RecipePantry Conservative uses the November 11 condition-call repair.\nThe other configurations retain their November 10 captures; Aggressive was not rerun.',y=.22,size=18)

f=page('Count white reads against actual Access demand','Using only an ID is valid demand. Visiting a node is not required for its Access to be useful.')
box(f,.065,.48,.27,.25,'Valid Access demand','The user query needs the node.\nReading jid(n) counts too.\nA helper need not visit the\nnode for its Access to count.')
box(f,.365,.48,.27,.25,'Filtered candidates','The node is outside the\nexplicit graph-query filter:\ne.g. a cooked Meal when\nstatus == planned is required.',AGG)
box(f,.665,.48,.27,.25,'Unused prefetch','Prefetched payload never\nread by foreground code.\nThis is one measurable\nclass of unnecessary fetch.',RED)
text(f,.07,.36,'Observed coverage = demanded IDs returned by prefetch / all demanded IDs',22,NAVY,'bold')
note(f,'Counts are unique within each HTTP request / Session, then summed over the workflow.\nThe denominator includes root reads and memory hits. This is not a database cache-hit rate.',y=.25,size=17)
note(f,'Confirmed white reads = unused + disjoint, excluded graph-query candidates.\nReturning only IDs instead of full properties is a separate projection optimization.',y=.15,size=17)

f=page('Fixed workloads and explicit measurement provenance','The summary combines accepted captures; it is not a simultaneous new three-app rerun.')
table(f,['App','Business workflow','Capture used'],[
 ['JDrive','List / visible tree / trash / create folder','Nov 10: both policies'],
 ['LittleX','Feed / likes / follow / profile / tweet','Nov 10: both policies'],
 ['RecipePantry','Plan / buy / cook / boards / shopping','Nov 10 Agg.; Nov 11 Cons.']],widths=[.17,.52,.31],rowh=.09,size=15)
bullet(f,.33,'Same RecipePantry scenarios and business results','The repair changes Access extraction; native control flow, responses and persisted state agree.')
note(f,'Thread executor, GIL disabled, 1 worker, limit 2048. Each reported configuration has n=3.\nThe Nov 11 validation ran 8 fresh workflows: 2 excluded warmups + 6 measurements.\nOnly the repaired Conservative results are presented here.',y=.19,size=16)

f=page('Aggressive vs. Conservative: summary','Hit rate means demand coverage; white reads fall outside actual Access demand.')
rows=[]
for app in apps:
    a,c=G[app,'aggressive'],G[app,'conservative']
    def waste(g):
        v=g['confirmed_unnecessary_lower_bound']
        return 'Not audited' if v is None else ('At least '+str(v) if v else '0 confirmed')
    rows.append([names[app],pct(a['coverage']),pct(c['coverage']),waste(a),waste(c)])
table(f,['App','Aggressive\nhit rate','Conservative\nhit rate','Aggressive\nunnecessary fetches','Conservative\nunnecessary fetches'],rows,widths=[.15,.18,.19,.24,.24],top=.73,rowh=.112,size=16)
note(f,'RecipePantry Conservative audited: 118 prefetched / 118 used / 0 confirmed white reads.',y=.225,size=16)
note(f,'RecipePantry Aggressive is the earlier 112 / 167 capture, not a rerun on the repaired version.\nWhite reads count unnecessary nodes; valid jid-only accesses are not counted as waste.',y=.17,size=15)
note(f,'Request-local unique IDs summed per workflow; all three repetitions agree.',y=.095,size=14)

f=page('Payload counts: use is not the same as necessity','Latest accepted counts per configuration; all three repetitions agree')
rows=[]
for app in apps:
    for mode in ('aggressive','conservative'):
        g=G[app,mode];fil=g['confirmed_filter_only'];bad=g['confirmed_unnecessary_lower_bound']
        rows.append([names[app]+' / '+('Agg.' if mode=='aggressive' else 'Cons.'),g['prefetched'],g['covered'],g['unused'],'Not audited' if fil is None else fil,'Not audited' if bad is None else (str(bad)+' min.' if bad else '0 found')])
table(f,['App / policy','Prefetched','Used','Unused','Filter-only','Unnecessary\nlower bound'],rows,widths=[.27,.13,.10,.10,.18,.22],rowh=.073,size=15)
note(f,'RecipePantry Conservative: all 118 prefetched objects were subsequently demanded.\nThe unfiltered _owns query intentionally reads neighbor IDs; these are valid Accesses.\nNo prefetched Meal was excluded by the planned-status graph-query filter in ShoppingList.',y=.18,size=16)

f=page('JDrive: unused and filter-only payloads','The trashed == False predicate avoids full-node fetches for rejected candidates.')
ax=f.add_axes([.12,.48,.80,.18]);left=0
for value,label,col in [(258,'258 used by tree traversal',CONS),(61,'61 filter-only',AGG),(771,'771 unused',RED)]:
    ax.barh([0],[value],left=left,color=col,height=.6,label=label);left+=value
ax.set_xlim(0,1090);ax.set_yticks([]);ax.set_xlabel('Aggressive prefetched payloads: 1,090',fontsize=17);ax.spines[['top','left','right']].set_visible(False)
ax.legend(loc='upper center',bbox_to_anchor=(.5,1.50),ncol=3,frameon=False,fontsize=15)
box(f,.07,.21,.40,.18,'Aggressive: at least 832','771 unused + 61 rejected trashed\ncandidates with avoidable full payloads.',AGG)
box(f,.53,.21,.40,.18,'Conservative: 265 used','258 tree nodes + 7 ListFolder Accesses.\n0 unnecessary examples in audited classes.')
note(f,'November 10 capture retained. Matched business outputs and final states; no new JDrive run.',y=.12,size=16)

f=page('LittleX: Access-only demand is real demand','357 prefetched and used in both policies; 92.97% observed coverage')
box(f,.07,.49,.25,.24,'Profile ability','here.to_profile_view()\nTyped helper call\nOrdinary graph accesses')
box(f,.39,.49,.25,.24,'Access demands','Followers / following\nTweets / profile fields\nNo invented Visit events')
box(f,.71,.49,.22,.24,'Result','Native business code\nreads those objects\nand returns the view')
arrow(f,(.325,.61),(.382,.61));arrow(f,(.645,.61),(.702,.61))
table(f,['Conservative payload use','Count'],[['Prefetched and entered','287'],['Useful without Visit','70'],['Total used prefetch','357']],widths=[.72,.28],top=.40,rowh=.065,size=17)
note(f,'A helper read is a valid demand even if the walker never visits the object.\nNovember 10 accepted capture retained; no new LittleX run.',y=.115,size=16)

f=page('RecipePantry: repaired Conservative results','Condition calls and ordinary calls now share Access extraction; GIL-off threads, n=3.')
table(f,['Measure','Current result'],[
 ['Observed foreground demand',C['successful_demand_objects']],['Prefetched / subsequently used',f"{C['payload_objects']} / {C['demanded_prefetch_objects']}"],
 ['Observed demand coverage',f"{C['demanded_prefetch_objects']} / {C['successful_demand_objects']} = {pct(C['coverage'])}"],
 ['Unused prefetch / uncovered demand',f"{C['unused_payload_objects']} / {C['successful_demand_objects']-C['demanded_prefetch_objects']}"],
 ['Data / control / total SQL',f"{C['sql_data']} / {C['sql_control']} / {C['total_sql']}"]],widths=[.60,.40],rowh=.079,size=18)
note(f,'All counts agree across the three measured workflows. Business outputs and persisted state pass.\nAll n3 audits find 0 unused and 0 excluded graph-query candidates. ID-only demand counts.\nThese precision captures alone do not establish a latency speedup.',y=.18,size=16)

f=page('One Access analysis for helpers and conditions','Prefetch supported reads when their real dependencies are available; keep control flow native.')
box(f,.065,.51,.27,.22,'1  Bind the object','meal = jobj(self.meal_id)\nNative lookup materializes\nthe actual Meal object.')
box(f,.365,.51,.27,.22,'2  Prefetch helper Access','Before _owns(meal, Meal):\ncheck the actual safe type;\nprefetch [root-->] demand.')
box(f,.665,.51,.27,.22,'3  Follow native control','Execute _owns once.\nAfter ownership / status:\nprefetch _requirements.')
arrow(f,(.34,.62),(.355,.62));arrow(f,(.64,.62),(.655,.62))
text(f,.08,.42,'isinstance(item, kind) and jid(item) in [jid(n) for n in [root-->]]',18,NAVY,'bold',family='DejaVu Sans Mono')
bullet(f,.31,'Short-circuit guards remain part of the demand','A false AND-left or true OR-left prevents right-side prefetch; opaque predicates run natively.')
note(f,'Unknown predicate results do not discard a supported helper Access prefix.\nHooks can resume at supported statement boundaries after actual local bindings become available.',y=.16,size=16)

f=page('SQL counts are a separate outcome','Latest accepted data / control counts; request-local object coverage is not SQL hit rate.')
table(f,['App','Aggressive data / control','Conservative data / control'],[
 [names[a],f'{G[a,"aggressive"]["data_sql"]} / {G[a,"aggressive"]["control_sql"]}',f'{G[a,"conservative"]["data_sql"]} / {G[a,"conservative"]["control_sql"]}'] for a in apps],widths=[.26,.37,.37],rowh=.095,size=19)
bullet(f,.32,'RecipePantry covers 118 demands with 213 data SQL calls','Access extraction supplies demand information; it does not fuse every path or payload query.')
note(f,'RecipePantry Aggressive is an earlier capture; Conservative is the repaired November 11 version.\nA Session demand can be satisfied from memory. A higher coverage ratio does not by itself\nprove fewer SQL calls, less semantic waste, or lower latency.',y=.18,size=16)

f=page('What to improve next','Optimize the demand representation as well as the number of demands covered.')
bullet(f,.73,'1  Optimize field projection separately','Ownership membership uses IDs. Returning fewer properties can save bytes without changing white-read counts.')
bullet(f,.56,'2  Cover the remaining actual demand','RecipePantry still has 46 uncovered request-local demand IDs. Preserve control-flow guards.')
bullet(f,.39,'3  Fuse compatible accesses and measure overhead','Track path / payload / control SQL separately; re-test request wall time with matched instrumentation.')
bullet(f,.22,'4  Keep demand and waste measurements distinct','Report coverage, unused nodes and excluded query candidates; do not label valid ID-only demand as waste.')

f=page('Evidence and scope','Current results are bound to accepted sources, captures and reproducible derivation.')
bullet(f,.73,'RecipePantry repair: 8 fresh workflows, 6 measured','3 measured per version plus excluded warmups; only repaired results are shown in this deck.')
bullet(f,.56,'Validation: 61 pure tests + 89 native regression tests','Native outputs / state / restart / GIL-off and all eight owned database cleanup checks passed.')
bullet(f,.39,'Raw-derived results, with explicit provenance','256 new sealed files checked; all n3 counts match. Original three-app evidence is preserved.')
note(f,'Editable render_v4.py + accepted results + per-object necessity-audit.json evidence.\nThe new raw archives remain in the measurement workspace; the package retains its original 24 archives.\nRecipePantry white reads audited across all n3. Aggressive / JDrive / LittleX were not rerun.',y=.23,size=16)

checks=[]
pdf=OUT/'ttg-access-visit-comparison.pdf'
with PdfPages(pdf) as pp:
    for i,f in enumerate(pages,1):
        f.canvas.draw();ren=f.canvas.get_renderer();W,H=f.canvas.get_width_height()
        for t in f.texts:
            bb=t.get_window_extent(ren)
            checks.append(dict(page=i,text=t.get_text(),left=bb.x0/W,right=bb.x1/W,bottom=bb.y0/H,top=bb.y1/H))
            assert bb.x0>=0 and bb.x1<=W and bb.y0>=0 and bb.y1<=H,(i,t.get_text(),bb)
        pp.savefig(f);f.savefig(OUT/f'slide-{i:02}.png',dpi=95);plt.close(f)
def ref(p):return {'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
(OUT/'layout-checks.json').write_text(json.dumps({'passed':True,'checks':checks},indent=2)+'\n')
manifest=dict(pages=len(pages),titles=labels,source=ref(Path(__file__)),data=ref(HERE/'slide-data.json'),update=ref(HERE/'slide-data-v4.json'),audit=ref(HERE/'update-20261111/necessity-audit.json'),
              outputs=[ref(p) for p in sorted(OUT.iterdir()) if p.name!='report-manifest.json'])
(OUT/'report-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps({'pdf':str(pdf),'pages':len(pages),'sha256':ref(pdf)['sha256']}))
