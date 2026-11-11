"""Symmetric precision diagnostic. No ability replacement or new native waits.

Demand means successful foreground Session.get/batch_get outside prefetch planning.
Native OSP entries are a separate measurement, not a substitute for payload demand.
Logical props bytes are UTF-8 JSON representation bytes, NOT wire/SQL scan bytes.
"""
from contextvars import ContextVar
from functools import wraps
import json
import time
import uuid
from pathlib import Path
import continuation_probe as probe

PLANNING = ContextVar('precision_planning', default=0)
DEPTH = ContextVar('precision_demand_depth', default=0)
LOADING = ContextVar('precision_loading', default=None)


def wrap_planning(fn):
    @wraps(fn)
    def call(*args, **kwargs):
        token = PLANNING.set(PLANNING.get()+1)
        try:
            return fn(*args, **kwargs)
        finally:
            PLANNING.reset(token)
    return call


def wrap_demand(fn, batch=False):
    @wraps(fn)
    def call(mem, *args, **kwargs):
        outer = DEPTH.get() == 0
        started = time.perf_counter_ns()
        token = DEPTH.set(DEPTH.get()+1)
        try:
            result = fn(mem, *args, **kwargs)
        finally:
            DEPTH.reset(token)
        if outer and probe.binding()[1] == 'foreground':
            anchors = list(result.values()) if batch else ([] if result is None else [result])
            if anchors:
                probe.event('precision_access', session=id(mem), started_ns=started,
                    planning=bool(PLANNING.get()),
                    ids=[str(a.id) for a in anchors],
                    kinds=[type(a).__name__ for a in anchors])
        return result
    return call


def wrap_prefetch(fn):
    @wraps(fn)
    def call(mem, ids):
        values = list(ids)
        batch = str(uuid.uuid4())
        probe.event('precision_prefetch_batch', session=id(mem), batch=batch,
                    ids=[str(uid) for uid in values])
        token = LOADING.set(batch)
        try:
            return fn(mem, values)
        finally:
            probe.event('precision_prefetch_batch_end', session=id(mem), batch=batch)
            LOADING.reset(token)
    return call


def wrap_store_raw(fn):
    @wraps(fn)
    def call(mem, uid, row):
        batch = LOADING.get()
        if batch is not None:
            # A real load_full result reached this callback, including rows that
            # store_raw will discard because demand already materialized them.
            probe.event('precision_payload_returned', session=id(mem), batch=batch,
                uid=str(uid), anchor_kind=row.kind, arch_type=row.arch_type,
                props_bytes=len(json.dumps(row.props, sort_keys=True, separators=(',', ':'),
                    ensure_ascii=False).encode('utf-8')),
                already_materialized=uid in mem.__mem__)
        return fn(mem, uid, row)
    return call


def wrap_promote(fn):
    @wraps(fn)
    def call(mem, uid):
        result = fn(mem, uid)
        if result is not None:
            probe.event('precision_promotion', session=id(mem), uid=str(uid),
                planning=bool(PLANNING.get()))
        return result
    return call


def install():
    from jaclang.server.session import Session
    from jaclang.runtime import prefetch, ttg_dependency_prefetch, osp_kernel_sv

    prefetch.run_prefetch_policy = wrap_planning(prefetch.run_prefetch_policy)
    ttg_dependency_prefetch.prefetch_continuation = wrap_planning(
        ttg_dependency_prefetch.prefetch_continuation)
    Session.get = wrap_demand(Session.get)
    Session.batch_get = wrap_demand(Session.batch_get, batch=True)
    Session.prefetch = wrap_prefetch(Session.prefetch)
    Session.store_raw = wrap_store_raw(Session.store_raw)
    Session.promote_raw = wrap_promote(Session.promote_raw)
    old_entry = osp_kernel_sv._sv_noop_entry_hook

    @wraps(old_entry)
    def entry(walker, anchor):
        probe.event('precision_osp_entry', uid=str(anchor.id),
            walker=type(walker).__name__)
        return old_entry(walker, anchor)

    osp_kernel_sv._sv_noop_entry_hook = entry
    probe.event('precision_observer_installed', version=1,
        demand='Successful foreground Session.get/batch_get, excluding planning',
        payload='Every store_raw callback inside actual Session.prefetch, even discarded late rows',
        entry='Native OSP entry callback before running the node handlers')


def validate_case(directory):
    """Check complete observer delivery before sealing/dropping any case DB."""
    directory = Path(directory)
    requests = json.loads((directory/'requests.json').read_text())
    keys = {(str(r['server_generation']),r['request']) for r in requests if r['phase']=='workflow'}
    events = [json.loads(line) for path in directory.glob('server-*.events.jsonl')
              for line in path.read_text().splitlines() if line.strip()]
    assert any(e['kind']=='precision_observer_installed' for e in events)
    selected = [e for e in events if (str(e['server_generation']),e.get('origin_request_id')) in keys]
    batches = {e['batch']:e for e in selected if e['kind']=='precision_prefetch_batch'}
    ends = {e['batch']:e for e in selected if e['kind']=='precision_prefetch_batch_end'}
    assert batches and batches.keys() == ends.keys(), 'Incomplete actual prefetch batches'
    deliveries = [e for e in selected if e['kind']=='precision_payload_returned']
    for e in deliveries:
        b = batches[e['batch']]
        assert e['session']==b['session'] and e['uid'] in b['ids']
        assert e['origin_request_id']==b['origin_request_id']
        assert b['timestamp_ns']<=e['timestamp_ns']<=ends[e['batch']]['timestamp_ns']
    accesses = [e for e in selected if e['kind']=='precision_access' and not e['planning']]
    entries = [e for e in selected if e['kind']=='precision_osp_entry']
    assert deliveries and accesses and entries, 'Missing precision witness'
    result=dict(passed=True,batches=len(batches),payload_row_deliveries=len(deliveries),
                demand_access_records=len(accesses),native_osp_entry_records=len(entries))
    (directory/'precision-proof.json').write_text(json.dumps(result,indent=2)+'\n')
    return result
