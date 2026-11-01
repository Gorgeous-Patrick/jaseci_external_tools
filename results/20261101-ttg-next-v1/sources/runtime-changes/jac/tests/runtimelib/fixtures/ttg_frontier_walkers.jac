"""Queue fixtures with state-dependent paths and an opaque source ability."""
node FrontierStart {}
node FrontierBranch {
    has value: int = 0;
}

node FrontierLeaf {
    has value: int = 0;
}

node FrontierDerivedLeaf(FrontierLeaf) {}

edge FrontierQueue {}
edge FrontierLeft {}
edge FrontierRight {}

walker FrontierWalk {
    has i: int = 0;

    def reset_counter -> None {
        self.i = 0;
    }

    can start with FrontierStart entry {
        visit [->:FrontierQueue:->[?:FrontierBranch]];
        self.reset_counter();
    }

    can branch with FrontierBranch entry {
        self.i += 1;
        if self.i == 1 {
            visit [->:FrontierLeft:->[?:FrontierLeaf]];
        } else {
            visit [->:FrontierRight:->[?:FrontierLeaf]];
        }
    }

    can leaf with FrontierLeaf entry {
        report here.value;
    }
}

walker FrontierCancel {
    has entered: list[int] = [];

    can start with FrontierStart entry {
        visit [->:FrontierQueue:->[?:FrontierBranch]];
    }

    can branch with FrontierBranch entry {
        self.entered.append(here.value);
        if here.value == 1 {
            disengage;
        }
        visit [->:FrontierRight:->[?:FrontierLeaf]];
    }

    can leaf with FrontierLeaf entry {
        report here.value;
    }
}

walker FrontierDuplicate {
    can branch with FrontierBranch entry {
        visit [->:FrontierRight:->[?:FrontierLeaf]];
        visit [->:FrontierRight:->[?:FrontierLeaf]];
    }

    can leaf with FrontierLeaf entry {
        report here.value;
    }
}

walker FrontierNoVisit {
    has i: int = 0;

    can start with FrontierStart entry {
        self.i += 1;
    }

    can branch with FrontierBranch entry {
        self.i += 1;
        if self.i == 2 {
            visit [->:FrontierLeft:->[?:FrontierLeaf]];
        } else {
            visit [->:FrontierRight:->[?:FrontierLeaf]];
        }
    }

    can leaf with FrontierLeaf entry { }
}
