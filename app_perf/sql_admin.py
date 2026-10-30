#!/usr/bin/env python3
"""Owned PgWire administration over JSON stdin; each connection closes per query."""
import argparse
import json
import sys
import jaclang
from jaclang.data.pgwire import PgWireConnection

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--port', required=True, type=int)
parser.add_argument('--lease', help='Synthetic active-session test only; waits for stdin EOF')
args = parser.parse_args()

def connect(database):
    return PgWireConnection(user='ttgperf', host='127.0.0.1', port=args.port,
        database=database, application_name='ttg-performance-owned-admin')

if args.lease:
    connection = connect(args.lease)
    print('TTG_ADMIN_LEASE_READY', flush=True)
    try:
        sys.stdin.read()
    finally:
        connection.close()
else:
    for line in sys.stdin:
        connection = None
        try:
            request = json.loads(line)
            connection = connect(request['database'])
            rows = connection.run(request['sql'])
            response = {'ok': True, 'rows': rows}
        except Exception as error:
            response = {'ok': False, 'error': f'{type(error).__name__}: {error}'}
        finally:
            if connection is not None:
                connection.close()
        print('TTG_ADMIN_RESULT=' + json.dumps(response), flush=True)
