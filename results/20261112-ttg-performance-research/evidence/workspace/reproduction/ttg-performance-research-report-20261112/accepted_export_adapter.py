"""Thin presentation mapping of the actual t3 accepted export (source-only draft).

No Jac/plotting imports; no raw archive, metric, runtime-tree or DB reads. This
module preserves n3 partial stage scope and precision:null. It does not construct
an accepted_complete report document or invent n5/other-app/precision values.
Not executed or tested while t3 timing is active.
"""
import argparse
import hashlib
import json
from pathlib import Path
import statistics

# Accepted primary export already uses ms, so there is no unit rescaling here.
FIELDS = {
    'HTTP_response_sum_ms':'http_response_ms',
    'HTTP_response_union_ms':'http_response_union_ms',
    'HTTP_response_span_ms':'http_span_ms',
    'DB_sum_ms':'db_protocol_sum_ms',
    'DB_union_ms':'db_protocol_union_ms',
    'data_SQL':'data_sql',
    'control_SQL':'control_sql',
    'total_SQL':'total_sql',
    'data_SQL_per_business_request':'data_sql_per_business_request',
    'business_requests':'business_http_requests',
}
MODES = ('off','aggressive','conservative')


def map_accepted_export(export):
    """Return only observed cells/samples and the actual uncompleted inventory."""
    if export.get('passed') is not True:
        raise ValueError('An accepted primary export is required')
    samples=export['samples']
    trial_ids=[s['trial_id'] for s in samples]
    if len(trial_ids)!=len(set(trial_ids)):
        raise ValueError('Duplicate actual trial identity')
    if any(s.get('precision') is not None for s in samples):
        raise ValueError('The actual timing export has precision:null; precision must stay separate')
    grouped={}
    for sample in samples:
        if sample['phase']!='measured':
            continue
        if sample['config_id'] not in MODES:
            raise ValueError('Unexpected policy identity')
        key=(sample['case_id'],sample['config_id'])
        row={target:sample[source] for source,target in FIELDS.items()}
        row.update(repeat=sample['repeat'],trial_id=sample['trial_id'],
                   source_references=sample['references'],gil_proof=sample['GIL_proof'],
                   roles=sample['roles'],actual_overlap=sample['actual_overlap'],RPCs=sample['RPCs'])
        if row['total_sql']!=row['data_sql']+row['control_sql']:
            raise ValueError('All-role SQL split is inconsistent')
        if row['business_http_requests']!=len(row['RPCs']):
            raise ValueError('Actual HTTP count and per-RPC records differ')
        if row['db_protocol_union_ms']>row['db_protocol_sum_ms']+0.00001:
            raise ValueError('DB interval union exceeds its sum')
        grouped.setdefault(key,[]).append(row)
    rows={(row['case_id'],row['config_id']):row for row in export['rows']}
    if len(rows)!=len(export['rows']) or set(rows)!=set(grouped):
        raise ValueError('Grouped row and actual measured sample inventory differ')
    cells=[]
    for key,trials in grouped.items():
        trials.sort(key=lambda s:s['repeat'])
        source=rows[key]
        if source['n'] not in (3,5) or len(trials)!=source['n']:
            raise ValueError('Only actually observed n3 or n5 stage rows are admitted')
        if [r['repeat'] for r in trials]!=list(range(source['n'])):
            raise ValueError('Missing/duplicate measured repeat')
        for original,normalized in FIELDS.items():
            values=[r[normalized] for r in trials]
            declared=source[original]
            if declared['n']!=len(values) or declared['values']!=values:
                raise ValueError('Accepted vector and actual sample values differ: '+original)
            if (declared['median']!=statistics.median(values) or declared['min']!=min(values)
                    or declared['max']!=max(values) or declared['mean']!=statistics.mean(values)):
                raise ValueError('Accepted descriptive statistic differs: '+original)
        cells.append(dict(case_id=key[0],app=source['app'],scale=source['scale'],mode=key[1],
                          status='accepted',n=source['n'],trials=trials))
    inventory=export['inventory']
    expected={(r['case_id'],r['config_id']) for r in inventory}
    if len(expected)!=len(inventory):
        raise ValueError('Duplicate declared inventory cell')
    if any(r['completed']!=((r['case_id'],r['config_id']) in rows) for r in inventory):
        raise ValueError('Stage completion inventory differs from actual rows')
    missing=[dict(case_id=case,mode=mode) for case,mode in sorted(expected-set(rows))]
    return dict(schema='ttg-primary-stage-presentation-map-v1',status='accepted_stage_only',
                final_render_ready=False,primary_n_by_cell=[dict(case_id=c['case_id'],mode=c['mode'],n=c['n']) for c in cells],
                cells=cells,missing_primary_cells=missing,precision=None,
                actual_counts=export['counts'],plan=export['plan'],postprocessor=export['source'],
                accepted_export_definitions=export['definitions'],
                excluded_samples=[dict(trial_id=s['trial_id'],phase=s['phase'],case_id=s['case_id'],mode=s['config_id'])
                                  for s in samples if s['phase']!='measured'],
                interpretation='A partial n3 accepted stage remains partial. Full n5 fixture/policy inventory, separate precision and quiet accepted report metadata must be assembled before rendering.')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--export',required=True,type=Path)
    parser.add_argument('--expected-sha256',required=True)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args()
    if args.output.exists():
        raise ValueError('Use a new presentation-mapping output path')
    raw=args.export.read_bytes()
    digest=hashlib.sha256(raw).hexdigest()
    if digest!=args.expected_sha256:
        raise ValueError('Accepted export hash differs')
    value=map_accepted_export(json.loads(raw))
    value['accepted_export']={'path':str(args.export.resolve()),'sha256':digest}
    value['adapter']={'path':str(Path(__file__).resolve()),'sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(value,indent=2)+'\n')
    print(json.dumps(dict(mapped_cells=len(value['cells']),status=value['status'],final_render_ready=False)))


if __name__=='__main__':
    main()
