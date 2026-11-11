"""Main-only hash-bound formal release for continuation measurements.

This module never creates an authorization. Synthetic/unit paths may be passed
to validate() by tests; the formal CLI always uses the fixed AUTHORIZATION path.
"""
from dataclasses import dataclass
import gzip
import itertools
import json
from pathlib import Path
import re
from evidence import checked_ref, read_json, sha256, verify_case
from configuration import run_config,signature as config_signature

OWN = Path(__file__).resolve().parent
WORKSPACE = OWN.parent.parent
EVIDENCE = WORKSPACE / 'project-notes/measurements/ttg-continuation-performance-20261030'
AUTHORIZATION = EVIDENCE / 'formal-run-authorization.json'
CONFIGURATIONS = (
    ('none', 'none', 'none'),
    ('legacy_ttg_thread', 'legacy_ttg', 'thread'),
    ('continuation_always_thread', 'continuation_always', 'thread'),
    ('continuation_always_process', 'continuation_always', 'process'),
    ('continuation_expected_benefit_thread', 'continuation_expected_benefit', 'thread'),
    ('continuation_expected_benefit_process', 'continuation_expected_benefit', 'process'),
)
CORE_SOURCE_NAMES=('gate.py','evidence.py','intervals.py','observation.py','protocol.py',
    'worker_clock.py','configuration.py','continuation_probe.py','boundary_overlay.py',
    'http_observer.py','control_server.py','perf_serve.py','runtime.sh','owned_postgres.py',
    'sql_admin.py','sql_reconciliation.py')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(value):
    require(isinstance(value, str) and re.fullmatch('[0-9a-f]{64}', value), 'Missing/invalid SHA256')
    return value


def payload_errors(value, path='$'):
    """Find nested fallback failures; top-level error lists are insufficient."""
    found = []
    if isinstance(value, dict):
        for key, child in value.items():
            here = path + '.' + key
            if key == 'payload_error' and child not in (None, False, '', [], {}):
                found.append(dict(path=here, error=child))
            if key in ('status', 'phase_status') and child == 'payload_error':
                found.append(dict(path=here, error=child))
            found.extend(payload_errors(child, here))
    elif isinstance(value, list):
        for i, child in enumerate(value):
            found.extend(payload_errors(child, f'{path}[{i}]'))
    return found


def check_tree(manifest_path):
    m = read_json(manifest_path)
    require(m.get('files'), 'Empty source manifest')
    root = Path(m['root']) if 'root' in m else Path(manifest_path).parent
    if not root.is_absolute():
        root = Path(manifest_path).parent / root
    root = root.resolve()
    actual = {str(p.relative_to(root)) for p in root.rglob('*') if p.is_file()}
    require(actual == set(m['files']), 'Snapshot contains missing or unlisted files')
    for name, expected in m['files'].items():
        path = (root / name).resolve()
        require(path.is_relative_to(root), 'Source path escapes snapshot')
        require(path.is_file() and sha256(path) == digest(expected), 'Source mutation: ' + str(path))
    for origin in m.get('origins', []):
        path = Path(origin['path'])
        require(path.is_file() and sha256(path) == digest(origin['sha256']), 'Source origin mutated')
    return m


def accepted_ref(reference, parent, label):
    path = checked_ref(reference, parent)
    value = read_json(path)
    require(value.get('passed') is True or value.get('accepted') is True, label + ' has not passed review')
    require(value.get('passed') is not False and value.get('accepted') is not False, label + ' contains a failed review flag')
    require(not payload_errors(value), label + ' contains payload_error')
    return path, value


def inspect_case_evidence(reference, parent):
    path = checked_ref(reference, parent)
    evidence = read_json(path)
    require(evidence.get('passed') is True, 'Failed correctness evidence')
    directory = path.parent
    seal = verify_case(directory, required=(path.name,))
    require(not payload_errors(evidence), 'Nested plan payload_error in correctness evidence')
    artifact = read_json(directory / 'artifacts.json')
    # Every structured raw model/request/worker file is inspected. Nothing is
    # accepted merely because an index omitted a late child or fallback error.
    for name in artifact['files']:
        source = directory / name
        if name.endswith(('.jsonl', '.jsonl.gz')):
            opener = gzip.open if name.endswith('.gz') else open
            with opener(source, 'rt') as file:
                for line in file:
                    if line.strip():
                        require(not payload_errors(json.loads(line)), 'Raw plan payload_error: ' + name)
        elif name.endswith('.json'):
            require(not payload_errors(read_json(source)), 'Raw plan payload_error: ' + name)
    return evidence, seal


@dataclass(frozen=True)
class Release:
    authorization_path: Path
    authorization_sha256: str
    runtime_manifest: Path
    overlay_manifest: Path
    suite_manifest: Path
    selection_path: Path
    correctness_path: Path
    instrument_path: Path
    plan_path: Path
    plan: dict
    selected_cases: tuple
    source_refs: tuple


def validate(path=AUTHORIZATION):
    path = Path(path).resolve()
    require(path.is_file(), 'Formal authorization absent; main has not released performance')
    authorization = read_json(path)
    require(authorization.get('schema_version') == 1, 'Unsupported authorization schema')
    require(authorization.get('approved') is True and authorization.get('approved_by') == 'main', 'Main approval required')
    parent = path.parent
    refs = authorization['artifacts']
    required = ('runtime', 'overlay', 'suite', 'selection', 'correctness', 'instrument', 'plan', 'main_review')
    require(set(refs) == set(required), 'Incomplete or unexpected release artifact set')
    paths = {name: checked_ref(refs[name], parent) for name in required}
    proof_refs = []
    review = read_json(paths['main_review'])
    require(review.get('accepted') is True, 'Main runtime/correctness review incomplete')
    for name in ('runtime', 'overlay', 'suite', 'selection', 'correctness', 'instrument', 'plan'):
        require(review['artifact_sha256'].get(name) == refs[name]['sha256'], 'Main review has stale ' + name)
    runtime = check_tree(paths['runtime'])
    require(runtime.get('kind') == 'runtime_snapshot' and runtime.get('immutable') is True, 'Tested immutable runtime required')
    require(re.fullmatch('[0-9a-f]{40}', runtime.get('commit', '')), 'Exact runtime commit required')
    require(runtime.get('continuation_dispatch') == 'runtime_hooks', 'Actual hook-driven continuation required')
    test_path, test_result = accepted_ref(runtime['test_evidence'], paths['runtime'].parent, 'Runtime tests')
    require(test_result.get('passed') is True, 'Runtime test execution must pass')
    proof_refs.append((str(test_path), sha256(test_path)))
    overlay = check_tree(paths['overlay'])
    require(overlay.get('kind') == 'experiment_overlay' and overlay.get('same_for_all_configurations') is True, 'Common experiment-only overlay required')
    require(overlay['base_runtime_manifest_sha256'] == refs['runtime']['sha256'], 'Overlay base mismatch')
    patch_path = checked_ref(overlay['patch'], paths['overlay'].parent)
    proof_refs.append((str(patch_path), sha256(patch_path)))
    suite = check_tree(paths['suite'])
    require(suite.get('kind') == 'benchmark_suite_snapshot' and suite.get('final') is True, 'Final coherent benchmark snapshot required')
    inventory_path = checked_ref(suite['case_inventory'], paths['suite'].parent)
    inventory_rows = read_json(inventory_path)['cases']
    inventory = {c['case_id']: c for c in inventory_rows}
    require(len(inventory) == len(inventory_rows), 'Duplicate testcase IDs in inventory')
    proof_refs.append((str(inventory_path), sha256(inventory_path)))
    selection = read_json(paths['selection'])
    require(selection.get('accepted') is True and selection['case_inventory_sha256'] == sha256(inventory_path), 'Case selection is incomplete/stale')
    selected = tuple(selection['case_ids'])
    require(selected and len(set(selected)) == len(selected), 'Empty/duplicate selected cases')
    require(all(c in inventory and inventory[c].get('implemented') is True for c in selected), 'Selected testcase is unimplemented')
    for c in selected:
        require({'native','oracle','fresh_session','restart'} <= set(inventory[c]['required_checks']), 'Mandatory correctness checks missing from inventory')
    plan = read_json(paths['plan'])
    require(plan.get('case_ids') == list(selected), 'Plan silently changes selected coverage')
    actual_configs = [(c['id'], c['policy'], c['executor']) for c in plan['configurations']]
    require(actual_configs == list(CONFIGURATIONS), 'All six required configurations must be explicit')
    for c in plan['configurations']:
        digest(c['effective_config_sha256'])
        require(c.get('run')==run_config(c['id']) and c['effective_config_sha256']==config_signature(c['id']),
            'Primary run settings differ from predeclared workers1/limit256/policy/model/executor controls')
    require(plan.get('measured_repeats', 0) >= 3 and plan.get('excluded_warmups', 0) >= 1, 'Three measured trials and excluded warmup required')
    require(plan.get('quiet_window_confirmed') is True, 'Coordinated quiet window not released')
    require(plan.get('startup_ipc_accounting') == 'included_and_separate', 'Process startup/IPC must remain included and separately attributed')
    require(plan.get('cache_regime') and plan.get('model_regime'), 'Explicit cache/model regimes required')
    seeds = plan['seeds']
    require(seeds and all(type(seed) is int for seed in seeds) and len(set(seeds)) == len(seeds), 'Explicit unique integer seeds required')
    instrument = read_json(paths['instrument'])
    require(instrument.get('passed') is True, 'Instrumentation not accepted')
    for name in ('protocol_validation', 'independent_sql_reconciliation', 'overhead_review', 'concurrency_review'):
        proof_path, _ = accepted_ref(instrument[name], paths['instrument'].parent, name)
        proof_refs.append((str(proof_path), sha256(proof_path)))
    require(instrument.get('runtime_manifest_sha256') == refs['runtime']['sha256'] and instrument.get('overlay_manifest_sha256') == refs['overlay']['sha256'], 'Instrumentation validation uses other runtime/overlay')
    required_sources = {str(OWN / name) for name in CORE_SOURCE_NAMES}
    require(required_sources <= set(instrument['sources']), 'Core observer/gate sources must be bound')
    for name, expected in instrument['sources'].items():
        require(Path(name).is_absolute(), 'Bound source paths must be absolute')
        require(sha256(name) == digest(expected), 'Instrument/analysis source mutation: ' + name)
    correctness = read_json(paths['correctness'])
    require(correctness.get('passed') is True, 'Correctness preflight not complete')
    require(correctness.get('runtime_manifest_sha256') == refs['runtime']['sha256'] and correctness.get('suite_manifest_sha256') == refs['suite']['sha256'], 'Correctness runtime/suite mismatch')
    rows = correctness['cases']
    keys = [(r['case_id'], r['seed'], r['config_id']) for r in rows]
    expected = set(itertools.product(selected, seeds, [c[0] for c in CONFIGURATIONS]))
    require(len(keys) == len(set(keys)) and set(keys) == expected, 'Incomplete/duplicate selected testcase correctness matrix')
    configurations = {c['id']: c for c in plan['configurations']}
    equivalence = {}
    for row in rows:
        require(row.get('passed') is True and not payload_errors(row), 'Failed case or nested plan payload_error')
        case = inventory[row['case_id']]
        require(all(row['checks'].get(name) is True for name in case['required_checks']), 'Incomplete native/fresh-session/restart/oracle checks')
        require(row['effective_config_sha256'] == configurations[row['config_id']]['effective_config_sha256'], 'Actual effective config differs')
        semantic_signature = tuple(digest(row[field]) for field in ('fixture_sha256', 'actions_sha256', 'output_sha256', 'state_sha256', 'oracle_sha256'))
        key = (row['case_id'], row['seed'])
        require(key not in equivalence or equivalence[key] == semantic_signature, 'Non-equivalent fixture/actions/results/state/oracle across configurations')
        equivalence[key] = semantic_signature
        evidence, seal = inspect_case_evidence(row['evidence'], paths['correctness'].parent)
        proof_refs.append((seal['path'], seal['sha256']))
        for name, expected_hash in read_json(seal['path'])['files'].items():
            proof_refs.append((str(Path(seal['path']).parent / name), expected_hash))
        require(evidence['case_id'] == row['case_id'] and evidence['config_id'] == row['config_id'] and evidence['seed'] == row['seed'], 'Evidence/index identity mismatch')
        for field in ('fixture_sha256', 'actions_sha256', 'output_sha256', 'state_sha256', 'oracle_sha256'):
            require(evidence[field] == row[field], 'Evidence/index semantic hash mismatch')
    return Release(path, sha256(path), paths['runtime'], paths['overlay'], paths['suite'], paths['selection'],
        paths['correctness'], paths['instrument'], paths['plan'], plan, selected,
        tuple((str(paths[k]), refs[k]['sha256']) for k in required) + tuple(proof_refs))


def revalidate(release):
    require(sha256(release.authorization_path) == release.authorization_sha256, 'Authorization changed during experiment')
    for path, expected in release.source_refs:
        require(sha256(path) == expected, 'Release artifact changed during experiment')
    for path in (release.runtime_manifest, release.overlay_manifest, release.suite_manifest):
        check_tree(path)
    instrument = read_json(release.instrument_path)
    for path, expected in instrument['sources'].items():
        require(sha256(path) == expected, 'Bound execution/analysis source changed during experiment')
