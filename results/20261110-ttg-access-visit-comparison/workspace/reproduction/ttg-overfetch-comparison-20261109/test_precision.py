"""Tiny observer contract checks; fake methods preserve original return values."""
import types
import unittest
from unittest.mock import patch
import precision_observer as p


class Contracts(unittest.TestCase):
    def setUp(self):
        self.events=[]
        self.mock=patch.object(p, 'probe', types.SimpleNamespace(
            binding=lambda: ('r','foreground','none'),
            event=lambda kind,**fields:self.events.append(dict(kind=kind,**fields))))
        self.mock.start()
        self.addCleanup(self.mock.stop)

    def test_nested_get_only_one_demand(self):
        anchor=types.SimpleNamespace(id='x')
        batch=p.wrap_demand(lambda mem,ids:{'x':anchor},batch=True)
        get=p.wrap_demand(lambda mem,uid:batch(mem,[uid])['x'])
        self.assertIs(get(object(),'x'),anchor)
        self.assertEqual(len(self.events),1)
        self.assertFalse(self.events[0]['planning'])

    def test_planning_is_not_demand(self):
        get=p.wrap_demand(lambda mem,uid:types.SimpleNamespace(id=uid))
        p.wrap_planning(get)(object(),'x')
        self.assertTrue(self.events[0]['planning'])
        self.assertEqual(p.PLANNING.get(),0)

    def test_late_materialized_payload_is_retained(self):
        mem=types.SimpleNamespace(__mem__={'x':object()})
        row=types.SimpleNamespace(kind='NodeAnchor',arch_type='X',props={'value':2})
        called=[]
        store=p.wrap_store_raw(lambda mem,uid,row:called.append(uid))
        load=p.wrap_prefetch(lambda mem,ids:store(mem,ids[0],row))
        load(mem,['x'])
        self.assertEqual(called,['x'])
        self.assertTrue(self.events[1]['already_materialized'])
        self.assertEqual(self.events[1]['props_bytes'],11)
        self.assertEqual([e['kind'] for e in self.events],
            ['precision_prefetch_batch','precision_payload_returned','precision_prefetch_batch_end'])
        self.assertIsNone(p.LOADING.get())

    def test_failed_get_is_not_successful_access(self):
        get=p.wrap_demand(lambda mem,uid:None)
        self.assertIsNone(get(object(),'x'))
        self.assertEqual(self.events,[])

    def test_planning_exception_restores_context(self):
        def fail():raise ValueError('expected')
        with self.assertRaises(ValueError):p.wrap_planning(fail)()
        self.assertEqual(p.PLANNING.get(),0)

if __name__=='__main__':unittest.main()
