"""Fail-closed GIL assertions in every actual Python process and SQL thread.

Uses the existing observer boundaries; never wraps walker abilities. Omitting
PYTHON_GIL=0 intentionally allows an incompatible extension to enable the GIL,
which is then detected instead of being forced to run unsafely without it.
"""
import atexit
import json
import os
from pathlib import Path
import sys
import sysconfig
import threading
import time

if os.environ.get('TTG_REQUIRE_GIL_OFF') == '1':
    def require_gil_off():
        try:
            assert sys.flags.optimize == 0
            assert sysconfig.get_config_var('Py_GIL_DISABLED') == 1
            assert sys._is_gil_enabled() is False
        except BaseException:
            os.write(2, b'FATAL: required free-threaded GIL-off assertion failed\n')
            os._exit(86)  # sitecustomize/import and native worker errors cannot swallow this.

    require_gil_off()
    if os.environ.get('TTG_PERF_DIR'):
        import continuation_probe as probe
        original_binding = probe.binding
        def explicit_worker_binding():
            # Free-threaded Python inherits ContextVars by default. The native
            # prefetch observer's explicit worker identity overrides that copied
            # foreground request context; request ID itself stays unchanged.
            return getattr(threading.current_thread(), '_ttg_perf_binding', None) or original_binding()
        probe.binding = explicit_worker_binding
        records = []
        lock = threading.RLock()

        def record(kind):
            require_gil_off()
            origin, role, executor = probe.binding()
            with lock:
                records.append(dict(kind=kind, pid=os.getpid(), thread_id=threading.get_ident(),
                    native_thread_id=threading.get_native_id(), gil_enabled=False,
                    Py_GIL_DISABLED=1, origin_request_id=origin, role=role,
                    actual_executor=executor, timestamp_ns=time.perf_counter_ns(),
                    server_generation=os.environ['TTG_PERF_SERVER_GENERATION']))

        record('python_startup')
        old_boundary = probe.record_boundary
        def boundary(*args, **kwargs):
            record('sql_boundary')
            return old_boundary(*args, **kwargs)
        probe.record_boundary = boundary
        old_event = probe.event
        def event(kind, **fields):
            require_gil_off()
            if kind in ('dependency_outcome', 'native_context_close', 'explicit_profile_reset'):
                record(kind)
            return old_event(kind, **fields)
        probe.event = event

        def flush():
            record('python_exit')
            path = Path(os.environ['TTG_PERF_DIR']) / ('gil-proof-' + str(os.getpid()) + '.jsonl')
            with lock:
                path.write_text(''.join(json.dumps(r) + '\n' for r in records))
        atexit.register(flush)
