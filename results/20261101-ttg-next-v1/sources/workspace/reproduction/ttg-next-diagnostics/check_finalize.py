"""DB-free actual failed-native transcript replay through the repaired adapter."""
from pathlib import Path
import hashlib
import json
import shutil
import tempfile
from types import SimpleNamespace
from runner import Trial, Postgres, read_json, reference, require, EVIDENCE


def main():
    source=EVIDENCE/'recapture-v1/cases/linked_list1000-baseline850-diagnostic'
    before={str(p.relative_to(source)):hashlib.sha256(p.read_bytes()).hexdigest() for p in source.rglob('*') if p.is_file()}
    case=dict(case_id='linked_list1000',app='linked_list',scale='medium',length=1000,config_id='baseline850',phase='diagnostic')
    # Use the actual accepted inventory's scale, rather than guessing fixture sizes.
    plan=read_json(Path('/home/baichuan/jaseci/project-notes/measurements/ttg-next-performance-20261101/correctness-plan-v2/plan.json'))
    case={**next(c for c in plan['correctness_schedule'] if c['case_id']=='linked_list1000' and c['config_id']=='baseline850'),'phase':'diagnostic'}
    with tempfile.TemporaryDirectory(prefix='offline-finalize-',dir=EVIDENCE) as temporary:
        root=Path(temporary);directory=root/source.name;shutil.copytree(source,directory)
        target=read_json(directory/'cleanup-target.json');target.update(case_directory=str(directory),run_directory=str(root));(directory/'cleanup-target.json').write_text(json.dumps(target)+'\n')
        pg=object.__new__(Postgres);pg.owner=target['cluster_owner'];pg.databases={target['database']};pg.services=[];pg.run_directory=root;pg.context=dict(directory=directory,case=case,cell='baseline850',source_manifest=plan['sources'],target=reference(directory/'cleanup-target.json'))
        pg.selection=read_json(EVIDENCE/'selection-v1.json');pg.verify_owner=lambda:None;pg.source_guard=lambda:None;statements=[];records=[]
        def mock_sql(sql,database='postgres'):
            statements.append(sql)
            if sql.startswith('WITH domain AS '):return json.dumps(read_json(directory/'final-graph-raw.json'))
            if sql.startswith('SELECT count(*) FROM pg_stat_activity '):return '0'
            if sql=='DROP DATABASE '+target['database']:return ''
            raise AssertionError('Unexpected offline mock statement: '+sql)
        pg.sql=mock_sql;pg.record=lambda kind,**fields:records.append(dict(kind=kind,**fields))
        trial=Trial();server=SimpleNamespace(process=None,requests=read_json(directory/'requests.json'))
        trial.finalize(case,'baseline850',directory,server,pg,target['database'],Path(plan['runtimes']['baseline850']['clean']['path']),Path(plan['runtimes']['baseline850']['overlay']['path']),None)
        require(not pg.databases and any(s.startswith('DROP DATABASE ') for s in statements),'Actual inherited acceptance did not reach mock DROP')
        require(read_json(directory/'diagnostic-acceptance.json')['passed'],'Selected completion/1000 rows/plans validation failed')
        result=read_json(pg.context['result']['metrics']['path']);require(result['stage']=='diagnostic','Stage changed')
        accepted=read_json(pg.context['result']['acceptance']['path']);require(accepted['semantic']['actual_operations_checked']==6,'Independent six-operation oracle missing')
        proof=dict(passed=True,scope='DB-free actual recorded native transcript through repaired compression/finalize/selected completion/independent replay/physical census mock/metrics/owned DROP mock',actual_DB_connections=0,actual_SQL_or_Drop_executed=False,actual_native_operations_replayed=accepted['semantic']['actual_operations_checked'],selected_recursive_rows=1000,metrics_stage=result['stage'],mock_statements=statements,original_raw_unchanged=all(hashlib.sha256((source/p).read_bytes()).hexdigest()==h for p,h in before.items()))
        require(proof['original_raw_unchanged'],'Failed-v1 original changed')
    (EVIDENCE/'offline-finalize-v2-check.json').write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps(proof))


if __name__=='__main__':main()
