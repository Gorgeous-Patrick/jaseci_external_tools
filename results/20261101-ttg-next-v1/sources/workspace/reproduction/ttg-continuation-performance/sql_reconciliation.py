"""Offline exact SQL-event reconciliation, pending validation on final runtime.

Consume sealed inputs through evidence.py before calling this module. SQL
identity preserves literal values and quoted content; only exterior whitespace
is normalized. No guessed execute+error equality: execution errors can follow
an execute record, while parse errors have only an ERROR record.
"""
from collections import Counter, defaultdict
import hashlib
import re


def canonical_sql(sql):
    if not isinstance(sql,str) or not sql.strip():
        raise ValueError('Missing actual wire SQL')
    out=[];i=0;space=False
    while i<len(sql):
        char=sql[i]
        if char.isspace():
            space=True;i+=1;continue
        if space and out: out.append(' ')
        space=False
        if char in "'\"":
            quote=char;start=i;i+=1
            while i<len(sql):
                if sql[i]==quote:
                    i+=1
                    if i<len(sql) and sql[i]==quote: i+=1;continue
                    break
                # Keep escaped content byte-for-byte rather than rewriting it.
                if sql[i]=='\\' and i+1<len(sql): i+=2
                else: i+=1
            else: raise ValueError('Unterminated quoted SQL content')
            out.append(sql[start:i]);continue
        if char=='$':
            match=re.match(r'\$(?:[A-Za-z_][A-Za-z_0-9]*)?\$',sql[i:])
            if match:
                tag=match.group();end=sql.find(tag,i+len(tag))
                if end<0: raise ValueError('Unterminated dollar-quoted SQL content')
                out.append(sql[i:end+len(tag)]);i=end+len(tag);continue
        # Preserve comments as content. Failing an innocuous formatting mismatch
        # is safer than collapsing different SQL text without lexical proof.
        if sql.startswith('--',i):
            end=sql.find('\n',i)
            if end<0: out.append(sql[i:]);break
            out.append(sql[i:end+1]);i=end+1;continue
        if sql.startswith('/*',i):
            start=i;depth=1;i+=2
            while i<len(sql) and depth:
                if sql.startswith('/*',i): depth+=1;i+=2
                elif sql.startswith('*/',i): depth-=1;i+=2
                else: i+=1
            if depth: raise ValueError('Unterminated SQL comment')
            out.append(sql[start:i]);continue
        out.append(char);i+=1
    return ''.join(out)


def fingerprint(sql):
    return hashlib.sha256(canonical_sql(sql).encode()).hexdigest()


def sql_kind(sql):
    match=re.match(r'\s*([A-Za-z]+)',sql)
    token=match.group(1).upper() if match else ''
    if token in {'BEGIN','START','SET','SAVEPOINT','RELEASE','DISCARD','COMMIT','END',
                 'ROLLBACK','ABORT','RESET','SHOW','DEALLOCATE','CLOSE'}:
        return 'control'
    if token in {'SELECT','WITH','INSERT','UPDATE','DELETE','MERGE','VALUES','FETCH'}:
        return 'data'
    return 'other'  # Retained in totals; no silent dropping of unclassified SQL.


def reconcile(calls,csv_rows,database,connections,allowed_jac_commands=('run','-c')):
    """Match ordered actual dispatches against each backend's CSV SQL events.

    connections maps actual BackendKeyData PIDs to observed startup metadata.
    The client label is verified as observed, never used as a PostgreSQL PID.
    All SQL dispatches for the owned diagnostic database must be supplied,
    including request-excluded startup/control/admin calls when present.
    """
    if not database or not connections: raise ValueError('Owned database/connections required')
    expected=defaultdict(list)
    for call in calls:
        if call.get('send_ns') is None: continue
        pid=call['backend_pid']
        if pid not in connections: raise ValueError('Unknown driver backend PID')
        connection=connections[pid]
        if call['database']!=database or connection['database']!=database:
            raise ValueError('Driver database ownership mismatch')
        if call['client_process_pid']!=connection['client_process_pid']:
            raise ValueError('Client OS process identity mismatch')
        if call.get('ready_ns') is None or call.get('ready_messages')!=1:
            raise ValueError('Incomplete protocol cycle')
        if call.get('protocol_mode')!='extended_single_statement':
            raise ValueError('Explicit single-statement extended-protocol evidence required')
        failed=bool(call.get('error_messages'))
        if call.get('command_complete')!=(0 if failed else 1):
            raise ValueError('CommandComplete/error counters inconsistent with one statement')
        expected[pid].append(call)
    actual=defaultdict(list)
    for row in csv_rows:
        if len(row)<23: raise ValueError('Malformed PostgreSQL CSV record')
        if row[2]!=database: continue
        message=row[13]
        executed=re.fullmatch(r'(?:execute <unnamed>: |statement: )([\s\S]+)',message)
        error=row[11]=='ERROR'
        looks_sql=message.startswith(('execute ','statement:'))
        if not (executed or error or looks_sql): continue
        try: pid=int(row[3]);line=int(row[6])
        except ValueError as error: raise ValueError('Invalid CSV backend/line identity') from error
        if pid not in connections: raise ValueError('Server SQL from unexpected owned-DB backend')
        connection=connections[pid]
        label=row[22]
        jac_label=re.fullmatch(r'jac:([1-9][0-9]*):([^\r\n:]+)',label)
        admin_label=re.fullmatch(r'ttg-cont-admin:([1-9][0-9]*)',label)
        valid_label=(jac_label and int(jac_label.group(1))==connection['client_process_pid']
            and jac_label.group(2) in allowed_jac_commands) or (
            admin_label and int(admin_label.group(1))==connection['client_process_pid'])
        if label!=connection['application_name'] or not valid_label:
            raise ValueError('Unexpected backend application label')
        if looks_sql and not executed: raise ValueError('Unexpected SQL logging format or named statement')
        if executed: actual[pid].append(dict(line=line,kind='execute',sql=canonical_sql(executed.group(1))))
        if error:
            if not row[19]: raise ValueError('Server error missing query text')
            actual[pid].append(dict(line=line,kind='error',sql=canonical_sql(row[19])))
    rows=[];totals=Counter()
    for pid in set(expected)|set(actual):
        events=sorted(actual[pid],key=lambda r:r['line'])
        if len({e['line'] for e in events})!=len(events): raise ValueError('Duplicate CSV SQL event line')
        cursor=0
        for call in sorted(expected[pid],key=lambda c:c['send_ns']):
            sql=canonical_sql(call['sql']);failed=bool(call['error_messages']);executed=False;error=False
            if cursor<len(events) and events[cursor]['kind']=='execute':
                if events[cursor]['sql']!=sql: raise ValueError('Driver/server SQL or order mismatch')
                executed=True;cursor+=1
            if failed:
                if cursor==len(events) or events[cursor]['kind']!='error' or events[cursor]['sql']!=sql:
                    raise ValueError('Expected driver error missing matching server error')
                error=True;cursor+=1
            elif not executed:
                raise ValueError('Successful driver call missing server execute')
            kind=sql_kind(sql)
            rows.append(dict(backend_pid=pid,fingerprint=fingerprint(sql),kind=kind,
                driver_dispatch=1,server_execute=int(executed),server_error=int(error)))
            totals.update(driver_dispatch=1,server_execute=int(executed),server_error=int(error),
                **{kind+'_dispatch':1})
        if cursor!=len(events): raise ValueError('Server SQL extras remain unmatched')
    return dict(passed=True,database=database,totals=dict(totals),statements=rows,
        definition='Exact ordered SQL dispatch/error reconciliation per observed PostgreSQL backend; execute/error logs are not blindly added')
