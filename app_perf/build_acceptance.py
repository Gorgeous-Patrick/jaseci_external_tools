#!/usr/bin/env python3
"""Adapt final suite evidence and main independent audit; never grants release."""
import argparse
import json
from pathlib import Path
import shutil
import gate

def reference(path):
    return dict(path=str(path.resolve()), sha256=gate.sha(path))

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--suite', type=Path, required=True)
    parser.add_argument('--status', type=Path, required=True)
    parser.add_argument('--english', type=Path, required=True)
    parser.add_argument('--main-audit', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    suite = gate.verify_snapshot(args.suite.resolve(), 'suite', check_origins=True)
    status, english, audit = [gate.read(path) for path in (args.status, args.english, args.main_audit)]
    gate.require(status.get('complete_acceptance_entries') == 30 and status.get('english_audit_current') is True,
        'Shared suite all30/English gate incomplete')
    gate.require(audit.get('passed') is True and audit.get('cases') == 60 and audit.get('entries') == 30,
        'Main independent audit incomplete')
    gate.require(audit.get('source_status_sha256') == gate.sha(args.status), 'Main audit status hash stale')
    gate.require(not english.get('findings') and bool(english.get('inventory')), 'English scan incomplete')
    for item in english['inventory']:
        gate.require(gate.sha(gate.ROOT / item['path']) == item['sha256'], f'English audit stale: {item["path"]}')
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    for name, path in [('main-independent-audit.json', args.main_audit), ('suite-status.json', args.status), ('english-source-audit.json', args.english)]:
        shutil.copyfile(path, out / name)
    bound = dict(passed=True, suite_manifest_sha256=gate.sha(args.suite),
        basis='Main independent all60 audit plus current English source inventory; no performance authorization',
        main_audit=reference(out / 'main-independent-audit.json'), source_audit=reference(out / 'english-source-audit.json'))
    (out / 'english-audit-bound.json').write_text(json.dumps(bound, indent=2) + '\n')
    checked = {(row['app'], row['policy']): row for row in audit['checks']}
    value = dict(schema_version=1, suite_manifest_sha256=gate.sha(args.suite),
        main_audit=reference(out / 'main-independent-audit.json'), entries=[])
    for entry in status['entries']:
        app = entry['id']
        adapted = dict(app=app, policies={})
        for policy in ('none', 'ttg'):
            case = entry['per_policy'][policy]['best_case']
            gate.require(case['complete_case'] is True and all(case['gates'].values()), f'Incomplete {app}/{policy}')
            path = Path(case['summary'])
            main_checked = checked[(app, policy)]
            gate.require(str(path) == main_checked['summary'] and gate.sha(path) == main_checked['summary_sha256'],
                f'Summary differs from main audit: {app}/{policy}')
            adapted['policies'][policy] = dict(native=True, restart_persistence=True, source_freshness=True,
                english_audit=True, browser=app != 'linked_list', browser_restart=app != 'linked_list',
                summary=reference(path), english_audit_evidence=reference(out / 'english-audit-bound.json'))
        value['entries'].append(adapted)
    gate.verify_acceptance(value, gate.sha(args.suite), out, suite)
    (out / 'acceptance.json').write_text(json.dumps(value, indent=2) + '\n')
    print(str(out / 'acceptance.json'))

if __name__ == '__main__':
    main()
