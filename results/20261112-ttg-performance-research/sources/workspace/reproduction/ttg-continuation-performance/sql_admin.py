"""Owned JSON/PgWire admin; no psql dependency and no retained target session."""
import argparse
import json
import os
import sys
import jaclang
from jaclang.data.pgwire import PgWireConnection

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--port',required=True,type=int)
args=parser.parse_args()
for line in sys.stdin:
    connection=None
    try:
        request=json.loads(line)
        connection=PgWireConnection(user='ttgperf',host='127.0.0.1',port=args.port,
            database=request['database'],application_name=f'ttg-cont-admin:{os.getpid()}')
        rows=connection.run(request['sql'])
        response=dict(ok=True,rows=rows)
    except Exception as error:
        response=dict(ok=False,error=f'{type(error).__name__}: {error}')
    finally:
        if connection is not None: connection.close()
    print('TTG_ADMIN_RESULT='+json.dumps(response),flush=True)
