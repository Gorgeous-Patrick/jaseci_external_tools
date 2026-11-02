"""Add complete LIMIT-boundary tie candidates without changing DBGEN tables."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sqlite3
from prepare import reference_module
from compare import order_key


def prepare(fixture,output):
    output.mkdir(parents=True,exist_ok=False);module=reference_module();module.DATA_DIR=fixture/'tables';db=sqlite3.connect(':memory:')
    try:
        for ddl,_,_ in module.SCHEMA.values():db.execute(ddl)
        for table,(_,filename,columns) in module.SCHEMA.items():module.load_tbl(db,table,filename,columns)
        module.create_indexes(db);cases=[]
        for number,(sql,params) in module.build_queries().items():
            rows=db.execute(sql,params).fetchall();columns=module.QUERY_COLUMNS[number];boundary=None
            limit=re.search(r'\s+LIMIT\s+(\d+)\s*;?\s*$',sql,re.I)
            if limit and len(rows)==int(limit[1]) and rows:
                full_sql=sql[:limit.start()];all_rows=db.execute(full_sql,params).fetchall()
                last=order_key(number,dict(zip(columns,rows[-1])))
                eligible=[row for row in all_rows if order_key(number,dict(zip(columns,row)))==last]
                boundary={'limit':int(limit[1]),'eligible_rows':eligible,'complete_boundary_bucket':True,'uncapped_sql_sha256':hashlib.sha256(full_sql.encode()).hexdigest()}
            reference=dict(columns=columns,rows=rows,boundary_ties=boundary,source='Pinned SQL; deterministic DBGEN fixture',numeric_contract={'absolute':'0.000001','relative':'0.000000001','conversion':'Decimal(str(number)); no string/bool/NULL numeric coercion; exact integer IDs/counts','order_key_scale':'Declared TPC-H DECIMAL scales only, not financial value tolerance','inherited_repository_tolerance':'0.02 or1e-4 relative; not silently used by this stricter adapter'})
            path=output/f'q{number}.expected.json';path.write_text(json.dumps(reference,indent=2)+'\n');cases.append({'case_id':f'tpch/Q{number}','expected':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'boundary_candidates':len(boundary['eligible_rows']) if boundary else 0})
        manifest={'fixture_manifest_sha256':hashlib.sha256((fixture/'fixture-manifest.json').read_bytes()).hexdigest(),'cases':cases,'comparator_sha256':hashlib.sha256((Path(__file__).parent/'compare.py').read_bytes()).hexdigest(),'native':'pending'}
        (output/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n');print('Prepared22 ordered/numeric oracle contracts; no native execution')
    finally:db.close()


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--fixture',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();prepare(a.fixture,a.output)
