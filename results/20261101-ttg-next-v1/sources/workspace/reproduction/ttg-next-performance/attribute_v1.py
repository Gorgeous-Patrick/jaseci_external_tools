"""Post-primary, read-only exact request/fingerprint attribution; no DB execution."""
import argparse,gzip,hashlib,json,re,statistics,sys
from collections import defaultdict,Counter
from pathlib import Path
OWN=Path(__file__).resolve().parent
sys.path.insert(0,str(OWN))
from next_interop import load_jsonl,scope_calls,totals,verify_case,reference,read_json
from sql_reconciliation import fingerprint,sql_kind
E=OWN.parents[1]/'project-notes/measurements/ttg-next-performance-20261101'

def category(sql):
    text=sql.lstrip()
    if sql_kind(sql)=='control':return 'control'
    if text.startswith('SELECT DISTINCT') and '"arch_type"' in text and '"arch_module"' in text:return 'catalog'
    if '"slot"' in text and '"arity"' in text and 'LEFT JOIN LATERAL' in text:
        return 'fused_recursive' if re.search(r'WITH\s+RECURSIVE',text,re.I) else 'fused_batch'
    if re.match(r'SELECT n[0-9]+\.id, e[0-9]+\.id',text):return 'ordinary_path'
    if re.match(r'SELECT a\.id, a\.kind, a\.arch_type',text):return 'payload'
    if re.search(r'\bidentity_(?:users|lookups|identities)\b',text):return 'identity'
    if re.match(r'(?:INSERT|UPDATE|DELETE|MERGE)\b',text,re.I):return 'mutation'
    return 'other_data'

def run(out):
    assert not out.exists();out.mkdir(parents=True)
    index=read_json(E/'formal-v1/index.json');audits=E.parent/'ttg-next-review-20261101/formal72-raw-audit'
    summary=read_json(audits/'summary.json');assert summary['passed'] and summary['all_export_statistics_and_CSV_match']
    samples=[]
    for row in index['rows']:
        if row['phase']!='measured' or row['case_id'] not in ('linked_list1000','littlex'):continue
        directory=Path(row['result']['raw']['path']).parent
        seal=verify_case(directory,required=('http-raw.jsonl',))
        calls=load_jsonl(directory,'server-*.calls.jsonl*');requests=load_jsonl(directory,'http-raw.jsonl*')
        assigned,_=scope_calls(calls,requests);rpcs=[]
        previous=read_json(audits/(row['trial_id']+'.json'))
        for ordinal,request in enumerate(r for r in requests if r['phase']=='workflow'):
            selected=[c for c,r in assigned if r is request]
            aggregate=totals(selected);assert aggregate['protocol_sum_ns']==previous['RPCs'][ordinal]['protocol_sum_ns']
            groups=defaultdict(list);categories=defaultdict(list)
            for c in selected:
                groups[(fingerprint(c['sql']),c['role'])].append(c);categories[category(c['sql'])].append(c)
            fps=[dict(fingerprint=k[0],role=k[1],category=category(v[0]['sql']),sql=v[0]['sql'],**totals(v),
                backend_pids=sorted({c['backend_pid'] for c in v}),process_pids=sorted({c['client_process_pid'] for c in v}))
                for k,v in groups.items()]
            detail=[{k:c.get(k) for k in ('sql','role','backend_pid','client_process_pid','send_ns','ready_ns','data_rows','data_row_payload_bytes')}
                for c in selected] if row['case_id']=='linked_list1000' and ordinal==0 else []
            rpcs.append(dict(ordinal=ordinal,path=request['path'],request=request['request'],server_generation=request['server_generation'],
                **aggregate,categories={k:totals(v) for k,v in categories.items()},
                fingerprints=sorted(fps,key=lambda v:-v['protocol_sum_ns']),Traverse_call_intervals=detail))
        samples.append(dict(**{k:row[k] for k in ('case_id','config_id','repeat','trial_id')},raw_seal=seal,
            prior_independent_audit=reference(audits/(row['trial_id']+'.json')),RPCs=rpcs))
    result=dict(passed=True,source=reference(Path(__file__)),export=reference(E/'export-v1/results.json'),
        independent_audit=reference(audits/'summary.json'),samples=samples,
        scope='All3 measured trials, every business RPC for LL1000/LittleX; exact sealed SQL and actual origin join; protocol contributions are not pure server execution/CPU.')
    (out/'results.json').write_text(json.dumps(result,indent=2)+'\n')
    for app in ('linked_list1000','littlex'):
        print(app)
        for mode in ('off','baseline850','next'):
            selected=[s for s in samples if s['case_id']==app and s['config_id']==mode]
            rpc_ordinals=(0,) if app=='linked_list1000' else range(len(selected[0]['RPCs']))
            for ordinal in rpc_ordinals:
                rr=[s['RPCs'][ordinal] for s in selected]
                print(mode,ordinal,rr[0]['path'].split('/')[2], 'ms', [round(r['protocol_sum_ns']/1e6,3) for r in rr],
                    'categories', {k:([r['categories'].get(k,{}).get('sql_dispatches',0) for r in rr],
                    [round(r['categories'].get(k,{}).get('protocol_sum_ns',0)/1e6,3) for r in rr]) for k in rr[0]['categories']})
    print('output',reference(out/'results.json'))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);run(p.parse_args().output.resolve())
