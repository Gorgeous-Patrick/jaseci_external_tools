"""Focused DB-free changes: fixed scope, policy and zero-prefetch/thread checks."""
import json,sys,tempfile,unittest
from pathlib import Path
from ia_config import APPS,MODES,run_config,schedule,OWN,PREVIOUS
sys.path.insert(0,str(PREVIOUS));sys.path.insert(0,str(OWN))
from precision_observer import validate_case
from gil_audit import verify_gil_case
class Checks(unittest.TestCase):
 def test_fixed_scope(self):
  self.assertEqual(len(set(APPS)),17)
  self.assertEqual(len(schedule('first')),45)
  self.assertEqual(len(schedule('small-rest')),210)
  self.assertEqual(len(schedule('larger')),45)
  self.assertEqual(len(schedule('extend-n5')),120)
  self.assertEqual(len(schedule('precision')),60)
 def test_policy_only_variation(self):
  configs=[run_config(m) for m in MODES]
  for c in configs:self.assertEqual(c['async_prefetch'],'thread');self.assertEqual(c['prefetch_workers'],1)
  common=[{k:v for k,v in c.items() if k not in ('prefetching','ttg_fused_sql')} for c in configs]
  self.assertEqual(common[0],common[1]);self.assertEqual(common[1],common[2])
 def test_zero_prefetch_precision(self):
  with tempfile.TemporaryDirectory() as t:
   d=Path(t);(d/'requests.json').write_text(json.dumps([dict(server_generation=1,request='1:0',phase='workflow')]))
   events=[dict(kind='precision_observer_installed',server_generation='1',origin_request_id=None),dict(kind='native_context_close',server_generation='1',origin_request_id='1:0')]
   (d/'server-1.events.jsonl').write_text(''.join(json.dumps(e)+'\n' for e in events))
   proof=validate_case(d);self.assertEqual(proof['batches'],0);self.assertEqual(proof['payload_row_deliveries'],0)
 def test_unmatched_delivery_rejected(self):
  with tempfile.TemporaryDirectory() as t:
   d=Path(t);(d/'requests.json').write_text(json.dumps([dict(server_generation=1,request='1:0',phase='workflow')]))
   events=[dict(kind='precision_observer_installed',server_generation='1',origin_request_id=None),dict(kind='precision_payload_returned',server_generation='1',origin_request_id='1:0',batch='missing')]
   (d/'server-1.events.jsonl').write_text(''.join(json.dumps(e)+'\n' for e in events))
   with self.assertRaises((KeyError,AssertionError)):validate_case(d)
 def test_all_thread_policy_labels(self):
  for mode in ('aggressive','conservative'):
   with tempfile.TemporaryDirectory() as t:
    d=Path(t);base=dict(pid=42,gil_enabled=False,Py_GIL_DISABLED=1,server_generation='1',origin_request_id='1:0',native_thread_id=900)
    events=[dict(base,kind='python_startup',thread_id=1,role='foreground',actual_executor='none'),
      dict(base,kind='sql_boundary',thread_id=1,role='foreground',actual_executor='none'),
      dict(base,kind='sql_boundary',thread_id=2,role='background_prefetch',actual_executor='thread'),
      dict(base,kind='python_exit',thread_id=1,role='foreground',actual_executor='none')]
    (d/'gil-proof-42.jsonl').write_text(''.join(json.dumps(e)+'\n' for e in events))
    calls=[dict(client_process_pid=42,thread_id=i,server_generation='1',origin_request_id='1:0',send_ns=1,
     role='foreground' if i==1 else 'background_prefetch',actual_executor='none' if i==1 else 'thread',backend_pid=20+i) for i in (1,2)]
    (d/'server-1.calls.jsonl').write_text(''.join(json.dumps(e)+'\n' for e in calls))
    (d/'requests.json').write_text(json.dumps([dict(server_generation=1,request='1:0',phase='workflow')]))
    self.assertTrue(verify_gil_case(d,mode)['passed'])
 def test_transport_boundaries(self):
  from http_post import post
  import inspect
  source=inspect.getsource(post)
  self.assertIn('timeout=300',source)
  self.assertLess(source.index('started = time.perf_counter_ns()'),source.index('urllib.request.urlopen(request'))
  self.assertLess(source.index('ended = time.perf_counter_ns()'),source.index("result = json.loads(raw)"))
  self.assertLess(source.index('ended = time.perf_counter_ns()'),source.index("/drain"))
  self.assertNotIn('jaclang',sys.modules)
if __name__=='__main__':unittest.main()
