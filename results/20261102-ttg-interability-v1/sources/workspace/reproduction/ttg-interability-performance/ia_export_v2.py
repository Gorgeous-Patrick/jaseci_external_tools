"""Strict48 export:12 excluded warmups,36 measured fresh workflows,12 cells n3."""
import argparse
from collections import defaultdict
import csv
import json
from pathlib import Path
import statistics
from ia_config import CASES as APP_CASES,MODES as CELLS,schedule
from ia_interop import require,read_json,reference,checked_ref,verify_case
# Own release is loaded by exact path; ia_interop deliberately prepends
# borrowed directories, so an unqualified 'runner' would resolve the old suite.
import importlib.util
_RELEASE_PATH=Path(__file__).resolve().with_name('ia_runner.py')
_release_spec=importlib.util.spec_from_file_location('_ttg_interability_export_release_v1',_RELEASE_PATH)
_release_module=importlib.util.module_from_spec(_release_spec)
_release_spec.loader.exec_module(_release_module)
release=_release_module.release


def dispersion(values):
    require(bool(values),'No samples')
    return dict(n=len(values),median=statistics.median(values),min=min(values),max=max(values),
        mean=statistics.mean(values),stdev=statistics.stdev(values) if len(values)>1 else None)


def aggregate(samples):
    rows=[]
    for case,app,scale,length in APP_CASES:
        for cell in CELLS:
            chosen=[s for s in samples if s['case_id']==case and s['config_id']==cell and s['phase']=='measured']
            require(len(chosen)==3 and {s['repeat'] for s in chosen}=={0,1,2},'Exactly3 measured workflows/cell required')
            metrics=[s['metric'] for s in chosen]
            row=dict(case_id=case,app=app,scale=scale,length=length,config_id=cell,n=3,
                samples=[s['metric_ref'] for s in chosen])
            for key in ('protocol_sum_ns','protocol_union_ns','driver_sum_ns','driver_union_ns',
                'sql_dispatches','sql_data','sql_control','sql_other','data_rows','data_row_payload_bytes'):
                row[key]=dispersion([m['primary'][key] for m in metrics])
            row['roles']={role:{key:dispersion([m['primary']['roles'][role][key] for m in metrics])
                for key in ('sql_dispatches','protocol_sum_ns','protocol_union_ns')}
                for role in ('foreground','background_prefetch','background_continuation')}
            if length is not None:
                traversals=[]
                for metric in metrics:
                    requests=[r for r in metric['request_metrics'] if r['phase']=='workflow' and
                        r['path'].split('/')[2:3]==['Traverse']]
                    require(len(requests)==1,'One native Traverse per LinkedList workflow required')
                    require(len(metric['Traverse_requests'])==1 and
                        metric['Traverse_requests'][0]['actual']==length and
                        metric['Traverse_requests'][0]['native_visited']==length,'Native Traverse coverage differs')
                    traversals.append(requests[0])
                row['Traverse']={key:dispersion([r[key] for r in traversals]) for key in
                    ('protocol_sum_ns','protocol_union_ns','sql_dispatches','sql_data','sql_control','sql_other')}
                row['Traverse']['native_visited']=length
            rows.append(row)
    return rows


def export(index_path,output):
    index_path=Path(index_path).resolve();index=read_json(index_path)
    require(index.get('passed') is True and index['status']=='complete' and index['stage']=='formal',
        'Complete formal index required')
    require([{k:r[k] for k in schedule(True)[0]} for r in index['rows']]==schedule(True),
        'Exact48 schedule/order required, without missing/reused samples')
    plan_path=checked_ref(index['plan'],index_path.parent);plan=read_json(plan_path)
    settings=read_json(checked_ref(index['postgres_settings'],index_path.parent))
    require(settings['passed'] and all(settings['settings'][k]==plan['postgres'][k] for k in
        ('min_wal_size','max_wal_size')),'Actual PostgreSQL WAL setting proof differs')
    require(release(plan_path,plan)[0]==index['authorization'],'Formal release differs')
    require(len({r['trial_id'] for r in index['rows']})==48,'Reused trial identity')
    databases=set();samples=[]
    for row in index['rows']:
        require(row['passed'] is True,'Failed formal row')
        result=row['result'];proof=read_json(checked_ref(result['proof'],index_path.parent))
        directory=Path(result['raw']['path']).parent;seal=verify_case(directory)
        require(reference(directory/'artifacts.json')==result['raw'],'Raw seal/index mismatch')
        acceptance=read_json(checked_ref(result['acceptance'],index_path.parent))
        metric=read_json(checked_ref(result['metrics'],index_path.parent))
        require(acceptance['passed'] and acceptance['semantic']['passed'] and acceptance['raw_seal']==seal,
            'Independent acceptance mismatch')
        require(metric['passed'] and metric['raw_seal']==seal and metric['independent_acceptance']==result['acceptance'],
            'Metric/acceptance/raw mismatch')
        require(metric['case_id']==proof['case_id']==row['case_id'] and
            metric['config_id']==proof['config_id']==row['config_id'] and
            metric['stage']==proof['stage']==row['phase'],'Sample identity/phase mismatch')
        require(proof['database'] not in databases,'Fresh database per workflow required');databases.add(proof['database'])
        samples.append(dict(**{k:row[k] for k in ('case_id','config_id','phase','repeat','trial_id')},
            metric=metric,metric_ref=result['metrics']))
    rows=aggregate(samples)
    ratios=[]
    for case,app,scale,length in APP_CASES:
        grouped={r['config_id']:r for r in rows if r['case_id']==case}
        for cell in ('baseline9282','interability'):
            ratios.append(dict(case_id=case,config_id=cell,comparison='ratio to off median',
                protocol_sum=grouped[cell]['protocol_sum_ns']['median']/grouped['off']['protocol_sum_ns']['median'],
                protocol_union=grouped[cell]['protocol_union_ns']['median']/grouped['off']['protocol_union_ns']['median']))
    sanity=[]
    for case,app,scale,length in APP_CASES:
        if length is None:continue
        grouped={r['config_id']:r for r in rows if r['case_id']==case}
        sanity.append(dict(case_id=case,native_visited=length,scope='All-role real SQL dispatches during native Traverse',
            TOTAL_SQL={cell:grouped[cell]['Traverse']['sql_dispatches'] for cell in CELLS},
            DATA_SQL={cell:grouped[cell]['Traverse']['sql_data'] for cell in CELLS},
            next_to_baseline9282_total_ratio=grouped['interability']['Traverse']['sql_dispatches']['median']/
                grouped['baseline9282']['Traverse']['sql_dispatches']['median'],
            next_to_off_total_ratio=grouped['interability']['Traverse']['sql_dispatches']['median']/
                grouped['off']['Traverse']['sql_dispatches']['median']))
    output=Path(output).resolve();require(not output.exists(),'NEW numeric export required');output.mkdir()
    result=dict(passed=True,index=reference(index_path),plan=reference(plan_path),sources=plan['sources'],postprocessor=reference(Path(__file__)),
        postgres_settings=index['postgres_settings'],
        validation='Strict saved-metric, identity and raw-seal validation; independent raw numerical reaggregation is separate',
        sample_counts=dict(all=48,excluded_warmups=12,measured=36,cells=12,n_per_cell=3),
        rows=rows,ratios=ratios,LinkedList_total_SQL_sanity=sanity,
        samples=[{k:v for k,v in s.items() if k!='metric'} for s in samples],
        definitions=dict(primary='workflow sendall-to-ReadyForQuery protocol completion wall',
            time_unit='nanoseconds',sum='Overlapping intervals summed',union='Union of actual intervals',
            SQL='Actual all-role dispatches including control commands, path and payload queries',
            dispersion='n,median,min,max,mean,sample stdev; n counts fresh workflows',
            regime=plan['regime'],postgres=plan['postgres']))
    path=output/'results.json';path.write_text(json.dumps(result,indent=2)+'\n')
    columns=['case_id','config_id','n','protocol_sum_ms_median','protocol_sum_ms_min','protocol_sum_ms_max',
        'protocol_union_ms_median','protocol_union_ms_min','protocol_union_ms_max','SQL_total_median',
        'SQL_data_median','SQL_control_median','SQL_other_median','Traverse_visited','Traverse_SQL_total_median']
    with (output/'table.csv').open('w') as file:
        writer=csv.DictWriter(file,fieldnames=columns);writer.writeheader()
        for row in rows:
            record={k:row[k] for k in ('case_id','config_id','n')}
            for metric,label in [('protocol_sum_ns','protocol_sum_ms'),('protocol_union_ns','protocol_union_ms')]:
                for stat in ('median','min','max'):record[label+'_'+stat]=row[metric][stat]/1e6
            for key,label in [('sql_dispatches','SQL_total'),('sql_data','SQL_data'),
                ('sql_control','SQL_control'),('sql_other','SQL_other')]:record[label+'_median']=row[key]['median']
            if 'Traverse' in row:
                record.update(Traverse_visited=row['length'],Traverse_SQL_total_median=row['Traverse']['sql_dispatches']['median'])
            writer.writerow(record)
    (output/'artifacts.json').write_text(json.dumps(dict(passed=True,outputs=[reference(path),reference(output/'table.csv')],
        renderer_excluded=True),indent=2)+'\n')
    print(path)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--index',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args();export(args.index,args.output)
