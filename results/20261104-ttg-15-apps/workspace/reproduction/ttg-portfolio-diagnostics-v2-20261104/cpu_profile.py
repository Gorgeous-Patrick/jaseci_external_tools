"""Diagnostic direct same-thread boundary timers; no profiler or ability wrapping."""
import functools,importlib,json,os,sys,threading,time
from pathlib import Path
LOCAL=threading.local()
HOOKS={
 'jaclang.runtime.ttg_dependency_prefetch': ['record_model_event','prefetch_continuation','dispatch_fused_payload','finish_prefetch_feedback'],
 'jaclang.runtime.ttg_regions':['resolve_interability_region'],
 'jaclang.runtime.ttg_frontier':['collect_frontier','resolve_frontier'],
 'jaclang.runtime.ttg_continuation':['plan_continuation'],
}
def timed(name,fn,args,kwargs):
    session=getattr(LOCAL,'session',None)
    if session is None:return fn(*args,**kwargs)
    stack=session['stack'];frame={'child':0};stack.append(frame)
    thread=threading.get_ident();wall=time.perf_counter_ns();cpu=time.thread_time_ns()
    try:return fn(*args,**kwargs)
    finally:
        endcpu=time.thread_time_ns();endwall=time.perf_counter_ns();elapsed=endcpu-cpu
        assert threading.get_ident()==thread and elapsed>=frame['child']>=0
        assert stack.pop() is frame
        if stack:stack[-1]['child']+=elapsed
        session['events'].append(dict(name=name,thread_id=thread,cpu_ns=elapsed,exclusive_cpu_ns=elapsed-frame['child'],wall_ns=endwall-wall,start_ns=wall,end_ns=endwall,depth=len(stack)))
def install():
    import asyncio
    from contextvars import ContextVar
    from jaclang.server.serving.app import ServingApp
    originals=[]
    for module,names in HOOKS.items():
        m=importlib.import_module(module)
        for name in names:
            f=getattr(m,name)
            def make(fn,label):
                @functools.wraps(fn)
                def wrapped(*a,**k):return timed(label,fn,a,k)
                return wrapped
            originals.append((f,make(f,module+'.'+name)))
    for m in list(sys.modules.values()):
        if m is None or not getattr(m,'__name__','').startswith('jaclang'):continue
        for key,value in list(vars(m).items()):
            for original,wrapper in originals:
                if value is original:setattr(m,key,wrapper)
    old_dispatch=ServingApp.dispatch;old_to_thread=asyncio.to_thread
    active=ContextVar('selected_cpu_boundary',default=None);completed=set()
    selected=set(json.loads(os.environ['TTG_CPU_REQUESTS']))
    def measured(func,args,kwargs,info):
        request_id,path=info;assert request_id not in completed;completed.add(request_id)
        session=dict(stack=[],events=[]);LOCAL.session=session;ok=False
        try:
            value=timed('native_spawn',func,args,kwargs);ok=True;return value
        finally:
            LOCAL.session=None;events=session['events'];outer=[x for x in events if x['name']=='native_spawn'];assert len(outer)==1
            outer=outer[0];assert sum(x['exclusive_cpu_ns'] for x in events)==outer['cpu_ns']
            record=dict(passed=ok,request=request_id,path=path,pid=os.getpid(),thread_id=threading.get_ident(),native_callable=func.__name__,thread_cpu_ns=outer['cpu_ns'],wall_ns=outer['wall_ns'],events=events,hooks=HOOKS,
                scope='Direct same-native-worker-thread timers around named runtime helpers; no cProfile, no ability wrapping. Inclusive times overlap; exclusive times partition this instrumented native-spawn boundary, not whole HTTP. Background worker CPU and server CPU excluded. Imports performed before request; timer overhead included. Diagnostic n=1, not primary timing or additive explanation of primary wall delta.')
            out=Path(os.environ['TTG_CPU_OUTPUT']);out.mkdir(parents=True,exist_ok=True);(out/(request_id.replace(':','-')+'.json')).write_text(json.dumps(record,indent=2)+'\n')
    async def to_thread(func,*args,**kwargs):
        info=active.get()
        if info is not None and getattr(func,'__name__','')=='_spawn_with_profile':return await old_to_thread(measured,func,args,kwargs,info)
        return await old_to_thread(func,*args,**kwargs)
    async def dispatch(self,request):
        request_id=request.headers.get('X-TTG-Perf-Request')
        if request_id not in selected:return await old_dispatch(self,request)
        token=active.set((request_id,str(request.url.path)))
        try:return await old_dispatch(self,request)
        finally:active.reset(token)
    asyncio.to_thread=to_thread;ServingApp.dispatch=dispatch

def clock_controls():
    results=[];barrier=threading.Barrier(2)
    def work(mode):
        barrier.wait();LOCAL.session=dict(stack=[],events=[])
        def child():
            if mode=='sleep':time.sleep(.04)
            else:
                stop=time.thread_time_ns()+40_000_000
                while time.thread_time_ns()<stop:sum(range(100))
        timed('outer',lambda:timed(mode,child,(),{}),(),{})
        events=LOCAL.session['events'];LOCAL.session=None
        outer=events[-1];assert sum(e['exclusive_cpu_ns'] for e in events)==outer['cpu_ns']
        if mode=='sleep':assert outer['wall_ns']>=35_000_000 and outer['cpu_ns']<10_000_000
        else:assert outer['cpu_ns']>=40_000_000
        results.append(dict(mode=mode,events=events))
    errors=[]
    def safe(mode):
        try:work(mode)
        except BaseException as e:errors.append(repr(e))
    ts=[threading.Thread(target=safe,args=(x,)) for x in ('sleep','busy')]
    for t in ts:t.start()
    for t in ts:t.join()
    assert len(results)==2 and not errors,errors
    return dict(passed=True,timer='direct thread_time_ns on same OS thread',concurrent=True,controls=results)
if __name__=='__main__':print(json.dumps(clock_controls(),indent=2))
