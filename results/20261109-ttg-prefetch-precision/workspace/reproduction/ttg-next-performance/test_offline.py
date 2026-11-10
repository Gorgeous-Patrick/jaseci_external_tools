"""Bounded DB-free observer/selection tests. No Jac runtime or service starts."""
import asyncio
import copy
import json
from pathlib import Path
import threading
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

import compact_observer as observer
from next_config import schedule,run_config

class Mem:
    def __init__(self):self._raw_lock=threading.RLock();self.__raw_mem__={'c':1}

def state():
    s=NS(ctx=NS(mem=Mem()),submitted={'a','b','c','d'},promoted={'a','b'},
        plans=[dict(status='resolved',resolved_nodes=3),dict(status='blocked',resolved_nodes=0)],
        continuations=[dict(ability='walk',point=1,stop='unknown',paths=[1,2],executions=[1])],
        fusion=dict(enabled=True,queries=1,regions=[dict(kind='linear')]),errors=[],model=NS(),provider=NS(),
        mode='process',feedback=[{}],cache_token='scope')
    s.summary=lambda:(_ for _ in ()).throw(AssertionError('Full native summary must not be called'))
    return s

class CompactTests(unittest.TestCase):
    def test_exact_counters_and_no_mutation(self):
        s=state();before=copy.deepcopy((s.plans,s.continuations,s.fusion,s.submitted,s.promoted))
        r=observer.project_state(s)
        self.assertEqual((r['submitted_count'],r['promoted_count'],r['unused_cached_count'],r['unavailable_count']),(4,2,1,1))
        self.assertEqual((r['resolved_plan_count'],r['resolved_targets_cumulative']),(1,3))
        self.assertEqual(r['continuation_path_count'],2);self.assertEqual(r['continuation_execution_count'],1)
        self.assertEqual(r['continuation_stop_counts'],{'unknown':1})
        self.assertEqual((s.plans,s.continuations,s.fusion,s.submitted,s.promoted),before)
    def test_payload_error_cannot_hide_in_empty_top_errors(self):
        s=state();s.plans[1]['payload_error']='actual child failed'
        r=observer.project_state(s);self.assertEqual(r['payload_error_count'],1)
        self.assertEqual(r['payload_errors'][0]['payload_error'],'actual child failed')
    def test_large_suffix_is_not_iterated_or_serialized(self):
        class LenOnly:
            def __len__(self):return 1_000_000
            def __iter__(self):raise AssertionError('Suffix records traversed')
        s=state();s.continuations[0].update(paths=LenOnly(),executions=LenOnly())
        r=observer.project_state(s)
        self.assertEqual(r['continuation_path_count'],1_000_000)
        self.assertLess(len(json.dumps(r)),4096)
    def test_mode_and_fallback_reason_retained(self):
        s=state();s.fusion.update(effective_mode='per_path',fallback_reason='actual unsupported event')
        r=observer.project_state(s)
        self.assertEqual(r['fusion']['fallback_reason'],'actual unsupported event')

    def test_observer_preserves_native_close_and_callback_identity(self):
        ready=threading.Event();release=threading.Event();closed=threading.Event();events=[]
        class Session:pass
        class Context:
            def __init__(self):self.mem=Session()
            def close(self):closed.set();return 'native close'
        class Serving:
            async def dispatch(self,request):return 'native response'
        class Walker:
            def ability(self):return 1
        identity=Walker.ability
        dependency=NS(finish_prefetch_feedback=lambda s:'finished')
        checkpoints=NS(_capture=NS(get=lambda:None))
        worker=threading.Thread(target=lambda:(ready.set(),release.wait(),events.append(('late_worker',{}))))
        worker.start();self.assertTrue(ready.wait(1))
        try:
            with patch.object(observer.probe,'event',side_effect=lambda kind,**kw:events.append((kind,kw))):
                observer.install(Serving,Context,dependency,checkpoints)
                context=Context();self.assertEqual(context.close(),'native close')
                self.assertTrue(closed.is_set());self.assertFalse(release.is_set())
                self.assertEqual(dependency.finish_prefetch_feedback(state()),'finished')
                self.assertEqual(Walker.ability,identity)
                self.assertEqual(asyncio.run(Serving().dispatch(NS(headers={}))), 'native response')
            self.assertEqual(events[0][0],'native_context_close')
            self.assertEqual(events[1][1]['format'],'ttg-next-compact-v1')
        finally:release.set();worker.join(1)
        self.assertTrue(any(kind=='late_worker' for kind,data in events))

class SelectionTests(unittest.TestCase):
    def test_fixed_cases_and_balanced_n3(self):
        rows=schedule(True);self.assertEqual(len(rows),72)
        self.assertEqual(sum(r['phase']=='excluded_warmup' for r in rows),18)
        self.assertEqual(len({r['app'] for r in rows}),5)
        self.assertEqual(len({r['case_id'] for r in rows}),6)
        for case in {r['case_id'] for r in rows}:
            selected=[r for r in rows if r['case_id']==case and r['phase']=='measured']
            self.assertEqual(len(selected),9)
            for mode in ('off','baseline850','next'):
                self.assertEqual(sum(r['config_id']==mode for r in selected),3)
                self.assertEqual(sum(selected[n]['config_id']==mode for n in (0,3,6)),1)
    def test_off_first_correctness(self):
        rows=schedule(False);self.assertEqual(len(rows),18)
        self.assertTrue(all(rows[n]['config_id']=='off' for n in range(0,18,3)))
    def test_cannot_override_common_regime(self):
        with self.assertRaises(ValueError):run_config('next',{'prefetch_workers':8})
        with self.assertRaises(ValueError):run_config('next',{'ttg_fused_sql':False})

if __name__=='__main__':unittest.main()
