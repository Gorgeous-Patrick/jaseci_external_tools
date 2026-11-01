"""Complete cache publication, overflow and retained abstract type facts."""
import from threading { RLock }
import from unittest.mock { patch }
import from jaclang.runtime.runtime { JacRuntimeInterface }
import from uuid { UUID }
import from jaclang.runtime.ttg_fusion { resolve_fused_region, certify_fused_region }
import from jaclang.runtime.ttg_dependencies { analyze_walker_dependencies }
import from .fixtures.ttg_fusion_walkers { FusedItem, FusedWalk, FusedSum }

obj CapturedStore {
    has promotions: dict = {},
        result: list = [];

    def rows(sql: str, params: dict) -> list {
        return self.result;
    }
}

obj CapturedMemory {
    has store: any,
        published: list = [],
        _lock: any = RLock();

    def read_barrier { }
    def query_cache_put(key: any, value: any) {
        self.published.append((key, value));
    }
}


def fake_resolution(rows: list, budget: int = 20) -> tuple {
    graph = analyze_walker_dependencies(FusedWalk);
    event = next(
        e
        for e in graph.events
        if e.kind == 'visit'
    );
    memory: any = CapturedMemory(store=CapturedStore(result=rows));
    metrics = {
        'queries': 0,
        'overflow': 0,
        'cache_paths': 0,
        'cache_empty_paths': 0,
        'regions': []
    };
    active = {
        'id': UUID(int=1),
        'node_type': FusedItem,
        'transition_state': {
            'self.visited': 1,
            'self.limit': 20,
            'walk::here.value': 0
        },
        'transition_pending': []
    };
    with patch.object(JacRuntimeInterface, 'get_context', return_value=None) {
        result = resolve_fused_region(
            memory, FusedWalk(), graph, active, event, None, budget, metrics
        );
    }
    return (result, memory.published, metrics);
}


test "Overflow rejects the entire region before any cache publication" {
    (result, published, metrics) = fake_resolution([(), (), ()], 2);
    assert result is None;
    assert published == [];
    assert metrics['overflow'] == 1;
    assert metrics['cache_paths'] == 0;
}


test "Empty marker publishes both exact empty native and typed path caches" {
    (result, published, metrics) = fake_resolution(
        [(0, 0, UUID(int=1), None, None, None, None, None, None)]
    );
    assert len(result) == 1;
    assert len(published) == 2;
    assert any(value == ((), ()) for (key, value) in published);
    assert metrics['cache_empty_paths'] == 1;
}


test "Incomplete positive cardinality cannot publish a partial native path" {
    graph = analyze_walker_dependencies(FusedWalk);
    event = next(
        e
        for e in graph.events
        if e.kind == 'visit'
    );
    memory: any = CapturedMemory(
        store=CapturedStore(
            result=[
                (
                    0,
                    0,
                    UUID(int=1),
                    UUID(int=2),
                    UUID(int=12),
                    'FusedItem',
                    FusedItem.__module__,
                    1,
                    2
                )
            ]
        )
    );
    metrics = {
        'queries': 0,
        'overflow': 0,
        'cache_paths': 0,
        'cache_empty_paths': 0,
        'regions': []
    };
    active = {
        'id': UUID(int=1),
        'node_type': FusedItem,
        'transition_state': {'self.visited': 1, 'self.limit': 20},
        'transition_pending': []
    };
    caught = False;
    try {
        with patch.object(JacRuntimeInterface, 'get_context', return_value=None) {
            resolve_fused_region(
                memory, FusedWalk(), graph, active, event, None, 20, metrics
            );
        }
    } except ValueError {
        caught = True;
    }
    assert caught;
    assert memory.published == [];
}


test "Unknown integer accumulation is preserved in a resumed Sum certificate" {
    graph = analyze_walker_dependencies(FusedSum);
    event = next(
        e
        for e in graph.events
        if e.kind == 'visit'
    );
    active = {
        'id': UUID(int=1),
        'node_type': FusedItem,
        'transition_unknown_integers': {'self.total'}
    };
    region = certify_fused_region(
        graph, active, event.id, {}, [], 8, resume_event=event.id
    );
    assert region['kind'] == 'linear' , str(region);
    assert region['max_origins'] >= 8;
    assert any(
        'self.total' in t['unknown_integers'] for t in region['transition_trace']
    );
}
