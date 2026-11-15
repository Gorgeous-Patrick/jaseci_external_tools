import from typing { cast }

node AccessPerson {
    has value: int = 0,
        active: bool = True;
}
node AccessPost {
    has value: int = 0;
}
edge AccessFollow {}
edge AccessPostEdge {}
node AccessProfile {
    def view -> list[int] {
        people = [p.value for p in [self->:AccessFollow:->[?:AccessPerson]]];
        posts = [p.value for p in [self->:AccessPostEdge:->[?:AccessPost]]];
        return people + posts;
    }
}
walker AccessView {
    has seen: list[int] = [];
    can read with AccessProfile entry {
        self.seen = here.view();
    }
}
walker AccessGuard {
    has enabled: bool = False,
        seen: list[int] = [];
    can read with AccessProfile entry {
        if self.enabled {
            self.seen = [
                p.value for p in [here->:AccessFollow:->[?:AccessPerson, active == True]]
            ];
        }
    }
}
walker AccessVisit {
    has seen: list[int] = [];
    can start with AccessProfile entry {
        visit [here->:AccessPostEdge:->[?:AccessPost]];
    }
    can read with AccessPost entry {
        self.seen.append(here.value);
    }
}

def access_lookup_posts(profile: AccessProfile) -> list[int] {
    return [p.value for p in [profile->:AccessPostEdge:->[?:AccessPost]]];
}

walker AccessLookup {
    has target_id: str,
        seen: list[int] = [];
    can read with AccessProfile entry {
        key = self.target_id;
        found = jobj(id=key);
        again = jobj(key);
        self.seen = access_lookup_posts(cast(AccessProfile, found));
    }
}

walker AccessLookupGuard {
    has target_id: str,
        enabled: bool = False,
        seen: list[int] = [];
    can read with AccessProfile entry {
        if self.enabled {
            found = jobj(self.target_id);
            self.seen = access_lookup_posts(cast(AccessProfile, found));
        }
    }
}

walker AccessLookupMissing {
    has target_id: str,
        seen: list[int] = [];
    can read with AccessProfile entry {
        found = jobj(self.target_id);
        if found is None {
            self.seen = [-1];
        }
    }
}

walker AccessLookupRoot {
    has seen: list[int] = [];
    can read with AccessProfile entry {
        found = jobj('root');
        self.seen = [1 if found == root else 0];
    }
}

# The planner deliberately cannot summarize this function's effects.
def access_resume_allowed(w: any, target: any) -> bool {
    w.condition_calls += 1;
    if w.raise_guard {
        raise ValueError('native guard failure');
    }
    return w.allowed and target is not None;
}

def access_resume_replace(w: any, target: any) -> any {
    if w.replacement_id {
        return jobj(w.replacement_id);
    }
    return target;
}

walker AccessResume {
    has target_id: str,
        allowed: bool = True,
        stop_after: bool = False,
        raise_guard: bool = False,
        replacement_id: str = '',
        condition_calls: int = 0,
        seen: list[int] = [];
    can read with AccessProfile entry {
        found = jobj(self.target_id);
        if not access_resume_allowed(self, found) {
            return;
        }
        if self.stop_after {
            return;
        }
        found = access_resume_replace(self, found);
        self.seen = access_lookup_posts(cast(AccessProfile, found));
    }
}

walker AccessResumeBranch {
    has target_id: str,
        allowed: bool = True,
        raise_guard: bool = False,
        condition_calls: int = 0,
        seen: list[int] = [];
    can read with AccessProfile entry {
        found = jobj(self.target_id);
        if access_resume_allowed(self, found) {
            self.seen = access_lookup_posts(cast(AccessProfile, found));
        } else {
            self.seen = access_lookup_posts(here);
        }
    }
}

# Same access summary whether the return value is assigned or used by an if.
def access_owns(item: object, kind: type) -> bool {
    return isinstance(item, kind) and jid(item) in [jid(n) for n in [root-->]];
}

walker AccessOwnsCondition {
    has target_id: str,
        enabled: bool = True,
        seen: list[int] = [];
    can read with AccessProfile entry {
        found = jobj(self.target_id);
        if self.enabled and access_owns(found, AccessProfile) {
            self.seen = [1];
        } else {
            self.seen = [0];
        }
    }
}

walker AccessOwnsValue {
    has target_id: str,
        seen: list[int] = [];
    can read with AccessProfile entry {
        found = jobj(self.target_id);
        owned = access_owns(found, AccessProfile);
        if owned {
            self.seen = [1];
        } else {
            self.seen = [0];
        }
    }
}

walker AccessOwnsOr {
    has target_id: str,
        bypass: bool = True,
        seen: list[int] = [];
    can read with AccessProfile entry {
        found = jobj(self.target_id);
        if self.bypass or access_owns(found, AccessProfile) {
            self.seen = [1];
        } else {
            self.seen = [0];
        }
    }
}
