"""Fail-closed formal-run checks; this module NEVER creates authorization."""
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / 'project-notes/measurements/ttg-app-performance-20261030'
AUTHORIZATION = EVIDENCE / 'formal-run-authorization.json'
COMMIT = '5f94eb62da2857ab991de704935e7333b405cb8e'
APPS = ('linked_list', 'littlex', 'jacord', 'jdrive', 'issue_desk', 'approval_desk',
        'stock_room', 'clinic_queue', 'course_path', 'library_loans', 'event_seats',
        'help_queue', 'recipe_pantry', 'trip_board', 'delivery_route', 'hiring_pipeline',
        'sales_pipeline', 'grant_review', 'lab_samples', 'asset_care', 'utility_meter',
        'volunteer_shift', 'poll_assembly', 'budget_ledger', 'build_release',
        'knowledge_map', 'return_counter', 'garden_plan', 'tournament', 'incident_room')
POLICIES = ('none', 'ttg', 'dependency_always', 'dependency_expected_benefit')

class GateError(RuntimeError):
    pass

def require(condition, message):
    if not condition:
        raise GateError(message)

def sha(path):
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError as error:
        raise GateError(f'Missing/unreadable artifact: {path}') from error

def read(path):
    try:
        value = json.loads(Path(path).read_text())
    except (OSError, ValueError) as error:
        raise GateError(f'Missing/invalid JSON artifact: {path}') from error
    require(isinstance(value, dict), f'Expected JSON object: {path}')
    return value

def referenced(reference, base):
    require(isinstance(reference, dict) and isinstance(reference.get('path'), str), 'Missing evidence reference')
    path = Path(reference['path'])
    if not path.is_absolute():
        path = base / path
    require(sha(path) == reference.get('sha256'), f'Evidence hash mismatch: {path}')
    return path, read(path)

def verify_snapshot(path, kind, check_origins=False):
    manifest, root = read(path), path.parent
    require(manifest.get('kind') == kind, f'Expected {kind} snapshot')
    require(isinstance(manifest.get('files'), dict) and manifest['files'], 'Empty source manifest')
    if kind in ('runtime', 'runtime_overlay'):
        require(manifest.get('commit') == COMMIT, 'Wrong runtime commit')
        if kind == 'runtime':
            require(bool(manifest.get('supplemental_dependencies')), 'Unrecorded runtime bootstrap dependencies')
        else:
            require(manifest.get('patch_file') in manifest['files'], 'Exact instrumentation patch omitted')
    else:
        require(manifest.get('final') is True, 'Exploratory suite cannot authorize formal runs')
        require(manifest.get('before_sha256') == manifest.get('after_sha256'), 'Incoherent suite snapshot')
        require('app_suite/registry.json' in manifest['files'], 'Suite registry.json omitted')
    for name, digest in manifest['files'].items():
        file = root / name
        require(file.resolve().is_relative_to(root.resolve()), 'Manifest path escapes snapshot')
        require(sha(file) == digest, f'Snapshot source mutated: {file}')
        if check_origins:
            original = manifest.get('origins', {}).get(name)
            require(original is not None and sha(original) == digest, f'Shared source mutated since release: {original}')
    from freeze import EXTENSIONS, EXCLUDED
    extras = [str(p.relative_to(root)) for p in root.rglob('*') if p.is_file()
              and p.suffix in EXTENSIONS and str(p.relative_to(root)) not in manifest['files']
              and p != path and not any(part in EXCLUDED for part in p.relative_to(root).parts)]
    require(not extras, f'Unmanifested source files: {extras[:5]}')
    return manifest

def verify_acceptance(value, suite_hash, base, suite_manifest=None):
    require(value.get('schema_version') == 1, 'Unsupported acceptance schema')
    require(value.get('suite_manifest_sha256') == suite_hash, 'Acceptance suite mismatch')
    entries = value.get('entries', [])
    require(len(entries) == 30 and {e.get('app') for e in entries} == set(APPS), 'Acceptance must cover exactly all30')
    for entry in entries:
        app = entry['app']
        for policy in ('none', 'ttg'):
            case = entry.get('policies', {}).get(policy, {})
            gates = ['native', 'restart_persistence', 'source_freshness', 'english_audit']
            if app != 'linked_list':
                gates += ['browser', 'browser_restart']
            for name in gates:
                require(case.get(name) is True, f'Incomplete acceptance {app}/{policy}/{name}')
            _, summary = referenced(case.get('summary'), base)
            require(summary.get('app') == app and summary.get('policy') == policy and summary.get('seed') == 42,
                    f'Wrong summary identity {app}/{policy}')
            require(summary.get('native', summary.get('native_replay')) == 'passed', f'Native summary failed {app}/{policy}')
            require(summary.get('restart_persistence') == 'passed', f'Restart summary failed {app}/{policy}')
            if suite_manifest is not None:
                sources = summary.get('source_sha256', {})
                oracles = summary.get('acceptance_source_sha256', {})
                require(bool(sources) and bool(oracles), f'Unhashed backend/oracles: {app}/{policy}')
                reverse = {str(Path(origin).resolve()): name for name, origin in suite_manifest.get('origins', {}).items()}
                for filename, digest in sources.items():
                    name = reverse.get(str(Path(filename).resolve())) if Path(filename).is_absolute() else 'app_suite/' + filename
                    require(suite_manifest['files'].get(name) == digest, f'Stale accepted backend {app}/{policy}/{filename}')
                for filename, digest in oracles.items():
                    require(suite_manifest['files'].get('app_suite/' + filename) == digest, f'Stale accepted oracle {app}/{policy}/{filename}')
            if app != 'linked_list':
                require(summary.get('browser') == 'passed' and summary.get('browser_mutations_after_restart') == 'passed',
                        f'Browser summary failed {app}/{policy}')
            _, audit = referenced(case.get('english_audit_evidence'), base)
            require(audit.get('passed') is True and audit.get('suite_manifest_sha256') == suite_hash, 'English audit missing/stale')

def verify_preflight(value, runtime_hash, suite_hash, base, overlay_hash=None):
    require(value.get('schema_version') == 1, 'Unsupported preflight schema')
    require(value.get('runtime_manifest_sha256') == runtime_hash and value.get('suite_manifest_sha256') == suite_hash,
            'Preflight source mismatch')
    if overlay_hash is not None:
        require(value.get('overlay_manifest_sha256') == overlay_hash, 'Preflight effective overlay mismatch')
    cases = value.get('cases', [])
    expected = {(app, policy) for app in APPS for policy in POLICIES}
    require(len(cases) == 120 and {(c.get('app'), c.get('policy')) for c in cases} == expected, 'Preflight must cover all30 x4')
    for app in APPS:
        group = [c for c in cases if c['app'] == app]
        for case in group:
            require(case.get('seed') == 42 and case.get('passed') is True, f'Failed preflight {app}/{case.get("policy")}')
            _, details = referenced(case.get('evidence'), base)
            require(details.get('passed') is True and details.get('app') == app and details.get('policy') == case['policy'],
                    f'Failed/misidentified preflight evidence {app}/{case["policy"]}')
            for field in ('fixture_sha256', 'actions_sha256', 'outputs_sha256'):
                digest = case.get(field)
                require(isinstance(digest, str) and len(digest) == 64 and details.get(field) == digest,
                        f'Absent/inconsistent {field} {app}/{case["policy"]}')
        for field in ('fixture_sha256', 'actions_sha256', 'outputs_sha256'):
            require(len({c[field] for c in group}) == 1, f'Non-equivalent {field}: {app}')

@dataclass(frozen=True)
class Release:
    authorization_sha256: str
    runtime_manifest: Path
    overlay_manifest: Path
    suite_manifest: Path
    acceptance_manifest: Path
    preflight_manifest: Path
    instrument_manifest: Path
    experiment_plan: Path

def validate_formal_release(authorization=AUTHORIZATION):
    """Production uses the fixed default; override exists only for unit tests."""
    authorization = Path(authorization)
    value = read(authorization)
    require(value.get('schema_version') == 1 and value.get('status') == 'approved', 'No approved main review')
    require(value.get('reviewer') == 'main-agent', 'Reviewer must be main-agent')
    artifacts = {key: referenced(value.get(key), authorization.parent)[0] for key in (
        'runtime_manifest', 'overlay_manifest', 'suite_manifest', 'acceptance_manifest', 'preflight_manifest', 'instrument_manifest', 'experiment_plan')}
    runtime_hash, suite_hash = sha(artifacts['runtime_manifest']), sha(artifacts['suite_manifest'])
    verify_snapshot(artifacts['runtime_manifest'], 'runtime')
    overlay = verify_snapshot(artifacts['overlay_manifest'], 'runtime_overlay')
    require(overlay.get('base_runtime_manifest_sha256') == runtime_hash, 'Overlay clean-base mismatch')
    suite = verify_snapshot(artifacts['suite_manifest'], 'suite', True)
    verify_acceptance(read(artifacts['acceptance_manifest']), suite_hash, artifacts['acceptance_manifest'].parent, suite)
    verify_preflight(read(artifacts['preflight_manifest']), runtime_hash, suite_hash, artifacts['preflight_manifest'].parent,
                     sha(artifacts['overlay_manifest']))
    instrument = read(artifacts['instrument_manifest'])
    require(instrument.get('protocol_validation_passed') is True, 'Protocol validation incomplete')
    require(instrument.get('overhead_control_passed') is True, 'Overhead control incomplete')
    require(bool(instrument.get('files')), 'Missing instrumentation source hashes')
    for reference in instrument['files']:
        path = Path(reference['path'])
        if not path.is_absolute():
            path = artifacts['instrument_manifest'].parent / path
        require(sha(path) == reference.get('sha256'), f'Instrumentation mutated: {path}')
    plan = read(artifacts['experiment_plan'])
    require(plan.get('seed') == 42 and plan.get('measured_trials', 0) >= 3, 'Plan requires seed42 and >=3 trials')
    require(set(plan.get('apps', [])) == set(APPS) and set(plan.get('policies', [])) == set(POLICIES), 'Incomplete experiment plan')
    require(plan.get('runtime_manifest_sha256') == runtime_hash and plan.get('suite_manifest_sha256') == suite_hash, 'Plan source mismatch')
    require(plan.get('overlay_manifest_sha256') == sha(artifacts['overlay_manifest']), 'Plan overlay mismatch')
    require(plan.get('primary_instrumentation') == 'direct_boundary', 'Primary metrics require disclosed direct boundary overlay')
    return Release(sha(authorization), **artifacts)

def revalidate(previous):
    current = validate_formal_release()
    require(current == previous, 'Release changed; stop and start a NEW experiment')
    return current
