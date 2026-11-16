"""Observation-only exact-key diagnostic; no Jac imports until install().

Install after the accepted compact/background observers. Buffer in memory and
flush after their existing POST-HTTP Future drain; never add a demand wait.
"""
import atexit
import contextvars
import functools
import hashlib
import json
import os
from pathlib import Path
import sys
import threading
import time
from types import FunctionType
from uuid import UUID

ACCESS = contextvars.ContextVar('library_exact_access', default=None)
PAYLOAD = contextvars.ContextVar('library_payload', default=None)
JOB = contextvars.ContextVar('library_job', default=None)


def typed(value, classes=None):
    """Lossless supported cache-key encoding, without repr/getters/SQL work."""
    if value is None: return ['none']
    if type(value) is bool: return ['bool', value]
    if type(value) is int: return ['int', str(value)]
    if type(value) is float: return ['float', value.hex()]
    if type(value) is str: return ['str', value]
    if type(value) is bytes: return ['bytes', value.hex()]
    if type(value) is UUID: return ['uuid', value.hex]
    if type(value) is tuple: return ['tuple', [typed(v,classes) for v in value]]
    if type(value) is list: return ['list', [typed(v,classes) for v in value]]
    if type(value) is dict: return ['dict', [[typed(k,classes), typed(v,classes)] for k,v in value.items()]]
    if isinstance(value,type):
        if classes is None:raise TypeError('Class cache key requires retained identity registry')
        ident=id(value)
        if ident not in classes:
            # Invoke builtin type storage descriptors directly: custom
            # metaclass __getattribute__/__dict__/__qualname__ are not called.
            namespace=type.__dict__['__dict__'].__get__(value,type(value))
            module=namespace.get('__module__')
            qualname=type.__dict__['__qualname__'].__get__(value,type(value))
            encoded=['type','c'+str(len(classes)+1),
                     dict(module=module if type(module)is str else None,qualname=qualname)]
            classes[ident]=(value,encoded)  # Strong reference prevents id reuse.
        return classes[ident][1]
    raise TypeError('Unsupported exact cache-key component')


def readiness(before, after):
    """Future readiness bracket only; lease/coverage validity is separate."""
    if before is True:return 'future_ready_before_lookup'
    if before is False and after is False:return 'future_pending_through_lookup'
    return 'readiness_boundary_or_unknown'


class Observer:
    def __init__(self, directory, sink, modules, max_events=500000):
        self.directory=Path(directory);self.directory.mkdir(parents=True,exist_ok=True)
        self.path=self.directory/f'library-timeliness-{os.getpid()}.jsonl'
        self.sink=sink;self.modules=modules;self.limit=max_events
        self.lock=threading.RLock();self.events=[];self.sequence=0;self.dropped=0
        self.sessions={};self.epochs={};self.keys={};self.jobs={};self.writes={}
        self.raw_writes={};self.retained=[];self.stores={};self.installed=[]
        self.class_refs={}
        self.drain_code=modules['background'].BackgroundSQLRun.drain.__code__
        self.enqueue_code=modules['background'].BackgroundSQLRun.enqueue.__code__

    def binding(self):
        try:
            b=self.sink.binding()
            return list(b) if b is not None else None
        except LookupError:return None

    def emit(self, kind, **fields):
        now=time.perf_counter_ns()
        with self.lock:
            self.sequence+=1
            row=dict(kind=kind,seq=self.sequence,ns=now,pid=os.getpid(),
                     thread=threading.get_ident(),binding=self.binding(),**fields)
            if len(self.events)<self.limit:self.events.append(row)
            else:self.dropped+=1
        return row

    def context(self, mem):
        cache=mem._query_cache
        with self.lock:
            if id(mem) not in self.sessions:
                self.sessions[id(mem)]='s'+str(len(self.sessions)+1);self.retained.append(mem)
                if mem.store is not None:self.stores[id(mem.store)]=self.sessions[id(mem)]
            if id(cache) not in self.epochs:
                self.epochs[id(cache)]='e'+str(len(self.epochs)+1);self.retained.append(cache)
            return dict(session=self.sessions[id(mem)],epoch=self.epochs[id(cache)])

    def key(self, value):
        with self.lock:encoded=typed(value,self.class_refs)
        canonical=json.dumps(encoded,separators=(',',':'),ensure_ascii=False)
        kid=hashlib.sha256(canonical.encode()).hexdigest()
        with self.lock:
            if kid not in self.keys:
                self.keys[kid]=encoded;self.emit('key_definition',key_id=kid,key=encoded)
            elif self.keys[kid]!=encoded:raise AssertionError('Cache-key digest collision')
        return kid

    def future_states(self, mem):
        ctx=self.context(mem);out=[]
        with self.lock:jobs=list(self.jobs.items())
        for jid,m in jobs:
            if m['session']!=ctx['session']:continue
            future=m.get('future');run=m['run']
            out.append(dict(job_id=jid,observed_ns=time.perf_counter_ns(),
                done=None if future is None else future.done(),
                cancelled=None if future is None else future.cancelled(),
                lease_cancelled=m['cancel'].is_set(),epoch_equal=m['epoch']==ctx['epoch'],
                owner_closed=bool(run.closed),snapshot_equal=run.snapshot==m['snapshot']))
        return out

    @staticmethod
    def source_stack():
        frame=sys._getframe(2);out=[]
        for _ in range(14):
            if frame is None:break
            name=frame.f_code.co_filename
            if name.endswith('.jac'):
                out.append(dict(file=name,line=frame.f_lineno,function=frame.f_code.co_name))
            frame=frame.f_back
        return out

    def wrap(self, owner, name, build):
        old=getattr(owner,name);new=functools.wraps(old)(build(old))
        setattr(owner,name,new);self.installed.append((owner,name,old,new))
        # Jac impl functions can retain a separate execution globals dict.
        # Replace only exact aliases of this original seam, never other calls.
        if owner is self.modules.get('planner'):
            for value in list(vars(owner).values()):
                if type(value) is FunctionType and value.__globals__.get(name) is old:
                    value.__globals__[name]=new
                    self.emit('alias_binding',seam=name,consumer=value.__name__)

    def logical(self, old):
        def call(mem,*args,**kwargs):
            if ACCESS.get() is not None:return old(mem,*args,**kwargs)
            query=(args[1] if old.__name__=='_sql_pairs' and len(args)>1 else
                   args[0] if old.__name__=='resolve_query_count' and args else None)
            from_visit=getattr(query,'from_visit',None) if query is not None else None
            ctx=self.context(mem);start=self.emit('access_begin',seam=old.__name__,
                from_visit=from_visit,caller=self.source_stack(),**ctx);token=ACCESS.set(start['seq'])
            try:
                result=old(mem,*args,**kwargs)
                self.emit('access_end',access_id=start['seq'],**self.context(mem))
                return result
            except BaseException as exc:
                self.emit('access_error',access_id=start['seq'],error=type(exc).__name__,**self.context(mem));raise
            finally:ACCESS.reset(token)
        return call

    def cache_get(self, old):
        def call(mem,key):
            ctx=self.context(mem);kid=self.key(key)
            before=self.future_states(mem) if ACCESS.get() is not None else []
            began=time.perf_counter_ns();value=old(mem,key);ended=time.perf_counter_ns()
            after=self.future_states(mem) if ACCESS.get() is not None else []
            w=self.writes.get((ctx['session'],ctx['epoch'],kid))
            source=w['source'] if w and w['value'] is value and value is not None else None
            self.emit('cache_lookup',access_id=ACCESS.get(),key_id=kid,hit=value is not None,
                empty_path=(isinstance(value,tuple) and len(value)==2 and isinstance(value[0],tuple) and len(value[0])==0) if value is not None else None,
                lookup_start_ns=began,lookup_end_ns=ended,futures_before=before,futures_after=after,
                write_source=source,write_seq=w['seq'] if source else None,**ctx)
            return value
        return call

    def publication(self, frame):
        if frame.f_code is self.drain_code:
            record=frame.f_locals.get('record')
            if type(record) is dict and record.get('job_id') in self.jobs:
                return dict(kind='background',job_id=record['job_id'])
        if ACCESS.get() is not None:return dict(kind='native_access',access_id=ACCESS.get())
        return dict(kind='other_observed_write')

    def cache_put(self, old):
        def call(mem,key,value):
            ctx=self.context(mem);kid=self.key(key);source=self.publication(sys._getframe(1))
            at_capacity=len(mem._query_cache)>=4096;result=old(mem,key,value)
            stored=key in mem._query_cache and mem._query_cache[key] is value
            if at_capacity and stored:
                self.writes={k:v for k,v in self.writes.items() if k[:2]!=(ctx['session'],ctx['epoch'])}
            row=self.emit('cache_write',key_id=kid,source=source,stored=stored,**ctx)
            if stored:self.writes[ctx['session'],ctx['epoch'],kid]=dict(source=source,value=value,seq=row['seq'])
            return result
        return call

    def invalidate(self, old):
        def call(mem,*args,**kwargs):
            before=self.context(mem);result=old(mem,*args,**kwargs)
            self.emit('epoch_invalidation',old_epoch=before['epoch'],**self.context(mem));return result
        return call

    def submit(self, old):
        def call(pool,job):
            frame=sys._getframe(1)
            if frame.f_code is not self.enqueue_code:
                self.emit('diagnostic_error',error='Unexpected submit caller');return old(pool,job)
            run=frame.f_locals['self'];ctx=self.context(run.mem);jid=job['job_id']
            with self.lock:self.jobs[jid]=dict(**ctx,run=run,cancel=job['cancel'],snapshot=job['snapshot'])
            self.emit('job_capture',job_id=jid,native_request_id=job['request_id'],
                actor=job['actor'],snapshot=job['snapshot'],origin=job['origin'],region=self.encode(job['region']),
                caller=self.source_stack(),**ctx)
            future=old(pool,job)
            with self.lock:self.jobs[jid]['future']=future
            self.emit('future_attached',job_id=jid,done_observed=future.done())
            def completed(f):
                self.emit('future_done_observed',job_id=jid,done_observed=f.done(),cancelled=f.cancelled())
            future.add_done_callback(completed)
            return future
        return call

    def encode(self,value):
        with self.lock:return typed(value,self.class_refs)

    def worker(self, old):
        def call(job):
            token=JOB.set(job['job_id'])
            try:
                result=old(job)
                keys=[self.key(k) for k,v in result.get('puts',[])] if type(result) is dict else []
                payloads=[str(u) for u in result.get('loaded',{})] if type(result) is dict else []
                self.emit('worker_return',job_id=job['job_id'],key_ids=keys,payload_ids=payloads,
                    result_error=bool(result.get('error')) if type(result) is dict else True,
                    cancelled=bool(result.get('cancelled')) if type(result) is dict else None,
                    coverage_materialized=bool(type(result) is dict and 'puts' in result))
                return result
            finally:JOB.reset(token)
        return call

    def event(self, old):
        def call(event):
            began=time.perf_counter_ns();result=old(event)
            self.emit('job_phase',native_event=dict(event),observed_start_ns=began)
            return result
        return call

    def payload(self, old):
        def call(mem,ids,*args,**kwargs):
            if PAYLOAD.get() is not None:return old(mem,ids,*args,**kwargs)
            actual=[ids] if old.__name__=='get' else list(ids) if type(ids) in (list,tuple) else None
            row=self.emit('payload_begin',seam=old.__name__,ids=[str(u)for u in actual] if actual is not None else None,
                          **self.context(mem));token=PAYLOAD.set(row['seq'])
            try:
                result=old(mem,ids,*args,**kwargs)
                self.emit('payload_end',payload_id=row['seq'],returned=result is not None,**self.context(mem))
                return result
            finally:PAYLOAD.reset(token)
        return call

    def store_raw(self, old):
        def call(mem,uid,row):
            source=self.publication(sys._getframe(1));result=old(mem,uid,row)
            stored=mem.__raw_mem__.get(uid) is row
            event=self.emit('raw_write',uid=str(uid),source=source,stored=stored,**self.context(mem))
            if stored:self.raw_writes[id(mem),uid]=(row,source,event['seq'])
            return result
        return call

    def promote(self, old):
        def call(mem,uid):
            raw=mem.__raw_mem__.get(uid);prior=self.raw_writes.get((id(mem),uid));result=old(mem,uid)
            source=prior[1] if prior and prior[0] is raw else None
            self.emit('payload_promotion',payload_id=PAYLOAD.get(),uid=str(uid),served=result is not None,
                      raw_source=source,raw_write_seq=prior[2] if source else None,**self.context(mem))
            return result
        return call

    def load_full(self, old):
        def call(store,ids,*args,**kwargs):
            actual=[str(u)for u in ids] if type(ids) in (list,tuple) else None
            began=time.perf_counter_ns();result=old(store,ids,*args,**kwargs)
            self.emit('payload_load',access_id=ACCESS.get(),payload_id=PAYLOAD.get(),job_id=JOB.get(),
                session=self.stores.get(id(store)),ids=actual,loaded_ids=[str(u)for u in result] if type(result)is dict else None,
                start_ns=began,end_ns=time.perf_counter_ns())
            return result
        return call

    def run_sql(self, old):
        def call(store,*args,**kwargs):
            sql=args[0] if args else kwargs.get('sql')
            started=self.emit('sql_begin',access_id=ACCESS.get(),payload_id=PAYLOAD.get(),job_id=JOB.get(),
                session=self.stores.get(id(store)),sql=sql if type(sql)is str else None)
            try:return old(store,*args,**kwargs)
            finally:self.emit('sql_end',sql_id=started['seq'])
        return call

    def flush(self):
        with self.lock:
            rows=self.events;self.events=[];dropped=self.dropped;self.dropped=0
        if dropped:rows.append(dict(kind='diagnostic_overflow',dropped=dropped))
        if rows:
            with self.path.open('a') as f:
                for row in rows:f.write(json.dumps(row,separators=(',',':'))+'\n')

    def install(self):
        q=self.modules['planner'];b=self.modules['background'];session=self.modules['Session'];store=self.modules['PgStore']
        for name in ('_sql_pairs','resolve_query_count'):self.wrap(q,name,self.logical)
        for name,build in (('query_cache_get',self.cache_get),('query_cache_put',self.cache_put),
                           ('invalidate_query_cache',self.invalidate),('get',self.payload),('batch_get',self.payload),
                           ('store_raw',self.store_raw),('promote_raw',self.promote)):
            self.wrap(session,name,build)
        self.wrap(b,'_background_submit',self.submit);self.wrap(b,'_background_work',self.worker)
        self.wrap(b,'background_job_event',self.event)
        self.wrap(store,'load_full',self.load_full);self.wrap(store,'_run',self.run_sql)
        old=self.sink.drain_after_response
        @functools.wraps(old)
        def drain(*args,**kwargs):
            try:return old(*args,**kwargs)
            finally:self.flush()
        self.sink.drain_after_response=drain
        self.emit('trace_header',format='library-exact-key-v1',source=str(Path(__file__).resolve()),
                  source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  scope='observational, instrumented; flush after existing POSTHTTP drain; no additional waits')
        self.flush()  # Install receipt exists even when Off has no lookup/job events.
        atexit.register(self.flush)
        return self


def install(output_dir, sink=None, modules=None):
    if sink is None:import continuation_probe as sink
    if modules is None:
        from jaclang.data import query_planner
        from jaclang.runtime import ttg_access_plan
        from jaclang.server.session import Session
        from jaclang.data.store import PgStore
        modules=dict(planner=query_planner,background=ttg_access_plan,Session=Session,PgStore=PgStore)
    return Observer(output_dir,sink,modules).install()


def validate_trace(paths, require_activity=False, require_access_sql=False):
    """Small completeness check for t3; classification is a separate offline step."""
    rows=[]
    for path in paths:
        rows.extend(json.loads(line)for line in Path(path).read_text().splitlines())
    errors=[r for r in rows if r['kind'] in ('diagnostic_error','diagnostic_overflow')]
    if not any(r['kind']=='trace_header'for r in rows):errors.append(dict(kind='missing_header'))
    for pid in {r.get('pid')for r in rows}:
        seq=[r['seq']for r in rows if r.get('pid')==pid and 'seq'in r]
        if len(seq)!=len(set(seq)) or seq!=sorted(seq):errors.append(dict(kind='sequence_error',pid=pid))
    logical=sum(r['kind']=='access_begin'for r in rows)
    attempts=sum(r['kind']=='cache_lookup'and r.get('access_id')is not None for r in rows)
    joined_sql=sum(r['kind']=='sql_begin'and r.get('access_id')is not None for r in rows)
    if require_activity and (not logical or not attempts):errors.append(dict(kind='inactive_logical_access_seam'))
    if require_access_sql and not joined_sql:errors.append(dict(kind='no_native_access_sql_join'))
    return dict(passed=not errors,events=len(rows),errors=errors,
                logical_accesses=logical,cache_attempts=attempts,access_sql_calls=joined_sql)
