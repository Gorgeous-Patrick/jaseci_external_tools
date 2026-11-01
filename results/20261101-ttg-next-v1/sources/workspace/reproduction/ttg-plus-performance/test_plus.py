"""Bounded offline tests; no runtime, service, DB, or benchmark execution."""
import copy
import contextlib
import gzip
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from plus_config import OWN,EVIDENCE,APP_CASES,CELLS,schedule,run_config,MAX_STEPS,PREVIOUS
from interop import Applications,sha256,read_json,reference,checked_ref,verify_case,scope_calls,totals
from storage import compress_closed_traces
from semantic import independent_replay
from export import aggregate,dispersion
from review import release,check_sources,check_regime,build
from runner import absolute_paths,linked_list_mechanism,run
from plus_metrics import compact_outcome,iter_events,summarize
from trial import load_unsealed


class Configuration(unittest.TestCase):
    def test_exact9_and36(self):
        self.assertEqual(len(schedule(False)),9);self.assertEqual(len(schedule(True)),36)
        self.assertEqual(len({r['trial_id'] for r in schedule(True)}),36)
        for case,*_ in APP_CASES:
            for cell in CELLS:
                chosen=[r for r in schedule(True) if r['case_id']==case and r['config_id']==cell]
                self.assertEqual([r['repeat'] for r in chosen],[-1,0,1,2])
    def test_common_budget_toggle(self):
        self.assertEqual(MAX_STEPS,32768)
        a=run_config('prefusion');b=run_config('ttg_plus')
        self.assertEqual({k:v for k,v in a.items() if k!='ttg_fused_sql'},
                         {k:v for k,v in b.items() if k!='ttg_fused_sql'})
        self.assertFalse(a['ttg_fused_sql']);self.assertTrue(b['ttg_fused_sql'])
        self.assertEqual(a['prefetch_limit'],2048);self.assertEqual(a['prefetch_workers'],1)
        self.assertEqual(a['async_prefetch'],'process');self.assertEqual(run_config('off')['prefetching'],'none')
    def test_balanced_measured_order(self):
        for case,*_ in APP_CASES:
            rows=[r for r in schedule(True) if r['case_id']==case and r['phase']=='measured']
            for cell in CELLS:self.assertEqual({i%3 for i,r in enumerate(rows) if r['config_id']==cell},{0,1,2})
    def test_missing_release(self):
        with patch('review.check_plan',return_value={}):
            with self.assertRaisesRegex(ValueError,'release is absent'):release(Path('/not-a-plan'))
    def test_final_rebuild_accepts_identical_closure_at_new_path(self):
        # Metadata-only build twice, preserving the exact original runtime refs.
        # No runtime/bootstrap/SQL occurs; tree check is outside this path test.
        with tempfile.TemporaryDirectory(dir=OWN) as temp:
            root=Path(temp);runtime=root/'runtime.json';runtime.write_text('{}')
            overlay=root/'overlay.json';overlay.write_text('{}')
            first=root/'first';final=root/'final'
            with patch('review.check_plan'):
                build(first,runtime,overlay);build(final,runtime,overlay)
            a=read_json(first/'plan.json');b=read_json(final/'plan.json')
            self.assertNotEqual(a['sources']['path'],b['sources']['path'])
            check_regime(a,b,root)
    def test_rebuild_rejects_different_source_closure(self):
        with tempfile.TemporaryDirectory(dir=OWN) as temp:
            root=Path(temp);one=root/'one.json';two=root/'two.json'
            one.write_text(json.dumps(dict(files={str(Path(__file__).resolve()):sha256(__file__)})))
            two.write_text(json.dumps(dict(files={str(OWN/'plus_config.py'):sha256(OWN/'plus_config.py')})))
            with self.assertRaisesRegex(ValueError,'closure differs'):
                check_regime(dict(sources=reference(one)),dict(sources=reference(two)),root)


class Compression(unittest.TestCase):
    def test_roundtrip_and_duplicate(self):
        with tempfile.TemporaryDirectory(dir=OWN) as temp:
            path=Path(temp)/'server-1.calls.jsonl';raw=b'{"actual":true}\n'*100;path.write_bytes(raw)
            result=compress_closed_traces(temp,True)
            self.assertFalse(path.exists());self.assertEqual(gzip.decompress(path.with_suffix('.jsonl.gz').read_bytes()),raw)
            self.assertEqual(result[0]['uncompressed_bytes'],len(raw))
            path.write_bytes(raw)
            with self.assertRaisesRegex(ValueError,'Duplicate'):compress_closed_traces(temp,True)
    def test_active_services_refused(self):
        with self.assertRaisesRegex(ValueError,'stopped'):compress_closed_traces(OWN,False)
    def test_unowned_refused(self):
        with self.assertRaisesRegex(ValueError,'NEW owned'):compress_closed_traces('/tmp',True)


class RecordedNativeOracle(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.apps=Applications()
        cls.origin=PREVIOUS.parent.parent/'project-notes/measurements/ttg-continuation-performance-20261030/apps-preflight-866222-v2/linked_list-none'
    def prepare(self,temp,corrupt=False):
        path=Path(temp)
        for name in ('summary.json','requests.json','final-graph-raw.json','mapping-initial.json'):
            (path/name).write_bytes((self.origin/name).read_bytes())
        rows=[json.loads(line) for line in (self.origin/'http-raw.jsonl').read_text().splitlines()]
        rows=[r for r in rows if r['phase'] not in ('steady_warmup','steady_read')]
        if corrupt:
            row=next(r for r in rows if r['phase']=='workflow' and '/walker/Traverse/' in r['path'])
            row['output']['data']['reports'][0]=999
        (path/'http-raw.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows))
        semantic=self.apps.semantic.audit(path,sealed=False)
        proof=dict(passed=True,checks=dict(native=True,oracle=True,fresh_session=True,restart=True),
            output_sha256=semantic['full_semantic_sha256'],full_response={k:semantic[k] for k in
                ('full_semantic_sha256','full_actions_sha256')})
        (path/'plus-proof.json').write_text(json.dumps(proof))
        (path/'artifacts.json').write_text(json.dumps(dict(passed=True,files={p.name:sha256(p)
            for p in path.iterdir() if p.name!='artifacts.json'})))
        return dict(case_id='linked_list32',app='linked_list',scale='smoke',length=32)
    def test_actual_recorded_native_shape(self):
        with tempfile.TemporaryDirectory(dir=OWN) as temp:
            case=self.prepare(temp);result=independent_replay(temp,case)
            self.assertTrue(result['passed']);self.assertEqual(result['actual_operations_checked'],6)
    def test_truthfully_resealed_wrong_business_result(self):
        with tempfile.TemporaryDirectory(dir=OWN) as temp:
            case=self.prepare(temp,True);verify_case(temp)
            with self.assertRaises((AssertionError,ValueError)):independent_replay(temp,case)
    def test_source_mutation_refused(self):
        with tempfile.TemporaryDirectory(dir=OWN) as temp:
            path=Path(temp)/'bound.py';path.write_text('original')
            manifest=Path(temp)/'sources.json';manifest.write_text(json.dumps(dict(files={str(path):sha256(path)})))
            check_sources(manifest);path.write_text('changed')
            with self.assertRaisesRegex(ValueError,'mutated'):check_sources(manifest)
    def test_actual_dry_fixture_preparation_all_three_workloads(self):
        native=self.apps.native;old=native.corpus.revision
        native.corpus.revision=lambda path:dict(source_kind='immutable_accepted_app_snapshot',requested_path=str(path))
        try:
            with tempfile.TemporaryDirectory(dir=OWN) as temp:
                for case,app,scale,length in APP_CASES:
                    directory=Path(temp)/case
                    self.assertFalse(directory.exists())
                    native.prepare(app,directory,scale,42,'none')
                    self.assertTrue((directory/'server.jac').is_file())
                    self.assertTrue((directory/'dataset/manifest.json').is_file())
                    self.assertTrue((directory/'native_seed.py').is_file())
                    with self.assertRaises(FileExistsError):native.prepare(app,directory,scale,42,'none')
        finally:native.corpus.revision=old
    def test_relative_launch_paths_become_exact_absolute_context(self):
        output,cluster=absolute_paths('project-notes/measurements/ttg-plus-performance-20261031/new-test',
            'reproduction/ttg-plus-performance/new-pg-test')
        self.assertTrue(output.is_absolute() and cluster.is_absolute())
        directory=output/'cases'/'linked_list32-off-correctness-0'
        self.assertEqual(directory,directory.resolve())
        self.assertEqual(str(directory/'dataset'),str(directory.resolve()/'dataset'))


class Arithmetic(unittest.TestCase):
    def test_dispersion_is_workflow_n(self):
        result=dispersion([10,20,30]);self.assertEqual((result['n'],result['median'],result['stdev']),(3,20,10))
    def test_missing_sample_refused(self):
        with self.assertRaisesRegex(ValueError,'Exactly3'):aggregate([])
    def test_total_counts_do_not_drop_background_controls(self):
        def call(a,b,sql,role):return dict(send_ns=a,ready_ns=b,driver_start_ns=a-1,driver_end_ns=b+1,
            role=role,sql=sql,command_complete=1,ready_messages=1,error_messages=0,data_rows=1,data_row_payload_bytes=8)
        result=totals([call(0,10,'SELECT 1','foreground'),call(5,15,'DISCARD ALL','background_continuation')])
        self.assertEqual((result['sql_dispatches'],result['sql_data'],result['sql_control']),(2,1,1))
        self.assertEqual((result['protocol_sum_ns'],result['protocol_union_ns']),(20,15))


class MechanismSanity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        index=read_json(EVIDENCE/'correctness-v3/index.json')
        cls.recorded={row['config_id']:read_json(checked_ref(row['result']['metrics'],EVIDENCE))
            for row in index['rows'] if row['case_id']=='linked_list32'}
        assert set(cls.recorded)==set(CELLS)
        for metric in cls.recorded.values():
            metric['model_outcomes']=[compact_outcome(e,dict(unit_fixture=True,index=i))
                for i,e in enumerate(metric['model_outcomes'])]
    def positive(self,case='linked_list32'):
        # Pure synthetic counter fixture, never sealed/exported as a sample.
        metrics=copy.deepcopy(self.recorded)
        for cell,metric in metrics.items():metric['case_id']=case
        def traverse(cell):
            return next(r for r in metrics[cell]['request_metrics'] if r['phase']=='workflow' and
                r['path'].split('/')[2:3]==['Traverse'])
        for cell in ('prefusion','ttg_plus'):
            request=traverse(cell)
            summary=next(e['summary'] for e in metrics[cell]['model_outcomes'] if
                e['origin_request_id']==request['request'] and
                str(e['server_generation'])==str(request['server_generation']))
            summary['resolved_plan_count']=1;summary['resolved_targets_cumulative']=31
            summary['submitted_count']=1;summary['fusion']['payload_dispatches']=1
            request['roles']['background_continuation']['sql_dispatches']=3
            request['roles']['foreground']['sql_dispatches']=request['sql_dispatches']-3
            if cell=='ttg_plus':
                summary['fusion']['queries']=1;request['sql_dispatches']=15
                request['sql_data']=8;request['sql_control']=7
                request['roles']['foreground']['sql_dispatches']=12
        return metrics
    def test_recorded_all75_fusion0_rejected(self):
        result=linked_list_mechanism('linked_list32',self.recorded)
        self.assertFalse(result['passed']);self.assertEqual(result['status'],'failed')
        self.assertEqual({v['total_SQL'] for v in result['facts'].values()},{75})
        self.assertEqual(result['facts']['ttg_plus']['fused_queries'],0)
        self.assertEqual(len(result['failed_checks']),4)
    def test_synthetic_reduced_total_with_activation_passes_both_lengths(self):
        for case in ('linked_list32','linked_list1000'):
            with self.subTest(case=case):self.assertTrue(linked_list_mechanism(case,self.positive(case))['passed'])
    def test_foreground_shift_without_total_reduction_rejected(self):
        metrics=self.positive();request=next(r for r in metrics['ttg_plus']['request_metrics'] if '/walker/Traverse/' in r['path'])
        request['sql_dispatches']=75;request['sql_data']=68
        request['roles']['background_continuation']['sql_dispatches']=63
        result=linked_list_mechanism('linked_list32',metrics)
        self.assertFalse(result['checks']['Traverse_TOTAL_SQL_below_off'])
    def test_planned_payload_without_actual_background_SQL_rejected(self):
        metrics=self.positive();request=next(r for r in metrics['prefusion']['request_metrics'] if '/walker/Traverse/' in r['path'])
        request['roles']['background_continuation']['sql_dispatches']=0
        request['roles']['foreground']['sql_dispatches']=75
        result=linked_list_mechanism('linked_list32',metrics)
        self.assertFalse(result['checks']['prefusion_payload_active'])
    def test_other_request_or_generation_fusion_does_not_activate_Traverse(self):
        for foreign in ('request','generation'):
            metrics=self.positive();request=next(r for r in metrics['ttg_plus']['request_metrics'] if '/walker/Traverse/' in r['path'])
            event=next(e for e in metrics['ttg_plus']['model_outcomes'] if e['origin_request_id']==request['request'])
            event['summary']['fusion']['queries']=0;extra=copy.deepcopy(event);extra['summary']['fusion']['queries']=99
            if foreign=='request':extra['origin_request_id']='different-request'
            else:extra['server_generation']='different-generation'
            metrics['ttg_plus']['model_outcomes'].append(extra)
            with self.subTest(foreign=foreign):
                self.assertFalse(linked_list_mechanism('linked_list32',metrics)['checks']['Traverse_fused_queries_positive'])
    def test_runner_stops_before_next_workload_preserves_status_and_closes_cluster(self):
        for failed_case,expected_started in [('linked_list32',3),('linked_list1000',6)]:
            with self.subTest(failed_case=failed_case),tempfile.TemporaryDirectory(dir=EVIDENCE) as temp:
                root=Path(temp);output=root/'run';file=root/'synthetic.json';file.write_text(json.dumps(dict(root=str(root))))
                value=reference(file);plan=dict(runtime=value,overlay=value,sources=value,app_snapshot=value)
                plan_path=root/'plan.json';plan_path.write_text(json.dumps(plan));started=[];closed=[];test=self
                class FakePostgres:
                    def __init__(self,*args):self.owner='synthetic-only';self.databases=set()
                    def __enter__(self):return self
                    def __exit__(self,*args):closed.append(True)
                class FakeTrial:
                    def run(self,row,cell,directory,pg,*args):
                        started.append(row['case_id']);directory.mkdir()
                        metric=(copy.deepcopy(test.recorded[cell]) if row['case_id']==failed_case else test.positive(row['case_id'])[cell])
                        metric['case_id']=row['case_id'];path=directory/'metric.json';path.write_text(json.dumps(metric))
                        proof=directory/'proof.json';proof.write_text('{}')
                        pg.context['result']=dict(metrics=reference(path),proof=reference(proof))
                with patch('runner.check_plan',return_value=plan),patch('runner.check_sources'),patch('runner.check_tree'),\
                     patch('runner.OwnedPostgres',FakePostgres),patch('runner.Trial',FakeTrial),\
                     contextlib.redirect_stdout(io.StringIO()):
                    with self.assertRaisesRegex(ValueError,'mechanism sanity failed: '+failed_case):
                        run('correctness',plan_path,output,root/'not-a-real-PG')
                index=read_json(output/'index.json');status=read_json(output/'mechanism'/(failed_case+'.json'))
                self.assertEqual(len(started),expected_started);self.assertEqual(len(index['rows']),expected_started)
                self.assertNotIn('littlex',started);self.assertTrue(closed)
                if failed_case=='linked_list32':self.assertNotIn('linked_list1000',started)
                self.assertEqual(index['status'],'failed');self.assertEqual(index['mechanism_status'],'failed')
                self.assertFalse(status['passed']);self.assertTrue(all(r['passed'] for r in index['rows']))


class CompactDerived(unittest.TestCase):
    def test_exact_counters_and_raw_reference_without_native_payload_copy(self):
        event=dict(kind='dependency_outcome',origin_request_id='request',server_generation=2,scope_id='distinct-scope',
            checkpoints=[1],hits=[2],summary=dict(model='AlwaysPrefetch',executor='process',errors=['retained-error'],
                submitted_ids=['a','b'],promoted_ids=['a'],unused_cached_ids=['b'],unavailable_ids=[],
                plans=[dict(status='submitted',resolved_nodes=2),dict(status='resolved',resolved_nodes=0)],
                continuations=[dict(paths=[1,2],executions=[1,2,3],stop='end')]*100,
                feedback=[1],fusion=dict(queries=1,payload_dispatches=1,regions=[dict(kind='linear',huge=[0]*100)]*100)))
        raw=dict(path='/sealed/raw.gz',sha256='unchanged',line=7,record_sha256='exact-record')
        result=compact_outcome(event,raw);summary=result['summary']
        self.assertEqual(result['raw_event'],raw);self.assertEqual(result['scope_id'],'distinct-scope')
        self.assertEqual(summary['errors'],['retained-error']);self.assertEqual(summary['submitted_count'],2)
        self.assertEqual((summary['resolved_plan_count'],summary['resolved_targets_cumulative']),(1,2))
        self.assertEqual((summary['continuation_path_count'],summary['continuation_execution_count']),(200,300))
        self.assertEqual(summary['region_count'],100);self.assertEqual(summary['fusion']['queries'],1)
        self.assertNotIn('plans',summary);self.assertNotIn('continuations',summary);self.assertNotIn('regions',summary['fusion'])
        self.assertLess(len(json.dumps(result)),3000)
    def test_streamed_records_keep_exact_line_hashes_and_late_error(self):
        import hashlib
        with tempfile.TemporaryDirectory(dir=OWN) as temp:
            directory=Path(temp);path=directory/'server-1.events.jsonl.gz'
            lines=[json.dumps(dict(kind='first'))+'\n',json.dumps(dict(kind='late',payload_error='native-error'))+'\n']
            with gzip.open(path,'wt') as file:file.writelines(lines)
            (directory/'artifacts.json').write_text(json.dumps(dict(passed=True,files={path.name:sha256(path)})))
            iterator=iter_events(directory);self.assertNotIsInstance(iterator,list)
            rows=list(iterator);self.assertEqual(len(rows),2)
            self.assertEqual(rows[1][1]['line'],2)
            self.assertEqual(rows[1][1]['record_sha256'],hashlib.sha256(lines[1].encode()).hexdigest())
            from interop import payload_errors
            self.assertTrue(payload_errors(rows[1][0]))
            native_iterator=load_unsealed(directory,'server-*.events.jsonl*')
            self.assertNotIsInstance(native_iterator,list)
            self.assertEqual([r['kind'] for r in native_iterator],['first','late'])
    def test_recorded_LL32_all_primary_fields_exactly_equal(self):
        index=read_json(EVIDENCE/'correctness-v4/index.json')
        for row in index['rows']:
            if row['case_id']!='linked_list32':continue
            with self.subTest(cell=row['config_id']):
                old=read_json(checked_ref(row['result']['metrics'],EVIDENCE))
                actual=summarize(Path(row['result']['raw']['path']).parent,Path(row['result']['acceptance']['path']))
                self.assertEqual({k:v for k,v in old.items() if k!='model_outcomes'},
                    {k:v for k,v in actual.items() if k not in ('model_outcomes','model_outcome_format')})
                self.assertEqual(len(old['model_outcomes']),len(actual['model_outcomes']))
                for before,after in zip(old['model_outcomes'],actual['model_outcomes']):
                    self.assertEqual(after['summary']['submitted_count'],len(before['summary']['submitted_ids']))
                    self.assertEqual(after['summary']['resolved_plan_count'],sum(p.get('resolved_nodes',0)>0 for p in before['summary']['plans']))
                    self.assertEqual(after['summary']['fusion'],{k:v for k,v in before['summary']['fusion'].items() if k!='regions'})
                    self.assertEqual(after['scope_id'],before['scope_id']);checked_ref(after['raw_event'],EVIDENCE)


if __name__=='__main__':unittest.main(verbosity=2)
