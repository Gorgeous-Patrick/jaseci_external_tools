import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import formal_supervisor as supervisor
import workloads
import gate

class SupervisorTests(unittest.TestCase):
    def fixture(self,root):
        reference=root/'reference.json'
        reference.write_text(json.dumps({'cases':[{'app':a,'policy':p,'full_semantic_sha256':'x','full_actions_sha256':'y'}
            for a in supervisor.ORIGINALS for p in gate.POLICIES]}))
        verifier=Path(supervisor.__file__).parent/'semantic_responses.py'
        plan=root/'plan.json';plan.write_text(json.dumps({'original_response_reference':{'path':str(reference),'sha256':gate.sha(reference)},
            'semantic_verifier_sha256':gate.sha(verifier)}))
        (root/'http-raw.jsonl').write_text('{}\n')
        return SimpleNamespace(experiment_plan=plan)
    def test_full_response_check_precedes_accepted_flag(self):
        with tempfile.TemporaryDirectory(prefix='ttg-supervisor-unit-') as directory:
            root=Path(directory);release=self.fixture(root);events=[]
            def trial(*args,**kwargs):
                events.append('workload_complete');kwargs['validate_after']();events.append('accepted');return {'passed':True}
            def audit(*args,**kwargs):events.append('full_response_check');return {'full_semantic_sha256':'x'}
            with patch.object(workloads,'trial',trial),patch.object(supervisor,'audit',audit):
                supervisor.install_semantic_guard(release)
                result=workloads.trial('linked_list','none',root,validate_after=lambda:events.append('source_guard'))
                self.assertTrue(result['passed'])
            self.assertEqual(events,['workload_complete','source_guard','full_response_check','accepted'])
            self.assertTrue((root/'response-semantic-audit.json').exists())
    def test_mismatch_never_reaches_accepted_flag(self):
        with tempfile.TemporaryDirectory(prefix='ttg-supervisor-unit-') as directory:
            root=Path(directory);release=self.fixture(root);events=[]
            def trial(*args,**kwargs):kwargs['validate_after']();events.append('accepted')
            with patch.object(workloads,'trial',trial),patch.object(supervisor,'audit',side_effect=ValueError('changed author')):
                supervisor.install_semantic_guard(release)
                with self.assertRaisesRegex(ValueError,'changed author'):
                    workloads.trial('jacord','ttg',root,validate_after=lambda:None)
            self.assertEqual(events,[])

if __name__=='__main__':unittest.main()
