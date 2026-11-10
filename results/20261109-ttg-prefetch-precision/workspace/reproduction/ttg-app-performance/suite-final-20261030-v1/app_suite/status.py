#!/usr/bin/env python3
"""Report the 30-entry target from native evidence and current backend hashes."""
import argparse
import hashlib
import json
from pathlib import Path

SUITE = Path(__file__).resolve().parent
WORKSPACE = SUITE.parent.parent
ORIGINAL = [
    ('linked_list', 'LinkedList', 'microbenchmark', SUITE.parent / 'linked_list' / 'main.jac'),
    ('littlex', 'LittleX', 'application', SUITE.parent / 'littlex5' / 'server.jac'),
    ('jacord', 'Jacord', 'application', WORKSPACE / 'Jacord' / 'server.jac'),
    ('jdrive', 'JDrive', 'application', WORKSPACE / 'JDrive' / 'server.jac')]
ADDITIONS = [
    ('issue_desk', 'IssueDesk'), ('approval_desk', 'ApprovalDesk'), ('stock_room', 'StockRoom'),
    ('clinic_queue', 'ClinicQueue'), ('course_path', 'CoursePath'), ('library_loans', 'LibraryLoans'),
    ('event_seats', 'EventSeats'), ('help_queue', 'HelpQueue'), ('recipe_pantry', 'RecipePantry'),
    ('trip_board', 'TripBoard'), ('delivery_route', 'DeliveryRoute'), ('hiring_pipeline', 'HiringPipeline'),
    ('sales_pipeline', 'SalesPipeline'), ('grant_review', 'GrantReview'), ('lab_samples', 'LabSamples'),
    ('asset_care', 'AssetCare'), ('utility_meter', 'UtilityMeter'), ('volunteer_shift', 'VolunteerShift'),
    ('poll_assembly', 'PollAssembly'), ('budget_ledger', 'BudgetLedger'), ('build_release', 'BuildRelease'),
    ('knowledge_map', 'KnowledgeMap'), ('return_counter', 'ReturnCounter'), ('garden_plan', 'GardenPlan'),
    ('tournament', 'Tournament'), ('incident_room', 'IncidentRoom')]


def build_status(evidence_root, snapshot):
    from native import acceptance_sources
    current_oracles = acceptance_sources()
    runtime_hash = hashlib.sha256(snapshot.read_bytes()).hexdigest() if snapshot.exists() else None
    english_path = evidence_root / 'english-audit-final.json'
    english = json.loads(english_path.read_text()) if english_path.exists() else {}
    audited = {str((WORKSPACE / row['path']).resolve()): row['sha256'] for row in english.get('inventory', [])}
    english_current = bool(audited) and not english.get('findings') and all(
        Path(path).exists() and hashlib.sha256(Path(path).read_bytes()).hexdigest() == digest
        for path, digest in audited.items()) and all(str((SUITE / path).resolve()) in audited for path in current_oracles)
    snapshot_valid = False
    if snapshot.exists():
        snapshot_data = json.loads(snapshot.read_text())
        snapshot_files = snapshot_data.get('runtime_source_sha256', {})
        snapshot_valid = bool(snapshot_files) and all(
            (snapshot.parent / 'jac' / 'jaclang' / name).exists() and
            hashlib.sha256((snapshot.parent / 'jac' / 'jaclang' / name).read_bytes()).hexdigest() == digest
            for name, digest in snapshot_files.items())
    entries = ORIGINAL + [(key, name, 'application', SUITE / 'apps' / key / 'server.jac') for key, name in ADDITIONS]
    assert len(entries) == 30 and len({row[0] for row in entries}) == 30
    results = []
    summaries = [(path, json.loads(path.read_text())) for path in evidence_root.rglob('summary.json')]
    for key, name, kind, source in entries:
        cases = []
        for path, summary in summaries:
            if summary.get('app') != key:
                continue
            native = summary.get('native', summary.get('native_replay')) == 'passed'
            persisted = summary.get('restart_persistence') == 'passed'
            browser = kind == 'microbenchmark' or summary.get('browser') == 'passed'
            browser_restart = kind == 'microbenchmark' or summary.get('browser_mutations_after_restart') == 'passed'
            source_hashes = summary.get('source_sha256', {})
            current = bool(source_hashes)
            for filename, expected in source_hashes.items():
                file = Path(filename)
                if not file.is_absolute():
                    file = SUITE / file
                current = current and file.exists() and hashlib.sha256(file.read_bytes()).hexdigest() == expected
            oracle_hashes = summary.get('acceptance_source_sha256', {})
            oracle_current = oracle_hashes == current_oracles
            manifest = {}
            for manifest_name in ['run-manifest.json', 'run-run-manifest.json']:
                if (path.parent / manifest_name).exists(): manifest = json.loads((path.parent / manifest_name).read_text()); break
            if not manifest:
                for manifest_name in ['manifest.json', 'run-manifest.json']:
                    if (path.parent.parent / manifest_name).exists(): manifest = json.loads((path.parent.parent / manifest_name).read_text()); break
            pinned = snapshot_valid and bool(runtime_hash) and manifest.get('runtime', {}).get('snapshot_sha256') == runtime_hash
            backend_audited = all(str((Path(filename) if Path(filename).is_absolute() else SUITE / filename).resolve()) in audited for filename in source_hashes)
            gates = {'native': native, 'restart': persisted, 'browser': browser,
                     'browser_restart': browser_restart, 'backend_current': current,
                     'ui_oracle_current': oracle_current, 'pinned_runtime': pinned,
                     'seed42': summary.get('seed') == 42, 'english_current': english_current and backend_audited}
            cases.append({'seed': summary.get('seed'), 'policy': summary.get('policy'),
                          'scale': summary.get('scale', 'domain_scenario'), 'summary': str(path.resolve()),
                          'gates': gates, 'missing_gates': [name for name, value in gates.items() if not value],
                          'functional_passed': native and persisted and browser and browser_restart,
                          'current_functional_passed': native and persisted and browser and browser_restart and current and oracle_current,
                          'complete_case': all(gates.values())})
        policies = {}
        for policy in ['none', 'ttg']:
            matching = [case for case in cases if case['policy'] == policy]
            best = max(matching, key=lambda c: sum(c['gates'].values()), default=None)
            policies[policy] = {'accepted': any(c['complete_case'] for c in matching),
                                'best_case': best, 'missing_case': not matching,
                                'missing_gates': best['missing_gates'] if best else ['case_missing']}
        complete = all(policy['accepted'] for policy in policies.values())
        any_current = any(c['current_functional_passed'] for c in cases)
        results.append({'id': key, 'name': name, 'kind': kind, 'source': str(source),
                        'status': 'accepted' if complete else 'verified_any_policy' if any_current else 'implemented_unverified' if source.exists() else 'candidate',
                        'complete_acceptance': complete, 'verified_any_policy': any_current,
                        'historical_functional_passed': any(c['functional_passed'] for c in cases),
                        'per_policy': policies, 'cases': cases})
    verified = [row for row in results if row['complete_acceptance']]
    result = {'target_entries': 30, 'target_microbenchmarks': 1, 'target_full_applications': 29,
              'verified_entries': len(verified), 'complete_acceptance_entries': len(verified),
              'verified_any_policy_entries': sum(r['verified_any_policy'] for r in results),
              'historical_functional_entries': sum(r['historical_functional_passed'] for r in results),
              'verified_microbenchmarks': sum(row['kind'] == 'microbenchmark' for row in verified),
              'verified_full_applications': sum(row['kind'] == 'application' for row in verified),
              'remaining_entries': 30 - len(verified), 'entries': results,
              'required_runtime_snapshot_sha256': runtime_hash,
              'runtime_snapshot_integrity': snapshot_valid,
              'english_audit_current': english_current,
              'counting_contract': 'Complete acceptance requires BOTH none and ttg, seed42, exact pinned runtime and current backend/UI/oracle source versions. Functional evidence under one policy is separate. Performance unmeasured.',
              'db_call_ms': None, 'sql_count': None}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence', type=Path, default=WORKSPACE / 'project-notes' / 'measurements' / 'ttg-app-suite-20261029')
    parser.add_argument('--snapshot', type=Path, default=Path('/tmp/ttg-app-suite-runtime-frozen-20261029/snapshot.json'))
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = build_status(args.evidence, args.snapshot)
    if args.output:
        args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(f'{result["complete_acceptance_entries"]}/30 complete two-policy acceptance; '
          f'{result["verified_any_policy_entries"]} current one-or-more-policy passes; '
          f'{result["historical_functional_entries"]} historical functional passes')
    for row in result['entries']:
        print(f'{row["name"]}: {row["status"]}')


if __name__ == '__main__':
    main()
