"""Bounded DB-free lineage/precision arithmetic checks; no capture source edits."""
import copy,importlib.util,json,tempfile,unittest
from pathlib import Path
E=Path(__file__).resolve().parent

def load(name,path):
 spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
line=load('nov12_lineage_export',E/'postprocess_lineage_v2.py')
precision=load('nov12_precision_export',E/'precision_postprocess_v1.py')
PLAN=E/'plan-v2/plan.json'
INDEX=[E/p/'index.json' for p in ('first-v1','small-rest-v1','larger-v1','extend-n5-v2')]

def payload(t=2,materialized=False):
 return dict(kind='precision_payload_returned',uid='node-A',anchor_kind='NodeAnchor',timestamp_ns=t,already_materialized=materialized,_ref={'line':1})
def demand(start=3,end=6):
 return dict(kind='precision_access',planning=False,role='foreground',ids=['node-A'],kinds=['NodeAnchor'],started_ns=start,timestamp_ns=end,_ref={'line':2})
def promotion(t=4,planning=False):
 return dict(kind='precision_promotion',uid='node-A',planning=planning,role='foreground',timestamp_ns=t,_ref={'line':3})

class Checks(unittest.TestCase):
 def test_actual_lineage_selection(self):
  parts=line.lineage_indexes(PLAN,INDEX)
  self.assertEqual([len(p[2]) for p in parts],[45,210,30,114])
  rows=[r for p in parts for r in p[2]]
  self.assertEqual(len({r['trial_id'] for r in rows}),399)
  self.assertFalse(any(r['case_id']=='linked_list-1000' for r in rows))
 def test_missing_prefix_rejected(self):
  with self.assertRaises(AssertionError):line.lineage_indexes(PLAN,INDEX[1:])
 def test_extra_prefix_row_rejected(self):
  p=line.read(PLAN);p['lineage']['accepted_prefixes'][2]['end']=31
  with tempfile.TemporaryDirectory(dir=E) as d:
   f=Path(d)/'plan.json';f.write_text(json.dumps(p))
   with self.assertRaises(AssertionError):line.lineage_indexes(f,INDEX)
 def test_incomplete_extension_rejected(self):
  p=line.read(INDEX[-1]);p['rows'].pop()
  with tempfile.TemporaryDirectory(dir=E) as d:
   f=Path(d)/'index.json';f.write_text(json.dumps(p))
   with self.assertRaises(AssertionError):line.lineage_indexes(PLAN,INDEX[:-1]+[f])
 def test_valid_zero_prefetch(self):
  r=precision.classify_group([demand()]);self.assertEqual(r['returned_unique'],0)
  self.assertEqual(r['overlap_coverage'],0);self.assertIsNone(r['returned_demand_fraction'])
  self.assertIsNone(precision.classify_group([])['overlap_coverage'])
 def test_late_overlap_is_not_service(self):
  r=precision.classify_group([demand(1,5),payload(10,True)])
  self.assertEqual(r['returned_demand_intersection'],1);self.assertEqual(r['raw_promotion_served_unique'],0)
  self.assertEqual(r['post_return_successful_demand_overlap'],0)
  self.assertEqual(r['already_materialized_late_deliveries'],1)
 def test_timely_actual_promotion(self):
  r=precision.classify_group([payload(),demand(),promotion()])
  self.assertEqual(r['raw_promotion_served_unique'],1);self.assertEqual(r['served_return_before_demand_call_unique'],1)
 def test_delivery_during_call_separate(self):
  r=precision.classify_group([payload(4),demand(),promotion(5)])
  self.assertEqual(r['raw_promotion_served_unique'],1);self.assertEqual(r['served_return_before_demand_call_unique'],0)
 def test_planning_promotion_not_service(self):
  r=precision.classify_group([payload(),demand(),promotion(planning=True)])
  self.assertEqual(r['raw_promotion_served_unique'],0)
 def test_duplicate_rows_and_unused_node(self):
  r=precision.classify_group([payload(),payload(4)])
  self.assertEqual(r['actual_row_deliveries'],2);self.assertEqual(r['repeated_row_deliveries'],1)
  self.assertEqual(r['unused_returned_unique'],1);self.assertEqual(r['confirmed_unused_node_prefetch_lower_bound'],1)
 def test_unknown_kind_not_guessed_node(self):
  p=payload();p['anchor_kind']='unrecognized'
  r=precision.classify_group([p]);self.assertEqual(r['unused_returned_unique'],1)
  self.assertEqual(r['confirmed_unused_node_prefetch_lower_bound'],0)

if __name__=='__main__':unittest.main(verbosity=2)
