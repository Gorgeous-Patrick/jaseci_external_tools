#!/usr/bin/env python3
"""Trace-backed per-cell observations and separately labeled CPU diagnostics."""
import argparse
from collections import defaultdict
import json
from pathlib import Path
import pstats
import hashlib
from gate import APPS,POLICIES
from metrics import load_calls,verify_artifacts

def sql_profile(directory):
    verify_artifacts(directory,required=('requests.json',))
    requests=json.loads((directory/'requests.json').read_text())
    chosen={r['request'] for r in requests if r['phase']=='workflow'}
    profile=defaultdict(lambda:{'calls':0,'protocol_ms':0.0,'control':False,'roles':set()})
    for call in load_calls(directory):
        if call.get('request') not in chosen:continue
        row=profile[call['fingerprint']];row['calls']+=1;row['control']=call['control'];row['roles'].add(call['role'])
        if call.get('ready_ns') is not None:row['protocol_ms']+=(call['ready_ns']-call['send_ns'])/1e6
    return profile

def cpu_profile(directory):
    verify_artifacts(directory,required=('requests.json',))
    requests=json.loads((directory/'requests.json').read_text())
    prefixes=[r['request'].replace(':','-')+'-' for r in requests if r['phase']=='workflow']
    files=[p for p in (directory/'foreground-profiles').glob('*-thread_cpu.pstats') if any(p.name.startswith(prefix) for prefix in prefixes)]
    if not files:return None
    stats=pstats.Stats(str(files[0]))
    for path in files[1:]:stats.add(str(path))
    top=[]
    for (file,line,name),(primitive,calls,self_time,cumulative,callers) in sorted(stats.stats.items(),key=lambda item:item[1][2],reverse=True)[:15]:
        top.append(dict(source=file,line=line,function=name,calls=calls,self_thread_cpu_s=self_time,cumulative_thread_cpu_s=cumulative))
    return dict(clock='time.thread_time',scope='Captured foreground callback threads only, diagnostic overhead included; not primary CPU or blocked wait',
        profiles=len(files),total_profiled_thread_cpu_s=stats.total_tt,top_self_cpu=top)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--experiment',type=Path,required=True)
    parser.add_argument('--review-artifacts',type=Path,required=True)
    parser.add_argument('--diagnostics',type=Path,required=True)
    parser.add_argument('--static-plans',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    integrity=json.loads((args.experiment/'results-integrity.json').read_text())
    if hashlib.sha256((args.experiment/'results.json').read_bytes()).hexdigest()!=integrity['results_sha256']:
        raise ValueError('Derived result integrity mismatch')
    result=json.loads((args.experiment/'results.json').read_text());assert result['complete']
    cells={(c['app'],c['policy']):c for c in result['cells'] if c['phase']=='workflow'}
    cover=json.loads((args.review_artifacts/'preflight-diagnostic-coverage.json').read_text())
    coverage={(c['app'],c['policy']):c for c in cover['cases']}
    static=json.loads(args.static_plans.read_text());plans={a['app']:a for a in static['apps']}
    fingerprints={}
    for app in APPS:
        for policy in POLICIES:
            samples=[s for s in result['samples'] if s['app']==app and s['policy']==policy and s['mode']=='primary' and s['phase']=='workflow']
            merged=defaultdict(lambda:{'calls':0,'protocol_ms':0.0,'control':False,'roles':set()})
            for sample in samples:
                for sql,value in sql_profile(Path(sample['directory'])).items():
                    merged[sql]['calls']+=value['calls'];merged[sql]['protocol_ms']+=value['protocol_ms']
                    merged[sql]['control']=value['control'];merged[sql]['roles'].update(value['roles'])
            fingerprints[(app,policy)]=(merged,len(samples))
    rows=[]
    for app in APPS:
        baseline=cells[(app,'none')];base_profile,base_n=fingerprints[(app,'none')]
        for policy in POLICIES[1:]:
            current=cells[(app,policy)];profile,n=fingerprints[(app,policy)];deltas=[]
            for sql in set(base_profile)|set(profile):
                before=base_profile.get(sql,{'calls':0,'protocol_ms':0});after=profile.get(sql,{'calls':0,'protocol_ms':0})
                deltas.append(dict(fingerprint=sql,mean_calls_per_trial_before=before['calls']/base_n,
                    mean_calls_per_trial_after=after['calls']/n,
                    mean_protocol_ms_per_trial_delta=after['protocol_ms']/n-before['protocol_ms']/base_n,
                    mean_calls_per_trial_delta=after['calls']/n-before['calls']/base_n))
            deltas.sort(key=lambda r:abs(r['mean_protocol_ms_per_trial_delta']),reverse=True)
            observed=coverage.get((app,policy))
            diag=args.diagnostics/f'{app}-{policy}'
            cpu=cpu_profile(diag) if (diag/'artifacts.json').exists() else None
            observations=[f"Measured protocol-sum median ratio policy/none: {current['protocol_sum_ms']['median']/baseline['protocol_sum_ms']['median']:.4f}.",
                f"Observed median SQL dispatch change: {current['sql_dispatches']['median']-baseline['sql_dispatches']['median']:+g}; control dispatch change: {current['control_dispatches']['median']-baseline['control_dispatches']['median']:+g}.",
                'Fingerprint deltas are observed contributors, not an exact causal partition; timing/reference variability remains.']
            if observed is not None and observed['totals']['considered_plans']==0:
                observations.append('No dependency plans were considered in recorded correctness diagnostics. This is zero observed mechanism coverage, not successful prefetch.')
            if observed is not None and observed['errors']:
                observations.append('Dependency diagnostics recorded errors; retain explicit feature-error/fallback status and investigate.')
            barriers=[{'walker':w['plan']['walker_name'],'candidate_abilities':w['plan']['candidates'],
                'supported_typed_visits':w['supported_typed_visits'],'potential_barriers':w['barrier_count'],
                'source_examples':w['barriers'][:2]} for w in plans[app]['walkers']]
            rows.append(dict(app=app,policy=policy,observations=observations,
                measured_sql_fingerprint_deltas=deltas[:10],foreground_cpu_diagnostic=cpu,
                profile_coverage='Captured separate diagnostic CPU profile' if cpu else 'Primary SQL trace profile only; no foreground CPU profile for this cell',
                actual_checkpoint_and_model_evidence=observed,
                static_plan_summary=barriers,
                static_interpretation='Potential compiler barriers/candidates only; not claimed dynamically reached without actual checkpoint/visit records'))
    args.output.write_text(json.dumps({'cells':rows,'pure_foreground_wait_ms':None,'no_fixed_overhead_subtraction':True},indent=2)+'\n')
    print(args.output)

if __name__=='__main__':main()
