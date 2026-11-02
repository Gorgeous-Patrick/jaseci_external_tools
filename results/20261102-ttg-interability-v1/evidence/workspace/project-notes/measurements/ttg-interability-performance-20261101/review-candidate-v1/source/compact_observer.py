"""NEW compact parent outcome observer; direct SQL clocks/sinks are unchanged.

No ability method is wrapped. The borrowed HTTP dispatch/native-close observer
is installed with its outcome wrapper disabled; only the same finish boundary
emits this compact state view. Native state/arrays are never pruned or modified.
"""
from collections import Counter
import importlib.util
from pathlib import Path
import sys

PREVIOUS=Path(__file__).resolve().parents[1]/'ttg-continuation-performance'
sys.path.insert(0,str(PREVIOUS))
import continuation_probe as probe

def counts(values):return dict(Counter(values))

def project_state(state,capture=None):
    mem=state.ctx.mem
    with mem._raw_lock:
        unused=state.submitted & set(mem.__raw_mem__)
    plans=state.plans;continuations=state.continuations;fusion=state.fusion
    payload_errors=[dict(plan_index=i,payload_error=p['payload_error']) for i,p in enumerate(plans) if 'payload_error' in p]
    # Scalar native counters/mode/reasons are retained. The large regions list
    # and suffix/path/execution dictionaries stay solely in native memory.
    scalar_fusion={k:v for k,v in fusion.items() if v is None or type(v) in (bool,int,float,str)}
    # New disclosed ABI extension: fixed reason taxonomy counters only.
    # Native suffix/path/region structures remain omitted and untouched.
    reason_counts=fusion.get('region_fallback_reasons')
    if type(reason_counts) is dict and all(type(k) is str and type(v) is int for k,v in reason_counts.items()):
        scalar_fusion['region_fallback_reasons']=dict(reason_counts)
    omitted=[k for k in fusion if k not in scalar_fusion]
    regions=fusion.get('regions',[])
    return dict(format='ttg-interability-compact-v1',model=type(state.model).__name__,executor=state.mode or 'sync',
        feature_provider=type(state.provider).__name__,errors=list(state.errors),payload_errors=payload_errors,
        payload_error_count=len(payload_errors),fusion=scalar_fusion,omitted_fusion_fields=omitted,
        submitted_count=len(state.submitted),promoted_count=len(state.promoted),unused_cached_count=len(unused),
        unavailable_count=len(state.submitted-state.promoted-unused),plan_count=len(plans),
        resolved_plan_count=sum(p.get('resolved_nodes',0)>0 for p in plans),
        resolved_targets_cumulative=sum(p.get('resolved_nodes',0) for p in plans),
        plan_status_counts=counts(p.get('status','<missing>') for p in plans),
        continuation_count=len(continuations),continuation_path_count=sum(len(c.get('paths',[])) for c in continuations),
        continuation_execution_count=sum(len(c.get('executions',[])) for c in continuations),
        continuation_stop_counts=counts(c.get('stop','<missing>') for c in continuations),
        reached_point_counts=counts(str((c.get('ability'),c.get('point'),c.get('stop'))) for c in continuations),
        feedback_count=len(state.feedback),region_count=len(regions),
        region_kind_counts=counts(r.get('kind','<missing>') for r in regions),
        checkpoint_count=len(capture.records) if capture else 0,hit_count=len(capture.hits) if capture else 0,
        worker_process_pids=list(getattr(mem,'_prefetch_process_pids',[])),
        worker_process_startup_ms=list(getattr(mem,'_prefetch_process_startup_ms',[])),
        disclosure='Native suffix structures retained unchanged; compact output omits their detail, not native cost.')

def install(serving_app=None,execution_context=None,dependency=None,checkpoints=None):
    if serving_app is None:
        from jaclang.server.serving.app import ServingApp as serving_app
        from jaclang.runtime.context import ExecutionContext as execution_context
        from jaclang.runtime import ttg_dependency_prefetch as dependency
        from jaclang.runtime import ttg_checkpoints as checkpoints
    spec=importlib.util.spec_from_file_location('borrowed_next_http_observer',PREVIOUS/'http_observer.py')
    borrowed=importlib.util.module_from_spec(spec);spec.loader.exec_module(borrowed)
    borrowed.install(serving_app,execution_context,None,checkpoints)
    if dependency is None:return
    old_finish=dependency.finish_prefetch_feedback
    def finish(state):
        result=old_finish(state)
        capture=checkpoints._capture.get() if checkpoints is not None else None
        probe.event('dependency_outcome',scope_id=str(state.cache_token),scope_instance=id(state),
            summary=project_state(state,capture),format='ttg-interability-compact-v1',
            capture_regime='compact counters; native default checkpoint policy; no added analysis')
        return result
    dependency.finish_prefetch_feedback=finish
