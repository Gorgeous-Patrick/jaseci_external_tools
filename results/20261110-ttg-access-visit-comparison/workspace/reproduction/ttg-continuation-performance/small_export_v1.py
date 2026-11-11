"""Strict 48-workflow completeness and sealed numeric export, no DB actions."""
import argparse
from collections import Counter, defaultdict
import csv
import io
import json
from pathlib import Path
import statistics
import gate
from evidence import checked_ref, read_json, sha256, verify_case
from small_runner_v1 import APPS, schedule, sources, validate_release
from small_metrics_v1 import summarize

FIELDS = ('protocol_sum_ns','protocol_union_ns','driver_sum_ns','driver_union_ns',
          'sql_dispatches','sql_data','sql_control','sql_other','command_complete',
          'protocol_cycles','server_error_messages','data_rows','data_row_payload_bytes')


def dispersion(values):
    gate.require(len(values) == 3, 'Exactly3 independent measured workflows required')
    quartiles = statistics.quantiles(values,n=4,method='inclusive')
    return dict(n=3,median=statistics.median(values),minimum=min(values),maximum=max(values),
                q1=quartiles[0],q3=quartiles[2],iqr=quartiles[2]-quartiles[0],samples=values)


def completeness(rows):
    expected = schedule()
    keys = ('app','config_id','phase','repeat','trial_id')
    gate.require(len(rows) == 48 and all(row.get('passed') is True for row in rows),
                 'Complete48 passed workflows required; partial exports rejected')
    gate.require([{k:r[k] for k in keys} for r in rows] == expected,
                 'Trial identity/order differs, duplicate or missing workflow')
    counts = Counter((r['app'],r['config_id'],r['phase']) for r in rows)
    for app in APPS:
        for cell,_,_ in gate.CONFIGURATIONS:
            gate.require(counts[app,cell,'excluded_warmup']==1 and counts[app,cell,'measured']==3,
                         'Wrong independent warmup/measured sample counts')
    return counts


def export(run, output):
    run=Path(run).resolve();output=Path(output).resolve()
    release=validate_release()
    gate.require(release.selected_cases == ('apps/littlex','apps/issue_desk'), 'Wrong selected release')
    index=read_json(run/'index.json')
    gate.require(index.get('passed') is True and index.get('status')=='complete','Run is incomplete/failed')
    gate.require(index['authorization']==dict(path=str(release.authorization_path),sha256=release.authorization_sha256),
                 'Run belongs to another authorization')
    gate.require(index['sources']==sources()==read_json(release.instrument_path)['sources'],
                 'Frozen numeric/execution source closure differs')
    completeness(index['cases'])
    grouped=defaultdict(list); samples=[]; raw_refs=[]; databases=set()
    for row in index['cases']:
        directory=run/row['trial_id']
        gate.require(verify_case(directory)==row['raw_seal'],'Run/raw seal identity differs')
        path=checked_ref(row['metrics'],run)
        metric=read_json(path)
        acceptance=checked_ref(metric['independent_acceptance'],run)
        actual=summarize(directory,acceptance)
        gate.require(actual==metric,'Numerical reaggregation differs from captured metric proof')
        gate.require(metric['case_id']=='apps/'+row['app'] and metric['config_id']==row['config_id'],
                     'Metric belongs to another logical cell')
        database=read_json(acceptance)['database_state']['database']
        gate.require(database not in databases,'A fresh trial reused an earlier database')
        databases.add(database)
        raw_refs.append(dict(raw_seal=row['raw_seal'],metrics=row['metrics'],
                             acceptance=metric['independent_acceptance']))
        sample=dict(app=row['app'],config_id=row['config_id'],phase=row['phase'],repeat=row['repeat'],
                    trial_id=row['trial_id'],**{k:metric['primary'][k] for k in FIELDS},
                    distinct_backend_overlap_ns=sum(r['distinct_backend_overlap_ns']
                        for r in metric['primary']['actual_overlap']['requests']),
                    separate_process_overlap_ns=sum(r['separate_process_distinct_backend_overlap_ns']
                        for r in metric['primary']['actual_overlap']['requests']),
                    business_HTTP_requests=metric['primary']['HTTP_requests'])
        samples.append(sample)
        if row['phase']=='measured':grouped[row['app'],row['config_id']].append(sample)
    table=[]
    for app in APPS:
        for cell,_,_ in gate.CONFIGURATIONS:
            rows=sorted(grouped[app,cell],key=lambda r:r['repeat'])
            table.append(dict(app=app,config_id=cell,n=3,
                metrics={key:dispersion([r[key] for r in rows]) for key in (*FIELDS,
                    'distinct_backend_overlap_ns','separate_process_overlap_ns')},
                business_HTTP_requests=[r['business_HTTP_requests'] for r in rows]))
    gate.require(len(table)==12,'Incomplete two-app six-policy export')
    ratios=[]
    for app in APPS:
        base=next(r for r in table if r['app']==app and r['config_id']=='none')
        for row in [r for r in table if r['app']==app and r['config_id']!='none']:
            ratios.append(dict(app=app,config_id=row['config_id'],metric='protocol_sum_ns',
                ratio_to_off=None if base['metrics']['protocol_sum_ns']['median']==0 else
                    row['metrics']['protocol_sum_ns']['median']/base['metrics']['protocol_sum_ns']['median'],
                definition='ratio of independent workflow medians; not a paired causal estimate'))
    gate.revalidate(release)
    output.mkdir(parents=True,exist_ok=False)
    result=dict(passed=True,scope='PARTIAL: LittleX and IssueDesk only; not all30 or paper61',
        authorization=index['authorization'],source_hashes=sources(),index=dict(path=str(run/'index.json'),sha256=sha256(run/'index.json')),
        warmup_workflows=12,measured_workflows=36,logical_cells=12,table=table,ratios=ratios,samples=samples,
        raw_references=raw_refs,primary_phase='workflow',steady_reads_are_independent_repeats=False,
        dispersion='n3; min/max and inclusive linear quartiles, no confidence interval claim',
        definition='Actual PgWire send-to-Z protocol completion wall, includes row decoding/client progress; SQL dispatches/control/data retained',
        app_HTTP_e2e='Instrumented auxiliary raw only; no clean e2e dataset',CPU='Not measured; no CPU-cause claim')
    (output/'results.json').write_text(json.dumps(result,indent=2)+'\n')
    buffer=io.StringIO();writer=csv.writer(buffer)
    writer.writerow(['app','configuration','n','protocol_sum_median_ms','protocol_sum_iqr_ms',
        'protocol_union_median_ms','protocol_union_iqr_ms','SQL_total_median','SQL_data_median',
        'SQL_control_median','SQL_other_median','cycles_median','foreground_background_overlap_median_ms'])
    for row in table:
        m=row['metrics']
        writer.writerow([row['app'],row['config_id'],3,m['protocol_sum_ns']['median']/1e6,
            m['protocol_sum_ns']['iqr']/1e6,m['protocol_union_ns']['median']/1e6,m['protocol_union_ns']['iqr']/1e6,
            m['sql_dispatches']['median'],m['sql_data']['median'],m['sql_control']['median'],m['sql_other']['median'],
            m['protocol_cycles']['median'],m['distinct_backend_overlap_ns']['median']/1e6])
    (output/'table.csv').write_text(buffer.getvalue())
    files={p.name:sha256(p) for p in output.iterdir() if p.is_file()}
    (output/'artifacts.json').write_text(json.dumps(dict(passed=True,files=files),indent=2)+'\n')
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();result=export(args.run,args.output)
    print(json.dumps(dict(passed=True,cells=len(result['table']),measured_workflows=36,excluded_warmups=12)))
