import from collections { OrderedDict }
import from threading { RLock }
import from jaclang.runtime.ttg_prefetch_model { PrefetchFeatures, PrefetchOutcome }

obj PrefetchFeatureProvider {
    def estimate(context: PrefetchFeatures) -> PrefetchFeatures abst;
    def observe(outcome: PrefetchOutcome) { }
    def record_entry(ability_key: str) { }
    def record_visit(ability_key: str, site_key: str) { }
}

obj SiteMeasurements {
    has opportunities: int = 0,
        demanded: int = 0,
        resolution_count: int = 0,
        resolution_sum: float = 0.0,
        payload_count: int = 0,
        payload_sum: float = 0.0,
        overlap_count: int = 0,
        overlap_sum: float = 0.0,
        nodes_count: int = 0,
        nodes_sum: float = 0.0;
}

obj OnlinePrefetchProfile(PrefetchFeatureProvider) {
    has capacity: int = 2048,
        sites: any = OrderedDict(),
        branches: any = OrderedDict(),
        lock: any = RLock();

    def _site(key: str) -> SiteMeasurements {
        if key not in self.sites {
            self.sites[key] = SiteMeasurements();
        }
        self.sites.move_to_end(key);
        while len(self.sites) > self.capacity {
            self.sites.popitem(last=False);
        }
        return self.sites[key];
    }

    def _branch(key: str) -> dict {
        if key not in self.branches {
            self.branches[key] = {'entries': 0, 'visits': {}};
        }
        self.branches.move_to_end(key);
        while len(self.branches) > self.capacity {
            self.branches.popitem(last=False);
        }
        return self.branches[key];
    }

    def record_entry(ability_key: str) {
        with self.lock {
            branch = self._branch(ability_key);
            branch['entries'] += 1;
        }
    }

    def record_visit(ability_key: str, site_key: str) {
        with self.lock {
            branch = self._branch(ability_key);
            branch['visits'][site_key] = branch['visits'].get(site_key, 0) + 1;
        }
    }

    def observe(outcome: PrefetchOutcome) {
        with self.lock {
            stats = self._site(outcome.site_key);
            stats.opportunities += 1;
            stats.demanded += int(outcome.demanded);
            if outcome.resolution_ms is not None {
                stats.resolution_count += 1;
                stats.resolution_sum += outcome.resolution_ms;
            }
            if outcome.payload_ms is not None {
                stats.payload_count += 1;
                stats.payload_sum += outcome.payload_ms;
            }
            if outcome.overlap_ms is not None {
                stats.overlap_count += 1;
                stats.overlap_sum += outcome.overlap_ms;
            }
            if outcome.resolved_nodes is not None {
                stats.nodes_count += 1;
                stats.nodes_sum += outcome.resolved_nodes;
            }
        }
    }

    def estimate(context: PrefetchFeatures) -> PrefetchFeatures {
        with self.lock {
            stats = self.sites.get(context.site_key);
            branch = self.branches.get(context.ability_key);
            if branch is not None and branch['entries'] > 0 {
                context.branch_frequency = branch['visits'].get(context.site_key, 0)
                    / branch['entries'];
            }
            if stats is None {
                return context;
            }
            context.opportunities = stats.opportunities;
            context.use_probability = (stats.demanded + 1.0)
                / (stats.opportunities + 2.0);
            context.samples = min(
                stats.resolution_count, stats.payload_count, stats.overlap_count
            );
            if stats.resolution_count {
                context.resolution_ms = stats.resolution_sum / stats.resolution_count;
            }
            if stats.payload_count {
                context.payload_ms = stats.payload_sum / stats.payload_count;
            }
            if stats.overlap_count {
                context.overlap_ms = stats.overlap_sum / stats.overlap_count;
            }
            if stats.nodes_count {
                context.estimated_nodes = stats.nodes_sum / stats.nodes_count;
            }
            return context;
        }
    }

    def clear {
        with self.lock {
            self.sites.clear();
            self.branches.clear();
        }
    }
}

glob default_prefetch_profile = OnlinePrefetchProfile();
