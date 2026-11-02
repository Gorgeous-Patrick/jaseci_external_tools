"""Bounded pure fixture/schedule/statistics tests; no Jac/runtime/compiler/DB import."""
import copy,json,tempfile,unittest,time,threading
from types import SimpleNamespace
from pathlib import Path
from ia_config import schedule,guard_schedule,OWN
from ia_fixtures import fixture,prove_chain
class Preparation(unittest.TestCase):
 def test_schedule(self):
  self.assertEqual(len(schedule()),12);self.assertEqual(len(schedule(True)),48)
  self.assertEqual(sum(r['phase']=='measured' for r in schedule(True)),36)
  self.assertEqual(len({r['trial_id'] for r in schedule(True)}),48)
  self.assertEqual(len(guard_schedule()),3)
 def test_finite_shapes_and_oracles(self):
  for row in [r for r in schedule() if r['config_id']=='off' and r['app']=='linked_list']:
   f=fixture(row);self.assertEqual(f['reports'],list(range(row['length'])));self.assertTrue(f['shape_proof']['acyclic'])
 def test_shape_rejects_cycle_or_fanout(self):
  row=schedule()[0];f=fixture(row);g=f['graph'];g.edge('item:31','Next','item:0')
  with self.assertRaises(AssertionError):prove_chain(g,32)
 def test_bool_alternative(self):
  true=fixture(next(r for r in schedule() if r['app']=='region_chain'));false=fixture(guard_schedule()[0])
  self.assertEqual(true['reports'],[10,20,30]);self.assertEqual(false['reports'],[10,20])
  self.assertEqual(true['graph'].edges,false['graph'].edges)
  t=copy.deepcopy(true['graph'].nodes);f=copy.deepcopy(false['graph'].nodes)
  self.assertTrue(t['item:1']['fields'].pop('active'));self.assertFalse(f['item:1']['fields'].pop('active'));self.assertEqual(t,f)
 def test_two_changes_only(self):
  meta=json.loads((OWN/'apps/linked_list/source-overlay.json').read_text())
  before=Path(meta['original']['path']).read_text();after=Path(meta['finite_copy']['path']).read_text()
  before=before.replace('        if self.visited >= 10000 {\n            disengage;\n        }\n','')
  a=before.index('walker Traverse');b=before.index('walker Sum')
  before=before[:a]+before[a:b].replace('visit [->:Next:->];','visit [->:Next:->[?:Item]];')+before[b:]
  self.assertEqual(before,after)

 def test_observer_reason_counts_only(self):
  from compact_observer import project_state
  mem=SimpleNamespace(_raw_lock=threading.RLock(),__raw_mem__={1:object()})
  state=SimpleNamespace(ctx=SimpleNamespace(mem=mem),submitted={1},promoted={1},plans=[],continuations=[],errors=[],feedback=[],
    fusion={'region_queries':1,'region_fallback_reasons':{'fanout':2},'regions':[{'kind':'static_interability','paths':object()}]},model=object(),provider=object(),mode='process')
  out=project_state(state);self.assertEqual(out['fusion']['region_fallback_reasons'],{'fanout':2})
  self.assertNotIn('regions',out['fusion']);self.assertIn('regions',out['omitted_fusion_fields'])
 def test_tiny_negative_total_is_retained(self):
  from ia_sanity import from_metrics
  def metric(mode,total):
   return dict(passed=True,request_metrics=[dict(phase='workflow',path='/walker/RegionChain/target',request='1:1',sql_dispatches=total)],
     model_outcomes=[dict(origin_request_id='1:1',summary=dict(fusion=dict(region_queries=1,region_cache_paths=2,region_reuses=1)))])
  group={m:metric(m,20 if m=='interability' else 12) for m in ['off','baseline9282','interability']}
  self.assertTrue(from_metrics(dict(app='region_chain'),group)['passed'])
  group['interability']['model_outcomes'][0]['summary']['fusion']['region_queries']=0
  self.assertFalse(from_metrics(dict(app='region_chain'),group)['passed'])
 def test_actual_post_stats_boundary_all_modes(self):
  from ia_trial import Trial
  from ia_config import MODES
  global SETUP_WALKERS
  SETUP_WALKERS={'SuiteRoot','SuiteInspect','SuiteImport'}
  for mode in MODES:
   with tempfile.TemporaryDirectory() as scratch:
    root=Path(scratch);directory=root/'case';directory.mkdir();overlay=root/'overlay.json';overlay.write_text(json.dumps({'root':str(root/'runtime')}))
    events=[]
    class Base:
     def __init__(self):self.phase='setup';self.reset_next=True;self.url='postgresql://owned/db';self.requests=[]
     def post(self,path,body,token=None):
      name=path.split('/')[2] if path.startswith('/walker/') else None
      effective='setup' if name in SETUP_WALKERS or not name else self.phase
      if effective=='workflow':
       events.append('HTTP/profile_reset' if self.reset_next else 'HTTP');self.reset_next=False
       self.requests.append(dict(phase='workflow',start_ns=time.perf_counter_ns()))
      return {}
    class PG:
     owner='owner';databases={'db'}
     def sql(self,sql,db):
      self.assert_db=db;events.append(sql)
      if sql.startswith('ANALYZE'):return ''
      return json.dumps(dict(relations=[dict(relname='anchors',reltuples=3),dict(relname='graph_types',reltuples=5)],statistics_rows=8))
    pg=PG();w=SimpleNamespace(Server=Base,config=lambda *a:None)
    def fake_trial(*a,**kw):
     server=w.Server();server.post('/walker/SuiteRoot',{});server.phase='workflow';server.post('/walker/SuiteInspect',{})
     self.assertEqual(events,[])
     server.post('/walker/load_feed',{});server.post('/walker/load_feed',{})
     proof=json.loads((directory/'planner-statistics-before-workflow.json').read_text())
     self.assertLessEqual(proof['admin_end_ns'],server.requests[0]['start_ns']);self.assertTrue(proof['primary_excluded'])
     self.assertEqual(events[:2],['ANALYZE anchors','ANALYZE graph_types']);self.assertEqual(events[3:],['HTTP/profile_reset','HTTP'])
    w.trial=fake_trial;n=SimpleNamespace(corpus=SimpleNamespace(revision=lambda p:None),SOURCES={'littlex':None})
    trial=Trial.__new__(Trial);trial.w=w;trial.native=n;trial.original_server=Base;trial.apps=SimpleNamespace(evaluate=None,readers=None)
    case=dict(app='littlex',scale='smoke',case_id='littlex',phase='correctness')
    trial.run(case,mode,directory,pg,overlay,overlay)

if __name__=='__main__':unittest.main()
