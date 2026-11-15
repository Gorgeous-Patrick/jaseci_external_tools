"""Executable Access demand contracts, using real Jac ASTs without a DB."""
import unittest
from types import SimpleNamespace
from uuid import UUID

from jaclang.compiler.frontend.parser.frontend import parse
from jaclang.compiler.frontend import unitree as u
from jaclang.runtime.ttg_access_plan import compile_access_plan, scalar_value, lookup_identity, Unresolved


def plan(source, walker='W'):
    module, failed = parse(source, 'access_plan_case.jac')
    assert not failed
    arch = next(a for a in module.body if isinstance(a, u.Archetype) and a.name.value == walker)
    return compile_access_plan(arch)


BASE = 'node A {} node B { has active: bool = True; } edge E {} '


class AccessPlanTests(unittest.TestCase):
    def test_conditional_and_value_calls_extract_identical_access(self):
        helper = 'def has_items(a: A) -> bool { return len([a->:E:->[?:B]]) > 0; } '
        value = plan(BASE + helper + 'walker W { can run with A entry { result = has_items(here); report result; } }')
        cond = plan(BASE + helper + 'walker W { can run with A entry { if has_items(here) { report True; } } }')
        a,b = [p['abilities']['run']['demands'] for p in (value,cond)]
        self.assertEqual(len(a),1)
        self.assertEqual(a[0]['path'],b[0]['path'])
        self.assertEqual(a[0]['calls'],b[0]['calls'])
        self.assertTrue(cond['abilities']['run']['rejections'])  # return remains unknown

    def test_owns_retains_type_short_circuit_and_waits_at_callsite(self):
        helper = 'def owns(item: object, kind: type) -> bool { return isinstance(item, kind) and jid(item) in [jid(n) for n in [root-->]]; } '
        for invoke in ['if not owns(found, A) { return; }', 'ok = owns(found, A); report ok;']:
            a = plan(BASE + helper + 'walker W { has target_id: str; can run with A entry { found = jobj(self.target_id); '+invoke+' } }')['abilities']['run']
            self.assertEqual(len(a['demands']),2)
            guard = a['demands'][1]['guards'][0]
            self.assertEqual(guard[0][0],'node_isinstance')
            self.assertEqual(guard[0][2],'A')
            self.assertTrue(guard[1])
            self.assertEqual(len(a['resumed_regions']),1)
            g = a['resumed_regions'][0]['demands'][0]['guards'][0][0]
            self.assertEqual(g[1]['origin'],'local')
            self.assertEqual(g[1]['local_name'],'found')

    def test_boolean_short_circuit_guards_apply_in_every_context(self):
        helper='def reads(a: A) -> bool { return len([a-->]) > 0; } '
        for expr,wanted in [('self.enabled and reads(here)',True),('self.enabled or reads(here)',False)]:
            for statement in ['result = '+expr+';', 'if '+expr+' { report True; }']:
                a=plan(BASE+helper+'walker W { has enabled: bool = False; can run with A entry { '+statement+' } }')['abilities']['run']
                self.assertEqual(a['demands'][0]['guards'],[[['field','self','enabled'],wanted]])

    def test_unknown_short_circuit_does_not_hoist_right_access(self):
        helper='def reads(a: A) -> bool { return len([a-->]) > 0; } '
        for expr in ['opaque() and reads(here)','opaque() or reads(here)']:
            a=plan(BASE+helper+'walker W { can run with A entry { if '+expr+' { report True; } } }')['abilities']['run']
            self.assertEqual(a['demands'],[])
            self.assertTrue(a['rejections'])

    def test_shadowed_isinstance_never_becomes_builtin_type_guard(self):
        helper='def isinstance(x: object, k: type) -> bool { return True; } def owns(a: A) -> bool { return isinstance(a, A) and len([a-->]) > 0; } '
        a=plan(BASE+helper+'walker W { can run with A entry { if owns(here) { report True; } } }')['abilities']['run']
        self.assertEqual(a['demands'],[])

    def test_type_predicate_short_circuit_uses_callback_only_when_reached(self):
        pred=['node_isinstance',{'origin':'here','hops':[]},'A'];calls=[]
        def check(binding,name):calls.append(name);return True
        for condition in [['and',['constant',False],pred],['or',['constant',True],pred]]:
            scalar_value(condition,{},{},None,None,node_predicate=check)
        self.assertEqual(calls,[])
        self.assertTrue(scalar_value(pred,{},{},None,None,node_predicate=check))
        self.assertEqual(calls,['A'])
        with self.assertRaises(Unresolved):scalar_value(pred,{},{},None,None)

    def test_receiver_guard_does_not_read_walkers_same_named_field(self):
        a=plan('node A { has active: bool = False; def reads -> bool { return self.active and len([self-->]) > 0; } } walker W { has active: bool = True; can run with A entry { if here.reads() { report True; } } }')['abilities']['run']
        self.assertEqual(a['demands'],[])
        self.assertTrue(a['rejections'])

    def test_unknown_guard_keeps_branch_access_in_live_region(self):
        p = plan(BASE + 'walker W { has target_id: str; can run with A entry { x = jobj(self.target_id); if allowed(x) { report [x->:E:->[?:B]]; } } }')
        a = p['abilities']['run']
        self.assertEqual([d['access_kind'] for d in a['demands']], ['lookup_by_id'])
        self.assertEqual(len(a['resumed_regions']), 1)
        r = a['resumed_regions'][0]
        self.assertEqual(r['demands'][0]['guards'], [])
        self.assertEqual(r['demands'][0]['path']['origin'], 'local')
        self.assertEqual(r['demands'][0]['path']['local_name'], 'x')

    def test_early_return_checks_resume_before_helper_not_before_condition(self):
        src = BASE + '''def items(a: A) { return [a->:E:->[?:B]]; }
walker W { has target_id: str; can run with A entry {
 x = jobj(self.target_id);
 if not owns(x) { return; }
 if not x.active { return; }
 report items(x);
} }'''
        r = plan(src)['abilities']['run']['resumed_regions']
        self.assertEqual(len(r), 1)
        self.assertEqual(r[0]['line'], 6)
        self.assertEqual(r[0]['demands'][0]['calls'], ['items'])
        self.assertEqual(r[0]['demands'][0]['path']['local_name'], 'x')

    def test_opaque_call_rebinds_live_alias_and_scalar_after_call(self):
        a = plan(BASE + 'walker W { has target_id: str; can run with A entry { x = jobj(self.target_id); x = change(x); key = compute_id(); report [x->:E:->[?:B]]; report jobj(key); } }')['abilities']['run']
        r = a['resumed_regions']
        self.assertEqual(len(r), 1)
        self.assertEqual(r[0]['demands'][0]['path']['local_name'], 'x')
        self.assertEqual(r[0]['demands'][1]['path']['lookup_id'], ['local', 'key'])
        self.assertEqual(scalar_value(['local', 'key'], {}, {}, None, None, {'key':'abc'}), 'abc')
        with self.assertRaises(Unresolved):
            scalar_value(['local', 'key'], {}, {}, None, None, {})

    def test_unknown_true_else_and_join_are_distinct_regions(self):
        a = plan(BASE + 'walker W { can run with A entry { if unknown() { report [here->:E:->[?:B]]; } else { report [root-->]; } report [here-->]; } }')['abilities']['run']
        self.assertEqual(len(a['resumed_regions']), 3)
        self.assertEqual(len({(r['line'],r['column']) for r in a['resumed_regions']}), 3)

    def test_return_never_creates_unreachable_suffix_region(self):
        a = plan(BASE + 'walker W { can run with A entry { return; report [here-->]; } }')['abilities']['run']
        self.assertEqual(a['resumed_regions'], [])

    def test_jobj_is_lookup_access_and_result_is_query_origin(self):
        p = plan(BASE + 'walker W { has target_id: str; can run with A entry { x = jobj(self.target_id); report [x->:E:->[?:B]]; } }')
        ds = p['abilities']['run']['demands']
        self.assertEqual([d['access_kind'] for d in ds], ['lookup_by_id', 'graph_query'])
        self.assertEqual(ds[0]['path']['lookup_id'], ['field', 'self', 'target_id'])
        self.assertEqual(ds[1]['path']['origin'], 'lookup')
        self.assertEqual(ds[1]['path']['lookup_id'], ds[0]['path']['lookup_id'])
        self.assertEqual(ds[1]['path']['hops'][0]['edge'], 'E')

    def test_jobj_keyword_scalar_alias_cast_and_helper_preserve_identity(self):
        p = plan(BASE + 'def items(a: A) { return [a->:E:->[?:B]]; } walker W { has target_id: str; can run with A entry { key = self.target_id; x = jobj(id=key); y = cast(A, x); report items(y); } }')
        ds = p['abilities']['run']['demands']
        self.assertEqual(len(ds), 2)
        self.assertEqual(ds[1]['path']['lookup_id'], ['field', 'self', 'target_id'])
        self.assertEqual(ds[1]['calls'], ['items'])

    def test_cast_does_not_invent_receiver_type(self):
        p = plan('node A { def view { return [self-->]; } } walker W { has target_id: str; can run with Root entry { x = cast(A, jobj(self.target_id)); report x.view(); } }')
        self.assertEqual(len(p['abilities']['run']['demands']), 1)
        self.assertIn('Unresolved receiver', p['abilities']['run']['rejections'][0]['reason'])

    def test_jobj_does_not_bypass_unknown_guard(self):
        p = plan(BASE + 'walker W { has target_id: str; can run with A entry { x = jobj(self.target_id); if allowed(x) { report [x->:E:->[?:B]]; } } }')
        self.assertEqual([d['access_kind'] for d in p['abilities']['run']['demands']], ['lookup_by_id'])
        self.assertTrue(p['abilities']['run']['rejections'])

    def test_jobj_false_guard_is_retained(self):
        p = plan(BASE + 'walker W { has enabled: bool = False, target_id: str; can run with A entry { if self.enabled { report jobj(self.target_id); } } }')
        self.assertEqual(p['abilities']['run']['demands'][0]['guards'], [[['field','self','enabled'],True]])

    def test_user_jobj_is_not_builtin(self):
        p = plan(BASE + 'def jobj(id: str) { return None; } walker W { can run with A entry { report jobj("x"); } }')
        self.assertEqual(p['abilities']['run']['demands'], [])

    def test_local_shadow_and_unknown_id_decline(self):
        for body in ['jobj = opaque; report jobj("x");', 'report jobj(make_id());']:
            p = plan(BASE + 'walker W { can run with A entry { '+body+' } }')
            self.assertEqual(p['abilities']['run']['demands'], [])
            self.assertTrue(p['abilities']['run']['rejections'])

    def test_lookup_uuid_forms_root_and_bad_id_preserve_native_validation(self):
        value = UUID('d2896883-89e3-456f-abd9-e4c457d42ce4')
        for key in [value.hex,str(value),'{'+str(value)+'}']:
            self.assertEqual(lookup_identity(['constant',key],{},{},None,None),value)
        self.assertEqual(lookup_identity(['constant','root'],{},{},None,SimpleNamespace(id=value)),value)
        for bad in [None, 17, '', 'broken']:
            with self.assertRaises((Unresolved, ValueError)):
                lookup_identity(['constant',bad],{},{},None,None)
        class Unsafe(str):
            def __str__(self): raise AssertionError('must not execute user conversion')
        with self.assertRaises(Unresolved):
            lookup_identity(['constant',Unsafe(str(value))],{},{},None,None)

    def test_jobj_inside_visit_still_records_payload_access(self):
        p=plan(BASE+'walker W { has target_id: str; can run with A entry { visit jobj(self.target_id); } }')
        self.assertEqual(p['abilities']['run']['demands'][0]['scheduling'],'ordinary_access')

    def test_access_does_not_create_visit(self):
        p = plan(BASE + 'walker W { can run with A entry { report [here->:E:->[?:B]]; } }')
        ds = p['abilities']['run']['demands']
        self.assertEqual(len(ds), 1)
        self.assertEqual(ds[0]['kind'], 'Access')
        self.assertEqual(ds[0]['scheduling'], 'ordinary_access')

    def test_visit_has_access_projection_but_alias_enqueues_no_new_query(self):
        p = plan(BASE + 'walker W { can run with A entry { xs = [here->:E:->[?:B]]; visit xs; visit [here->:E:->[?:B]]; } }')
        ds = p['abilities']['run']['demands']
        self.assertEqual([d['scheduling'] for d in ds], ['ordinary_access', 'visit_projection'])

    def test_typed_method_is_resolved_not_guessed_by_name(self):
        p = plan('node B {} edge E {} node Wrong { def view { return [self<--]; } } '
                 'node A { def view { return [self->:E:->[?:B]]; } } '
                 'walker W { can run with A entry { report here.view(); } }')
        ds = p['abilities']['run']['demands']
        self.assertEqual(len(ds), 1)
        self.assertEqual(ds[0]['path']['hops'][0]['edge'], 'E')
        self.assertEqual(ds[0]['calls'], ['here . view'])

    def test_unknown_receiver_does_not_match_unrelated_method(self):
        p = plan('node A { def view { return [self-->]; } } '
                 'walker W { can run with Root entry { report unknown.view(); } }')
        self.assertEqual(p['abilities']['run']['demands'], [])
        self.assertTrue(p['abilities']['run']['rejections'])

    def test_comprehension_origin_is_composed(self):
        p = plan('node C {} edge E {} edge F {} node B { def view { return [self->:F:->[?:C]]; } } '
                 'node A { def view { return [b.view() for b in [self->:E:->[?:B]]]; } } '
                 'walker W { can run with A entry { report here.view(); } }')
        ds = p['abilities']['run']['demands']
        self.assertEqual([[h['edge'] for h in d['path']['hops']] for d in ds], [['E'], ['E', 'F']])

    def test_singleton_selection_keeps_runtime_obligation(self):
        p = plan(BASE + 'walker W { can run with A entry { b = [here->:E:->[?:B]][0]; report [b-->]; } }')
        ds = p['abilities']['run']['demands']
        self.assertEqual(ds[-1]['path']['singletons'], [1])

    def test_global_helper_argument_binding(self):
        p = plan(BASE + 'def items(a: A) { return [a->:E:->[?:B]]; } '
                 'walker W { can run with A entry { report items(here); } }')
        ds = p['abilities']['run']['demands']
        self.assertEqual(ds[0]['path']['origin'], 'here')
        self.assertEqual(ds[0]['calls'], ['items'])

    def test_false_guard_keeps_demand_conditional(self):
        p = plan(BASE + 'walker W { has enabled: bool = False; can run with A entry { if self.enabled { report [here->:E:->[?:B]]; } } }')
        ds = p['abilities']['run']['demands']
        self.assertEqual(ds[0]['guards'], [[['field', 'self', 'enabled'], True]])
        self.assertFalse(scalar_value(ds[0]['guards'][0][0], {'enabled': False}, {}, None, None))

    def test_query_predicate_is_retained(self):
        p = plan(BASE + 'walker W { can run with A entry { report [here->:E:->[?:B, active == True]]; } }')
        self.assertEqual(p['abilities']['run']['demands'][0]['path']['hops'][0]['predicates'], [['active', '==', True]])

    def test_unknown_effect_stops_later_access(self):
        p = plan(BASE + 'walker W { can run with A entry { opaque(); report [here->:E:->[?:B]]; } }')
        self.assertEqual(p['abilities']['run']['demands'], [])

    def test_unknown_effect_in_callee_stops_caller(self):
        p = plan(BASE + 'def opaque_helper { opaque(); } walker W { can run with A entry { opaque_helper(); report [here->:E:->[?:B]]; } }')
        self.assertEqual(p['abilities']['run']['demands'], [])

    def test_predicate_input_not_evaluated_via_descriptor(self):
        with self.assertRaises(Unresolved):
            scalar_value(['field', 'here', 'active'], {}, {'active::unsafe': True}, None, None)

    def test_identity_guard_matches_native_hex_representation(self):
        uid = UUID('d2896883-89e3-456f-abd9-e4c457d42ce4')
        condition = ['compare', 'Eq', ['identity', 'here'], ['field', 'self', 'target_id']]
        self.assertTrue(scalar_value(condition, {'target_id': uid.hex}, {}, SimpleNamespace(id=uid), None))
        self.assertFalse(scalar_value(condition, {'target_id': str(uid)}, {}, SimpleNamespace(id=uid), None))


if __name__ == '__main__':
    unittest.main()
