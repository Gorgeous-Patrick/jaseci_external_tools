"""Targeted stored-response oracle checks; no server/runtime/DB execution."""
import copy,json,shutil,tempfile
from pathlib import Path
from next_config import ROOT,EVIDENCE
from next_interop import reference
from next_semantic import independent_replay,domain_replay

def validate():
    prior=ROOT/'project-notes/measurements/ttg-plus-performance-20261031/formal-v1/cases/linked_list32-off-measured-0'
    original=independent_replay(prior,dict(app='linked_list',scale='smoke',length=32),None)
    historical=ROOT/'project-notes/measurements/ttg-continuation-performance-20261030/apps-preflight-866222-v2'
    index=json.loads((historical/'index.json').read_text());checks=[]
    for app in ('issue_desk','knowledge_map'):
        row=next(r for r in index['cases'] if r['app']==app and r['config_id']=='none')
        source=Path(row['evidence']['path']).parent;seal=json.loads((source/'artifacts.json').read_text())
        with tempfile.TemporaryDirectory(prefix='stored-domain-',dir=EVIDENCE) as temp:
            directory=Path(temp)
            for name in ('http-raw.jsonl','fixture-raw.json','final-graph-raw.json'):
                assert reference(source/name)['sha256']==seal['files'][name]
                shutil.copyfile(source/name,directory/name)
            (directory/'plus-proof.json').write_text(json.dumps(row['proof']))
            result=domain_replay(directory,dict(app=app),row['proof'],row['evidence'],None)
            assert result['passed']
            rows=[json.loads(line) for line in (directory/'http-raw.jsonl').read_text().splitlines()]
            if app=='issue_desk':
                r=next(r for r in rows if r['path']=='/walker/ProjectBoard')
                board=r['output'].get('data',r['output'])['reports'][0]
                next(i for i in board['issues'] if i['title']=='Implement parser fix')['priority']=999
            else:
                r=next(r for r in rows if r['path']=='/walker/PublishArticle')
                r['output'].get('data',r['output'])['reports'][0]['ok']=True
            (directory/'http-raw.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows))
            rejected=False
            try:domain_replay(directory,dict(app=app),row['proof'],row['evidence'],None)
            except AssertionError:rejected=True  # independent frozen scenario, before hash checks
            assert rejected,'Domain semantic mutation survived independent scenario'
            checks.append(dict(app=app,positive=True,changed_business_with_unchanged_final_graph_rejected=True,
                historical_raw=row['evidence'],operations=result['actual_operations_checked']))
    out=EVIDENCE/'stored-replay-validation-v1.json'
    out.write_text(json.dumps(dict(passed=True,kind='DB-free stored response replay only',source=reference(Path(__file__)),
        original=dict(passed=original['passed'],operations=original['actual_operations_checked'],raw=original['raw_seal']),
        domains=checks),indent=2)+'\n')
    print(json.dumps(reference(out)))

if __name__=='__main__':validate()
