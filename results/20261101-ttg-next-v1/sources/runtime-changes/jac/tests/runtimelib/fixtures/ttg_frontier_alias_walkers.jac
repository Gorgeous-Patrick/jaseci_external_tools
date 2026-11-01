"""Alias spellings are not persisted archetype names."""
import from .ttg_frontier_walkers {
    FrontierBranch,
    FrontierRight as LinkAlias,
    FrontierLeaf as TargetAlias
}

walker FrontierAlias {
    can branch with FrontierBranch entry {
        visit [->:LinkAlias:->[?:TargetAlias]];
    }

    can leaf with TargetAlias entry {
        report here.value;
    }
}
