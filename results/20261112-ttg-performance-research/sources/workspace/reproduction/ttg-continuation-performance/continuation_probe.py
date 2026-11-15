"""Experiment-only direct-boundary sink, imported automatically in every child.

No Jac imports and no runtime plugin discovery. PgWire's disclosed source patch
imports this module. Child exec inherits an explicit environment from the
disclosed ProcessReader patch. Per-process buffers serialize after response
controls (parent) or at natural process exit (child); no shared JSONL writers.
"""
import atexit
import dataclasses
from contextlib import contextmanager
import contextvars
import hashlib
import json
import os
from pathlib import Path
import struct
import threading
import time
from uuid import UUID

ENABLED=bool(os.environ.get('TTG_PERF_DIR'))
ENV_KEYS=('TTG_PERF_DIR','TTG_PERF_CELL_ID','TTG_PERF_TRIAL_ID',
    'TTG_PERF_SERVER_GENERATION','TTG_PERF_CLOCK_DOMAIN','TTG_PERF_POSTGRES_INSTANCE_ID')
if ENABLED:
    for key in ENV_KEYS:
        if not os.environ.get(key): raise RuntimeError('Missing observer environment: '+key)
BASE={key:os.environ.get(key) for key in ENV_KEYS}
PID=os.getpid()
IS_CHILD=os.environ.get('TTG_PERF_OBSERVER_CHILD')=='1'
PARENT_PID=int(os.environ.get('TTG_PERF_PARENT_PID') or PID)
REQUEST=contextvars.ContextVar('continuation_perf_request',default=None)
DEFAULT=(os.environ.get('TTG_PERF_REQUEST_ID') or None,
    'background_prefetch' if IS_CHILD else 'foreground', 'process' if IS_CHILD else 'none')
LOCK=threading.RLock()
CALLS=[]
EVENTS=[]
CONNECTIONS={}
WORKERS=[]


def binding():
    return REQUEST.get() or getattr(threading.current_thread(),'_ttg_perf_binding',None) or DEFAULT


@contextmanager
def request_scope(origin_request_id):
    if not origin_request_id: raise ValueError('Explicit request ID required')
    token=REQUEST.set((origin_request_id,'foreground','none'))
    try: yield
    finally: REQUEST.reset(token)


def bind_worker_thread(thread,executor='thread'):
    """Called by explicit prefetch source patch before native Thread.start."""
    origin,_,_=binding()
    thread._ttg_perf_binding=(origin,'background_prefetch',executor)
    with LOCK: WORKERS.append(thread)


def child_environment():
    """Popen environment only; IPC protocol/payload and scheduling stay native."""
    result=os.environ.copy()
    origin,_,_=binding()
    if ENABLED and not origin:
        raise ValueError('Cannot spawn a measured child without an origin request')
    result.update({key:value for key,value in BASE.items() if value is not None})
    result['TTG_PERF_REQUEST_ID']=origin or ''
    result['TTG_PERF_OBSERVER_CHILD']='1'
    result['TTG_PERF_PARENT_PID']=str(PID)
    return result


def connected(connection,backend_process_pid):
    """Only BackendKeyData's first four bytes reach here, never its secret."""
    if not ENABLED: return
    if type(backend_process_pid) is not int or backend_process_pid<=0:
        raise ValueError('Invalid actual PostgreSQL backend PID')
    metadata=(backend_process_pid,str(connection.database),str(connection.application_name))
    with LOCK:
        CONNECTIONS[id(connection)]=metadata
        EVENTS.append(('connection',time.perf_counter_ns(),binding(),id(connection),metadata))


def event(kind,**fields):
    if ENABLED:
        with LOCK:
            EVENTS.append(dict(**_identity(binding()),kind=kind,
                timestamp_ns=time.perf_counter_ns(),**fields))


def _json_default(value):
    if isinstance(value,UUID): return str(value)
    if isinstance(value,set): return {'__observed_set__':list(value)}
    if dataclasses.is_dataclass(value) and type(value).__name__ in (
            'PrefetchFeatures','PrefetchAdmission','PrefetchOutcome'):
        return dataclasses.asdict(value)
    raise TypeError('Unserializable observation: '+type(value).__name__)


def record_boundary(connection,sql,original_sql,origin,thread_id,start_ns,send_ns,
        ready_ns,end_ns,commands,rows,row_bytes,errors,ready_messages,returned_rows,error,packet,sent):
    """Called only AFTER direct driver_end clock, including expected-error Z."""
    if not ENABLED: return
    metadata=CONNECTIONS.get(id(connection))
    if metadata is None: raise ValueError('SQL connection lacks observed BackendKeyData')
    with LOCK:
        CALLS.append((metadata,id(connection),sql,original_sql,origin,thread_id,
            start_ns,send_ns,ready_ns,end_ns,commands,rows,row_bytes,errors,
            ready_messages,returned_rows,error,packet,sent))


def _identity(origin):
    request,role,executor=origin
    return dict(cell_id=BASE['TTG_PERF_CELL_ID'],trial_id=BASE['TTG_PERF_TRIAL_ID'],
        server_generation=BASE['TTG_PERF_SERVER_GENERATION'],
        postgres_instance_id=BASE['TTG_PERF_POSTGRES_INSTANCE_ID'],
        clock_domain=BASE['TTG_PERF_CLOCK_DOMAIN'],origin_request_id=request,
        client_process_pid=PID,parent_process_pid=PARENT_PID,role=role,actual_executor=executor)


def _packet(packet):
    if packet is None: return dict(frontend_types=[],sync_messages=0,sent_bytes=0)
    kinds=[];cursor=0
    while cursor<len(packet):
        if len(packet)-cursor<5: raise ValueError('Truncated recorded frontend packet')
        size=struct.unpack('!I',packet[cursor+1:cursor+5])[0]
        if size<4 or cursor+1+size>len(packet): raise ValueError('Invalid recorded frontend packet')
        kinds.append(chr(packet[cursor]));cursor+=1+size
    return dict(frontend_types=kinds,sync_messages=kinds.count('S'),sent_bytes=len(packet))


def flush():
    """Explicit parent control / natural child exit; no per-recv callbacks."""
    if not ENABLED: return dict(calls=0,events=0)
    with LOCK:
        pending=list(CALLS);events=list(EVENTS)
        root=Path(BASE['TTG_PERF_DIR'])
        root.mkdir(parents=True,exist_ok=True)
        prefix=f"server-{BASE['TTG_PERF_SERVER_GENERATION']}-process-{PID}"
        if pending:
            with (root/(prefix+'.calls.jsonl')).open('a') as file:
                for raw in pending:
                    (metadata,connection,sql,original_sql,origin,thread_id,start,send,ready,end,
                        commands,rows,row_bytes,errors,ready_messages,returned_rows,error,packet,sent)=raw
                    backend,database,label=metadata
                    wire=_packet(packet)
                    record=dict(**_identity(origin),connection=connection,backend_pid=backend,
                        database=database,application_name=label,sql=sql,original_sql=original_sql,
                        sql_sha256=hashlib.sha256(sql.encode()).hexdigest(),thread_id=thread_id,
                        driver_start_ns=start,driver_end_ns=end,send_ns=send,ready_ns=ready,
                        command_complete=commands,data_rows=rows,data_row_payload_bytes=row_bytes,
                        error_messages=errors,ready_messages=ready_messages,returned_rows=returned_rows,
                        error=error,sendall_returned=sent,frontend=wire,
                        protocol_mode='extended_single_statement',recv_calls=None,received_bytes=None,
                        measurement='direct_send_to_Z_protocol_completion_wall')
                    file.write(json.dumps(record,separators=(',',':'))+'\n')
        if events:
            with (root/(prefix+'.events.jsonl')).open('a') as file:
                for item in events:
                    if isinstance(item,dict):
                        file.write(json.dumps(item,default=_json_default,separators=(',',':'))+'\n')
                        continue
                    kind,stamp,origin,connection,metadata=item
                    backend,database,label=metadata
                    file.write(json.dumps(dict(**_identity(origin),kind=kind,timestamp_ns=stamp,
                        connection=connection,backend_pid=backend,database=database,
                        application_name=label),separators=(',',':'))+'\n')
        del CALLS[:len(pending)];del EVENTS[:len(events)]
    return dict(calls=len(pending),events=len(events),client_process_pid=PID)


def drain_after_response(origin_request_id,timeout_seconds=30):
    """Observe natural completion first; explicitly join only after HTTP ends."""
    started=time.perf_counter_ns();deadline=time.monotonic()+timeout_seconds
    with LOCK: workers=[t for t in WORKERS if t._ttg_perf_binding[0]==origin_request_id]
    for worker in workers: worker.join(max(0,deadline-time.monotonic()))
    pending=sum(t.is_alive() for t in workers)
    result=dict(origin_request_id=origin_request_id,start_ns=started,end_ns=time.perf_counter_ns(),
        observed_threads=len(workers),pending=pending,flush=flush())
    with LOCK: WORKERS[:]=[t for t in WORKERS if t.is_alive()]
    if pending: raise TimeoutError('Unfinished late prefetch work')
    return result


atexit.register(flush)
