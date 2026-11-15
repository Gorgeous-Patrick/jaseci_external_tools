"""Supplement original logical oracles with full anchored response semantics.

Reads immutable per-response JSONL rather than mutable in-memory request-body
references. Retains result/reports/view fields and ordering. Only explicitly
identified mutation-generated timestamp fields are normalized, after validation.
"""
from datetime import datetime
import hashlib
import json
from pathlib import Path
from identity import Identities,encoded,key
from metrics import verify_artifacts

ORIGINALS={'linked_list','littlex','jacord','jdrive'}
CREATORS={'post:session:0':'create_tweet','reply:session:0':'PostReply','folder:session:0':'NewFolder'}

def read_raw(directory):
    return [json.loads(line) for line in (Path(directory)/'http-raw.jsonl').read_text().splitlines() if line.strip()]

def canonicalize(rows):
    mappings=[r['input']['mapping'] for r in rows if '/walker/SuiteInspect' in r['path']]
    if not mappings:raise ValueError('Original semantic audit requires final native inspection mapping')
    mapping=mappings[-1]
    identities=Identities({actual:logical for logical,actual in mapping.items()})
    logical_by_id={key(actual):logical for logical,actual in mapping.items()}
    windows={}
    for logical,walker in CREATORS.items():
        matches=[r for r in rows if r['path'].split('/')[2:3]==[walker]]
        if matches:windows[logical]=[(r['wall_start'],r['wall_end']) for r in matches]
    trash=[r for r in rows if r['path'].split('/')[2:3]==['TrashFolder']]
    if trash:windows['folder:root/0']=[(r['wall_start'],r['wall_end']) for r in trash]
    observed={};checks=[]
    def volatility(value,phase,path=()):
        if isinstance(value,list):return [volatility(v,phase,path+(i,)) for i,v in enumerate(value)]
        if not isinstance(value,dict):return value
        logical=None
        if isinstance(value.get('id'),str):
            try:logical=logical_by_id.get(key(value['id']))
            except ValueError:pass
        result={}
        for field,item in value.items():
            allowed=(logical in CREATORS and field in ('created_at','updated_at')) or (
                logical=='folder:root/0' and field=='updated_at' and bool(item))
            if allowed:
                if not isinstance(item,str) or not item:raise ValueError(f'Missing volatile timestamp {logical}.{field}')
                stamp=datetime.fromisoformat(item.replace('Z','+00:00')).timestamp()
                if logical not in windows or not any(begin-5<=stamp<=end+5 for begin,end in windows[logical]):
                    raise ValueError(f'Volatile timestamp outside actual mutation request window: {logical}.{field}')
                ident=(logical,field)
                if ident in observed and observed[ident]!=stamp:
                    raise ValueError(f'Volatile field changed between responses without a second mutation: {logical}.{field}')
                observed[ident]=stamp
                checks.append({'logical':logical,'field':field,'raw':item,'valid':True,'path':list(path)+( [field] )})
                result[field]=f'<validated-mutation-time:{logical}:{field}>'
            else:result[field]=volatility(item,phase,path+(field,))
        return result
    transcript=[];actions=[]
    for row in rows:
        if row['phase'] not in ('workflow','steady_warmup','steady_read'):continue
        parts=row['path'].split('/')
        if parts[1:2]!=['walker']:continue
        action={'phase':row['phase'],'walker':parts[2],'target':parts[3:],'input':row['input']}
        actions.append(identities.normalize(action))
        output=row['output']
        transcript.append({'action':identities.normalize(action),'output':identities.normalize(volatility(output,row['phase']))})
    for logical in CREATORS:
        if (logical,'created_at') in observed and (logical,'updated_at') in observed and observed[(logical,'created_at')]>observed[(logical,'updated_at')]:
            raise ValueError('Created-after-updated timestamp: '+logical)
    return dict(full_semantic_sha256=hashlib.sha256(encoded(transcript)).hexdigest(),
        full_actions_sha256=hashlib.sha256(encoded(actions)).hexdigest(),canonical_transcript=transcript,
        canonical_actions=actions,identity_map=identities.mapping,volatile_checks=checks,
        interpretation='Full original result/reports/view semantics and ordering supplement the independent logical-ID/final-graph oracle; only mutation-anchored timestamps normalized')

def audit(directory,expected=None,sealed=True):
    if sealed:verify_artifacts(directory,required=('http-raw.jsonl',))
    result=canonicalize(read_raw(directory))
    if expected:
        for field in ('full_semantic_sha256','full_actions_sha256'):
            if result[field]!=expected[field]:raise ValueError('Original full response equivalence failed: '+field)
    return result

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--preflight',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();index=json.loads(args.preflight.read_text());results=[];baselines={}
    for case in index['cases']:
        if case['app'] not in ORIGINALS:continue
        directory=Path(case['evidence']['path']).parent
        result=audit(directory,baselines.get(case['app']))
        baselines.setdefault(case['app'],result)
        result.update(app=case['app'],policy=case['policy'],raw_sha256=hashlib.sha256((directory/'http-raw.jsonl').read_bytes()).hexdigest())
        results.append(result)
    args.output.write_text(json.dumps({'cases':results,'complete_original16':len(results)==16,'formal_authorization':False},indent=2)+'\n')
    print(f'{len(results)}/16 original policy cases fully equivalent')
