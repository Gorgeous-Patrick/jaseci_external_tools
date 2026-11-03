"""Bounded offline controls for exact48 schedule, release and DB attribution.

Recorded inputs are correctness-only shape fixtures; no benchmark samples run.
"""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from small_runner_v1 import schedule, complete_preflight, validate_release
from small_export_v1 import completeness, dispersion
from small_metrics_v1 import totals, scope_calls, summarize
from evidence import load_jsonl, read_json
from validate_preparation import EVIDENCE, OWN


class SmallTests(unittest.TestCase):
    def test_exact48_fresh_workflows_not_steady_read_replicates(self):
        rows=[dict(**r,passed=True) for r in schedule()]
        counts=completeness(rows)
        self.assertEqual(sum(n for (a,c,p),n in counts.items() if p=='measured'),36)
        self.assertEqual(sum(n for (a,c,p),n in counts.items() if p=='excluded_warmup'),12)
        self.assertEqual(len({r['trial_id'] for r in rows}),48)

    def test_missing_or_duplicate_workflow_export_rejected(self):
        rows=[dict(**r,passed=True) for r in schedule()]
        for invalid in (rows[:-1],rows[:-1]+[rows[0]]):
            with self.assertRaises(ValueError):completeness(invalid)

    def test_failed_case_export_rejected(self):
        rows=[dict(**r,passed=True) for r in schedule()];rows[2]['passed']=False
        with self.assertRaises(ValueError):completeness(rows)

    def test_three_workflow_dispersion_exact(self):
        result=dispersion([10,20,40])
        self.assertEqual(result['n'],3);self.assertEqual(result['median'],20)
        self.assertEqual(result['iqr'],15)
        with self.assertRaises(ValueError):dispersion([10,20])

    def test_missing_formal_release_denies_before_DB(self):
        with patch('gate.AUTHORIZATION',EVIDENCE/'deliberately-absent-release.json'):
            # validate() default is fixed at module load; test its actual
            # function with an explicit absent path, not the formal CLI.
            from gate import validate
            with self.assertRaisesRegex(ValueError,'authorization absent'):
                validate(EVIDENCE/'deliberately-absent-release.json')

    def test_subset_release_rejects_wrong_case_selection(self):
        from types import SimpleNamespace
        with patch('gate.validate',return_value=SimpleNamespace(selected_cases=('apps/littlex',),plan={})):
            with self.assertRaisesRegex(ValueError,'ONLY LittleX'):validate_release()

    def test_current_incomplete180_cannot_launch_formal(self):
        current=read_json(EVIDENCE/'apps-preflight-866222-v2/index.json')
        current['status']='running';current['passed']=False
        with tempfile.TemporaryDirectory(dir=OWN) as temp:
            path=Path(temp)/'index.json';path.write_text(json.dumps(current))
            with self.assertRaisesRegex(ValueError,'full180'):complete_preflight(path)

    def test_recorded_frozen_v2_shape_and_control_counts(self):
        for name in ('littlex-continuation_always_process','issue_desk-none'):
            d=EVIDENCE/'apps-preflight-866222-v2'/name
            calls=load_jsonl(d,'server-*.calls.jsonl*');requests=load_jsonl(d,'http-raw.jsonl*')
            assigned,startup=scope_calls(calls,requests)
            self.assertEqual(len(assigned)+len(startup),len(calls))
            business=[c for c,r in assigned if r['phase']=='workflow']
            result=totals(business)
            self.assertEqual(result['sql_dispatches'],result['sql_data']+result['sql_control']+result['sql_other'])
            self.assertGreater(result['sql_control'],0)
            self.assertGreaterEqual(result['protocol_sum_ns'],result['protocol_union_ns'])

    def test_correctness_capture_not_accepted_as_formal_metrics(self):
        d=EVIDENCE/'apps-preflight-866222-v2/issue_desk-none'
        with self.assertRaisesRegex(ValueError,'Formal semantic proof'):
            summarize(d,d.parent/'cleanup-acceptance/issue_desk-none.json')

    def test_actual_recorded_shapes_end_to_end_with_explicit_unit_stage_mock(self):
        # Only the in-memory stage label is mocked to exercise formal numeric
        # shape handling. Raw/proofs stay unchanged and no result is exported.
        d=EVIDENCE/'apps-preflight-866222-v2/littlex-continuation_always_process'
        import small_metrics_v1 as metrics
        original=metrics.read_json
        def stage_mock(path):
            value=original(path)
            if Path(path).name=='continuation-proof.json':
                value=copy.deepcopy(value);value['stage']='formal'
            return value
        with patch.object(metrics,'read_json',side_effect=stage_mock):
            result=summarize(d,d.parent/'cleanup-acceptance/littlex-continuation_always_process.json')
        self.assertTrue(result['passed']);self.assertEqual(result['config_id'],'continuation_always_process')
        self.assertEqual(len(result['profile_reset_events']),1)
        self.assertIsNone(result['clean_HTTP_e2e'])

    def test_summed_intervals_and_union_differ_under_overlap(self):
        base=dict(send_ns=10,ready_ns=30,driver_start_ns=5,driver_end_ns=32,role='foreground',
            sql='SELECT 1',command_complete=1,ready_messages=1,error_messages=0,data_rows=1,data_row_payload_bytes=8)
        bg=dict(base,send_ns=20,ready_ns=40,driver_start_ns=15,driver_end_ns=42,role='background_prefetch')
        result=totals([base,bg])
        self.assertEqual(result['protocol_sum_ns'],40);self.assertEqual(result['protocol_union_ns'],30)

    def test_scope_rejects_unassigned_overlap_and_generation_mismatch(self):
        request=dict(request='1:0',server_generation=1,start_ns=100,end_ns=200,
                     post_response_drain=dict(pending=0,end_ns=250))
        call=dict(driver_start_ns=110,driver_end_ns=150,server_generation=1,origin_request_id=None)
        with self.assertRaisesRegex(ValueError,'Unexplained unassigned'):scope_calls([call],[request])
        call['server_generation']=2
        with self.assertRaisesRegex(ValueError,'generation without HTTP'):scope_calls([call],[request])

    def test_unsealed_trace_injection_rejected(self):
        from evidence import verify_case,sha256
        with tempfile.TemporaryDirectory(dir=OWN) as temp:
            p=Path(temp);(p/'summary.json').write_text('{}')
            (p/'artifacts.json').write_text(json.dumps(dict(passed=True,files={'summary.json':sha256(p/'summary.json')})))
            (p/'server-extra.calls.jsonl').write_text('{}\n')
            with self.assertRaisesRegex(ValueError,'Unsealed matching'):verify_case(p)


if __name__=='__main__':unittest.main()
