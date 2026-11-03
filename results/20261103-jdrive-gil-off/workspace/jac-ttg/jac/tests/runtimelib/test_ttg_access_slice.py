"""Independent tiny IR controls: access slicing must not erase sibling effects."""
import importlib.util
from pathlib import Path
import unittest

PATH = Path(__file__).resolve().parents[2] / 'jaclang/runtime/ttg_access_slice.py'
spec = importlib.util.spec_from_file_location('access_slice_under_test', PATH)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
slice_ = module.access_slice

def event(i, kind, reads=(), writes='', ability='walk'):
    return dict(id=i, kind=kind, reads=reads, writes=writes, ability=ability)
def edge(a, b, kind='data'):
    return dict(source=a, target=b, kind=kind)

class AccessSliceTest(unittest.TestCase):
    def test_output_branch_and_updates_are_not_access_dependencies(self):
        events=[event(0,'branch',['self.first']),event(1,'assign',writes='self.depth'),
                event(2,'scalar_update',['self.depth'],'self.depth'),event(3,'visit')]
        s=slice_(events,[edge(0,1,'control'),edge(1,2)])
        self.assertEqual(s['output_only'],[0,1,2]);self.assertEqual(s['relevant'],[3])

    def test_local_chain_into_visit_is_retained(self):
        events=[event(0,'assign',['self.limit'],'walk::x'),event(1,'assign',['walk::x'],'walk::y'),
                event(2,'branch',['walk::y']),event(3,'visit')]
        s=slice_(events,[edge(0,1),edge(1,2),edge(2,3,'control')])
        self.assertEqual(s['relevant'],[0,1,2,3]);self.assertEqual(s['shared_access_reads'],['self.limit'])

    def test_sibling_writer_and_its_control_are_retained(self):
        events=[event(0,'branch',['self.enabled'],ability='B'),
                event(1,'assign',['self.limit'],'self.count','B'),
                event(2,'branch',['self.count'],ability='C'),event(3,'visit',ability='C')]
        s=slice_(events,[edge(0,1,'control'),edge(2,3,'control')])
        self.assertEqual(s['relevant'],[0,1,2,3])
        self.assertEqual(s['shared_access_reads'],['self.count','self.enabled','self.limit'])

    def test_cancellation_retains_control_even_without_controlled_visit(self):
        events=[event(0,'scalar_update',['self.n'],'self.n'),event(1,'branch',['self.n']),
                event(2,'cancel'),event(3,'visit')]
        self.assertEqual(slice_(events,[edge(1,2,'control')])['relevant'],[0,1,2,3])

    def test_unknown_call_is_not_assumed_output_only(self):
        s=slice_([event(0,'barrier'),event(1,'visit')],[])
        self.assertEqual(s['unresolved_effects'],[0]);self.assertEqual(s['output_only'],[])

    def test_loop_carried_shared_state_is_retained(self):
        events=[event(0,'branch',['self.n']),event(1,'visit'),
                event(2,'scalar_update',['self.n'],'self.n')]
        self.assertEqual(slice_(events,[edge(0,1,'control')])['relevant'],[0,1,2])

    def test_dead_local_write_does_not_hide_live_global_source(self):
        events=[event(0,'assign',['self.x'],'a::unused'),event(1,'visit',['self.target']),
                event(2,'assign',['self.seed'],'self.target','b')]
        s=slice_(events,[]);self.assertEqual(s['relevant'],[1,2]);self.assertEqual(s['output_only'],[0])

    def test_opaque_reader_keeps_shared_writes_without_explicit_reads(self):
        events=[event(0,'assign',writes='self.x',ability='B'),event(1,'barrier',ability='C'),event(2,'visit',ability='C')]
        self.assertEqual(slice_(events,[])['relevant'],[0,1,2])

    def test_dangling_edges_rejected(self):
        with self.assertRaises(ValueError):slice_([event(0,'visit')],[edge(2,0)])

if __name__=='__main__':unittest.main()
