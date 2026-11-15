"""Diagnostic same-native-thread phase clocks; source prepared, not yet run.

No cProfile, ability wrappers, caller-frame hook wrappers or production edits.
Install only in the separately released diagnostic server after primary quiet.
"""
import functools
import importlib
import json
import os
from pathlib import Path
import sys
import threading
import time
from uuid import UUID

LOCAL = threading.local()
HOOKS = {
    'jaclang.runtime.prefetch': ['run_prefetch_policy', 'dispatch_prefetch'],
    'jaclang.runtime.prefetch_policy': ['get_prefetch_plan'],
    'jaclang.runtime.ttg_checkpoints': ['cached_checkpoint_plan'],
    'jaclang.runtime.ttg_dependency_prefetch': ['prefetch_continuation', 'dispatch_fused_payload'],
    'jaclang.runtime.ttg_continuation': ['plan_continuation'],
    'jaclang.runtime.ttg_frontier': ['collect_frontier', 'resolve_frontier'],
    'jaclang.runtime.ttg_regions': ['resolve_interability_region'],
    'jaclang.runtime.ttg_access_plan': ['prefetch_accesses'],
    'jaclang.runtime.ttg_templates': ['select_template', 'hydrate_descriptor', 'bind_template'],
    'jaclang.runtime.ttg_sql': ['compile_layered', 'compile_specialized', 'compile_undirected_probe'],
    'jaclang.data.query_planner': ['compile_query', 'resolve_ttg_path'],
}
FORBIDDEN = {'access_checkpoint', 'with_access_checkpoint'}


def bind_path(target, mapping_path=None):
    """Rebind the observer target only; do not alter native path or input."""
    path='/walker/'+target['walker']
    witness={'logical_target':target.get('logical_target')}
    if target.get('logical_target') is not None:
        if mapping_path is None:
            raise ValueError('Fresh importer mapping is required')
        source=Path(mapping_path)
        raw=source.read_bytes();mapping=json.loads(raw)
        value=mapping[target['logical_target']]
        if type(value) is not str:
            raise ValueError('Native importer identity must be text')
        UUID(value)
        if len(set(mapping.values()))!=len(mapping):
            raise ValueError('Native importer map is not bijective')
        path+='/'+value
        witness.update(mapping_path=str(source),mapping_sha256=__import__('hashlib').sha256(raw).hexdigest(),actual_target=value)
    return path,witness


def timed(name, function, args, kwargs, details=None):
    session = getattr(LOCAL, 'session', None)
    if session is None:
        return function(*args, **kwargs)
    stack = session['stack']
    frame = {'child_cpu_ns': 0}
    stack.append(frame)
    thread = threading.get_ident()
    native_thread = threading.get_native_id()
    started_wall = time.perf_counter_ns()
    started_cpu = time.thread_time_ns()
    error = None
    try:
        return function(*args, **kwargs)
    except BaseException as exc:
        error = type(exc).__name__
        raise
    finally:
        ended_cpu = time.thread_time_ns()
        ended_wall = time.perf_counter_ns()
        cpu = ended_cpu - started_cpu
        if threading.get_ident() != thread or threading.get_native_id() != native_thread:
            raise AssertionError('Phase crossed native threads')
        if cpu < frame['child_cpu_ns'] or frame['child_cpu_ns'] < 0:
            raise AssertionError('Invalid nested direct CPU partition')
        if stack.pop() is not frame:
            raise AssertionError('Unbalanced phase stack')
        if stack:
            stack[-1]['child_cpu_ns'] += cpu
        session['events'].append(dict(name=name,thread_id=thread,native_thread_id=native_thread,
            start_ns=started_wall,end_ns=ended_wall,wall_ns=ended_wall-started_wall,
            thread_cpu_ns=cpu,exclusive_thread_cpu_ns=cpu-frame['child_cpu_ns'],
            depth=len(stack),error=error,details=details or {}))


def install(selection, output):
    """Borrowed direct-boundary method, limited to named safe phase functions."""
    import asyncio
    from contextvars import ContextVar
    from jaclang.server.serving.app import ServingApp
    from jaclang.runtime.runtime import JacRuntimeInterface
    import continuation_probe as probe
    if not selection or len(selection)>2:
        raise ValueError('Select one or two actual request sites in this workflow')
    if len({row['request'] for row in selection})!=len(selection):
        raise ValueError('Duplicate selected request identity')
    targets={row['request']:row for row in selection}
    output=Path(output)
    output.mkdir(parents=True,exist_ok=False)
    originals=[]
    bindings=[]
    for module,names in HOOKS.items():
        loaded=importlib.import_module(module)
        for name in names:
            if name in FORBIDDEN:
                raise AssertionError('Caller-frame-sensitive hook is prohibited')
            original=getattr(loaded,name)
            if not callable(original) or isinstance(original,type):
                raise TypeError('Phase must be an exact named module callable')
            def make(function,label):
                @functools.wraps(function)
                def wrapped(*args,**kwargs):
                    return timed(label,function,args,kwargs)
                return wrapped
            originals.append((original,make(original,module+'.'+name)))
    # Update already-loaded aliases by exact callable identity, never abilities.
    # The direct caller of access_checkpoint remains the original native ability.
    for module in list(sys.modules.values()):
        if module is None:
            continue
        namespace=vars(module)
        name=namespace.get('__name__','')
        if not name.startswith('jaclang'):
            continue
        for key,value in list(namespace.items()):
            for original,wrapper in originals:
                if value is original:
                    if key in FORBIDDEN:
                        raise AssertionError('Refuse to replace caller-frame hook')
                    setattr(module,key,wrapper)
                    bindings.append(dict(module=name,name=key,phase=wrapper.__module__+'.'+wrapper.__name__))
    old_dispatch=ServingApp.dispatch
    old_to_thread=asyncio.to_thread
    old_wait=threading.Event.wait
    active=ContextVar('selected_diagnostic_cpu_request',default=None)
    completed=set()

    def wait(event,*args,**kwargs):
        session=getattr(LOCAL,'session',None)
        if session is None or event is not getattr(session['mem'],'_prefetch_done',None):
            return old_wait(event,*args,**kwargs)
        timeout=args[0] if args else kwargs.get('timeout')
        # Preserve the actual Event object, timeout, wait call and return value.
        return timed('native_prefetch_done.Event.wait',old_wait,(event,*args),kwargs,
                     dict(timeout_seconds=timeout,event_object_id=id(event)))

    def measured(function,args,kwargs,target):
        request=target['request']
        if request in completed:
            raise AssertionError('Selected native callable invoked more than once')
        completed.add(request)
        ctx=JacRuntimeInterface.get_context()
        if ctx is None or ctx.mem is None:
            raise AssertionError('Selected native worker lacks actual request Session')
        session=dict(stack=[],events=[],mem=ctx.mem)
        LOCAL.session=session
        succeeded=False
        try:
            value=timed('native_spawn',function,args,kwargs)
            succeeded=True
            return value
        finally:
            LOCAL.session=None
            events=session['events']
            outer=[row for row in events if row['name']=='native_spawn']
            if len(outer)!=1 or session['stack']:
                raise AssertionError('Missing/unbalanced native CPU boundary')
            parent=outer[0]
            if sum(row['exclusive_thread_cpu_ns'] for row in events)!=parent['thread_cpu_ns']:
                raise AssertionError('Direct same-thread exclusive partition mismatch')
            record=dict(passed=succeeded,request=request,target=target,pid=os.getpid(),
                thread_id=threading.get_ident(),native_thread_id=threading.get_native_id(),
                callable_name=function.__name__,session_object_id=id(ctx.mem),
                thread_cpu_ns=parent['thread_cpu_ns'],wall_ns=parent['wall_ns'],events=events,
                hooks=HOOKS,installed_aliases=bindings,
                scope='Direct same-native-spawn-thread CPU. Exclusive phase CPU partitions this boundary only. Any delegated planner/payload thread, event-loop and DB-server CPU is excluded. A lower value does not establish total CPU saving. Inclusive wall phases overlap. Timer/wrapper overhead retained. No wall-minus-DB estimate; diagnostic n1, never pooled with primary n5.')
            (output/(request.replace(':','-')+'.json')).write_text(json.dumps(record,indent=2)+'\n')
            probe.event('direct_CPU_diagnostic_complete',selected_request=request,passed=succeeded,
                        actual_thread_id=record['thread_id'],native_thread_id=record['native_thread_id'])

    async def to_thread(function,*args,**kwargs):
        target=active.get()
        if target is not None and getattr(function,'__name__','')=='_spawn_with_profile':
            return await old_to_thread(measured,function,args,kwargs,target)
        return await old_to_thread(function,*args,**kwargs)

    async def dispatch(self,request):
        request_id=request.headers.get('X-TTG-Perf-Request')
        if request_id not in targets:
            return await old_dispatch(self,request)
        declared=targets[request_id]
        expected_path,witness=bind_path(declared,os.environ.get('TTG_CPU_MAPPING_FILE'))
        if str(request.url.path)!=expected_path:
            raise AssertionError('Selected actual path differs')
        if str(probe.BASE['TTG_PERF_SERVER_GENERATION'])!=str(declared['generation']):
            raise AssertionError('Selected server generation differs')
        target=dict(declared,actual_path=str(request.url.path),fresh_binding=witness)
        token=active.set(target)
        try:
            return await old_dispatch(self,request)
        finally:
            active.reset(token)

    threading.Event.wait=wait
    asyncio.to_thread=to_thread
    ServingApp.dispatch=dispatch
    return dict(hooks=HOOKS,forbidden=sorted(FORBIDDEN),request_ids=sorted(targets))


def clock_controls():
    """After quiet only: tiny concurrent sleep/busy nested thread-clock controls."""
    barrier=threading.Barrier(2)
    results=[]
    errors=[]
    def worker(kind):
        try:
            LOCAL.session=dict(stack=[],events=[])
            barrier.wait()
            def leaf():
                if kind=='sleep':
                    time.sleep(.04)
                else:
                    deadline=time.thread_time_ns()+40_000_000
                    while time.thread_time_ns()<deadline:
                        sum(range(100))
            timed('outer',lambda:timed(kind,leaf,(),{}),(),{})
            events=LOCAL.session['events']
            if sum(e['exclusive_thread_cpu_ns'] for e in events)!=events[-1]['thread_cpu_ns']:
                raise AssertionError('Control partition mismatch')
            outer=events[-1]
            if kind=='sleep' and not (outer['wall_ns']>=35_000_000 and outer['thread_cpu_ns']<10_000_000):
                raise AssertionError('Sleep control did not separate wall and thread CPU')
            if kind=='busy' and outer['thread_cpu_ns']<40_000_000:
                raise AssertionError('Busy control did not accumulate thread CPU')
            results.append(dict(kind=kind,events=events))
        except BaseException as exc:
            errors.append(repr(exc))
        finally:
            LOCAL.session=None
    threads=[threading.Thread(target=worker,args=(kind,)) for kind in ('sleep','busy')]
    for thread in threads:thread.start()
    for thread in threads:thread.join()
    if errors or len(results)!=2:
        raise AssertionError(errors)
    return dict(passed=True,controls=results,scope='Separate direct same-thread nested clock controls; not workload CPU or an overhead subtraction')


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--clock-controls-output',required=True,type=Path)
    args=parser.parse_args()
    if args.clock_controls_output.exists():
        raise ValueError('Use a new diagnostic clock-control output')
    args.clock_controls_output.write_text(json.dumps(clock_controls(),indent=2)+'\n')
