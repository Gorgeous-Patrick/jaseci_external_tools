import from contextlib { contextmanager }
import from contextvars { ContextVar }
import from math { isfinite }
import from threading { RLock }

obj PrefetchFeatures {
    has site_key: str,
        ability_key: str,
        phase: str,
        queue_position: int,
        remaining_budget: int,
        mode: str,
        resolved_nodes: int | None = None,
        estimated_nodes: float | None = None,
        use_probability: float | None = None,
        branch_frequency: float | None = None,
        overlap_ms: float | None = None,
        resolution_ms: float | None = None,
        payload_ms: float | None = None,
        samples: int = 0,
        opportunities: int = 0,
        probe: bool = False,
        version: int = 1;

    def to_dict -> dict {
        return {
            'version': self.version,
            'site_key': self.site_key,
            'ability_key': self.ability_key,
            'phase': self.phase,
            'queue_position': self.queue_position,
            'remaining_budget': self.remaining_budget,
            'mode': self.mode,
            'resolved_nodes': self.resolved_nodes,
            'estimated_nodes': self.estimated_nodes,
            'use_probability': self.use_probability,
            'branch_frequency': self.branch_frequency,
            'overlap_ms': self.overlap_ms,
            'resolution_ms': self.resolution_ms,
            'payload_ms': self.payload_ms,
            'samples': self.samples,
            'opportunities': self.opportunities,
            'probe': self.probe
        };
    }
}

obj PrefetchAdmission {
    has admit: bool,
        reason: str,
        score_ms: float | None = None,
        probe: bool = False;

    def to_dict -> dict {
        return {
            'admit': self.admit,
            'reason': self.reason,
            'score_ms': self.score_ms,
            'probe': self.probe
        };
    }
}

obj PrefetchOutcome {
    has site_key: str,
        ability_key: str,
        demanded: bool,
        resolution_ms: float | None = None,
        payload_ms: float | None = None,
        overlap_ms: float | None = None,
        resolved_nodes: int | None = None;

    def to_dict -> dict {
        return {
            'site_key': self.site_key,
            'ability_key': self.ability_key,
            'demanded': self.demanded,
            'resolution_ms': self.resolution_ms,
            'payload_ms': self.payload_ms,
            'overlap_ms': self.overlap_ms,
            'resolved_nodes': self.resolved_nodes
        };
    }
}

obj PrefetchDecisionModel {
    def decide(features: PrefetchFeatures) -> PrefetchAdmission abst;
    def observe(outcome: PrefetchOutcome) { }
}

obj AlwaysPrefetch(PrefetchDecisionModel) {
    def decide(features: PrefetchFeatures) -> PrefetchAdmission {
        return PrefetchAdmission(True, 'always baseline');
    }
}

obj ExpectedBenefit(PrefetchDecisionModel) {
    has min_samples: int = 3,
        margin_ms: float = 0.0,
        unused_weight: float = 1.0,
        cold_start_prefetch: bool = True,
        probe_every: int = 20;

    def decide(features: PrefetchFeatures) -> PrefetchAdmission {
        if features.version != 1 or features.phase not in ('resolve', 'load') {
            return PrefetchAdmission(False, 'unsupported feature schema or phase');
        }
        if features.mode not in ('thread', 'process') {
            return PrefetchAdmission(False, 'synchronous loading provides no overlap');
        }
        if features.probe {
            return PrefetchAdmission(True, 'continue measurement probe', probe=True);
        }
        if self.probe_every > 0
            and features.phase == 'resolve'
            and features.opportunities > 0
            and (features.opportunities + 1) % self.probe_every == 0 {
            return PrefetchAdmission(True, 'periodic measurement probe', probe=True);
        }
        if features.resolved_nodes == 0 {
            return PrefetchAdmission(False, 'empty resolved target set');
        }
        if features.opportunities >= self.min_samples
            and features.estimated_nodes == 0 {
            return PrefetchAdmission(False, 'observed target sets are empty');
        }
        values = [features.overlap_ms, features.resolution_ms, features.payload_ms];
        probability = features.use_probability;
        if features.samples < self.min_samples
            or probability is None
            or any(value is None for value in values) {
            return PrefetchAdmission(
                self.cold_start_prefetch,
                'insufficient measurements',
                probe=self.cold_start_prefetch
            );
        }
        if not isfinite(probability)
            or not 0 <= probability <= 1
            or any(
                not isfinite(value) or value < 0
                for value in values
                if value is not None
            ) {
            return PrefetchAdmission(False, 'invalid measurement values');
        }
        overlap = features.overlap_ms as float;
        payload = features.payload_ms as float;
        resolution = features.resolution_ms as float;
        benefit = probability * min(payload, overlap);
        resolution_cost = resolution if features.phase == 'resolve' else 0.0;
        unused_cost = (1.0 - probability) * payload * self.unused_weight;
        score = benefit - resolution_cost - unused_cost - self.margin_ms;
        return PrefetchAdmission(
            score > 0.0,
            'positive estimated benefit'
                if score > 0.0
                else 'estimated cost exceeds benefit',
            score_ms=score
        );
    }
}

glob _model_override: any = ContextVar(
         'ttg_prefetch_model_override', **{'default': None}
     ),
     _model_lock = RLock(),
     _model_factories: dict[str, any] = {
         'always': AlwaysPrefetch,
         'expected_benefit': ExpectedBenefit
     };

def register_prefetch_model(name: str, factory: any, replace: bool = False) {
    if not name or not callable(factory) {
        raise ValueError('Model name and callable factory are required');
    }
    with _model_lock {
        if name in _model_factories and not replace {
            raise ValueError('Prefetch model is already registered: ' + name);
        }
        _model_factories[name] = factory;
    }
}

def unregister_prefetch_model(name: str) {
    with _model_lock {
        if name in ('always', 'expected_benefit') {
            raise ValueError('Built-in model names must remain registered');
        }
        _model_factories.pop(name, None);
    }
}

def create_prefetch_model(name: str) -> PrefetchDecisionModel {
    with _model_lock {
        factory = _model_factories.get(name);
    }
    if factory is None {
        raise ValueError('Unknown prefetch decision model: ' + name);
    }
    model = factory();
    if not isinstance(model, PrefetchDecisionModel) {
        raise TypeError('Model factory must return PrefetchDecisionModel');
    }
    return model;
}

@contextmanager
def use_prefetch_model(model: PrefetchDecisionModel) -> any {
    token = _model_override.set(model);
    try {
        yield model;
    } finally {
        _model_override.reset(token);
    }
}
