#!/usr/bin/env python3
"""Postprocess actual model/checkpoint evidence; retain zero-opportunity cases."""
import argparse
from collections import Counter
import json
import gzip
from pathlib import Path
from metrics import verify_artifacts

def summarize(directory):
    verify_artifacts(directory,required=('requests.json',))
    requests = json.loads((directory / 'requests.json').read_text())
    lookup = {r['request']: r for r in requests}
    result = {'directory': str(directory), 'requests': [], 'scope': 'Observed correctness-preflight diagnostics; not performance samples'}
    per_request = {}
    for path in sorted(directory.glob('server-*.calls.events.jsonl*')):
        opener=gzip.open if path.suffix=='.gz' else open
        with opener(path,'rt') as file:lines=file.read().splitlines()
        for line in lines:
            event = json.loads(line)
            rid = event.get('request')
            if event['kind'] != 'dependency' or rid not in lookup:
                continue
            request = lookup[rid]
            row = per_request.setdefault(rid, dict(request=rid, path=request['path'], phase=request['phase'],
                dependency_scopes=0, checkpoint_hits=0, certified_candidates=0,
                considered_plans=0, submitted=0, promoted=0, unused_cached=0, unavailable=0,
                reasons=Counter(), statuses=Counter(), actual_features=[], actual_outcomes=[], errors=[],
                checkpoint_records=[], hit_records=[]))
            row['dependency_scopes'] += 1
            summary = event['summary']
            row['checkpoint_hits'] += len(event.get('hits', []))
            row['hit_records'].extend(event.get('hits', []))
            row['checkpoint_records'].extend(event.get('checkpoints', []))
            for checkpoint in event.get('checkpoints', []):
                decision = checkpoint.get('decision', {})
                row['certified_candidates'] += int(all(decision.get(k) is True for k in ('stable', 'path_determined', 'execution_preserved')))
                row['reasons'].update(decision.get('reasons', []))
                row['statuses'].update([checkpoint.get('prefetch_status', 'not-recorded')])
            row['considered_plans'] += len(summary['plans'])
            for source, target in [('submitted_ids','submitted'), ('promoted_ids','promoted'),
                ('unused_cached_ids','unused_cached'), ('unavailable_ids','unavailable')]:
                row[target] += len(summary.get(source, []))
            row['actual_outcomes'].extend(summary.get('feedback', []))
            row['errors'].extend(summary.get('errors', []))
            for plan in summary['plans']:
                # Preserve the original feature snapshots, decision reasons,
                # probe/sample state, timing and actual target cardinalities.
                row['actual_features'].append(plan)
                row['statuses'].update([plan.get('status', 'not-recorded')])
    for rid, row in per_request.items():
        row['reasons'], row['statuses'] = dict(row['reasons']), dict(row['statuses'])
        row['payload_consumed_bytes'] = None
        row['zero_opportunities'] = row['considered_plans'] == 0
        result['requests'].append(row)
    result['totals'] = {name: sum(r[name] for r in result['requests']) for name in (
        'dependency_scopes', 'checkpoint_hits', 'certified_candidates', 'considered_plans',
        'submitted', 'promoted', 'unused_cached', 'unavailable')}
    result['errors'] = [error for r in result['requests'] for error in r['errors']]
    return result

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--preflight', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    index = json.loads(args.preflight.read_text())
    rows = []
    for case in index['cases']:
        if case['policy'].startswith('dependency_'):
            result = summarize(Path(case['evidence']['path']).parent)
            result.update(app=case['app'], policy=case['policy'])
            rows.append(result)
    args.output.write_text(json.dumps({'cases': rows, 'not_performance_samples': True}, indent=2) + '\n')
