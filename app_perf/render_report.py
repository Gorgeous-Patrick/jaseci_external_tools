#!/usr/bin/env python3
"""Render English report and vector PDF slides only from complete actual results."""
import argparse
import hashlib
import json
from pathlib import Path
import statistics
import textwrap
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from gate import APPS,POLICIES

LABELS={'none':'None','ttg':'Original TTG','dependency_always':'Dependency: always','dependency_expected_benefit':'Dependency: expected benefit'}
COLORS={'ttg':'#176d99','dependency_always':'#e58a2b','dependency_expected_benefit':'#34885a'}

def load(path):return json.loads(Path(path).read_text())
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def nice(app):return {'linked_list':'LinkedList','littlex':'LittleX','jdrive':'JDrive'}.get(app,''.join(word.capitalize() for word in app.split('_')))

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--experiment',type=Path,required=True)
    parser.add_argument('--review-artifacts',type=Path,required=True)
    parser.add_argument('--diagnostics',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    integrity=load(args.experiment/'results-integrity.json')
    if sha(args.experiment/'results.json')!=integrity['results_sha256'] or sha(args.experiment/'per-app-results.csv')!=integrity['csv_sha256']:
        raise ValueError('Derived result artifact integrity mismatch')
    data=load(args.experiment/'results.json')
    if data.get('complete') is not True or data.get('primary_cells')!=120:
        raise ValueError('All30 x4 measured primary cells are required')
    diagnostics=load(args.diagnostics/'diagnostics.json')
    if diagnostics.get('status')!='complete' or not all(c['passed'] for c in diagnostics['checks']):
        raise ValueError('Independent query-count/profile diagnostics are incomplete')
    explanations=load(args.experiment/'explanations.json')
    if len(explanations.get('cells',[]))!=90:raise ValueError('Missing trace-backed observations for all app/policy comparisons')
    # CPU fields in the historical explanation export are unaccepted evidence.
    # Never read leaders/comparisons into accepted report/figure inputs.
    explanations={'cells':[{k:c[k] for k in ('app','policy','observations','measured_sql_fingerprint_deltas',
        'actual_checkpoint_and_model_evidence','static_plan_summary','static_interpretation')} for c in explanations['cells']]}
    plan=load(args.review_artifacts/'plan.json')
    instrument=load(args.review_artifacts/'instrument.json')
    experiment=load(args.experiment/'experiment.json')
    main_review=args.experiment.parent.parent/'ttg-app-main-review-20261030'
    calibration=load(instrument['raw_calibration']['path'])
    coverage=load(args.review_artifacts/'preflight-diagnostic-coverage.json')
    cells={(c['app'],c['policy'],c['phase']):c for c in data['cells']}
    def timing(app,policy,phase):
        d=cells[(app,policy,phase)]['protocol_sum_ms']
        return f"{d['median']:.2f} [{d['q1']:.2f}, {d['q3']:.2f}]"
    def sql_counts(app,policy,phase):
        c=cells[(app,policy,phase)]
        # Subtraction is valid here because each count is constant across trials.
        for name in ('sql_dispatches','control_dispatches'):
            if c[name]['minimum']!=c[name]['maximum']:
                raise ValueError('Count table requires constant verified trial counts')
        total=c['sql_dispatches']['median'];control=c['control_dispatches']['median']
        return {'total':total,'non_control':total-control,'control':control}
    def counts_text(app,policy,phase):
        c=sql_counts(app,policy,phase)
        return f"{c['total']:g} / {c['non_control']:g} / {c['control']:g}"
    for app in APPS:
        for policy in POLICIES:
            if cells[(app,policy,'workflow')]['n']<3:raise ValueError('Insufficient primary repetitions')
    if [a for a in APPS if cells[(a,'ttg','workflow')]['protocol_sum_ms']['median']<cells[(a,'none','workflow')]['protocol_sum_ms']['median']]!=['linked_list']:
        raise ValueError('Observed-outcome prose no longer matches the result mapping')
    if any(cells[(a,p,'workflow')]['sql_dispatches']!=cells[(a,'none','workflow')]['sql_dispatches'] for a in APPS for p in POLICIES[2:]):
        raise ValueError('Dependency SQL-count observation no longer matches results')
    if len(coverage['cases'])!=60 or any(c['totals']['considered_plans']!=0 for c in coverage['cases']):
        raise ValueError('Zero-opportunity prose no longer matches preflight evidence')
    out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    (out/'accepted-db-observations.json').write_text(json.dumps(explanations,indent=2)+'\n')
    from dependency_coverage import summarize as summarize_dependency
    new_coverage=[]
    for case in diagnostics['checks']:
        if case['policy'] not in POLICIES[2:]:continue
        row=summarize_dependency(args.diagnostics/(case['app']+'-'+case['policy']))
        row.update(app=case['app'],policy=case['policy'],scope='Separate post-primary detailed diagnostic; not a primary timing sample')
        new_coverage.append(row)
    (out/'new-diagnostic-mechanism-coverage.json').write_text(json.dumps({'cases':new_coverage,'not_performance_samples':True},indent=2)+'\n')
    figure_data={'units':'Protocol completion wall-time sums in milliseconds; actual SQL dispatch counts',
        'tables':{phase:[{'app':app,'policies':{policy:{'protocol_sum_ms':cells[(app,policy,phase)]['protocol_sum_ms']['median'],
            'protocol_dispersion_ms':cells[(app,policy,phase)]['protocol_sum_ms'],
            'sql_dispatches':cells[(app,policy,phase)]['sql_dispatches']['median'],
            'sql_counts':sql_counts(app,policy,phase),'n':cells[(app,policy,phase)]['n']}
            for policy in POLICIES}} for app in APPS] for phase in ('workflow','first_workflow_request','steady_read')},
        'workflow_ratios':{policy:[{'app':app,'none_over_policy':cells[(app,'none','workflow')]['protocol_sum_ms']['median']/cells[(app,policy,'workflow')]['protocol_sum_ms']['median']}
            for app in APPS] for policy in POLICIES[1:]}}
    littlex=next(c for c in explanations['cells'] if c['app']=='littlex' and c['policy']=='ttg')
    recursive=[dict(q,fingerprint_sha256=hashlib.sha256(q['fingerprint'].encode()).hexdigest())
        for q in littlex['measured_sql_fingerprint_deltas'] if q['fingerprint'].startswith('WITH RECURSIVE')][:4]
    figure_data['littlex_recursive_contributors']=recursive
    diagnostic_activity=[]
    for c in new_coverage:
        before=next(p for p in coverage['cases'] if p['app']==c['app'] and p['policy']==c['policy'])
        diagnostic_activity.append(dict(app=c['app'],policy=c['policy'],
            preflight_hits=before['totals']['checkpoint_hits'],preflight_plans=before['totals']['considered_plans'],
            new_diagnostic_hits=c['totals']['checkpoint_hits'],new_diagnostic_plans=c['totals']['considered_plans']))
    figure_data['distinct_mechanism_datasets']=diagnostic_activity
    from metrics import verify_artifacts
    preflight_root=Path(instrument['preflight']['path']).parent
    checkpoint_sources=[]
    for app,filename in [('littlex','server.jac'),('jacord','server.impl.jac')]:
        directory=preflight_root/(app+'-dependency_always')
        verify_artifacts(directory,required=(filename,))
        checkpoint_sources.append(directory/filename)
    if 'Follow' not in checkpoint_sources[0].read_text().splitlines()[272] or '_message_view(here)' not in checkpoint_sources[1].read_text().splitlines()[245]:
        raise ValueError('Checkpoint source excerpt no longer matches sealed executed copies')
    inventory=[]
    for app in APPS:
        sample=next(s for s in data['samples'] if s['app']==app and s['policy']=='none' and s['phase']=='workflow' and s['repeat']==1)
        directory=Path(sample['directory'])
        verify_artifacts(directory,required=('summary.json','actions-canonical.json'))
        summary=load(directory/'summary.json')
        inventory.append(dict(app=app,seed=summary['seed'],scale=summary['scale'],
            observed_anchor_kind_counts=summary['initial_domain_kind_counts'],fixture_sha256=summary['fixture_sha256'],
            actions_sha256=summary['actions_sha256'],source_case=str(directory),
            action_list=load(directory/'actions-canonical.json')))
    (out/'workload-inventory.json').write_text(json.dumps(inventory,indent=2)+'\n')
    (out/'numeric-figure-data.json').write_text(json.dumps(figure_data,indent=2)+'\n')
    text=['# TTG application performance results','',
        'All 30 entries (one microbenchmark and 29 full applications) were measured under all four configurations at seed42. '
        'Each primary cell has at least three independent measured fresh-database trials after one excluded full-workflow warmup. '
        'The complete original app walkers and domain workflows retain their native correctness and restart oracles.','',
        '## Main observations','',
        'Legacy TTG lowered the median full-workflow protocol sum for LinkedList, while all 29 full applications had higher medians in this local workload. '
        'These are comparisons of observed medians with n=3, not statistical significance claims. '
        'Both dependency configurations issued exactly the same SQL dispatch counts as prefetch off in every app. '
        'The separately captured 60 dependency preflight cases considered zero plans despite actual checkpoint activity. '
        'No admission plan reached either model; these observations do not evaluate learned discrimination or probing. '
        'Their timing variation must not be presented as a dependency-prefetch benefit or an evaluation of trained model discrimination.','',
        '## What is measured','',
        'Primary DB protocol completion wall time runs from immediately before actual sendall of a prebuilt packet to ReadyForQuery Z. '
        'It includes PostgreSQL work, transport and driver decoding/progress. SQL construction, compiler/model CPU and parameter encoding are outside that interval. '
        'Driver-call wall time is separately retained and includes encoding. Summed DB intervals can overlap; interval union is separately reported. '
        'SQL dispatches, CommandComplete messages, protocol cycles and transaction/control commands are different measured counts. '
        'Foreground protocol time includes synchronous speculative resolution and is not pure blocked-thread wait.','',
        'Natural close ordering is preserved. A separate post-response control drains late workers and serializes evidence. '
        'Primary HTTP is labeled instrumented auxiliary data. Clean app HTTP is deferred because the frozen clean path does not honor the cold-provider reset; '
        'all clean HTTP cells remain absent. No fixed overhead subtraction is used.','',
        '## Workload results','',
        'Entries show median [Q1, Q3] summed protocol-completion milliseconds for the complete ordered workflow. '
        'Every cell has n=3 independent trials. Quartiles describe these three observations, not confidence intervals. '
        'Full ranges, standard deviations, interval unions, driver times and foreground/background counts are in CSV/JSON.','',
        '| Application | None | Original TTG | Dependency always | Dependency expected benefit |',
        '|---|---:|---:|---:|---:|']
    for app in APPS:
        row=[]
        for policy in POLICIES:
            c=cells[(app,policy,'workflow')]
            row.append(timing(app,policy,'workflow'))
        text.append('| '+nice(app)+' | '+' | '.join(row)+' |')
    for phase,label in [('first_workflow_request','First workflow request: cold model'),('steady_read','Final-state warmed read-only phase')]:
        text+=['','## '+label,'','Median [Q1, Q3] summed protocol milliseconds; n=3 independent trials.','',
            '| Application | None | Original TTG | Dependency always | Dependency expected benefit |',
            '|---|---:|---:|---:|---:|']
        for app in APPS:text.append('| '+nice(app)+' | '+' | '.join(timing(app,p,phase) for p in POLICIES)+' |')
    text+=['','## Actual SQL dispatch counts','',
        'Each entry is total / non-control data / control dispatches for the full workflow. These counts are identical across all three trials in each cell. '
        'Non-control means the measured control classifier is false, including data reads/writes and other non-control SQL. '
        'Protocol cycles and CommandComplete counts remain separate measured quantities.','',
        '| Application | None | Original TTG | Dependency always | Dependency expected benefit |',
        '|---|---:|---:|---:|---:|']
    for app in APPS:text.append('| '+nice(app)+' | '+' | '.join(counts_text(app,p,'workflow') for p in POLICIES)+' |')
    text+=['','## Fixed seed and initial graph sizes','',
        'Seed42 and smoke/domain fixtures are used throughout. Counts below retain the actual persisted anchor-kind encodings, '
        'independently validated on a dedicated native fixture. They count the domain-related census, not every auth/system anchor. '
        'Full fixture hashes and ordered action lists are in workload-inventory.json and sealed case evidence.','',
        '| Application | NodeAnchor | EdgeAnchor | Fixture SHA256 prefix |','|---|---:|---:|---|']
    for row in inventory:
        k=row['observed_anchor_kind_counts']
        text.append(f"| {nice(row['app'])} | {k.get('NodeAnchor','unknown')} | {k.get('EdgeAnchor','unknown')} | {row['fixture_sha256'][:16]} |")
    text+=['','## Cache, model and mutation interpretation','',plan['cache_state'],'',plan['model_state'],'',
        'Workflow results include accepted and rejected mutations, permission checks and reads. Seed/provision/authentication setup is excluded. '
        'Per-request authentication/root resolution and transaction completion naturally belong to each actual walker request. '
        'Final-state read-only results have three defined warmup reads and three measured reads within each independent trial; '
        'their dataset and warmed profile differ from the initial workflow. These phases are not pooled.','',
        'Original-app logical outputs, ordering/authorship and full graph topology are checked. Raw wall-clock mutation timestamps are retained; '
        'only documented source-oracle exemptions are normalized with validity and created-before-updated checks. '
        'Domain-app identities use a persistent bijection preserving references, ordering, amounts, status, URLs and embedded IDs.','',
        '## Calibration and independent checks','',
        'The main agent accepted the disclosed direct-boundary overlay after independent PG CSV validation and rotated SQL-only controls. '
        'The same effective overlay is used for all four primary configurations. The following are observed calibration deltas, '
        'not exact causal overhead estimates; raw reference dispersion is retained.','',
        '| Synthetic SQL control | Outer-call median delta (us) | Protocol/reference median delta (us) |',
        '|---|---:|---:|']
    for shape,entry in calibration['by_shape'].items():
        p=entry['options']['primary']
        text.append(f"| {shape} | {p['outer_added_ms']*1000:.3f} | {p['protocol_added_ms']*1000:.3f} |")
    text+=['',f"Independent app diagnostics checked {len(diagnostics['checks'])} representative app/policy cases against PostgreSQL CSV execute/error records. "
        'Primary/clean timing has statement logging off. Detailed bytes/model/profile runs use separate diagnostics with statement logging on; '
        'their elapsed times never replace primary samples. CPU capture was unsuccessful: main found impossible negative self/cumulative entries in 167 of 1432 profiles. '
        'All CPU leaders and comparisons are excluded, including apparently nonnegative subsets, pending controlled timer/thread validation. '
        'Raw profiles and historical CPU-derived explanation fields remain preserved as unaccepted data. '
        'Newly captured diagnostics and earlier preflight mechanism evidence remain distinct datasets.','',
        '## Dependency-prefetch mechanism coverage','',
        'The following support observations come from separately labeled correctness-preflight diagnostics, not formal timing samples. '
        'Zero opportunities are retained and do not count as successful prefetch. Actual considered plans, feature snapshots where present, decision reasons, '
        'sample/probe state, submitted/promoted/unused IDs, outcomes and source locations remain in raw events. '
        'Static compiler barriers are potential limitations; they are not labeled dynamically reached without corresponding visit/checkpoint evidence.','',
        '| Application | Always considered plans | Expected-benefit considered plans |',
        '|---|---:|---:|']
    counts={}
    for app in APPS:
        for policy in POLICIES[2:]:
            d=next(d for d in coverage['cases'] if d['app']==app and d['policy']==policy)
            counts[(app,policy)]=d['totals']['considered_plans']
        text.append(f"| {nice(app)} | {counts[(app,POLICIES[2])]} | {counts[(app,POLICIES[3])]} |")
    text+=['','## Profiles and limits','',
        'Validated per-fingerprint primary SQL times/counts and separate detailed query traces explain observed SQL contributions. '
        'CPU profiles were captured but failed validity review, so no CPU leaders/comparisons or CPU causes of DB latency are asserted. '
        'Consumed prefetch bytes and pure foreground blocked wait are unknown unless separately measured. '
        'A demanded visit is not evidence that its payload was promoted.','',
        'Accepted per-app SQL observations and static/dynamic mechanism evidence are in `accepted-db-observations.json`. '
        'The frozen historical `explanations.json` also contains CPU-derived fields; those fields are unaccepted and excluded from the report.','']
    text+=['## Newly captured diagnostic query-count validation','',
        'The following are separate post-primary diagnostics with detailed wrappers, foreground-thread CPU profiling and PG CSV logging enabled. '
        'Their timings are not primary samples. Server execute/error counts are independently reconciled by SQL fingerprint and owned database; '
        'a parse error may lack an execute log, while an execution error can overlap one.','',
        '| Application | Policy | Driver dispatches | PG execute records | PG error records |','|---|---|---:|---:|---:|']
    for c in diagnostics['checks']:
        text.append(f"| {nice(c['app'])} | {LABELS[c['policy']]} | {c['driver_dispatches']} | {c['server_execute_records']} | {c['server_error_records']} |")
    text+=['',diagnostics.get('original_checker_failure',''),
        'Supplemental strict backend-label reconciliation preserves the failed original checker and binds CSV, case seals, profiles and adapter source hashes.','']
    text+=['## Preflight versus newly captured mechanism activity','',
        'The same checkpoint-hit/considered-plan counts were observed in these separate captures. These rows are not pooled with timing trials.','',
        '| Application | Policy | Preflight hits / plans | New diagnostic hits / plans |','|---|---|---:|---:|']
    for c in diagnostic_activity:
        text.append(f"| {nice(c['app'])} | {LABELS[c['policy']]} | {c['preflight_hits']} / {c['preflight_plans']} | {c['new_diagnostic_hits']} / {c['new_diagnostic_plans']} |")
    text+=['','## Concrete primary trace evidence: LittleX','',
        'The four largest recursive fingerprint contributors below are absent with prefetch off. Their mean protocol-sum differences come from all three primary trials. '
        'The total workload medians are 42.405 ms (none) and 121.952 ms (legacy TTG); a mean fingerprint delta is not a decomposition of a median difference.','',
        '| Recursive fingerprint SHA256 prefix | Mean dispatches none → TTG | Mean protocol difference (ms) |','|---|---:|---:|']
    for q in recursive:text.append(f"| {q['fingerprint_sha256'][:12]} | {q['mean_calls_per_trial_before']:g} → {q['mean_calls_per_trial_after']:g} | {q['mean_protocol_ms_per_trial_delta']:+.3f} |")
    text.append('')
    for item in explanations['cells']:
        text.append('### '+nice(item['app'])+' — '+LABELS[item['policy']])
        text.append('')
        text.extend(item['observations']);text.append('')
        text.append('Largest observed mean per-trial fingerprint deltas from the three primary SQL traces (not a causal decomposition):')
        text.append('')
        text.append('| SQL fingerprint excerpt | Dispatch change | Protocol sum change (ms) |')
        text.append('|---|---:|---:|')
        for q in item['measured_sql_fingerprint_deltas'][:3]:
            excerpt=q['fingerprint'].replace('|','\\|').replace('`','')[:150]
            text.append(f"| `{excerpt}` | {q['mean_calls_per_trial_delta']:+.3f} | {q['mean_protocol_ms_per_trial_delta']:+.3f} |")
        text.append('')
        observed=item['actual_checkpoint_and_model_evidence']
        if observed is not None:
            checkpoint=next((c for r in observed['requests'] for c in r['checkpoint_records']),None)
            if checkpoint:
                reasons='; '.join(checkpoint.get('decision',{}).get('reasons',[]))
                text.append(f"Preflight checkpoint example: ability {checkpoint['source_ability']}, line {checkpoint['line']}, column {checkpoint['column']}; status {checkpoint.get('prefetch_status','unknown')}; reasons: {reasons}.")
                text.append('')
        static=item['static_plan_summary']
        if static:
            text.append('Static compiler examples (potential support/barriers only): '+ '; '.join(
                f"{s['walker']}: {s['supported_typed_visits']} supported typed visits, {s['potential_barriers']} barriers" for s in static[:2])+'.')
            text.append('')
    text.extend([
        'This is a local fixed-seed smoke/domain workload study. No held-out43/44 or injected-latency result is implied. '
        'OS/disk caches were not flushed. Small microsecond differences within calibration/reference variation are not established speedups. '
        'Per-cell n, quartiles/range, raw trials, dataset/source hashes and exact action lists accompany the results.','',
        '## Reproducibility artifacts','',
        f"- Raw experiment: `{args.experiment}`",
        f"- Full per-app CSV: `{args.experiment/'per-app-results.csv'}`",
        f"- Raw samples and aggregate JSON: `{args.experiment/'results.json'}`",
        f"- Main-reviewed plan/instrument manifests: `{args.review_artifacts}`",
        f"- Independent diagnostic counts/profiles: `{args.diagnostics}`"])
    text.extend(['',f"- Main export audit: `{main_review/'formal-export-audit.json'}`",
        f"- Main supplemental-diagnostic audit: `{main_review/'diagnostic-reconciliation-audit.json'}`",'',
        '| Bound input | SHA256 |','|---|---|'])
    for name,value in experiment['artifacts'].items():text.append(f"| {name} | {value['sha256']} |")
    (out/'REPORT.md').write_text('\n'.join(text)+'\n')
    with PdfPages(out/'ttg-app-performance.pdf') as pdf:
        number=[0]
        def slide(title,subtitle=''):
            fig=plt.figure(figsize=(16,9),facecolor='white');number[0]+=1
            fig.text(.055,.925,title,fontsize=25,weight='bold',color='#17334b')
            if subtitle:fig.text(.055,.88,subtitle,fontsize=12,color='#435463')
            fig.text(.055,.035,'TTG application performance | actual seed42 measurements',fontsize=10,color='#667681')
            fig.text(.94,.035,str(number[0]),fontsize=10,color='#667681')
            return fig
        def prose(title,items,subtitle=''):
            fig=slide(title,subtitle);y=.78
            for item in items:
                wrapped=textwrap.fill(item,105)
                fig.text(.07,y,wrapped,fontsize=16,va='top',linespacing=1.35)
                y-=.042*(wrapped.count('\n')+1)+.03
            pdf.savefig(fig);plt.close(fig)
        prose('TTG application performance',[
            '30 entries: one microbenchmark plus29 full applications; all4 configurations.',
            'Actual driver/socket observations, complete domain workflows, native correctness and restart checks.',
            'Seed42; >=3 independent measured primary trials per cell; one excluded workflow warmup.',
            'Primary protocol time, driver time and SQL/control counts stay separate. Clean HTTP controls are deferred.'])
        prose('Measurement boundaries',[
            'Protocol completion wall time: prebuilt packet -> real sendall -> PostgreSQL/transport/decoding -> ReadyForQuery Z.',
            'Driver-call time separately includes parameter encoding. Compiler/SQL construction/model CPU is outside protocol time.',
            'Count actual SQL dispatches, Sync/Z cycles, CommandComplete C and DataRow D; retain controls and expected errors.',
            'Natural close remains unchanged; late workers are drained and traced after the app response.'])
        prose('Observed outcomes',[
            'Legacy TTG: lower full-workflow protocol median for LinkedList; higher medians for all29 full applications in this local fixed-seed study.',
            'Both dependency policies: unchanged SQL counts versus none for every application.',
            'All60 dependency preflight cases considered zero plans. Actual checkpoint barriers remain visible; this is zero observed mechanism coverage.',
            'n=3 with dispersion reported. Timing differences without mechanism activity are not evidence of dependency-prefetch benefit.'])
        prose('Experimental controls',[
            plan['cache_state'],plan['model_state'],
            'Fresh equivalent state and deterministic actions; rotated policy order; no held-out training.',
            'Clean app HTTP/e2e is deferred: the frozen clean path does not honor the cold-provider reset. No clean times are substituted from instrumented HTTP.'])
        fig=slide('SQL-only calibration','Observed deltas and reference variation; no fixed subtraction')
        rows=[]
        for shape,e in calibration['by_shape'].items():
            p=e['options']['primary'];ref=p['reference_trial_medians_ms']
            rows.append([shape,f"{p['outer_added_ms']*1000:+.3f}",f"{p['protocol_added_ms']*1000:+.3f}",
                f"{min(ref)*1000:.2f}–{max(ref)*1000:.2f}"])
        ax=fig.add_axes([.06,.25,.88,.5]);ax.axis('off')
        table=ax.table(cellText=rows,colLabels=['Synthetic SQL','Outer delta (us)','Protocol delta (us)','Reference medians range (us)'],loc='center',cellLoc='center')
        table.auto_set_font_size(False);table.set_fontsize(14);table.scale(1,2.8)
        fig.text(.07,.15,'Rotated repeats; statement logging off for controls. Independent PG CSV checks and profiles are separate diagnostics.',fontsize=13)
        pdf.savefig(fig);plt.close(fig)
        for phase,label in [('workflow','Full ordered workflows'),('first_workflow_request','First workflow request: cold model'),('steady_read','Final-state read-only phase')]:
            for start in range(0,30,10):
                fig=slide(f'{label}: applications {start+1}–{start+10}',
                    'Each cell: median [Q1, Q3] summed protocol milliseconds. n=3 independent trials; quartiles are not confidence intervals.')
                rows=[]
                for app in APPS[start:start+10]:
                    rows.append([nice(app)]+[timing(app,p,phase) for p in POLICIES])
                ax=fig.add_axes([.055,.13,.89,.68]);ax.axis('off')
                table=ax.table(cellText=rows,colLabels=['Application','None','Original TTG','Dep. always','Dep. benefit'],loc='center',cellLoc='center')
                table.auto_set_font_size(False);table.set_fontsize(11);table.scale(1,2.6)
                if phase=='steady_read':fig.text(.06,.085,'Three measured reads after three warmup reads in each fresh trial; final mutated dataset, warmed profile.',fontsize=12)
                pdf.savefig(fig);plt.close(fig)
        for start in range(0,30,10):
            fig=slide(f'Actual SQL counts: applications {start+1}–{start+10}',
                'Full workflow: total / non-control data / control dispatches. Each count is constant across all three measured trials.')
            rows=[[nice(app)]+[counts_text(app,p,'workflow') for p in POLICIES] for app in APPS[start:start+10]]
            ax=fig.add_axes([.055,.13,.89,.68]);ax.axis('off')
            table=ax.table(cellText=rows,colLabels=['Application','None','Original TTG','Dep. always','Dep. benefit'],loc='center',cellLoc='center')
            table.auto_set_font_size(False);table.set_fontsize(13);table.scale(1,2.6)
            pdf.savefig(fig);plt.close(fig)
        fig=slide('Per-application relative protocol sums','Ratio of measured medians: none / policy. Full dispersion remains in CSV/JSON; small differences are uncertain.')
        ax=fig.add_axes([.2,.12,.74,.7])
        for i,policy in enumerate(POLICIES[1:]):
            ratios=[cells[(app,'none','workflow')]['protocol_sum_ms']['median']/cells[(app,policy,'workflow')]['protocol_sum_ms']['median'] for app in APPS]
            ax.scatter(ratios,[j+(i-1)*.2 for j in range(30)],s=25,label=LABELS[policy],color=COLORS[policy])
        ax.axvline(1,color='#555',linewidth=1);ax.set_xscale('log');ax.set_yticks(range(30),[nice(a) for a in APPS],fontsize=9)
        ax.invert_yaxis();ax.set_xlabel('None / policy protocol-sum ratio');ax.grid(axis='x',alpha=.2);ax.legend(loc='best',fontsize=10)
        pdf.savefig(fig);plt.close(fig)
        for start in range(0,30,10):
            fig=slide(f'Diagnostic mechanism coverage: {start+1}–{start+10}',
                'Observed considered dependency plans in correctness preflight; zero is retained, not a successful-prefetch claim.')
            rows=[[nice(a),counts[(a,POLICIES[2])],counts[(a,POLICIES[3])]] for a in APPS[start:start+10]]
            ax=fig.add_axes([.12,.15,.76,.65]);ax.axis('off')
            table=ax.table(cellText=rows,colLabels=['Application','Always considered','Expected-benefit considered'],loc='center',cellLoc='center')
            table.auto_set_font_size(False);table.set_fontsize(14);table.scale(1,2.5)
            pdf.savefig(fig);plt.close(fig)
        fig=slide('LittleX: measured recursive SQL contributions',
            'Primary SQL traces, n=3. Mean per-trial fingerprint contributions; distinct from workload median differences.')
        rows=[[q['fingerprint_sha256'][:12],f"{q['mean_calls_per_trial_before']:g} -> {q['mean_calls_per_trial_after']:g}",
            f"{q['mean_protocol_ms_per_trial_delta']:+.3f}"] for q in recursive]
        ax=fig.add_axes([.09,.36,.82,.38]);ax.axis('off')
        table=ax.table(cellText=rows,colLabels=['Recursive fingerprint SHA prefix','Mean dispatches: none -> TTG','Protocol-sum delta (ms)'],loc='center',cellLoc='center')
        table.auto_set_font_size(False);table.set_fontsize(14);table.scale(1,2.6)
        fig.text(.07,.25,'Workflow medians: 42.405 -> 121.952 ms. SQL dispatches: 153 -> 154; controls: 63 -> 75.',fontsize=15)
        fig.text(.07,.18,'Four added recursive fingerprints account for observed SQL contributions, alongside fewer other queries.',fontsize=14)
        fig.text(.07,.12,'Full fingerprints and three-trial values are in accepted-db-observations.json; no CPU cause is inferred.',fontsize=13)
        pdf.savefig(fig);plt.close(fig)
        prose('Reached checkpoints: precise admission barriers',[
            'LittleX load_feed.run: checkpoint at server.jac:265, Profile.collect target; stable=true, path_determined=false, execution_preserved=true; status=blocked.',
            'Its prediction reports "Unknown effect or cancellation at 273". Compiler event5 is a barrier for collect at line273: the Follow/Profile/Post/Tweet multi-hop visit.',
            'Jacord gather_messages: checkpoint at server.impl.jac:242 targets Message.collect_message; blocked because prediction reports unknown effect at246, where report _message_view(here) occurs.',
            'Line numbers refer to sealed executed preflight copies, including the Jacord adapter prefix. These are reached checkpoints with predicted barriers, not proof that future statements executed.'])
        fig=slide('Separate captures: checkpoint activity and considered plans',
            'Actual preflight versus new detailed diagnostics. Each entry is checkpoint hits / considered plans; no pooling.')
        rows=[[nice(c['app']),LABELS[c['policy']].replace('Dependency: ',''),
            f"{c['preflight_hits']} / {c['preflight_plans']}",f"{c['new_diagnostic_hits']} / {c['new_diagnostic_plans']}"] for c in diagnostic_activity]
        ax=fig.add_axes([.06,.13,.88,.68]);ax.axis('off')
        table=ax.table(cellText=rows,colLabels=['Application','Policy','Preflight','New diagnostic'],loc='center',cellLoc='center')
        table.auto_set_font_size(False);table.set_fontsize(13);table.scale(1,2.6)
        pdf.savefig(fig);plt.close(fig)
        prose('Validated diagnostics and excluded CPU capture',[
            f"{len(diagnostics['checks'])} representative app/policy diagnostic cases reconcile driver dispatches/errors with PostgreSQL CSV logs.",
            '15,413 driver dispatches = 15,373 PG execute records +40 matching expected SQL-error records; strict per-fingerprint checks passed.',
            'CPU capture was unsuccessful: 167/1432 profiles have negative self/cumulative entries. All CPU leaders/comparisons are excluded pending controlled validation.',
            'Raw profiles and the original checker failure are preserved. Primary SQL timing/counts and actual checkpoint decisions provide the accepted explanation evidence.'])
        prose('Interpretation and reproducibility',[
            'This is a local seed42 smoke/domain study. No held-out seeds or injected-latency result is implied.',
            'Summed DB intervals may overlap; interval unions and foreground/background counts are separate.',
            'Unknown payload consumption bytes and pure blocked wait stay unknown. Demand predictions are not payload promotions.',
            'Full machine tables, raw timestamps/SQL, action/data manifests, source hashes, profiles and main review artifacts accompany this deck.'])
    inputs=[args.experiment/'results.json',args.experiment/'results-integrity.json',args.experiment/'explanations.json',
        args.review_artifacts/'plan.json',args.review_artifacts/'instrument.json',args.review_artifacts/'preflight-diagnostic-coverage.json',
        args.diagnostics/'diagnostics.json',args.diagnostics/'supplemental-validation.json',Path(instrument['raw_calibration']['path']),
        args.experiment/'experiment.json',main_review/'formal-export-audit.json',main_review/'diagnostic-reconciliation-audit.json',
        main_review/'cpu-profile-audit.json']
    inputs.extend(checkpoint_sources)
    inputs.append(args.experiment.parent/'static-dependency-plans-v1.json')
    manifest={'inputs':{str(p):sha(p) for p in inputs},
        'renderer_sha256':sha(Path(__file__)),'outputs':{p.name:sha(p) for p in out.iterdir() if p.is_file()}}
    (out/'report-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(out/'ttg-app-performance.pdf')

if __name__=='__main__':main()
