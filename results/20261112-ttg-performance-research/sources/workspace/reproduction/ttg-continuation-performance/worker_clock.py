"""Direct same-thread CPU/wall counters; no custom-timer cProfile statistics.

Diagnostic-only until controlled validation on the final interpreter/runtime.
"""
import os
import sys
import sysconfig
import threading
import time


def interpreter_state():
    enabled = getattr(sys, '_is_gil_enabled', None)
    return dict(executable=sys.executable, version=sys.version,
        py_gil_disabled_build=sysconfig.get_config_var('Py_GIL_DISABLED'),
        gil_enabled=enabled() if enabled else None,
        wall_clock=time.get_clock_info('perf_counter').implementation,
        thread_cpu_clock=time.get_clock_info('thread_time').implementation,
        pid=os.getpid())


class WorkerClock:
    def __init__(self, role, origin_request_id):
        self.role = role
        self.origin_request_id = origin_request_id

    def __enter__(self):
        self.pid = os.getpid()
        self.thread = threading.get_ident()
        self.native_thread = threading.get_native_id()
        self.wall_start = time.perf_counter_ns()
        self.cpu_start = time.thread_time_ns()
        return self

    def __exit__(self, error_type, error, traceback):
        cpu_end = time.thread_time_ns()
        wall_end = time.perf_counter_ns()
        if os.getpid() != self.pid or threading.get_ident() != self.thread:
            raise ValueError('CPU scope ended in another process/thread')
        cpu_ns, wall_ns = cpu_end - self.cpu_start, wall_end - self.wall_start
        if cpu_ns < 0 or wall_ns < 0 or cpu_ns > wall_ns:
            raise ValueError('Invalid direct CPU/wall counter relationship')
        self.result = dict(role=self.role, origin_request_id=self.origin_request_id,
            client_process_pid=self.pid, thread_ident=self.thread, native_thread_id=self.native_thread,
            start_ns=self.wall_start, end_ns=wall_end, wall_ns=wall_ns,
            thread_cpu_ns=cpu_ns, error_type=error_type.__name__ if error_type else None,
            scope='Direct elapsed CPU on the same callback thread; excludes other threads and is not DB execution time')
        return False
