"""Typed guarded interability microbenchmark; three actual native nodes."""
node A { has value: int = 10; }
node B { has value: int = 20, active: bool = True; }
node C { has value: int = 30; }
edge AB {}
edge BC {}
walker RegionChain {
    has visited: int = 0;
    can a with A entry {
        self.visited += 1;
        report here.value;
        visit [->:AB:->[?:B]];
    }
    can b with B entry {
        self.visited += 1;
        report here.value;
        if here.active {
            visit [->:BC:->[?:C]];
        }
    }
    can c with C entry {
        self.visited += 1;
        report here.value;
    }
}
