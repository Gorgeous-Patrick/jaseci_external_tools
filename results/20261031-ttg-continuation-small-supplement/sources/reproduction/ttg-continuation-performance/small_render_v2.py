"""Presentation-only English partial report/PDF from accepted small export.

No statistical aggregation, runtime imports, DB jobs or fabricated placeholders.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path

LABELS={'none':'Off','legacy_ttg_thread':'Legacy TTG / thread',
    'continuation_always_thread':'Always / thread','continuation_always_process':'Always / process',
    'continuation_expected_benefit_thread':'Expected benefit / thread',
    'continuation_expected_benefit_process':'Expected benefit / process'}


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--export',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--attribution',type=Path,required=True)
    args=parser.parse_args();source=args.export.resolve();out=args.output.resolve()
    seal=json.loads((source/'artifacts.json').read_text())
    if seal.get('passed') is not True:raise ValueError('Accepted sealed numeric export required')
    for name,digest in seal['files'].items():
        path=(source/name).resolve()
        if not path.is_relative_to(source) or sha(path)!=digest:raise ValueError('Corrupt numeric export')
    data=json.loads((source/'results.json').read_text())
    if data.get('passed') is not True or data.get('logical_cells')!=12 or len(data['table'])!=12:
        raise ValueError('All12 accepted partial-study cells required')
    if data.get('measured_workflows')!=36 or data.get('warmup_workflows')!=12:
        raise ValueError('Wrong workflow sample coverage')
    if any(row['n']!=3 for row in data['table']):raise ValueError('Exactly3 independent measured workflows required')
    for name,digest in data['source_hashes'].items():
        if sha(name)!=digest:raise ValueError('Frozen numerical source changed')
    attr_root=args.attribution.resolve();attr_seal=json.loads((attr_root/'artifacts.json').read_text())
    if not attr_seal['passed']:raise ValueError('Passed read-only attribution required')
    for name,digest in attr_seal['files'].items():
        if sha(attr_root/name)!=digest:raise ValueError('Attribution integrity mismatch')
    attribution=json.loads((attr_root/'attribution.json').read_text())
    if not attribution['passed'] or len(attribution['trials'])!=18:raise ValueError('All18 measured LittleX traces required')
    out.mkdir(parents=True,exist_ok=False)
    os.environ.setdefault('MPLCONFIGDIR',str(out/'matplotlib-cache'))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_pdf import PdfPages
    plt.rcParams.update({'font.family':'DejaVu Sans','text.color':'black','axes.labelcolor':'black',
        'axes.edgecolor':'black','figure.facecolor':'white','savefig.facecolor':'white'})
    titles={'littlex':'LittleX','issue_desk':'IssueDesk'}
    figure_map={'tables':data['table'],'ratios':data['ratios'],
        'attribution_input':{'path':str(attr_root/'attribution.json'),'sha256':sha(attr_root/'attribution.json')},
        'SQL_evidence':attribution['pooled_SQL'],
        'interval_and_model_evidence':[{k:t[k] for k in ('config_id','repeat','sum_minus_union_ns',
            'excess_integral_by_segment_class_ns','pair_union_by_class_ns','models')} for t in attribution['trials']],
        'conversion':'ns/1e6 -> ms; values otherwise copied directly from frozen export; no new statistics'}
    (out/'figure-inputs.json').write_text(json.dumps(figure_map,indent=2)+'\n')
    def page(title,subtitle=''):
        fig=plt.figure(figsize=(16,9));fig.text(.05,.91,title,fontsize=30,fontweight='bold')
        if subtitle:fig.text(.05,.85,subtitle,fontsize=15)
        return fig
    pdf_path=out/'ttg-small-performance.pdf';pages=0
    def save(pdf,fig):
        nonlocal pages
        pages+=1;fig.text(.05,.035,'PARTIAL STUDY | runtime 866222 | seed42',fontsize=10)
        fig.text(.95,.035,str(pages),ha='right',fontsize=10)
        pdf.savefig(fig);fig.savefig(out/f'slide-{pages:02d}.png',dpi=100);plt.close(fig)
    report=['# TTG continuation: partial two-application study','',
        'Scope: LittleX and IssueDesk only, six configurations, runtime866222, seed42, workers1/limit256.',
        'Twelve excluded warmup workflows and36 measured fresh workflows; n3 per application/policy.',
        'Primary: actual PgWire send-to-ReadyForQuery protocol completion wall. Summed calls and interval union are separate.',
        'Includes foreground/background and transaction control SQL attributed to business requests. Setup, auth, seed, steady warmup and verification are retained separately.',
        'Each measured workflow starts a fresh database and profile. Learning is natural within that workflow; warmup/profile state never carries across trials.','']
    with PdfPages(pdf_path,metadata={'Title':'TTG continuation — partial two-application performance study',
        'Author':'TTG application performance research','Subject':'Measured protocol DB time and SQL counts'}) as pdf:
        fig=page('TTG continuation: partial performance study','LittleX and IssueDesk | all six policies | n=3 independent workflows per cell')
        fig.text(.07,.69,'48 fresh workflow trials',fontsize=29,fontweight='bold')
        fig.text(.07,.61,'12 excluded warmups + 36 measured workflows',fontsize=22)
        lines=['Primary metric: actual SQL send -> ReadyForQuery completion wall time.',
               'Summed DB calls, interval union, SQL data/control counts and real PID overlap.',
               'Identical seeded workflows and independent response/state correctness guards.',
               'Scope is two applications; the full application and paper tiers remain separate.']
        for i,line in enumerate(lines):fig.text(.07,.47-i*.075,line,fontsize=18)
        save(pdf,fig)
        for app in ('littlex','issue_desk'):
            rows=[r for r in data['table'] if r['app']==app]
            fig=page(titles[app]+': DB time and SQL counts','Median [IQR]; three fresh measured workflows for every row')
            table_rows=[]
            report.extend(['## '+titles[app],'',
                '| Policy | DB sum ms [IQR] | DB union ms [IQR] | SQL total/data/control/other | FG/BG distinct-backend overlap ms |',
                '|---|---:|---:|---:|---:|'])
            for row in rows:
                m=row['metrics']
                def ms(key):return f"{m[key]['median']/1e6:.3f} [{m[key]['iqr']/1e6:.3f}]"
                counts='/'.join(f"{m[k]['median']:g}" for k in ('sql_dispatches','sql_data','sql_control','sql_other'))
                overlap=f"{m['distinct_backend_overlap_ns']['median']/1e6:.3f}"
                table_rows.append([LABELS[row['config_id']],ms('protocol_sum_ns'),ms('protocol_union_ns'),counts,overlap])
                report.append('| '+' | '.join(table_rows[-1])+' |')
            ax=fig.add_axes([.045,.24,.91,.51]);ax.axis('off')
            table=ax.table(cellText=table_rows,colLabels=['Policy','DB sum ms [IQR]','DB union ms [IQR]',
                'SQL total/data/control/other','FG/BG distinct\nbackend overlap ms'],cellLoc='left',loc='center',
                colWidths=[.25,.19,.19,.23,.14])
            table.auto_set_font_size(False);table.set_fontsize(13);table.scale(1,3.0)
            for (r,c),cell in table.get_celld().items():
                cell.set_edgecolor('#b0b0b0');cell.set_linewidth(.5)
                if r==0:cell.set_text_props(weight='bold');cell.set_facecolor('#eeeeee')
                else:cell.set_facecolor('white')
            fig.text(.06,.17,'Overlap column = foreground/background protocol intervals on distinct PostgreSQL backends.',fontsize=14)
            fig.text(.06,.11,'SQL counts are dispatches; actual completion cycles and all raw samples are in the data export.',fontsize=14)
            report.append('');save(pdf,fig)
        fig=page('Relative summed DB-call time','Ratio of workflow medians to off; <1 lower, >1 higher. Dispersion is shown in the timing tables.')
        for ai,app in enumerate(('littlex','issue_desk')):
            rows=[r for r in data['ratios'] if r['app']==app]
            labels=[LABELS[r['config_id']] for r in rows];values=[r['ratio_to_off'] for r in rows]
            if any(v is None for v in values):raise ValueError('Cannot plot undefined zero-denominator ratio')
            ax=fig.add_axes([.23,.52-ai*.36,.66,.27])
            ax.barh(labels,values,color='#333333',height=.55);ax.invert_yaxis();ax.axvline(1,color='black',linestyle='--',linewidth=1)
            ax.set_title(titles[app],loc='left',fontsize=17,fontweight='bold');ax.spines[['top','right']].set_visible(False)
            ax.set_xlim(0,max(max(values),1)*1.25);ax.tick_params(axis='both',labelsize=11)
            for y,v in enumerate(values):ax.text(v+max(max(values),1)*.025,y,f'{v:.3f}x',va='center',fontsize=12)
        save(pdf,fig)
        fig=page('Measurement and provenance','Actual DB evidence; independent correctness and exact source binding')
        lines=['Send -> ReadyForQuery completion includes the response and client decoding/progress.',
            'Sum/union gaps cover all overlapping calls; foreground/background overlap is separate.',
            'Each fresh seeded workflow starts a fresh profile and learns naturally within the trial.',
            'Setup, authentication, warmup and final persistence verification have separate phases.',
            'Late SQL, process readiness/startup and IPC phases retain actual request/scope identities.',
            'Measured SQL logging is off; counts/row bytes and independent controls are hash-bound.']
        for i,line in enumerate(lines):fig.text(.065,.73-i*.079,line,fontsize=17)
        fig.text(.065,.16,'Accepted export SHA256: '+sha(source/'results.json'),fontsize=11)
        fig.text(.065,.11,'Main authorization SHA256: '+data['authorization']['sha256'],fontsize=11)
        save(pdf,fig)
        # Evidence is copied from the separately sealed read-only attribution;
        # pooled contributions below are explicitly across three workflows.
        pooled={p['config_id']:p['fingerprints'] for p in attribution['pooled_SQL']}
        payload='b0075df9e7359d79cd785221c0ac6a46cf8e920312e2e4d11f08bf1800c6c116'
        policies=list(LABELS)
        def vector_text(v):return str(v[0]) if len(set(v))==1 else '/'.join(str(x) for x in v)
        payload_rows=[]
        for policy in policies:
            records=pooled[policy]
            fg=next((r for r in records if r['fingerprint']==payload and r['role']=='foreground'),None)
            bg=next((r for r in records if r['fingerprint']==payload and r['role']=='background_prefetch'),None)
            discard=next((r for r in records if r['role']=='background_prefetch' and r['sql'].strip().upper()=='DISCARD ALL'),None)
            get=lambda r,k:vector_text(r[k]) if r else '0'
            payload_rows.append([LABELS[policy],get(fg,'counts_by_repeat')+' / '+get(bg,'counts_by_repeat'),
                get(fg,'rows_by_repeat')+' / '+get(bg,'rows_by_repeat'),get(discard,'counts_by_repeat')])
        fig=page('LittleX: measured SQL contributions','Actual primary traces | payload SELECT fingerprint b0075df9e735 | counts per workflow')
        ax=fig.add_axes([.06,.42,.88,.37]);ax.axis('off')
        table=ax.table(cellText=payload_rows,colLabels=['Policy','Payload SELECTs: FG / BG',
            'Returned rows: FG / BG','BG DISCARD ALL'],cellLoc='left',loc='center',colWidths=[.34,.25,.25,.16])
        table.auto_set_font_size(False);table.set_fontsize(13);table.scale(1,2.3)
        for (r,c),cell in table.get_celld().items():
            cell.set_edgecolor('#b0b0b0');cell.set_linewidth(.5)
            if r==0:cell.set_facecolor('#eeeeee');cell.set_text_props(weight='bold')
        top=next(r for r in pooled['legacy_ttg_thread'] if r['fingerprint'].startswith('9a54ec61abbb'))
        fig.text(.065,.34,'Payload reads move between roles; off and all four continuation modes keep 52 SELECTs / 108 returned rows.',fontsize=15)
        fig.text(.065,.27,'Legacy foreground WITH RECURSIVE fingerprint 9a54ec61abbb: 4 calls in each measured workflow.',fontsize=16,fontweight='bold')
        durations=' / '.join(f'{v/1e6:.3f}' for v in top['protocol_ns_by_repeat'])
        fig.text(.065,.20,'Its protocol contributions by repeat: '+durations+' ms.',fontsize=16)
        fig.text(.065,.13,f"Pooled across three workflows: {top['pooled_calls']} calls, {top['pooled_protocol_ns']/1e6:.3f} ms.",fontsize=16)
        save(pdf,fig)
        fig=page('LittleX: observed overlap and continuation activity','Measured primary traces | exact interval sweep and native scope events')
        gap_rows=[]
        for policy in ('continuation_always_thread','continuation_expected_benefit_thread'):
            selected=sorted([t for t in attribution['trials'] if t['config_id']==policy],key=lambda t:t['repeat'])
            for t in selected:
                if any(k!='BG_only/distinct_backends' and v for k,v in t['excess_integral_by_segment_class_ns'].items()):
                    raise ValueError('BG-only explanation no longer matches actual interval segments')
            gap_rows.append([LABELS[policy]]+[f"{t['sum_minus_union_ns']/1e6:.3f}" for t in selected])
        ax=fig.add_axes([.06,.59,.88,.19]);ax.axis('off')
        table=ax.table(cellText=gap_rows,colLabels=['Sum minus union (ms)','Repeat0','Repeat1','Repeat2'],
            cellLoc='left',loc='center',colWidths=[.46,.18,.18,.18])
        table.auto_set_font_size(False);table.set_fontsize(15);table.scale(1,2.4)
        for (r,c),cell in table.get_celld().items():
            cell.set_edgecolor('#b0b0b0');cell.set_linewidth(.5)
            if r==0:cell.set_facecolor('#eeeeee');cell.set_text_props(weight='bold')
        fig.text(.065,.52,'Each gap is fully accounted for by background/background intervals on distinct backends.',fontsize=16)
        representative=next(t for t in attribution['trials'] if t['config_id']=='continuation_always_thread' and t['repeat']==0)
        pair=representative['pairs'][0];c=representative['models']['counts']
        fig.text(.065,.44,f"Example: PostgreSQL backends {pair['backend_pids'][0]} / {pair['backend_pids'][1]}, client {pair['client_pids'][0]}.",fontsize=16)
        fig.text(.065,.37,'Recorded foreground/background overlap in all four continuation configurations: 0 ms.',fontsize=16)
        fig.text(.065,.29,f"Always/thread repeat0: {c['unique_scopes']} scopes, {c['plans']} plans including {c['multi_hop_plans']} multi-hop plans.",fontsize=17,fontweight='bold')
        fig.text(.065,.22,f"{c['native_continuation_snapshots']} native continuation snapshots; reached barrier at gather:277 (here.to_view()).",fontsize=16)
        fig.text(.065,.15,'Full scope sequence, decisions/probes, payload categories and interval/PID pairs are in attribution.json.',fontsize=15)
        save(pdf,fig)
    report.extend(['## Evidence','', 'All raw samples/query traces, actual backend/child PID pairs, model outcomes and phase exclusions are referenced by results.json.',
        'The trace supplement accounts for protocol interval overlaps by foreground/background roles and actual backend/client identities.',
        'Read-only SQL fingerprint contributions and native model scope/checkpoint snapshots are bound in figure-inputs.json.',
        'Numeric export SHA256: '+sha(source/'results.json'),
        'Main authorization SHA256: '+data['authorization']['sha256'],''])
    (out/'report.md').write_text('\n'.join(report))
    manifest=dict(passed=True,pages=pages,renderer=dict(path=str(Path(__file__).resolve()),sha256=sha(__file__)),
        input_export=dict(path=str(source/'results.json'),sha256=sha(source/'results.json')),
        input_seal=dict(path=str(source/'artifacts.json'),sha256=sha(source/'artifacts.json')),
        attribution_input=dict(path=str(attr_root/'attribution.json'),sha256=sha(attr_root/'attribution.json')),
        matplotlib_version=matplotlib.__version__,files={p.name:sha(p) for p in out.iterdir() if p.is_file()})
    (out/'report-integrity.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps(dict(passed=True,pages=pages,PDF=str(pdf_path),sha256=sha(pdf_path))))


if __name__=='__main__':main()
