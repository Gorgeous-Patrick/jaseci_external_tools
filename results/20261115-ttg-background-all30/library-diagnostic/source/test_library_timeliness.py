"""Tiny DB/Jac-free checks of observation and exact identity, not benchmarks."""
import contextvars
from concurrent.futures import Future
import json
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
from uuid import UUID

import library_timeliness as trace


class Session:
    def __init__(self):self._query_cache={};self.store=object();self.__raw_mem__={}
    def query_cache_get(self,key):return self._query_cache.get(key)
    def query_cache_put(self,key,value):self._query_cache[key]=value
    def invalidate_query_cache(self):self._query_cache={}
    def get(self,uid):return self.batch_get([uid]).get(uid)
    def batch_get(self,ids):return {u:self.promote_raw(u)for u in ids}
    def store_raw(self,uid,row):self.__raw_mem__[uid]=row
    def promote_raw(self,uid):return self.__raw_mem__.pop(uid,None)


class Run:
    def __init__(self,mem):self.mem=mem;self.closed=False;self.snapshot='token';self.pending={}
    def enqueue(self):pass
    def drain(self):
        for future,record in self.pending.items():
            result=future.result()
            for key,value in result['puts']:self.mem.query_cache_put(key,value)


class Store:
    def load_full(self,ids):return {u:u for u in ids}
    def _run(self,sql,params=None):return [('unchanged',)]


class Checks(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.sink=SimpleNamespace(binding=lambda:('2:5','foreground','native'),drain_after_response=lambda *a,**k:{'unchanged':True})
        self.bg=SimpleNamespace(BackgroundSQLRun=Run)
        self.obs=trace.Observer(self.temp.name,self.sink,dict(background=self.bg))
        self.mem=Session()
    def tearDown(self):self.temp.cleanup()
    def key(self,origin='a',predicate=True):return ('pairs',1,'SELECT actual',(('origin',(origin,)),('filter',predicate)))
    def test_full_identity(self):
        keys=[self.key(),self.key('b'),self.key(predicate=False),('pairs',2,'SELECT actual',())]
        self.assertEqual(len({self.obs.key(k)for k in keys}),4)
        self.assertNotEqual(self.obs.key((True,)),self.obs.key((1,)))
        self.assertNotEqual(self.obs.key((UUID(int=1),)),self.obs.key((str(UUID(int=1)),)))
    def test_no_user_repr_or_getters(self):
        class Unsafe:
            def __repr__(self):raise AssertionError('repr executed')
            def __str__(self):raise AssertionError('str executed')
        with self.assertRaises(TypeError):self.obs.key((Unsafe(),))
    def test_empty_path_hit(self):
        key=self.key();value=((),());self.mem.query_cache_put(key,value)
        result=self.obs.cache_get(Session.query_cache_get)(self.mem,key)
        self.assertIs(result,value);self.assertTrue(self.obs.events[-1]['hit']);self.assertTrue(self.obs.events[-1]['empty_path'])
    def test_nested_attempts_one_logical_access(self):
        calls=[]
        get=self.obs.cache_get(Session.query_cache_get)
        def native(mem):
            calls.append('native');get(mem,('emitted',));get(mem,self.key());return ('native result',[])
        result=self.obs.logical(native)(self.mem)
        self.assertEqual(calls,['native']);self.assertEqual(result,('native result',[]))
        self.assertEqual(sum(x['kind']=='access_begin'for x in self.obs.events),1)
        self.assertEqual(sum(x['kind']=='cache_lookup'for x in self.obs.events),2)
    def test_native_write_source(self):
        put=self.obs.cache_put(Session.query_cache_put)
        def native(mem):put(mem,self.key(),((),()));return 7
        self.assertEqual(self.obs.logical(native)(self.mem),7)
        self.assertEqual(next(x for x in self.obs.events if x['kind']=='cache_write')['source']['kind'],'native_access')
    def test_epoch_retained_not_reused(self):
        first=self.obs.context(self.mem);self.obs.invalidate(Session.invalidate_query_cache)(self.mem)
        second=self.obs.context(self.mem);self.assertNotEqual(first['epoch'],second['epoch'])
        self.assertIsInstance(self.obs.retained[1],dict)
    def test_future_readiness_no_wait(self):
        future=Future();run=Run(self.mem);ctx=self.obs.context(self.mem)
        self.obs.jobs['j']=dict(**ctx,run=run,snapshot='token',cancel=threading.Event(),future=future)
        self.assertFalse(self.obs.future_states(self.mem)[0]['done'])
        future.set_result({});self.assertTrue(self.obs.future_states(self.mem)[0]['done'])
        self.assertEqual(trace.readiness(False,True),'readiness_boundary_or_unknown')
        self.assertEqual(trace.readiness(False,False),'future_pending_through_lookup')
        self.assertEqual(trace.readiness(True,True),'future_ready_before_lookup')
    def test_cancelled_job_has_unknown_key_coverage(self):
        f=self.obs.worker(lambda job:{'cancelled':True})
        self.assertEqual(f({'job_id':'j'}),{'cancelled':True})
        r=self.obs.events[-1];self.assertFalse(r['coverage_materialized']);self.assertEqual(r['key_ids'],[])
    def test_worker_return_actual_keys_only(self):
        value={'puts':[(self.key(),((),()))],'loaded':{UUID(int=2):'row'}}
        result=self.obs.worker(lambda job:value)({'job_id':'j'})
        self.assertIs(result,value);r=self.obs.events[-1]
        self.assertEqual(r['key_ids'],[self.obs.key(self.key())]);self.assertTrue(r['coverage_materialized'])
    def test_actual_publication_frame(self):
        run=Run(self.mem);ctx=self.obs.context(self.mem);future=Future();future.set_result({'puts':[(self.key(),((),()))]})
        self.obs.jobs['j']=dict(**ctx,run=run,cancel=threading.Event(),snapshot='token',future=future)
        run.pending[future]={'job_id':'j'}
        old=Session.query_cache_put;Session.query_cache_put=self.obs.cache_put(old)
        try:run.drain()
        finally:Session.query_cache_put=old
        row=next(r for r in self.obs.events if r['kind']=='cache_write')
        self.assertEqual(row['source'],{'kind':'background','job_id':'j'})
    def test_payload_service_separate(self):
        uid=UUID(int=4);row={'plain':'row'}
        self.obs.store_raw(Session.store_raw)(self.mem,uid,row)
        self.assertIs(self.obs.promote(Session.promote_raw)(self.mem,uid),row)
        event=self.obs.events[-1];self.assertEqual(event['kind'],'payload_promotion');self.assertTrue(event['served'])
    def test_sql_wrapper_calls_once_unchanged(self):
        store=Store();result=self.obs.run_sql(Store._run)(store,'SELECT original',{'x':1})
        self.assertEqual(result,[('unchanged',)])
        self.assertEqual([x['kind']for x in self.obs.events],['sql_begin','sql_end'])
    def test_buffer_flush_and_receipt_only_validation(self):
        self.obs.emit('trace_header',format='library-exact-key-v1');self.obs.flush()
        result=trace.validate_trace([self.obs.path]);self.assertTrue(result['passed']);self.assertEqual(result['logical_accesses'],0)
    def test_overflow_is_explicit_invalid_trace(self):
        self.obs.limit=1;self.obs.emit('trace_header');self.obs.emit('extra');self.obs.flush()
        self.assertFalse(trace.validate_trace([self.obs.path])['passed'])
    def test_detached_jac_globals_alias_is_rebound(self):
        namespace={};exec('def seam(mem): return 7\ndef consumer(mem): return seam(mem)',namespace)
        module=SimpleNamespace(seam=namespace['seam'],consumer=namespace['consumer'])
        self.obs.modules['planner']=module
        self.obs.wrap(module,'seam',lambda old:lambda mem:old(mem)+1)
        self.assertEqual(module.consumer(self.mem),8)
    def test_activity_gate_rejects_receipt_without_actual_seam(self):
        self.obs.emit('trace_header');self.obs.flush()
        self.assertFalse(trace.validate_trace([self.obs.path],require_activity=True)['passed'])
    def test_actual_emitted_class_bearing_native_shape(self):
        class HasPatron:pass
        class Patron:pass
        class HasLoan:pass
        class Loan:pass
        origin=UUID(int=13);actor=str(UUID(int=14))
        # Exact cache_key/native_shape structure from ttg_templates: UUID
        # origins + edge/node classes + direction + optional bool predicates.
        shape=((HasPatron,Patron,'out'),(HasLoan,Loan,'out',(('active','==',True),)))
        native=('ttg_compiled_pairs_v1',(origin,),shape,actor)
        worker=('ttg_compiled_pairs_v1',tuple([origin]),tuple(shape),actor)
        self.assertEqual(self.obs.key(native),self.obs.key(worker))
        self.assertEqual(len(self.obs.class_refs),4)
        changed=('ttg_compiled_pairs_v1',(origin,),((HasPatron,Patron,'out'),(HasLoan,Loan,'out',(('active','==',False),))),actor)
        self.assertNotEqual(self.obs.key(native),self.obs.key(changed))
    def test_same_class_display_does_not_collapse_identity(self):
        first=type('Same',(),{'__module__':'same.module'})
        second=type('Same',(),{'__module__':'same.module'})
        self.assertNotEqual(self.obs.key((first,)),self.obs.key((second,)))
        self.assertIs(self.obs.class_refs[id(first)][0],first)
        self.assertIs(self.obs.class_refs[id(second)][0],second)
    def test_class_metadata_bypasses_metaclass_user_code(self):
        class Hostile(type):
            def __getattribute__(cls,name):raise AssertionError('metaclass getter executed')
            @property
            def __dict__(cls):raise AssertionError('metaclass descriptor executed')
        class Value(metaclass=Hostile):pass
        self.assertEqual(self.obs.key((Value,)),self.obs.key((Value,)))


if __name__=='__main__':unittest.main()
