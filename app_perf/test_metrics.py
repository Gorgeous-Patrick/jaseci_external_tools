import unittest
import gzip
from pathlib import Path
import tempfile
import hashlib,json
from metrics import union_ns, aggregate, load_calls,verify_artifacts,audit_scope

class IntervalTests(unittest.TestCase):
    def test_first_workflow_request_is_a_separate_subset(self):
        requests=[dict(request='1:0',phase='workflow',end_ns=10_000_000,http_e2e_ms=10),
            dict(request='1:1',phase='workflow',end_ns=30_000_000,http_e2e_ms=10)]
        def call(rid,a,b):
            return dict(request=rid,send_ns=a*1_000_000,ready_ns=b*1_000_000,driver_start_ns=a*1_000_000,
                driver_end_ns=b*1_000_000,role='foreground',control=False,command_complete=1,ready_count=1,returned_rows=1,error=None)
        calls=[call('1:0',0,10),call('1:1',20,30)]
        self.assertEqual(aggregate(requests,calls,'workflow')['protocol_sum_ms'],20)
        first=aggregate(requests,calls,'first_workflow_request')
        self.assertEqual(first['requests'],1);self.assertEqual(first['protocol_sum_ms'],10)
    def test_valid_looking_unsealed_extra_trace_is_refused(self):
        with tempfile.TemporaryDirectory(prefix='ttg-injected-unit-') as directory:
            root=Path(directory);trace=root/'server-1.calls.jsonl';trace.write_text('{"request":"1:0"}\n')
            (root/'artifacts.json').write_text(json.dumps({'passed':True,'files':{trace.name:hashlib.sha256(trace.read_bytes()).hexdigest()}}))
            (root/'server-999.calls.jsonl').write_text('{"request":"1:0","ready_count":1000}\n')
            with self.assertRaisesRegex(ValueError,'unsealed'):load_calls(root)
    def test_unsealed_request_file_is_refused(self):
        with tempfile.TemporaryDirectory(prefix='ttg-request-unit-') as directory:
            root=Path(directory);(root/'artifacts.json').write_text(json.dumps({'passed':True,'files':{}}))
            (root/'requests.json').write_text('[]')
            with self.assertRaisesRegex(ValueError,'not sealed'):verify_artifacts(root,required=('requests.json',))
    def test_startup_is_proved_in_own_generation(self):
        requests=[dict(request='1:0',server_generation=1,start_ns=100,end_ns=200,phase='workflow'),
            dict(request='2:1',server_generation=2,start_ns=500,end_ns=600,phase='verify')]
        calls=[dict(request=None,trace_generation=1,source_trace='server-1.calls.jsonl',driver_start_ns=1,driver_end_ns=90),
            dict(request=None,trace_generation=2,source_trace='server-2.calls.jsonl',driver_start_ns=300,driver_end_ns=400)]
        self.assertEqual(audit_scope(requests,calls)['verified_startup_calls'],2)
        late=dict(calls[0],driver_start_ns=250,driver_end_ns=300)
        with self.assertRaisesRegex(ValueError,'after_last_recorded_http'):audit_scope(requests,calls+[late])
        overlap=dict(calls[0],driver_start_ns=150,driver_end_ns=160)
        with self.assertRaisesRegex(ValueError,'overlapping_recorded_http'):audit_scope(requests,calls+[overlap])
    def test_gap_and_wrong_generation_are_not_silently_excluded(self):
        requests=[dict(request='1:0',server_generation=1,start_ns=100,end_ns=200,phase='workflow'),
            dict(request='1:1',server_generation=1,start_ns=300,end_ns=400,phase='steady_read')]
        gap=dict(request=None,trace_generation=1,source_trace='server-1.calls.jsonl',driver_start_ns=220,driver_end_ns=240)
        with self.assertRaisesRegex(ValueError,'between_recorded_requests'):audit_scope(requests,[gap])
        wrong=dict(gap,request='1:0',trace_generation=2,source_trace='server-2.calls.jsonl')
        with self.assertRaisesRegex(ValueError,'generation_mismatch'):audit_scope(requests,[wrong])
    def test_valid_json_trace_replacement_is_refused_by_hash(self):
        with tempfile.TemporaryDirectory(prefix='ttg-artifact-unit-') as directory:
            root=Path(directory);trace=root/'server-1.calls.jsonl';trace.write_text('{"request":"1:0"}\n')
            (root/'artifacts.json').write_text(json.dumps({'passed':True,'files':{trace.name:hashlib.sha256(trace.read_bytes()).hexdigest()}}))
            self.assertEqual(verify_artifacts(root)['files_checked'],1)
            trace.write_text('{"request":"1:999"}\n')
            with self.assertRaisesRegex(ValueError,'hash mismatch'):load_calls(root)
    def test_duplicate_compressed_trace_is_refused(self):
        with tempfile.TemporaryDirectory(prefix='ttg-trace-unit-') as directory:
            path=Path(directory)/'server-1.calls.jsonl'
            path.write_text('{"request":"1:0"}\n')
            with gzip.open(str(path)+'.gz','wt') as file:
                file.write(path.read_text())
            with self.assertRaisesRegex(ValueError,'Duplicate raw/compressed'):
                load_calls(directory)

    def test_overlapping_sum_is_not_union(self):
        self.assertEqual(union_ns([(0,10),(5,15),(6,8),(20,25)]),20)
        self.assertEqual(union_ns([(None,None), (1,1)]),0)

    def test_controls_late_background_and_errors_are_retained(self):
        requests=[dict(request='1:0',phase='workflow',end_ns=12_000_000,http_e2e_ms=12)]
        def call(a,b,role,control,commands=1,error=None):
            return dict(request='1:0',send_ns=a*1_000_000,ready_ns=b*1_000_000,
                driver_start_ns=a*1_000_000,driver_end_ns=b*1_000_000,role=role,control=control,
                command_complete=commands,ready_count=1,returned_rows=0,error=error)
        calls=[call(0,10,'foreground',False),call(5,15,'background_prefetch',False),
            call(15,16,'foreground',True),call(16,17,'foreground',False,0,'expected SQL error')]
        result=aggregate(requests,calls,'workflow')
        self.assertEqual(result['protocol_sum_ms'],22)
        self.assertEqual(result['protocol_union_ms'],17)
        self.assertEqual(result['sql_dispatches'],4)
        self.assertEqual(result['protocol_cycles'],4)
        self.assertEqual(result['command_complete_count'],3)
        self.assertEqual(result['control_dispatches'],1)
        self.assertEqual(result['late_db_calls'],3)
        self.assertEqual(result['errors'],1)
        self.assertIsNone(result['pure_foreground_wait_ms'])

if __name__=='__main__':
    unittest.main()
