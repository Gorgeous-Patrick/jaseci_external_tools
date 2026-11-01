"""FIFO continuations used by the TTG planner regression tests."""
node ContinueA {}
node ContinueB {
    has value: int = 1;
}

node ContinueC {}
node ContinueD {}

node ContinueCustom(ContinueA) {
    def __getattribute__(name: str) -> any {
        return object.__getattribute__(self, name);
    }
}

walker ContinueChain {
    has count: int = 0;

    can first with ContinueA entry {
        visit [-->[?:ContinueB]];
    }

    can second with ContinueB entry {
        self.count = self.count + 1;
        if self.count == 1 {
            visit [-->[?:ContinueC]];
        } else {
            visit [-->[?:ContinueD]];
        }
    }

    can third with ContinueC entry {
        visit [-->[?:ContinueD]];
    }

    can last with ContinueD entry { }
}

walker ContinueUnknown {
    has count: int = 0;

    can first with ContinueA entry {
        visit [-->[?:ContinueB]];
    }

    can second with ContinueB entry {
        self.count = here.value;
        if self.count > 0 {
            visit [-->[?:ContinueC]];
        }
    }

    can third with ContinueC entry {
        visit [-->[?:ContinueD]];
    }

    can last with ContinueD entry { }
}

walker ContinueCancel {
    can first with ContinueA entry {
        visit [-->[?:ContinueB]];
    }

    can second with ContinueB entry {
        disengage;
    }

    can third with ContinueC entry {
        visit [-->[?:ContinueD]];
    }
}

walker ContinueCycle {
    has count: int = 0;

    can first with ContinueA entry {
        visit [-->[?:ContinueB]];
    }

    can second with ContinueB entry {
        self.count = self.count + 1;
        if self.count < 3 {
            visit [-->[?:ContinueB]];
        }
    }
}

walker ContinueAppend {
    has seen: list[int] = [];

    can first with ContinueA entry {
        visit [-->[?:ContinueB]];
    }

    can second with ContinueB entry {
        self.seen.append(here.value);
        visit [-->[?:ContinueC]];
    }

    can third with ContinueC entry { }
}

walker ContinueSourceCancel {
    has entered: bool = False;

    can first with ContinueA entry {
        visit [-->[?:ContinueB]];
        disengage;
    }

    can second with ContinueB entry {
        self.entered = True;
    }
}

walker ContinueExit {
    can first with ContinueA entry {
        visit [-->[?:ContinueB]];
    }

    can second with ContinueB entry { }
    can leave with ContinueA exit {
        visit [-->[?:ContinueC]];
    }
}

node AnalyzeItem {
    has value: int = 0;
}

edge AnalyzeNext {}

walker AnalyzeTraverse {
    has visited: int = 0;

    can walk with AnalyzeItem entry {
        self.visited += 1;
        report here.value;
        if self.visited >= 4 {
            disengage;
        }
        visit [->:AnalyzeNext:->];
    }
}

walker AnalyzeSum {
    has total: int = 0;

    can walk with AnalyzeItem entry {
        self.total += here.value;
        visit [->:AnalyzeNext:->];
    }
}

walker AnalyzeFind {
    has target: int = 2;

    can walk with AnalyzeItem entry {
        if here.value == self.target {
            report here.value;
            disengage;
        }
        visit [->:AnalyzeNext:->];
    }
}

walker AnalyzeDiv {
    has total: float = 1.0;

    can walk with AnalyzeItem entry {
        self.total = 1 / here.value;
        visit [->:AnalyzeNext:->];
    }
}

walker AnalyzeAlias {
    has items: list[int] = [];

    can walk with AnalyzeItem entry {
        self.items += [here.value];
        visit [->:AnalyzeNext:->];
    }
}

walker AnalyzeDependentSum {
    has total: int = 0;

    can walk with AnalyzeItem entry {
        self.total += here.value;
        if self.total < 3 {
            visit [->:AnalyzeNext:->];
        }
    }
}

walker AnalyzeRecover {
    has total: int = 0;

    can walk with AnalyzeItem entry {
        self.total += here.value;
        self.total = 1;
        if self.total == 1 {
            visit [->:AnalyzeNext:->];
        }
    }
}
