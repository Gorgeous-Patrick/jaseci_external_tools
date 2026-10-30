"""Mocked original-app control-flow test. Executes NO actual app or database."""
import json
from datetime import datetime, timezone
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import workloads

class OriginalBaselineTest(unittest.TestCase):
    def test_naive_local_and_aware_mutation_timestamps_preserve_validity(self):
        import time
        now=time.time()
        fields={'created_at':datetime.fromtimestamp(now).isoformat(),
            'updated_at':datetime.fromtimestamp(now+.001).isoformat()}
        request=dict(path='/walker/SuiteInspect',wall_start=now-1,wall_end=now+1,
            output={'data':{'reports':[{'nodes':{'folder:session:0':{'fields':fields}}}]}})
        server=SimpleNamespace(requests=[request])
        self.assertEqual(len(workloads.validate_volatile_timestamps(server)),2)
        fields['created_at']=datetime.fromtimestamp(now,timezone.utc).isoformat()
        self.assertEqual(len(workloads.validate_volatile_timestamps(server)),2)
        fields['created_at']='2020-01-01T00:00:00Z'
        with self.assertRaisesRegex(workloads.GateError,'Invalid volatile timestamp'):
            workloads.validate_volatile_timestamps(server)

    def test_successful_201_registration_and_post_response_control(self):
        class Response:
            def __init__(self, status, value): self.status, self.value = status, value
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self): return json.dumps(self.value).encode()
        with tempfile.TemporaryDirectory(prefix='ttg-http-unit-') as directory:
            with patch.object(workloads, 'free_port', return_value=1), patch.object(workloads.urllib.request, 'urlopen', side_effect=[
                Response(201, {'ok': True, 'data': {'user_id': 'new-user'}, 'error': None}),
                Response(200, {'pending': 0, 'observed_threads': 0})]) as transport:
                server = workloads.Server(Path(directory), 'unused', Path(directory), 'primary', 'Traverse')
                self.assertEqual(server.post('/user/register', {}), {'user_id': 'new-user'})
                self.assertEqual(server.requests[0]['http_status'], 201)
                self.assertEqual(transport.call_count, 2)
                self.assertIn('/drain', transport.call_args_list[1].args[0].full_url)

    def test_original_operation_does_not_overwrite_baseline_evidence(self):
        with tempfile.TemporaryDirectory(prefix='ttg-original-control-unit-') as directory:
            root = Path(directory)
            fixture = [dict(id='11111111-1111-4111-8111-111111111111', kind='test-node', arch_type='Item')]
            class FakePostgres:
                port = 0
                def create_database(self): return 'perf_unit_test'
                def sql(self, *args): return json.dumps(fixture)
                def drop_completed_database(self, *args, **kwargs): pass
                def record(self, *args, **kwargs): pass
            class FakeServer:
                def __init__(self, *args):
                    self.requests, self.transcript, self.fixture = [], [], None
                    self.process = None
                def start(self): pass
                def stop(self): pass
                def post(self, *args): return {'token': 'unit-test-token'}
                def walker(self, name, *args):
                    if name == 'SuiteRoot': return ['11111111-1111-4111-8111-111111111111']
                    if name == 'SuiteImport':
                        self.fixture = self.capture_fixture()
                        return [{'item:0': '11111111-1111-4111-8111-111111111111'}]
                    raise AssertionError(name)
            def prepare(app, path, *args):
                path.mkdir()
                (path / 'dataset').mkdir()
                (path / 'dataset/manifest.json').write_text(json.dumps({'files': {'nodes.jsonl': 'synthetic'}, 'config': {'length': 2}}))
                (path / 'server.jac').write_text('// mocked test only\n')
            corpus = SimpleNamespace(SCALES={'smoke': {'length': 2}},
                make_graph=lambda *args: SimpleNamespace(nodes={'item:0': {}}),
                session=lambda *args: [{'op': 'traverse', 'target': 'item:0'}],
                result=lambda *args: ['item:0', 'item:1'])
            native = SimpleNamespace(SOURCES={'linked_list': None}, TYPES={'linked_list': (['Item'], ['Next'])},
                prepare=prepare, corpus=corpus, verify_snapshot=lambda *args: None,
                replay=lambda *args: ['item:0', 'item:1'])
            with patch.object(workloads, 'Server', FakeServer):
                first = workloads.trial('linked_list', 'none', root / 'first', FakePostgres(), native, None,
                    {'linked_list': {'read_walker': 'Traverse'}}, root, 'primary', steady_reads=0)
                baseline = {field: first[field] for field in ('fixture_sha256', 'actions_sha256', 'outputs_sha256')}
                preserved = dict(baseline)
                second = workloads.trial('linked_list', 'ttg', root / 'second', FakePostgres(), native, None,
                    {'linked_list': {'read_walker': 'Traverse'}}, root, 'primary', steady_reads=0, expected=baseline)
                self.assertTrue(second['passed'])
                self.assertEqual(baseline, preserved)
                self.assertEqual(second['initial_domain_kind_counts'], {'test-node': 1})
                self.assertIsNone(second['initial_domain_nodes'])

if __name__ == '__main__':
    unittest.main(verbosity=2)
