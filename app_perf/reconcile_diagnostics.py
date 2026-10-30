#!/usr/bin/env python3
"""Supplemental, read-only reconciliation for the preserved diagnostic CSV labels.

The released run_diagnostics.py used application_name == 'jac'; the tested
runtime actually labels backends jac:<PID>:run. Do not edit or rerun that source.
This adapter accepts only that exact label and the known owned admin label.
"""
import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import re
from metrics import load_calls, verify_artifacts
from run_diagnostics import normalized

ADMIN='ttg-performance-owned-admin'
BACKEND=re.compile(r'jac:[1-9][0-9]*:run')
FAILURE='Frozen run_diagnostics.py exited 1 after all20 workflows and PG shutdown: application_name == jac selected zero actual jac:<PID>:run CSV rows; query mismatch at line77. No diagnostic rerun or bound source edit.'

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def reconcile(calls,server,database):
    driver=Counter(normalized(c['sql']) for c in calls if c.get('send_ns') is not None)
    driver_errors=Counter(normalized(c['sql']) for c in calls if c.get('send_ns') is not None and c.get('error'))
    executes,errors=Counter(),Counter()
    labels=set();admin_records=0
    for row in server:
        if len(row)<23:raise ValueError('Malformed PostgreSQL CSV record')
        if row[2]!=database:continue
        label=row[22]
        if label==ADMIN:
            admin_records+=1;continue
        if not BACKEND.fullmatch(label):raise ValueError('Unexpected backend label in owned database: '+repr(label))
        labels.add(label)
        if 'execute <unnamed>:' in row[13]:
            executes[normalized(row[13].split('execute <unnamed>:',1)[1])]+=1
        elif row[13].startswith(('execute ', 'statement:')):
            raise ValueError('Unexpected SQL dispatch log format')
        if row[11]=='ERROR':
            if not row[19]:raise ValueError('SQL error lacks a query fingerprint')
            errors[normalized(row[19])]+=1
    if not labels:raise ValueError('No runtime backend labels for owned database')
    if driver_errors!=errors:raise ValueError('Driver/server error fingerprints or counts differ')
    for sql in set(driver)|set(executes)|set(errors):
        if executes[sql]>driver[sql]:raise ValueError('Server SQL extras or excess execute count: '+sql)
        if driver[sql]-executes[sql]>errors[sql]:raise ValueError('Unexplained driver/server query mismatch: '+sql)
        if errors[sql]>driver[sql]:raise ValueError('Server SQL error extras: '+sql)
    return dict(driver_dispatches=sum(driver.values()),server_execute_records=sum(executes.values()),
        server_error_records=sum(errors.values()),trace_error_records=sum(driver_errors.values()),
        runtime_backend_labels=sorted(labels),excluded_admin_records=admin_records,passed=True,
        fingerprints=[dict(sql=q,driver=driver[q],server_execute=executes[q],server_error=errors[q]) for q in sorted(set(driver)|set(executes)|set(errors))])

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--diagnostics',type=Path,required=True)
    args=parser.parse_args();root=args.diagnostics.resolve()
    if (root/'postgres/data/postmaster.pid').exists():raise ValueError('PostgreSQL must be stopped before sealing logs')
    owner=json.loads((root/'postgres/owner.json').read_text())
    if owner['kind']!='ttg-performance-only':raise ValueError('Not an owned diagnostic cluster')
    output=root/'diagnostics.json'
    if output.exists():raise ValueError('Refuse to overwrite existing diagnostic completion evidence')
    paths=sorted((root/'postgres/data/logs').glob('*.csv'))
    if not paths:raise ValueError('Missing PostgreSQL CSV logs')
    before={str(p):sha(p) for p in paths};server=[]
    for path in paths:
        with path.open(newline='') as file:server.extend(csv.reader(file))
    cases=sorted(root.glob('*/summary.json'))
    if len(cases)!=20:raise ValueError('Exactly20 diagnostic cases required')
    checks=[];seals={};databases=set();apps=set()
    for path in cases:
        seal=verify_artifacts(path.parent,required=('summary.json','requests.json'))
        s=json.loads(path.read_text())
        if s['passed'] is not True or s['mode']!='diagnostic':raise ValueError('Invalid diagnostic case summary')
        if s['database'] in databases or not re.fullmatch(r'perf_[0-9a-f]{32}',s['database']):raise ValueError('Invalid/reused owned database')
        databases.add(s['database']);apps.add(s['app']);seals[str(path.parent)]=seal
        c=reconcile(load_calls(path.parent),server,s['database'])
        profiles=sorted((path.parent/'foreground-profiles').glob('*-thread_cpu.pstats'))
        if not profiles:raise ValueError('Missing thread-CPU profiles')
        c.update(app=s['app'],policy=s['policy'],database=s['database'],foreground_cpu_profiles=len(profiles),
            statement_logging=True,not_primary_timing=True)
        checks.append(c)
    from gate import POLICIES
    if len(apps)!=5 or {(c['app'],c['policy']) for c in checks}!={(a,p) for a in apps for p in POLICIES}:
        raise ValueError('Incomplete five-app/four-policy diagnostic matrix')
    after={str(p):sha(p) for p in paths}
    if before!=after:raise ValueError('CSV mutation during reconciliation')
    sources={str(Path(__file__).resolve()):sha(__file__)}
    for name in ('metrics.py','run_diagnostics.py'):
        p=Path(__file__).parent/name;sources[str(p.resolve())]=sha(p)
    report=dict(status='complete',apps=sorted(apps),checks=checks,
        role='Separate detailed SQL/bytes/model and foreground-thread CPU diagnostics; never substitute diagnostic HTTP/protocol times for primary data',
        profile_clock='time.thread_time for actual callback-thread CPU; other threads and blocking wait excluded',
        count_validation='Strict jac:<PID>:run backend labels and owned database; per-fingerprint executes/errors versus sealed driver dispatches; admin excluded explicitly',
        original_checker_failure=FAILURE,supplemental_reconciliation=True,
        csv_source_hashes=before,case_artifact_seals=seals,source_sha256=sources,
        profile_source_hashes={str(p):sha(p) for d in cases for p in sorted((d.parent/'foreground-profiles').glob('*-thread_cpu.pstats'))})
    output.write_text(json.dumps(report,indent=2)+'\n');print(output)

if __name__=='__main__':main()
