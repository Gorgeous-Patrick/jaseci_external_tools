"""Explicit harness HTTP/lifecycle observation; no DB/socket monkeypatches.

Install from perf_serve.py, never in process readers. Child observation comes
from the direct PgWire source import. Default checkpoint capture is preserved;
this does not enable per-pending-node diagnostic analysis in primary runs.
"""
import time
import uuid
import weakref
import threading
import continuation_probe as probe
SESSION_IDENTITIES={}
SESSION_LOCK=threading.Lock()


def install(serving_app=None,execution_context=None,dependency=None,checkpoints=None):
    if serving_app is None:
        from jaclang.server.serving.app import ServingApp as serving_app
        from jaclang.runtime.context import ExecutionContext as execution_context
        from jaclang.runtime import ttg_dependency_prefetch as dependency
        from jaclang.runtime import ttg_checkpoints as checkpoints
    old_dispatch=serving_app.dispatch
    async def dispatch(self,request):
        origin=request.headers.get('X-TTG-Perf-Request')
        # Health/openapi startup reads retain explicit request-excluded scope.
        if not origin: return await old_dispatch(self,request)
        with probe.request_scope(origin):
            if request.headers.get('X-TTG-Perf-Reset-Profile')=='1':
                from jaclang.runtime.ttg_prefetch_profile import default_prefetch_profile
                default_prefetch_profile.clear()
                probe.event('explicit_profile_reset',regime='before_first_workflow_request')
            started=time.perf_counter_ns()
            try: return await old_dispatch(self,request)
            finally:
                probe.event('native_dispatch_complete',path=str(request.url.path),
                    start_ns=started,end_ns=time.perf_counter_ns())
    serving_app.dispatch=dispatch
    old_close=execution_context.close
    def close(self,*args,**kwargs):
        started=time.perf_counter_ns()
        session=self.mem;identity=id(session)
        with SESSION_LOCK:
            previous=SESSION_IDENTITIES.get(identity)
            if previous is None or previous[0]() is not session:
                previous=(weakref.ref(session),str(uuid.uuid4()))
                SESSION_IDENTITIES[identity]=previous
            nonce=previous[1]
        completed=False
        # Native core owns its genuine joins/process close. No observer wait.
        try:
            result=old_close(self,*args,**kwargs);completed=True;return result
        finally:
            probe.event('native_context_close',start_ns=started,end_ns=time.perf_counter_ns(),
                session_nonce=nonce,session_object_id=identity,natural_close_completed=completed)
    execution_context.close=close
    if dependency is not None:
        old_finish=dependency.finish_prefetch_feedback
        def finish(state):
            result=old_finish(state)
            capture=checkpoints._capture.get() if checkpoints is not None else None
            probe.event('dependency_outcome',scope_id=str(state.cache_token),
                scope_instance=id(state),summary=state.summary(),
                checkpoints=list(capture.records) if capture else [],
                hits=list(capture.hits) if capture else [],
                capture_regime='native_default_no_added_pending_analysis')
            return result
        dependency.finish_prefetch_feedback=finish
