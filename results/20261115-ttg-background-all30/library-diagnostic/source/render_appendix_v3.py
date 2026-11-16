"""Three-page additive diagnostic appendix using the accepted Deck and pdfunite."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[2]
BASE=ROOT/'project-notes/measurements/ttg-background-pushdown-portfolio-report-20261115/report-candidate-v2e/ttg-background-pushdown-all30.pdf'
STYLE=ROOT/'reproduction/ttg-background-pushdown-portfolio-report-20261115/render_report_v2.py'


def ref(p):
    p=Path(p)
    return dict(path=str(p.resolve()),sha256=hashlib.sha256(p.read_bytes()).hexdigest())


def load_checked(item):
    p=Path(item['path']);assert ref(p)['sha256']==item['sha256'];return json.loads(p.read_text())


def build(deck,data):
    traced=[c for c in data['cases']if c['mode']=='restored'and c['traced']]
    off=next(c for c in data['cases']if c['mode']=='off')
    count=lambda c,k:c['classification']['ordinary_access']['outcomes'].get(k,0)
    p=deck.page('LibraryLoans: some exact-key prefetch arrives too late',
        'Three separate traced Restored workflows: 24–26 / 140 ordinary Access resolutions found matching work still pending.',
        kind='New diagnostic • 23 business HTTP per workflow • not primary n5')
    rows=[]
    labels=[('Background-publication cache hit','hit_background_publication'),
            ('Native-query cache hit','hit_native_access_cache'),
            ('Exact key: Future pending through lookup','future_pending_through_lookup'),
            ('Uncovered by observed materialized jobs','uncovered_by_observed_materialized_jobs'),
            ('Unknown job/key coverage','unknown_job_coverage'),
            ('No preexisting observed job','no_preexisting_observed_job')]
    for name,key in labels:rows.append([name,str(count(off,key))]+[str(count(c,key))for c in traced])
    deck.table(p,['Ordinary Access outcome (N = 140 each)','Off traced','Restored 0','Restored 1','Restored 2'],rows,
        widths=[.48,.13,.13,.13,.13],area=(.065,.405,.87,.35),size=13)
    deck.text(p,.07,.365,'Three background-attributed path hits per Restored run; total path hits remain 15: Off 15 native versus Restored 12 native + 3 background. This is not three proved avoided SQL calls.',14,width=.86)
    deck.text(p,.07,.285,'Separate payload callback denominator: 303 (logical get/batch call, requested UID) per traced workflow.',13,width=.86)
    deck.table(p,['Observed payload callbacks','Off','Restored 0 / 1 / 2'],[
        ['Native load_full returned the requested UID','237','237 / 237 / 237'],
        ['Memory or unclassified by these callbacks','66','66 / 66 / 66'],
        ['Observed background raw-promotion service','0','0 / 0 / 0']],
        widths=[.59,.14,.27],area=(.065,.14,.87,.125),size=11)
    deck.text(p,.07,.11,'Path denominator: one native logical resolver, nested emitted/ordinary lookups counted once; from_visit=False. Visit-backed resolutions are separate (17 each). Valid empty paths are hits.',11,width=.86)

    chosen=traced[0];timeline=load_checked(chosen['classification']['timeline'])
    a=timeline['access'];zero=timeline['job_capture']['ns']
    ms=lambda ns:(ns-zero)/1e6
    # Select the actual ordinary SQL key, not its emitted alias or fingerprint.
    from classify_timeliness import decoded
    ordinary=next(x for x in a['lookups']if decoded(timeline['key_definitions'][x['key_id']])[0]=='pairs')
    emitted=next(x for x in a['lookups']if decoded(timeline['key_definitions'][x['key_id']])[0]=='ttg_compiled_pairs_v1')
    phase=lambda name:next(x for x in timeline['phases']if x['native_event']['phase']==name)
    done=next(x for x in timeline['future_observations']if x['kind']=='future_done_observed')
    publication=next(x for x in timeline['publication']if x['key_id']==ordinary['key_id'])
    native=a['exact_native_sql'][0]
    interval=lambda x:f"{ms(x['lookup_start_ns']):.3f}–{ms(x['lookup_end_ns']):.3f}"
    p=deck.page('Actual same-key timeline: native read precedes availability',
        'Restored trace 0 • request 1:6 (PlaceHold) • root→Library helper Access. Times are relative to job capture / pre-submit.',
        kind='Exact key + PID / Session / epoch; one observed execution')
    deck.table(p,['Observed event','ms after capture','Meaning'],[
        ['Job captured / pre-submit','0.000','Snapshot export and owner checks occurred earlier.'],
        ['Worker started event',f"{ms(phase('started')['observed_start_ns']):.3f}",'Private job begins; no result yet.'],
        ['Emitted-alias lookup',interval(emitted),'MISS'],
        ['Exact ordinary SQL-key lookup',interval(ordinary),'MISS; Future.done false before and after.'],
        ['Native _run observer bracket',f"{ms(native['begin']['ns']):.3f}–{ms(native['end']['ns']):.3f}",'Owner executes the same path SQL.'],
        ['Worker completed-phase entry',f"{ms(phase('completed')['observed_start_ns']):.3f}",'Result-ready phase; not Future-ready.'],
        ['Worker return after cleanup',f"{ms(timeline['worker_return']['ns']):.3f}",'Actual exact-key result materialized.'],
        ['Future.done callback observed',f"{ms(done['ns']):.3f}",'Observed upper bound, not exact transition.'],
        ['Owner stores exact SQL key',f"{ms(publication['ns']):.3f}",'Publication after the native query.']],
        widths=[.37,.19,.44],area=(.065,.265,.87,.49),size=12)
    deck.text(p,.07,.225,f"Exact key {ordinary['key_id'][:16]}… • PID {a['pid']} • Session {timeline['job_capture']['session']} / epoch {timeline['job_capture']['epoch']} • job …{timeline['job_capture']['job_id'][-10:]}",12,width=.86)
    deck.text(p,.07,.17,'Frozen app source: _library:36 → _owns_title:41 → PlaceHold.hold:219. Actual key retains origin UUID, Library class/type, direction and actor/ACL parameters; SQL equality is exact, not fingerprint-only.',13,width=.86)
    deck.text(p,.07,.12,'The recorded job later returns this exact key in the same epoch. Availability was late for this lookup; this does not establish that moving the hook would improve business latency.',12,width=.86)

    p=deck.page('Interpretation and instrumentation limits',
        'Five fresh accepted workflows on frozen restored runtime 93ea / 5cb1; all native/state/restart/physical/GIL checks pass.',
        kind='Diagnostic timing, separate from the original n5 study')
    rows=[]
    for c in data['cases']:
        label=('Off traced'if c['mode']=='off'else f"Restored traced {c['repeat']}"if c['traced']else'Restored observer-disabled')
        rows.append([label,f"{c['HTTP_response_sum_ms']:.3f}",str(c['data_SQL']),str(c['control_SQL']),str(c['TOTAL_SQL'])])
    deck.table(p,['Fresh diagnostic workflow','HTTP sum ms','Data SQL','Control SQL','TOTAL SQL'],rows,
        widths=[.40,.18,.14,.14,.14],area=(.065,.455,.87,.30),size=13)
    deck.text(p,.07,.405,'Tracing changed observed timing and scheduling: Restored 385.568–395.768 ms / 987–1,011 SQL versus observer-disabled 331.104 ms / 954 SQL. The n1 control is not an isolated per-event overhead estimate.',15,width=.86)
    deck.card(p,.065,.16,.40,.185,'Direct measured answer','24–26 exact-key ordinary misses occur while matching Futures remain pending; the selected native query finishes before its job result and publication.')
    deck.card(p,.535,.16,.40,.185,'Limits retained','44–47 uncovered / 52–57 unknown cases remain distinct. Zero classified ready-unpublished or invalidated does not rule them out inside unknown coverage.',color='#b76b31')
    deck.text(p,.07,.12,'Payload zero is only zero observed background raw-promotion through covered callbacks. No CPU residual, causal hook-placement test, all-payload/usefulness claim, or transfer of these percentages to the primary n5.',11,width=.86)


def render(summary,output):
    spec=importlib.util.spec_from_file_location('accepted_all30_style',STYLE)
    style=importlib.util.module_from_spec(spec);spec.loader.exec_module(style)
    class AppendixDeck(style.Deck):
        def save(self):
            path=self.output/'appendix-only.pdf';violations=[]
            with self.PdfPages(path)as pdf:
                for i,f in enumerate(self.pages,29):
                    footer=self.text(f,.055,.045,'TTG • 2026-11-16 • LibraryLoans diagnostic appendix',10,width=.82,color=style.MUTED)
                    number=self.text(f,.94,.045,str(i),10,width=.03,color=style.MUTED)
                    f.canvas.draw();renderer=f.canvas.get_renderer();w,h=f.bbox.width,f.bbox.height;checks=[]
                    for t in f._tracked:
                        b=t.get_window_extent(renderer);box=[b.x0/w,b.y0/h,b.x1/w,b.y1/h]
                        if box[0]<.035 or box[2]>.965 or box[1]<.018 or box[3]>.95:violations.append((i,'bounds',t.get_text()))
                        if t is not footer and t is not number and box[1]<.06:violations.append((i,'footer',t.get_text()))
                        if hasattr(t,'_cell_bounds'):
                            x0,y0,x1,y1=t._cell_bounds
                            if box[0]<x0-.002 or box[2]>x1+.002 or box[1]<y0-.003 or box[3]>y1+.003:violations.append((i,'cell',t.get_text()))
                        checks.append(dict(text=t.get_text(),bounds=box))
                    self.checks.append(dict(page=i,text=checks));pdf.savefig(f)
                    f.savefig(self.output/f'appendix-page-{i}.png',dpi=100);self.plt.close(f)
            (self.output/'layout-checks.json').write_text(json.dumps(dict(passed=not violations,violations=violations,pages=self.checks),indent=2)+'\n')
            if violations:raise ValueError(str(violations))
            return path
    assert ref(BASE)['sha256']=='de0a661d0af1f26f15e9eb46dd1d8e0697f5c021a44e1154b127c63f37a67ee1'
    assert ref(summary)['sha256']=='e43d7fd47c85890eb1981068fdcd1edc7ec35bc28ce6e9beb6140f5bf613e01f'
    data=json.loads(Path(summary).read_text());assert data['passed']
    output=Path(output);output.mkdir(parents=True,exist_ok=False)
    deck=AppendixDeck(output,dict(recorded_date='2026-11-16'),True);build(deck,data);appendix=deck.save()
    merged=output/'ttg-background-pushdown-all30-with-library-diagnostic.pdf'
    subprocess.run(['pdfunite',str(BASE),str(appendix),str(merged)],check=True)
    text=lambda p:subprocess.check_output(['pdftotext','-f','1','-l','28','-layout',str(p),'-'])
    assert text(BASE)==text(merged),'Original first28 extracted text changed'
    # Native PDF raster validation only; original Matplotlib pages are never regenerated.
    from PIL import Image
    pageproof=[]
    with tempfile.TemporaryDirectory(dir=output,prefix='page-proof-')as temp:
        for name,pdf in [('original',BASE),('appended',merged)]:
            sub=Path(temp)/name;sub.mkdir()
            subprocess.run(['pdftoppm','-f','1','-l','28','-scale-to','800','-png',str(pdf),str(sub/'page')],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
        originals=sorted((Path(temp)/'original').glob('*.png'));copies=sorted((Path(temp)/'appended').glob('*.png'))
        assert len(originals)==len(copies)==28
        for n,(a,b)in enumerate(zip(originals,copies),1):
            with Image.open(a)as ia,Image.open(b)as ib:
                assert ia.size==ib.size and ia.convert('RGB').tobytes()==ib.convert('RGB').tobytes()
                pageproof.append(dict(page=n,size=ia.size,RGB_sha256=hashlib.sha256(ia.convert('RGB').tobytes()).hexdigest(),equal=True))
    (output/'first28-preservation.json').write_text(json.dumps(dict(passed=True,base=ref(BASE),appended=ref(merged),method='pdfunite append; first28 text exact and native800px raster RGB equal',pages=pageproof),indent=2)+'\n')
    (output/'figure-inputs.json').write_text(json.dumps(dict(summary=ref(summary),data=data,style=ref(STYLE),renderer=ref(__file__),base=ref(BASE)),indent=2)+'\n')
    files=[ref(p)for p in sorted(output.iterdir())if p.is_file()]
    manifest=dict(passed=True,base_pages=28,appended_pages=3,pages=31,pdf=ref(merged),appendix=ref(appendix),summary=ref(summary),renderer=ref(__file__),style=ref(STYLE),outputs=files)
    m=output/'appendix-manifest.json';m.write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps(dict(pdf=ref(merged),manifest=ref(m),pages=31)))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--summary',required=True);p.add_argument('--output',required=True)
    args=p.parse_args();render(args.summary,args.output)
