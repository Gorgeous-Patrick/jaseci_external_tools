from pathlib import Path
import json,gzip,hashlib,importlib.util
R=Path('/home/baichuan/jaseci');O=Path(__file__).resolve().parent;E=R/'project-notes/measurements/ttg-jdrive-freethreaded-20261103/comparison-access-v3'
spec=importlib.util.spec_from_file_location('fp',R/'reproduction/ttg-continuation-performance/sql_reconciliation.py');fp=importlib.util.module_from_spec(spec);spec.loader.exec_module(fp)
x=json.loads((E/'results.json').read_text());targets=[]
for mode in ['thread']:
 s=next(s for s in x['samples'] if s['mode']==mode and s['phase']=='measured' and s['repeat']==0);t=s['trees'][0];q=next(f['sql'] for f in t['fingerprints'] if f['category']==('path' if mode=='off' else 'tree_path'))
 d=Path(s['evidence']['raw']['path']).parent
 calls=[json.loads(l) for f in sorted(d.glob('server-*.calls.jsonl.gz')) for l in gzip.open(f,'rt')]
 c=next(c for c in calls if c.get('origin_request_id')==t['request'] and c.get('sql')==q and c.get('send_ns') is not None)
 targets.append(dict(config_id=mode,target_id=mode+'-first-tree',request=t['request'],generation=c['server_generation'],role=c['role'],fingerprint=fp.fingerprint(q),sql=q,occurrence=1,read_only_source_reviewed=True,returned_rows=c['returned_rows'],native_proof=s['evidence']['proof'],primary_raw=s['evidence']['raw']))
def ref(p):return dict(path=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest())
(O/'selection-v2.json').write_text(json.dumps(dict(purpose='matched_jdrive_read_only_diagnostic',targets=targets,context_refs=[ref(E/'results.json'),ref(E/'plan.json')]),indent=2)+'\n')
print([(t['config_id'],t['request'],t['returned_rows']) for t in targets])
