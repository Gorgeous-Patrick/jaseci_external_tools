"""Observe natural lifecycle; explicit draining is a post-response control step."""
from dataclasses import dataclass
import time


@dataclass
class WorkerHandle:
    origin_request_id: str
    alive: object
    join: object
    client_process_pid: int | None = None


class Observer:
    def __init__(self):
        self.workers = []
        self.events = []

    def register(self, handle):
        self.workers.append(handle)

    def natural_close(self, original_close, *args, **kwargs):
        # Never join, drain, flush SQL metadata, or repair native ordering here.
        before = sum(bool(w.alive()) for w in self.workers)
        try:
            return original_close(*args, **kwargs)
        finally:
            self.events.append(dict(kind='native_close_observed',
                timestamp_ns=time.perf_counter_ns(), pending_before=before,
                pending_after=sum(bool(w.alive()) for w in self.workers)))

    def drain_after_response(self, response_end_ns, timeout_seconds=10):
        start = time.perf_counter_ns()
        if start < response_end_ns:
            raise ValueError('Drain cannot precede native response completion')
        deadline = time.monotonic() + timeout_seconds
        for worker in self.workers:
            worker.join(max(0, deadline - time.monotonic()))
        pending = [w.origin_request_id for w in self.workers if w.alive()]
        event = dict(kind='explicit_post_response_drain', start_ns=start,
            end_ns=time.perf_counter_ns(), response_end_ns=response_end_ns,
            pending_origins=pending, passed=not pending)
        self.events.append(event)
        if pending:
            raise TimeoutError('Late workers remain: ' + repr(pending))
        return event
