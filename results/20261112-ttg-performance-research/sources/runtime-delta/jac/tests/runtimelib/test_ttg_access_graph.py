"""DB-free contracts using parsed Jac source, not fabricated graph objects."""
import unittest

from jaclang.runtime.ttg_access_graph import analyze_source


PRELUDE = 'node B { has active: bool = True; } edge E {} '


def graph(body):
    return analyze_source(PRELUDE + 'walker W { has enabled: bool = True; '
                          'can run with Root entry { ' + body + ' } }')


def nodes(g, kind):
    return [n for n in g['nodes'] if n['kind'] == kind]


class AccessVisitTests(unittest.TestCase):
    def test_jobj_access_id_dependency_and_query_origin(self):
        g=graph('key = "abcd"; found = jobj(id=key); report [found->:E:->[?:B]];')
        a=nodes(g,'Access')
        self.assertEqual([n['access_kind'] for n in a],['lookup_by_id','graph_query'])
        binding=next(n for n in nodes(g,'Assign') if n['name']=='found')
        self.assertTrue(any(e['source']==a[0]['id'] and e['target']==binding['id'] for e in g['edges']))
        self.assertTrue(any(e['source']==binding['id'] and e['target']==a[1]['id'] and e['label']=='origin' for e in g['edges']))
        self.assertEqual(nodes(g,'Visit'),[])

    def test_jobj_visit_and_false_control_are_separate(self):
        g=graph('if self.enabled { visit jobj("abcd"); }')
        a,v=nodes(g,'Access')[0],nodes(g,'Visit')[0]
        self.assertEqual(a['local_visit_targets'],[v['id']])
        self.assertTrue(any(e['target']==a['id'] and e['kind']=='control' for e in g['edges']))

    def test_user_jobj_stays_a_call(self):
        g=analyze_source('def jobj(id: str) { return None; } walker W { can run with Root entry { report jobj("abcd"); } }')
        self.assertEqual(nodes(g,'Access'),[])
        self.assertEqual(len(nodes(g,'Call')),1)

    def test_read_without_visit(self):
        g = graph('xs = [here->:E:->[?:B]]; report xs;')
        self.assertEqual(len(nodes(g, 'Access')), 1)
        self.assertEqual(nodes(g, 'Visit'), [])
        self.assertEqual(nodes(g, 'Access')[0]['local_visit_targets'], [])

    def test_inline_query_is_two_nodes(self):
        g = graph('visit [here->:E:->[?:B]];')
        a, v = nodes(g, 'Access')[0], nodes(g, 'Visit')[0]
        self.assertEqual(a['local_visit_targets'], [v['id']])
        self.assertTrue(any(e['source'] == a['id'] and e['target'] == v['id']
                            and e['kind'] == 'value' for e in g['edges']))

    def test_alias_and_duplicate_visits(self):
        g = graph('xs = [here->:E:->[?:B]]; ys = xs; visit ys; visit xs;')
        self.assertEqual(len(nodes(g, 'Access')), 1)
        self.assertEqual(len(nodes(g, 'Visit')), 2)
        self.assertEqual(nodes(g, 'Access')[0]['local_visit_targets'],
                         [v['id'] for v in nodes(g, 'Visit')])

    def test_branch_controls_visit_only(self):
        g = graph('xs = [here->:E:->[?:B]]; if self.enabled { visit xs; }')
        a, v, b = nodes(g, 'Access')[0], nodes(g, 'Visit')[0], nodes(g, 'Branch')[0]
        targets = {e['target'] for e in g['edges'] if e['kind'] == 'control'
                   and e['source'] == b['id']}
        self.assertIn(v['id'], targets)
        self.assertNotIn(a['id'], targets)

    def test_branch_controls_inline_access_too(self):
        g = graph('if self.enabled { visit [here->:E:->[?:B]]; }')
        b = nodes(g, 'Branch')[0]
        targets = {e['target'] for e in g['edges'] if e['kind'] == 'control'
                   and e['source'] == b['id']}
        self.assertIn(nodes(g, 'Access')[0]['id'], targets)
        self.assertIn(nodes(g, 'Visit')[0]['id'], targets)

    def test_access_condition_is_not_visit_target(self):
        g = graph('xs = [here->:E:->[?:B]]; if xs { visit [here->:E:->[?:B]]; }')
        a, other = nodes(g, 'Access')
        self.assertEqual(a['local_visit_targets'], [])
        self.assertEqual(len(other['local_visit_targets']), 1)
        self.assertTrue(any(e['source'] == nodes(g, 'Assign')[0]['id']
                            and e['kind'] == 'data' for e in g['edges']))

    def test_reassignment_kills_old_target(self):
        g = graph('xs = [here->:E:->[?:B]]; xs = [root->:E:->[?:B]]; visit xs;')
        first, second = nodes(g, 'Access')
        self.assertEqual(first['local_visit_targets'], [])
        self.assertEqual(len(second['local_visit_targets']), 1)

    def test_branch_merge_preserves_both_possible_sources(self):
        g = graph('xs = [here->:E:->[?:B]]; if self.enabled { xs = [root->:E:->[?:B]]; } visit xs;')
        self.assertEqual(len(nodes(g, 'Phi')), 1)
        self.assertTrue(all(len(a['local_visit_targets']) == 1 for a in nodes(g, 'Access')))

    def test_unknown_call_never_proves_absence(self):
        g = graph('xs = [here->:E:->[?:B]]; opaque(xs);')
        self.assertEqual(len(nodes(g, 'Call')), 1)
        self.assertTrue(next(iter(g['functions'].values()))['unknowns'])
        self.assertFalse(nodes(g, 'Access')[0]['global_nonvisit_proven'])

    def test_predicate_parameter_is_input_not_field_variable(self):
        g = graph('xs = [here->:E:->[?:B, active == self.enabled]]; visit xs;')
        a = nodes(g, 'Access')[0]
        inputs = [e for e in g['edges'] if e['target'] == a['id'] and e['label'] == 'predicate input']
        self.assertEqual(len(inputs), 1)
        self.assertEqual(g['nodes'][inputs[0]['source']]['operation'], 'attribute read; not Access v1')
        self.assertNotIn('active', [n.get('name') for n in nodes(g, 'Input')])

    def test_comprehension_is_access_not_visit(self):
        g = graph('report [b.active for b in [here->:E:->[?:B]]];')
        self.assertEqual(len(nodes(g, 'Access')), 1)
        self.assertEqual(nodes(g, 'Visit'), [])
        self.assertEqual(len(nodes(g, 'Iteration')), 1)

    def test_plain_method_body_is_included(self):
        g = analyze_source('node B { def view { report [self-->]; } }')
        self.assertEqual(len(nodes(g, 'Access')), 1)
        self.assertEqual(nodes(g, 'Visit'), [])
        self.assertEqual(next(iter(g['functions'].values()))['kind'], 'method')

    def test_separate_impl_body_is_included_and_bound(self):
        g = analyze_source('node B {} walker W { can run with Root entry; }',
                           'split.jac', [('impl W.run { visit [-->[?:B]]; }', 'split.impl.jac')])
        self.assertEqual(len(nodes(g, 'Access')), 1)
        self.assertEqual(len(nodes(g, 'Visit')), 1)
        self.assertEqual(nodes(g, 'Access')[0]['file'], 'split.impl.jac')
        self.assertEqual(g['unmatched_implementations'], [])
        self.assertEqual(len(g['annexes']), 1)

    def test_loop_access_and_visit_are_visible_but_not_certified(self):
        g = graph('for b in [here->:E:->[?:B]] { visit [b->:E:->[?:B]]; }')
        self.assertEqual(len(nodes(g, 'Access')), 2)
        self.assertEqual(len(nodes(g, 'Visit')), 1)
        self.assertEqual(nodes(g, 'Access')[0]['local_visit_targets'], [])
        self.assertTrue(next(iter(g['functions'].values()))['unknowns'])

    def test_returned_query_does_not_prove_global_nonvisit(self):
        g = analyze_source('node B { def items { return [self-->]; } }')
        self.assertEqual(nodes(g, 'Access')[0]['local_visit_targets'], [])
        self.assertFalse(nodes(g, 'Access')[0]['global_nonvisit_proven'])


if __name__ == '__main__':
    unittest.main()
