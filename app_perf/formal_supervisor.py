#!/usr/bin/env python3
"""Mandatory external response guard around the unchanged frozen runner.

Runs after requests and before the original trial's accepted flag, archive and
DB cleanup. No app action, measured clock, driver or server path is changed.
"""
import json
from pathlib import Path
import gate
import workloads
from semantic_responses import audit,ORIGINALS

def install_semantic_guard(release):
    plan=gate.read(release.experiment_plan)
    reference_path,reference=gate.referenced(plan['original_response_reference'],release.experiment_plan.parent)
    verifier=Path(__file__).resolve().parent/'semantic_responses.py'
    gate.require(gate.sha(verifier)==plan['semantic_verifier_sha256'],'Full-response verifier changed')
    expected={(case['app'],case['policy']):case for case in reference['cases']}
    gate.require(len(reference['cases'])==16 and len(expected)==16 and set(expected)=={(app,policy) for app in ORIGINALS for policy in gate.POLICIES},
        'Original full-response reference must cover all16')
    for app in ORIGINALS:
        for field in ('full_semantic_sha256','full_actions_sha256'):
            gate.require(len({expected[(app,p)][field] for p in gate.POLICIES})==1,'Non-equivalent original reference: '+app+'/'+field)
    original=workloads.trial
    def guarded(*args,**kwargs):
        app,policy,directory=args[:3]
        previous=kwargs.get('validate_after')
        if app in ORIGINALS:
            def validate():
                if previous:previous()
                result=audit(directory,expected[(app,policy)],sealed=False)
                result.update(passed=True,app=app,policy=policy,verifier_sha256=gate.sha(verifier),
                    reference_sha256=gate.sha(reference_path),raw_http_sha256=gate.sha(Path(directory)/'http-raw.jsonl'),
                    stage='After requests, before accepted flag/archive/owned DB cleanup; outside primary DB clocks')
                (Path(directory)/'response-semantic-audit.json').write_text(json.dumps(result,indent=2)+'\n')
            kwargs['validate_after']=validate
        return original(*args,**kwargs)
    workloads.trial=guarded

if __name__=='__main__':
    try:
        release=gate.validate_formal_release()
        install_semantic_guard(release)
        import runner
        runner.main()
    except gate.GateError as error:
        import sys
        print('REFUSED: '+str(error),file=sys.stderr)
        raise SystemExit(2)
