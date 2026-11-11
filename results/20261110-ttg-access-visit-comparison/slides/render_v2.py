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
OUT=HERE/'report-v2'; OUT.mkdir(exist_ok=True)
NAVY='#142c45'; INK='#263c50'; MUTED='#596f82'; AGG='#cf713c'; CONS='#14877c'; PALE='#eff4f7'; RED='#b34740'
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':18,'text.color':INK,'axes.labelcolor':INK,'pdf.fonttype':42})
pages=[]; labels=[]
def text(f,x,y,s,size=20,color=INK,weight='normal',**kw):
    return f.text(x,y,s,fontsize=size,color=color,weight=weight,va='top',**kw)
def page(title,subtitle):
    f=plt.figure(figsize=(16,9),facecolor='white'); pages.append(f);labels.append(title)
    f.add_artist(Rectangle((0,.962),1,.038,transform=f.transFigure,facecolor=NAVY,edgecolor='none'))
    text(f,.055,.915,title,29,NAVY,'bold');text(f,.055,.844,subtitle,16,MUTED)
    text(f,.055,.045,'TTG  /  Access & Visit  /  2026-11-10  /  source-bound precision study',11,MUTED)
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

f=page('Aggressive vs. Conservative TTG','What was prefetched, what was needed, and what the hit-rate denominator includes')
box(f,.065,.43,.27,.31,'JDrive','Aggressive: 832 confirmed\navoidable full-node fetches.\nConservative: none found\nin the two audited classes.',AGG)
box(f,.365,.43,.27,.31,'LittleX','357 prefetched and used\nin both policies.\nAccess-only reads are now\ncovered by Conservative.')
box(f,.665,.43,.27,.31,'RecipePantry','Coverage remains lower:\n31.10% vs. 67.07%.\nUnknown origins / later\ncheckpoints are still gaps.',AGG)
text(f,.07,.32,'24 fresh workflows  •  3 apps  •  n = 3 per policy  •  GIL-off threads',22,NAVY,'bold')
note(f,'Conservative includes the new Access-demand implementation.\n“832” is a confirmed lower bound, not an exhaustive minimal-read oracle.',y=.22,size=18)

f=page('Define “unnecessary” at the payload boundary','A node need not be visited to be useful; a node can be accessed and still be avoidably fetched.')
box(f,.065,.48,.27,.25,'Necessary payload','Fields are needed for the\nresult or later computation.\nAn ordinary helper read\ncounts, even without Visit.')
box(f,.365,.48,.27,.25,'Filter-only payload','Full node fetched only to\nreject it using a predicate.\nSQL can evaluate the filter\nwithout returning the node.',AGG)
box(f,.665,.48,.27,.25,'Unused prefetch','Payload returned by the\nprefetch worker, but never\nread by foreground code.\nThis is also avoidable.',RED)
text(f,.07,.36,'Confirmed unnecessary prefetch = unused + disjoint filter-only payloads',23,NAVY,'bold')
note(f,'The database still needs to evaluate predicates. We count complete node payloads transferred /\nmaterialized at the client, not PostgreSQL rows scanned or bytes read from disk.',y=.25,size=18)
note(f,'A zero in the confirmed-count table means “none found in these two classes”; it is not a proof\nthat all remaining full payloads or properties are semantically necessary.',y=.15,size=16)

f=page('A reproducible comparison, not a new workload','Same fixed business operations and current runtime in both policy configurations')
table(f,['App','Measured workflow','Policy pairs'],[
 ['JDrive','List / visible tree / trash / create folder','3 measured + 1 warmup'],
 ['LittleX','Feeds / likes / follow / profile / create tweet','3 measured + 1 warmup'],
 ['RecipePantry','Plan / buy / cook / boards / shopping states','3 measured + 1 warmup']],widths=[.19,.55,.26],rowh=.09,size=16)
bullet(f,.32,'Thread executor; GIL disabled','1 worker, limit 2048; actual execution assertions retained. All business/state checks pass.')
note(f,'6 excluded warmups + 18 measured workflows = 24 captures. Counts are identical across n=3.\nUnit: distinct node IDs per request/session, summed over the workflow. IDs may repeat across requests.\nBoth policies share the new frozen runtime; “Aggressive” is the legacy policy, not an old binary.',y=.18,size=16)

f=page('Aggressive vs. Conservative: summary', 'Observed demand coverage and confirmed unnecessary full-node fetches')
rows=[]
for app in apps:
    a,c=G[app,'aggressive'],G[app,'conservative']
    waste=lambda g: ('At least '+str(g['confirmed_unnecessary_lower_bound'])) if g['confirmed_unnecessary_lower_bound'] else '0 confirmed'
    rows.append([names[app],pct(a['coverage']),pct(c['coverage']),waste(a),waste(c)])
table(f,['App','Aggressive\nhit rate','Conservative\nhit rate','Aggressive\nunnecessary fetches','Conservative\nunnecessary fetches'],
      rows,widths=[.15,.18,.19,.24,.24],top=.73,rowh=.112,size=16)
note(f,'Hit rate: observed foreground reads covered by prefetch, including roots.',y=.225,size=17)
note(f,'Unnecessary fetches: avoidable full-node payloads, including unused and filter-only fetches.\n“0 confirmed” does not prove zero unnecessary reads.',y=.17,size=16)
note(f,'Request-local unique nodes summed per workflow; all three repetitions agree.',y=.095,size=14)

f=page('Payload counts: use is not the same as necessity','All numbers are per workflow; n=3 produces identical counts')
table(f,['App / policy','Prefetched','Used','Unused','Filter-only','Confirmed\nunnecessary'],[
 [names[a]+' / '+('Agg.' if m=='aggressive' else 'Cons.'),g['prefetched'],g['covered'],g['unused'],g['confirmed_filter_only'],
  str(g['confirmed_unnecessary_lower_bound'])+(' (at least)' if g['confirmed_unnecessary_lower_bound'] else ' found')]
 for a in apps for m in ['aggressive','conservative'] for g in [G[a,m]]],widths=[.29,.13,.10,.11,.14,.23],rowh=.073,size=16)
note(f,'Unused and filter-only sets are disjoint. Filter-only counts were checked against paired request IDs,\nsource predicates, actual node types and state. All zero counts refer only to these audited classes.',y=.16,size=16)

f=page('JDrive: 771 unused is not the whole story','The predicate trashed == False avoids another 61 full-node fetches per workflow')
ax=f.add_axes([.12,.48,.80,.18]);left=0
for value,label,col in [(258,'258 used by tree traversal',CONS),(61,'61 filter-only',AGG),(771,'771 unused',RED)]:
    ax.barh([0],[value],left=left,color=col,height=.6,label=label);left+=value
ax.set_xlim(0,1090);ax.set_yticks([]);ax.set_xlabel('Aggressive prefetched payloads: 1,090',fontsize=17);ax.spines[['top','left','right']].set_visible(False)
ax.legend(loc='upper center',bbox_to_anchor=(.5,1.50),ncol=3,frameon=False,fontsize=15)
box(f,.07,.21,.40,.18,'Aggressive: at least 832','771 unused + 61 read only as rejected\ntrashed candidates; full fetch avoidable.',AGG)
box(f,.53,.21,.40,.18,'Conservative: 265 used','258 tree nodes + 7 ordinary ListFolder\nAccesses. No examples in either class.')
note(f,'Matched outputs and final states. SQL still evaluates trashed; the claim is avoiding full-node payloads.',y=.12,size=16)

f=page('LittleX: Access-only demand is real demand','Conservative now matches Aggressive: 357 prefetched, 357 used, 0 unused')
box(f,.07,.49,.25,.24,'Profile ability','here.to_profile_view()\nTyped helper call\nOrdinary graph accesses')
box(f,.39,.49,.25,.24,'Access demands','Followers / following\nTweets / profile fields\nNo invented Visit events')
box(f,.71,.49,.22,.24,'Result','Native business code\nreads those objects\nand returns the view')
arrow(f,(.325,.61),(.382,.61));arrow(f,(.645,.61),(.702,.61))
table(f,['Conservative','Before Access support','After Access support'],[
 ['get_profile','1 used prefetch','70 used prefetches'],['follow_user','0','1'],['Whole workflow','287','357']],widths=[.30,.35,.35],top=.40,rowh=.065,size=17)
note(f,'357 = 287 prefetched-and-entered + 70 useful without Visit. Not entering a node is not evidence of waste.\nBefore/after counts are historical same-workflow observations; no cross-run latency comparison.',y=.115,size=15)

f=page('RecipePantry: the denominator and the coverage gap','Root reads explain part of the low percentage; the remaining gap is real')
table(f,['Measure','Aggressive','Conservative'],[
 ['All foreground demand','167','164'],['Root demand (global + user)','39','39'],
 ['Used prefetch','112','51'],['All-demand coverage','67.07%','31.10%'],
 ['Non-root observed coverage','112 / 128 = 87.50%','51 / 125 = 40.80%']],widths=[.44,.28,.28],rowh=.074,size=17)
note(f,'The root-excluded view changes only the denominator; it does not erase business misses.\nAggressive has 3 confirmed filter-only cooked Meal prefetches in ShoppingList, despite zero unused\nprefetches. Conservative still has substantially lower coverage, not a universal precision advantage.',y=.18,size=16)

f=page('Why Conservative misses later Accesses','Current implementation gap: unresolved origin ends the executable prefix')
box(f,.07,.52,.25,.19,'Ability entry hook','Compile/select Access prefix\nmeal = jobj(self.meal_id)',AGG)
box(f,.39,.52,.25,.19,'Origin becomes known','Native jobj returns Meal\nNo new Access checkpoint',RED)
box(f,.71,.52,.22,.19,'Ordinary helper','_requirements(meal)\nNormal demand reads')
arrow(f,(.325,.61),(.382,.61));arrow(f,(.645,.61),(.702,.61))
text(f,.09,.42,'Meal  →  Recipe  →  Requirement  →  Ingredient',27,NAVY,'bold')
bullet(f,.31,'CookMeal has no later explicit graph query after this helper','It checks stock and writes inventory / Consumption edges. The queries are inside the helper.')
note(f,'PlanMeal / CookMeal / BuyIngredient have no later prefetch submissions in these captures.\nA later ability entry can trigger prefetch, but an ordinary helper call is not a new ability entry.',y=.15,size=16)

f=page('SQL counts are a separate outcome','These precision captures do not establish an uninstrumented latency speedup')
table(f,['App','Aggressive data / control','Conservative data / control'],[
 [names[a],f'{G[a,"aggressive"]["data_sql"]} / {G[a,"aggressive"]["control_sql"]}',
  f'{G[a,"conservative"]["data_sql"]} / {G[a,"conservative"]["control_sql"]}'] for a in apps],
 widths=[.26,.37,.37],rowh=.095,size=19)
bullet(f,.32,'JDrive combines pruning with fewer data queries','LittleX has almost equal SQL counts. RecipePantry still uses more data queries in Conservative.')
note(f,'A Session demand is not necessarily a new SQL call. These are separate measurements.\nAdditional Access paths reuse the existing resolver; they are not all fused into one SQL statement.',y=.17,size=17)

f=page('What to improve next','Recover useful coverage without replacing selective analysis with broad traversal')
bullet(f,.73,'1  Model direct identity lookup as an Access origin','jobj(id) → object identity → typed subsequent graph paths.')
bullet(f,.56,'2  Resume after the last unresolved dependency','Insert a checkpoint after meal becomes known; preserve effects and native execution order.')
bullet(f,.39,'3  Extend the necessity audit','Separate payload, predicate columns and identity-only reads; keep root/entry demands visible.')
bullet(f,.22,'4  Re-test both objectives','Report useful coverage and confirmed unnecessary fetches together; keep slow/unsupported cases.')

f=page('Evidence and scope','All plotted figures come from immutable accepted captures or explicitly labelled historical counts')
bullet(f,.73,'24 captures / 18 measured / 6 excluded warmups','Native responses, persisted state, restarts, fresh sessions and GIL-off checks passed.')
bullet(f,.56,'Raw precision audit','1,920 sealed files rehashed; all measured counts identical across three repetitions.')
bullet(f,.39,'Editable and reproducible','slide-data.json + derive.py + render.py; accepted results.json / table.csv and raw case archives.')
note(f,'Definitions: “hit rate” here is observed demand coverage. “Unnecessary” is avoidable full-node payload,\nnot “not visited.” Confirmed unnecessary counts are lower bounds, not complete semantic-minimality proofs.\nNo DB experiment was added to produce this presentation.',y=.23,size=16)

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
manifest=dict(pages=len(pages),titles=labels,source=ref(Path(__file__)),data=ref(HERE/'slide-data.json'),
              outputs=[ref(p) for p in sorted(OUT.iterdir()) if p.name!='report-manifest.json'])
(OUT/'report-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps({'pdf':str(pdf),'pages':len(pages),'sha256':ref(pdf)['sha256']}))
