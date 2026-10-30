"""Acceptance must not confuse one-policy or stale evidence with final completion."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from native import SUITE, WORKSPACE, acceptance_sources
from status import build_status


class AcceptanceStatusTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.snapshot = Path('/tmp/ttg-app-suite-runtime-frozen-20261029/snapshot.json')
        self.backend = SUITE / 'apps/issue_desk/server.jac'
        inventory = [{'path': str((SUITE / name).relative_to(WORKSPACE)), 'sha256': digest}
                     for name, digest in acceptance_sources().items()]
        inventory.append({'path': str(self.backend.relative_to(WORKSPACE)), 'sha256': hashlib.sha256(self.backend.read_bytes()).hexdigest()})
        (self.root / 'english-audit-final.json').write_text(json.dumps({'inventory': inventory, 'findings': []}))

    def tearDown(self):
        self.temp.cleanup()

    def case(self, policy, stale=False, unpinned=False):
        directory = self.root / policy / 'issue_desk'
        directory.mkdir(parents=True)
        versions = acceptance_sources()
        if stale: versions['web/app.js'] = 'old-ui'
        summary = {'app': 'issue_desk', 'seed': 42, 'policy': policy,
                   'native': 'passed', 'restart_persistence': 'passed', 'browser': 'passed',
                   'browser_mutations_after_restart': 'passed',
                   'source_sha256': {str(self.backend): hashlib.sha256(self.backend.read_bytes()).hexdigest()},
                   'acceptance_source_sha256': versions}
        (directory / 'summary.json').write_text(json.dumps(summary))
        (directory / 'run-manifest.json').write_text(json.dumps({'runtime': {'snapshot_sha256':
            'wrong-runtime' if unpinned else hashlib.sha256(self.snapshot.read_bytes()).hexdigest()}}))

    def test_one_policy_is_functional_but_not_complete(self):
        self.case('none'); result = build_status(self.root, self.snapshot)
        self.assertEqual(result['verified_any_policy_entries'], 1)
        self.assertEqual(result['complete_acceptance_entries'], 0)
        self.assertTrue(next(r for r in result['entries'] if r['id'] == 'issue_desk')['per_policy']['ttg']['missing_case'])

    def test_both_current_pinned_policies_complete(self):
        self.case('none'); self.case('ttg')
        self.assertEqual(build_status(self.root, self.snapshot)['complete_acceptance_entries'], 1)

    def test_stale_ui_blocks_acceptance(self):
        self.case('none'); self.case('ttg', stale=True)
        self.assertEqual(build_status(self.root, self.snapshot)['complete_acceptance_entries'], 0)

    def test_different_runtime_blocks_acceptance(self):
        self.case('none'); self.case('ttg', unpinned=True)
        self.assertEqual(build_status(self.root, self.snapshot)['complete_acceptance_entries'], 0)

    def test_missing_current_english_audit_blocks_acceptance(self):
        self.case('none'); self.case('ttg'); (self.root / 'english-audit-final.json').unlink()
        self.assertEqual(build_status(self.root, self.snapshot)['complete_acceptance_entries'], 0)


if __name__ == '__main__':
    unittest.main()
