"""Authenticated dynamic-target ACL fixtures."""
import from jaclang.runtime.archetype { AccessLevel }
import from .ttg_fusion_walkers { FusedItem }

glob _access_calls: list[int] = [];
node CatalogGrant(FusedItem) {
    def __jac_access__ -> AccessLevel {
        _access_calls.append(1);
        return AccessLevel.READ;
    }
}

def reset_access_calls {
    _access_calls.clear();
}

def access_call_count -> int {
    return len(_access_calls);
}
