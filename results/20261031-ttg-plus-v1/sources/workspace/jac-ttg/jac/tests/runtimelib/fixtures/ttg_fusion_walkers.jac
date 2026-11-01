"""Semantic fusion fixtures independent of benchmark/schema identities."""
node FusedItem {
    has value: int = 0;
}

edge FusedNext {}
edge FusedLeft {}
edge FusedRight {}
node FusedHub {}
node FusedLeaf {
    has value: int = 0;

    def render -> int {
        return self.value;
    }
}

walker FusedWalk {
    has visited: int = 0,
        limit: int = 20;

    can walk with FusedItem entry {
        self.visited += 1;
        report here.value;
        if self.visited >= self.limit {
            disengage;
        }
        visit [->:FusedNext:->];
    }
}

walker FusedBatch {
    has seen: list[int] = [];

    can collect with FusedHub entry {
        visit [->:FusedLeft:->[?:FusedLeaf]];
        visit [->:FusedRight:->[?:FusedLeaf]];
    }

    can gather with FusedLeaf entry {
        self.seen.append(here.render());
    }
}

walker FusedSum {
    has total: int = 0;

    can walk with FusedItem entry {
        self.total += here.value;
        visit [->:FusedNext:->];
    }
}

walker FusedFind {
    has visited: int = 0,
        target: int = 2;

    can walk with FusedItem entry {
        self.visited += 1;
        if here.value == self.target {
            report here.value;
            disengage;
        }
        visit [->:FusedNext:->];
    }
}
