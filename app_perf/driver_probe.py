"""In-memory PgWire/socket observer. Never edits the runtime under test.

SQL and request traces are serialized only after request dispatch and context close.
Instrumentation callbacks do add CPU overhead; overhead controls are mandatory.
"""
from __future__ import annotations
import contextvars
from dataclasses import asdict, is_dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import threading
import time

REQUEST = contextvars.ContextVar('perf_request', default=None)
CALL = threading.local()
ROWS = []
BOUNDARIES = []
EVENTS = []
LOCK = threading.Lock()
THREADS = []
OUT = Path(os.environ['TTG_PERF_TRACE'])
ENABLED = os.environ.get('TTG_PERF_DRIVER', '1') == '1'
DETAIL = os.environ.get('TTG_PERF_DETAIL', 'detailed') == 'detailed'


def record_boundary(sql, rid, role, thread_id, connection, start_ns, send_ns,
                    ready_ns, end_ns, commands, data_rows, returned_rows, error, frame, sent):
    """Called by disclosed source overlay only AFTER its end clock."""
    with LOCK:
        BOUNDARIES.append((sql, rid, role, thread_id, connection, start_ns, send_ns,
            ready_ns, end_ns, commands, data_rows, returned_rows, error, frame, sent))


def expand_boundary(raw):
    (sql, rid, role, thread_id, connection, start_ns, send_ns, ready_ns, end_ns,
        commands, data_rows, returned_rows, error, frame, sent) = raw
    outgoing, sync = [], 0
    cursor = 0
    if frame is not None:
        while cursor + 5 <= len(frame):
            kind = chr(frame[cursor])
            size = int.from_bytes(frame[cursor + 1:cursor + 5], 'big')
            outgoing.append(kind)
            sync += int(kind == 'S')
            cursor += 1 + size
    row = dict(request=rid, connection=connection, thread_id=thread_id,
        role=role, sql=sql, driver_start_ns=start_ns, driver_end_ns=end_ns,
        send_ns=send_ns, ready_ns=ready_ns, send_calls=int(frame is not None),
        recv_calls=None, sync_sent=sync if sent else 0, ready_count=int(ready_ns is not None),
        command_complete=commands, data_rows=data_rows, returned_rows=returned_rows,
        data_row_payload_bytes=None, sent_bytes=len(frame) if sent else None,
        received_bytes=None, outgoing_types=outgoing, command_tags_raw=[], error=error,
        detail_mode='direct_boundary')
    return row


def wrap_close(original):
    """Observe natural close; never wait, reorder or repair runtime behavior."""
    def close(self, *args, **kwargs):
        threads = list(getattr(self.mem, '_prefetch_threads', []))
        before = sum(t.is_alive() for t in threads)
        started = time.perf_counter_ns()
        try:
            return original(self, *args, **kwargs)
        finally:
            EVENTS.append(dict(kind='context_closed', request=request_id(),
                start_ns=started, end_ns=time.perf_counter_ns(), pending_before=before,
                pending_after=sum(t.is_alive() for t in threads)))
    return close


def drain_request(rid, timeout=30):
    """Explicit harness control after application HTTP completion, outside its time."""
    started = time.perf_counter_ns()
    with LOCK:
        threads = [t for t in THREADS if getattr(t, '_perf_request', None) == rid]
    deadline = time.monotonic() + timeout
    for thread in threads:
        thread.join(max(0, deadline - time.monotonic()))
    remaining = sum(t.is_alive() for t in threads)
    EVENTS.append(dict(kind='post_response_drain', request=rid, start_ns=started,
        end_ns=time.perf_counter_ns(), observed_threads=len(threads), pending=remaining))
    with LOCK:
        THREADS[:] = [t for t in THREADS if t.is_alive()]
    flush()
    return {'request': rid, 'pending': remaining, 'observed_threads': len(threads)}


def request_id():
    return REQUEST.get() or getattr(threading.current_thread(), '_perf_request', None)


def simplify(value):
    if is_dataclass(value):
        return simplify(asdict(value))
    if isinstance(value, dict):
        return {str(k): simplify(v) for k, v in value.items() if k != 'walker'}
    if isinstance(value, (list, tuple, set)):
        return [simplify(v) for v in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


class SocketObserver:
    def __init__(self, sock):
        self.sock = sock
        if not DETAIL:
            # Bind the real recv directly: light mode has no per-recv callback.
            self.recv = sock.recv

    def __getattr__(self, name):
        return getattr(self.sock, name)

    def sendall(self, data, *args, **kwargs):
        row = getattr(CALL, 'row', None)
        if row is not None:
            row['send_calls'] += 1
            row['sent_bytes'] += len(data)
            # Parse actual outgoing framed messages; do not infer RTTs from SQL.
            cursor = 0
            while cursor + 5 <= len(data):
                kind = chr(data[cursor])
                length = int.from_bytes(data[cursor + 1:cursor + 5], 'big')
                row['outgoing_types'].append(kind)
                row['sync_sent'] += int(kind == 'S')
                cursor += 1 + length
            # Metadata parsing is outside the protocol wall-time interval.
            if row['send_ns'] is None:
                row['send_ns'] = time.perf_counter_ns()
        return self.sock.sendall(data, *args, **kwargs)

    def recv(self, *args, **kwargs):
        data = self.sock.recv(*args, **kwargs)
        row = getattr(CALL, 'row', None)
        if row is not None:
            row['received_bytes'] += len(data)
            row['recv_calls'] += 1
        return data


def flush():
    with LOCK:
        calls, events, boundaries = list(ROWS), list(EVENTS), list(BOUNDARIES)
        ROWS.clear()
        EVENTS.clear()
        BOUNDARIES.clear()
    calls.extend(expand_boundary(row) for row in boundaries)
    if calls:
        with OUT.open('a') as file:
            for row in calls:
                sql = row['sql']
                row['sql_sha256'] = hashlib.sha256(sql.encode()).hexdigest()
                normalized = re.sub(r"'(?:''|[^'])*'", '?', sql)
                normalized = re.sub(r'\b\d+\b', '?', normalized)
                row['fingerprint'] = re.sub(r'\s+', ' ', normalized).strip()
                command = sql.lstrip().split(None, 1)[0].upper() if sql.strip() else ''
                row['command'] = command
                row['control'] = command in {'BEGIN', 'SET', 'SAVEPOINT', 'RELEASE', 'DISCARD', 'COMMIT', 'ROLLBACK', 'RESET', 'START', 'END'}
                row['command_tags'] = [tag.rstrip(b'\0').decode(errors='replace') for tag in row.pop('command_tags_raw', [])]
                file.write(json.dumps(row) + '\n')
    if events:
        with OUT.with_suffix('.events.jsonl').open('a') as file:
            for row in events:
                file.write(json.dumps(simplify(row)) + '\n')


def install():
    from jaclang.data.pgwire import PgWireConnection
    from jaclang.server.serving.app import ServingApp
    from jaclang.runtime.context import ExecutionContext
    from jaclang.runtime import ttg_dependency_prefetch as dependency
    from jaclang.runtime import ttg_prefetch_profile as profile
    from jaclang.runtime import ttg_checkpoints as checkpoints

    old_thread_start = threading.Thread.start
    def start_thread(self, *args, **kwargs):
        self._perf_request = request_id()
        target_name = getattr(self._target, '__name__', '')
        self._perf_role = 'background_prefetch' if target_name == '_prefetch_worker' else 'foreground'
        result = old_thread_start(self, *args, **kwargs)
        if target_name in ('_prefetch_worker', '_signal_done_after_all'):
            with LOCK:
                THREADS.append(self)
        return result
    threading.Thread.start = start_thread

    if ENABLED:
        old_connect = PgWireConnection._connect_socket
        def connect(self, *args, **kwargs):
            result = old_connect(self, *args, **kwargs)
            self._sock = SocketObserver(self._sock)
            return result
        PgWireConnection._connect_socket = connect
        old_run = PgWireConnection.run
        def run(self, sql, **params):
            row = dict(request=request_id(), connection=id(self), thread_id=threading.get_ident(),
                thread=threading.current_thread().name,
                role=getattr(threading.current_thread(), '_perf_role', 'foreground'), sql=sql,
                driver_start_ns=0, driver_end_ns=None, send_ns=None, ready_ns=None,
                send_calls=0, recv_calls=0, sync_sent=0, ready_count=0, command_complete=0,
                data_rows=0, data_row_payload_bytes=0, sent_bytes=0, received_bytes=0,
                outgoing_types=[], command_tags_raw=[], returned_rows=None, error=None,
                detail_mode='detailed' if DETAIL else 'light')
            if not DETAIL:
                row.update(recv_calls=None, received_bytes=None, data_rows=None, data_row_payload_bytes=None)
            previous = getattr(CALL, 'row', None)
            CALL.row = row
            row['driver_start_ns'] = time.perf_counter_ns()
            try:
                result = old_run(self, sql, **params)
                row['driver_end_ns'] = time.perf_counter_ns()
                row['returned_rows'] = len(result)
                return result
            except Exception as error:
                row['driver_end_ns'] = time.perf_counter_ns()
                row['error'] = f'{type(error).__name__}: {error}'
                raise
            finally:
                CALL.row = previous
                with LOCK:
                    ROWS.append(row)
        PgWireConnection.run = run
        old_read = PgWireConnection._read_message
        def read(self, *args, **kwargs):
            result = old_read(self, *args, **kwargs)
            row = getattr(CALL, 'row', None)
            if row is not None:
                kind, payload = result
                if kind == 'Z':
                    row['ready_ns'] = time.perf_counter_ns()
                    row['ready_count'] += 1
                elif kind == 'C':
                    row['command_complete'] += 1
                    row['command_tags_raw'].append(payload)
                elif kind == 'D' and DETAIL:
                    row['data_rows'] += 1
                    row['data_row_payload_bytes'] += len(payload)
            return result
        PgWireConnection._read_message = read

    ExecutionContext.close = wrap_close(ExecutionContext.close)

    old_finish = dependency.finish_prefetch_feedback
    def finish(state):
        result = old_finish(state)
        capture = checkpoints._capture.get()
        EVENTS.append(dict(kind='dependency', request=request_id(), at_ns=time.perf_counter_ns(),
            summary=state.summary(), checkpoints=list(capture.records) if capture else [],
            hits=list(capture.hits) if capture else []))
        return result
    if DETAIL:
        dependency.finish_prefetch_feedback = finish

    old_dispatch = ServingApp.dispatch
    async def dispatch(self, request):
        if str(request.url.path) == '/__ttg_perf/drain':
            from jaclang.server.serving.datatypes import JSONResponse
            result = drain_request(request.headers.get('X-TTG-Perf-Drain-Request'))
            return JSONResponse(content=result)
        rid = request.headers.get('X-TTG-Perf-Request') or 'untracked'
        token = REQUEST.set(rid)
        if request.headers.get('X-TTG-Perf-Reset-Profile') == '1':
            profile.default_prefetch_profile.clear()
        started = time.perf_counter_ns()
        try:
            return await old_dispatch(self, request)
        finally:
            EVENTS.append(dict(kind='request_complete', request=rid, path=str(request.url.path),
                start_ns=started, end_ns=time.perf_counter_ns()))
            REQUEST.reset(token)
            # Harness drain control serializes AFTER HTTP response completion.
    ServingApp.dispatch = dispatch
