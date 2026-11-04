"""Backward access slicing of compiler-produced dependency events.

This pass never executes user code. Unknown effects and cancellation are roots,
not silently discarded statements. Shared walker fields use a whole-walker
fixed point, so writes in a sibling ability remain dependencies. Removing a
statement from this slice does NOT remove it from the native program or prove
its effects safe: the consumer must still validate its effect contract.
"""
from collections import defaultdict


def access_slice(events: list[dict], edges: list[dict]) -> dict:
    """Return an auditable backwards slice; accept serialized event records."""
    by_id = {e['id']: e for e in events}
    if len(by_id) != len(events):
        raise ValueError('Duplicate dependency event')
    incoming = defaultdict(set)
    for edge in edges:
        if edge['source'] not in by_id or edge['target'] not in by_id:
            raise ValueError('Dangling dependency edge')
        if edge['kind'] in ('data', 'control'):
            incoming[edge['target']].add(edge['source'])
    # An unsupported filtered visit is still an access root, even when the
    # existing SQL frontend represents it as a barrier.
    summarized = {e['id'] for e in events if e.get('effect', {}).get('contract') in ('node_identity', 'identity_map_write', 'fresh_output_map')}
    roots = {e['id'] for e in events if e['kind'] in ('visit', 'barrier', 'cancel') and e['id'] not in summarized}
    writes = defaultdict(set)
    for event in events:
        if event.get('writes'):
            writes[event['writes']].add(event['id'])
    live = set(roots)
    work = list(roots)
    while work:
        eid = work.pop()
        event = by_id[eid]
        dependencies = set(incoming[eid])
        if event['kind']=='barrier' and eid not in summarized:
            # An opaque call/unsupported control can observe hidden state.
            # Missing reads mean unknown, never an empty read set.
            dependencies.update(e['id'] for e in events if e.get('writes') and
                (e['writes'].startswith('self.') or e.get('ability')==event.get('ability')))
        for key in event.get('reads', ()):
            # All possible writers, including later iterations and siblings.
            # Local reads use reaching-definition edges instead.
            if key.startswith('self.'):
                dependencies.update(writes[key])
        for other in dependencies - live:
            live.add(other)
            work.append(other)
    relevant_fields = sorted({key for eid in live for key in by_id[eid].get('reads', ())
                              if key.startswith('self.')})
    removable = {'assign', 'scalar_update', 'append', 'output', 'branch'}
    ignored = sorted(e['id'] for e in events if e['id'] not in live and (e['kind'] in removable or e['id'] in summarized))
    return dict(version=1, roots=sorted(roots), relevant=sorted(live),
                output_only=ignored, shared_access_reads=relevant_fields,
                unresolved_effects=sorted(e['id'] for e in events if e['kind']=='barrier' and e['id'] not in summarized),
                conditional_contracts={str(e['id']):e['effect'] for e in events if e['id'] in summarized},
                contract='Output-only is a dependency fact, not an effect-safety proof; retain native execution and validate descriptors, aliases and exceptions before predictive use.')
