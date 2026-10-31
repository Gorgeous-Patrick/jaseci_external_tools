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
        lines=['Protocol completion wall includes row decoding/client progress, not server CPU alone.',
            'Sum/union gaps cover any overlapping calls; FG/BG overlap is a separate metric.',
            'Late prefetch SQL remains attributed to its original business request.',
            'Process startup/IPC remains in raw model/lifecycle evidence; no guessed subtraction.',
            'SQL logging is off in measured trials; independent reconciliation uses separate controls.',
            'Instrumented HTTP is auxiliary. No clean e2e or application-CPU conclusion is claimed.']
        for i,line in enumerate(lines):fig.text(.065,.73-i*.079,line,fontsize=17)
        fig.text(.065,.16,'Accepted export SHA256: '+sha(source/'results.json'),fontsize=11)
        fig.text(.065,.11,'Main authorization SHA256: '+data['authorization']['sha256'],fontsize=11)
        save(pdf,fig)
    report.extend(['## Evidence','', 'All raw samples/query traces, actual backend/child PID pairs, model outcomes and phase exclusions are referenced by results.json.',
        'Actual interval overlap is not proof of simultaneous server CPU execution. No clean application-e2e dataset or CPU profile is claimed.',
        'Numeric export SHA256: '+sha(source/'results.json'),
        'Main authorization SHA256: '+data['authorization']['sha256'],''])
    (out/'report.md').write_text('\n'.join(report))
    manifest=dict(passed=True,pages=pages,renderer=dict(path=str(Path(__file__).resolve()),sha256=sha(__file__)),
        input_export=dict(path=str(source/'results.json'),sha256=sha(source/'results.json')),
        input_seal=dict(path=str(source/'artifacts.json'),sha256=sha(source/'artifacts.json')),
        matplotlib_version=matplotlib.__version__,files={p.name:sha(p) for p in out.iterdir() if p.is_file()})
    (out/'report-integrity.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps(dict(passed=True,pages=pages,PDF=str(pdf_path),sha256=sha(pdf_path))))


if __name__=='__main__':main()
