"""Synthetic release fixtures exercise refusal paths; never write the real release."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import gate

def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()

class FormalGateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='ttg-gate-unit-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        runtime = self.root / 'runtime'
        suite = self.root / 'suite'
        runtime.mkdir()
        suite.mkdir()
        (runtime / 'source.py').write_text('# synthetic runtime test source\n')
        (suite / 'app_suite').mkdir()
        (suite / 'app_suite/registry.json').write_text('{}\n')
        self.put('runtime/snapshot.json', dict(kind='runtime', commit=gate.COMMIT,
            files={'source.py': gate.sha(runtime / 'source.py')}, supplemental_dependencies={'test': 'synthetic'}))
        self.put('suite/snapshot.json', dict(kind='suite', final=True, before_sha256='same', after_sha256='same',
            files={'app_suite/registry.json': gate.sha(suite / 'app_suite/registry.json')},
            origins={'app_suite/registry.json': str(suite / 'app_suite/registry.json')}))
        rh, sh = gate.sha(runtime / 'snapshot.json'), gate.sha(suite / 'snapshot.json')
        (self.root / 'overlay').mkdir()
        (self.root / 'overlay/instrument.patch').write_text('synthetic test patch')
        self.put('overlay/snapshot.json', dict(kind='runtime_overlay', commit=gate.COMMIT,
            base_runtime_manifest_sha256=rh, patch_file='instrument.patch',
            files={'instrument.patch': gate.sha(self.root / 'overlay/instrument.patch')}))
        self.put('audit.json', dict(passed=True, suite_manifest_sha256=sh))
        acceptance = dict(schema_version=1, suite_manifest_sha256=sh, entries=[])
        preflight = dict(schema_version=1, runtime_manifest_sha256=rh, suite_manifest_sha256=sh,
            overlay_manifest_sha256=gate.sha(self.root / 'overlay/snapshot.json'), cases=[])
        for app in gate.APPS:
            entry = dict(app=app, policies={})
            for policy in ('none', 'ttg'):
                name = f'{app}-{policy}-acceptance.json'
                self.put(name, dict(app=app, policy=policy, seed=42, native='passed', restart_persistence='passed',
                    browser='passed', browser_mutations_after_restart='passed',
                    source_sha256={'registry.json': gate.sha(suite / 'app_suite/registry.json')},
                    acceptance_source_sha256={'registry.json': gate.sha(suite / 'app_suite/registry.json')}))
                entry['policies'][policy] = dict(native=True, restart_persistence=True, source_freshness=True,
                    english_audit=True, browser=True, browser_restart=True, summary=self.ref(name),
                    english_audit_evidence=self.ref('audit.json'))
            acceptance['entries'].append(entry)
            for policy in gate.POLICIES:
                name = f'{app}-{policy}-preflight.json'
                case = dict(app=app, policy=policy, seed=42, passed=True,
                    fixture_sha256=digest(app + 'fixture'), actions_sha256=digest(app + 'actions'), outputs_sha256=digest(app + 'outputs'))
                self.put(name, case)
                case['evidence'] = self.ref(name)
                preflight['cases'].append(case)
        self.put('acceptance.json', acceptance)
        self.put('preflight.json', preflight)
        (self.root / 'probe.py').write_text('# synthetic instrumentation\n')
        self.put('instrument.json', dict(protocol_validation_passed=True, overhead_control_passed=True,
            files=[self.ref('probe.py')]))
        self.put('plan.json', dict(seed=42, measured_trials=3, apps=gate.APPS, policies=gate.POLICIES,
            runtime_manifest_sha256=rh, suite_manifest_sha256=sh, primary_instrumentation='direct_boundary',
            overlay_manifest_sha256=gate.sha(self.root / 'overlay/snapshot.json')))
        self.release = dict(schema_version=1, status='approved', reviewer='main-agent', **{
            key: self.ref(name) for key, name in [
                ('runtime_manifest', 'runtime/snapshot.json'), ('suite_manifest', 'suite/snapshot.json'),
                ('overlay_manifest', 'overlay/snapshot.json'),
                ('acceptance_manifest', 'acceptance.json'), ('preflight_manifest', 'preflight.json'),
                ('instrument_manifest', 'instrument.json'), ('experiment_plan', 'plan.json')]})
        self.auth = self.root / 'unit-test-authorization.json'
        self.put(self.auth.name, self.release)

    def put(self, name, value):
        (self.root / name).write_text(json.dumps(value))

    def ref(self, name):
        return dict(path=name, sha256=gate.sha(self.root / name))

    def resign(self, name, key):
        self.release[key] = self.ref(name)
        self.put(self.auth.name, self.release)

    def test_valid_synthetic_fixture(self):
        self.assertEqual(gate.validate_formal_release(self.auth).authorization_sha256, gate.sha(self.auth))

    def test_missing_authorization(self):
        with self.assertRaisesRegex(gate.GateError, 'Missing/invalid'):
            gate.validate_formal_release(self.root / 'absent.json')

    def test_not_approved(self):
        self.release['status'] = 'pending'
        self.put(self.auth.name, self.release)
        with self.assertRaisesRegex(gate.GateError, 'No approved'):
            gate.validate_formal_release(self.auth)

    def test_incomplete_acceptance_gates(self):
        baseline = gate.read(self.root / 'acceptance.json')
        for name in ('native', 'browser', 'browser_restart', 'restart_persistence', 'source_freshness', 'english_audit'):
            with self.subTest(gate=name):
                value = copy.deepcopy(baseline)
                value['entries'][1]['policies']['ttg'][name] = False
                self.put('acceptance.json', value)
                self.resign('acceptance.json', 'acceptance_manifest')
                with self.assertRaisesRegex(gate.GateError, 'Incomplete acceptance'):
                    gate.validate_formal_release(self.auth)

    def test_missing_policy(self):
        value = gate.read(self.root / 'acceptance.json')
        value['entries'][4]['policies'].pop('ttg')
        self.put('acceptance.json', value)
        self.resign('acceptance.json', 'acceptance_manifest')
        with self.assertRaisesRegex(gate.GateError, 'Incomplete acceptance'):
            gate.validate_formal_release(self.auth)

    def test_missing_app(self):
        value = gate.read(self.root / 'acceptance.json')
        value['entries'].pop()
        self.put('acceptance.json', value)
        self.resign('acceptance.json', 'acceptance_manifest')
        with self.assertRaisesRegex(gate.GateError, 'exactly all30'):
            gate.validate_formal_release(self.auth)

    def test_source_mutation(self):
        (self.root / 'runtime/source.py').write_text('# changed\n')
        with self.assertRaisesRegex(gate.GateError, 'source mutated'):
            gate.validate_formal_release(self.auth)

    def test_manifest_hash_mismatch(self):
        self.release['suite_manifest']['sha256'] = '0' * 64
        self.put(self.auth.name, self.release)
        with self.assertRaisesRegex(gate.GateError, 'hash mismatch'):
            gate.validate_formal_release(self.auth)

    def test_new_unmanifested_source(self):
        (self.root / 'suite/extra.py').write_text('# injected\n')
        with self.assertRaisesRegex(gate.GateError, 'Unmanifested'):
            gate.validate_formal_release(self.auth)

    def test_non_equivalent_fixture_actions_outputs(self):
        baseline = gate.read(self.root / 'preflight.json')
        for field in ('fixture_sha256', 'actions_sha256', 'outputs_sha256'):
            with self.subTest(field=field):
                value = copy.deepcopy(baseline)
                case = value['cases'][0]
                case[field] = 'a' * 64
                name = case['evidence']['path']
                details = dict(case)
                details.pop('evidence')
                self.put(name, details)
                case['evidence'] = self.ref(name)
                self.put('preflight.json', value)
                self.resign('preflight.json', 'preflight_manifest')
                with self.assertRaisesRegex(gate.GateError, 'Non-equivalent'):
                    gate.validate_formal_release(self.auth)

    def test_failed_four_policy_preflight(self):
        value = gate.read(self.root / 'preflight.json')
        value['cases'][3]['passed'] = False
        self.put('preflight.json', value)
        self.resign('preflight.json', 'preflight_manifest')
        with self.assertRaisesRegex(gate.GateError, 'Failed preflight'):
            gate.validate_formal_release(self.auth)

    def test_instrumentation_mutation(self):
        (self.root / 'probe.py').write_text('# changed\n')
        with self.assertRaisesRegex(gate.GateError, 'Instrumentation mutated'):
            gate.validate_formal_release(self.auth)

if __name__ == '__main__':
    unittest.main(verbosity=2)
