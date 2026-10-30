#!/usr/bin/env python3
"""Main-authorized representative count/profile diagnostics AFTER primary matrix."""
from collections import Counter
import argparse
import csv
import json
import os
from pathlib import Path
import re
import subprocess
import gate
from metrics import load_calls
from owned_postgres import OwnedPostgres
import workloads

def normalized(sql):
    sql=re.sub(r'(?<!:):[A-Za-z_]\w*|\$\d+','?',sql)
    return re.sub(r'\s+',' ',sql).strip()

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--experiment',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    release=gate.validate_formal_release()
    from formal_supervisor import install_semantic_guard
    install_semantic_guard(release)
    result=json.loads((args.experiment/'results.json').read_text())
    gate.require(result.get('complete') is True,'Complete primary matrix required before diagnostic selection')
    plan=gate.read(release.experiment_plan)
    selected=list(plan['diagnostics']['representative_count_validation_apps'])
    med={(c['app'],c['policy']):c['protocol_sum_ms']['median'] for c in result['cells'] if c['phase']=='workflow'}
    regressions=sorted(gate.APPS,key=lambda app:max(med[(app,p)]/med[(app,'none')] for p in gate.POLICIES[1:]),reverse=True)
    for app in regressions:
        if len(selected)>=5:break
        if app not in selected:selected.append(app)
    out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    native,evaluate,readers=workloads.configure(release.suite_manifest)
    preflight=gate.read(release.preflight_manifest)
    expected={(r['app'],r['policy']):r for r in preflight['cases']}
    summaries=[]
    original_popen=subprocess.Popen
    def diagnostic_popen(command,*positional,**kwargs):
        command=list(command)
        if str(workloads.OWN/'perf_serve.py') in command:
            command[command.index(str(workloads.OWN/'perf_serve.py'))]=str(workloads.OWN/'diagnostic_serve.py')
            kwargs['env']=dict(kwargs['env'],TTG_PERF_CPU_OUTPUT=str(Path(kwargs['cwd'])/'foreground-profiles'),
                               TTG_PERF_PROFILE_CLOCK='thread_cpu')
        return original_popen(command,*positional,**kwargs)
    subprocess.Popen=diagnostic_popen
    try:
        with OwnedPostgres(out/'postgres',statement_logging=True) as postgres:
            for app in selected:
                for policy in gate.POLICIES:
                    gate.revalidate(release)
                    directory=out/f'{app}-{policy}'
                    summary=workloads.trial(app,policy,directory,postgres,native,evaluate,readers,
                        release.runtime_manifest.parent,'diagnostic',expected=expected[(app,policy)],
                        validate_after=lambda:gate.revalidate(release))
                    summary['directory']=str(directory);summaries.append(summary)
                    print(f'Diagnostic {app}/{policy}',flush=True)
    finally:
        subprocess.Popen=original_popen
    server=[]
    for path in (out/'postgres/data/logs').glob('*.csv'):
        with path.open(newline='') as file:server.extend(csv.reader(file))
    checks=[]
    for summary in summaries:
        calls=load_calls(summary['directory'])
        driver=Counter(normalized(r['sql']) for r in calls if r.get('send_ns') is not None)
        db=summary['database']
        rows=[r for r in server if len(r)>22 and r[2]==db and r[22]=='jac']
        executes=Counter(normalized(r[13].split('execute <unnamed>:',1)[1]) for r in rows if 'execute <unnamed>:' in r[13])
        errors=Counter(normalized(r[19]) for r in rows if r[11]=='ERROR' and r[19])
        trace_errors=sum(bool(r.get('error')) and r.get('send_ns') is not None for r in calls)
        for sql,count in executes.items():gate.require(driver[sql]>=count,'Server executes exceed driver trace for '+summary['app'])
        for sql,count in driver.items():gate.require(count-executes[sql]<=errors[sql],'Unexplained driver/server query mismatch for '+summary['app'])
        gate.require(trace_errors==sum(errors.values()),'Server/driver SQL-error counts differ for '+summary['app'])
        profile_files=list((Path(summary['directory'])/'foreground-profiles').glob('*-thread_cpu.pstats'))
        gate.require(bool(profile_files),'Missing actual foreground-thread CPU profiles')
        checks.append(dict(app=summary['app'],policy=summary['policy'],database=db,
            driver_dispatches=sum(driver.values()),server_execute_records=sum(executes.values()),server_error_records=sum(errors.values()),
            trace_error_records=trace_errors,passed=True,foreground_cpu_profiles=len(profile_files),
            statement_logging=True,not_primary_timing=True))
    report=dict(status='complete',apps=selected,checks=checks,
        role='Separate detailed SQL/bytes/model and foreground-thread CPU diagnostics; never substitute diagnostic HTTP/protocol times for primary data',
        profile_clock='time.thread_time for actual callback-thread CPU; other threads and blocking wait excluded',
        count_validation='Independent PostgreSQL CSV execute/errors per owned DB vs driver dispatch fingerprints; parse errors lack execute logs; execution errors may overlap execute logs')
    (out/'diagnostics.json').write_text(json.dumps(report,indent=2)+'\n')
    print(out/'diagnostics.json')

if __name__=='__main__':main()
