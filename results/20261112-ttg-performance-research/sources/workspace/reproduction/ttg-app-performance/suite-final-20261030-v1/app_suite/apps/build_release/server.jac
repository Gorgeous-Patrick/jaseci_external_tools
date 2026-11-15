"""Artifact builds and dependency-gated checks before immutable deployments."""
import from typing { cast }
import from hashlib { sha256 }
node Release {
    has name: str;
}
node Build {
    has label: str,
        status: str = "created";
}
node Artifact {
    has digest: str;
}
node Check {
    has name: str,
        status: str = "pending";
}
node Deployment {
    has environment: str;
}
edge HasBuild {}
edge Produces {}
edge HasCheck {}
edge DependsOn {}
edge HasDeployment {}
def _release(r: object) -> bool {
    return isinstance(r, Release) and jid(r) in [jid(x) for x in [root-->[?:Release]]];
}
def _build(b: object) -> bool {
    return isinstance(b, Build)
        and any(_release(r) for r in [b<-:HasBuild:<-[?:Release]]);
}
walker Seed {
    has seed: int = 42;

    can seed with Root entry {
        if [-->[?:Release]] {
            report {"ok": True};
            return;
        }
        here ++> Release(name="Runtime release " + str(self.seed));
        report {"ok": True};
    }
}

walker ReleaseBoard {
    has releases: list[dict] = [];

    can start with Root entry {
        visit [-->[?:Release]];
    }
    can release with Release entry {
        self.releases.append(
            {
                "id": jid(here),
                "name": here.name,
                "builds": [
                    {
                        "id": jid(b),
                        "label": b.label,
                        "status": b.status,
                        "artifacts": [a.digest for a in [b->:Produces:->[?:Artifact]]],
                        "checks": [
                            {
                                "id": jid(c),
                                "name": c.name,
                                "status": c.status,
                                "dependencies": [
                                    d.name for d in [c->:DependsOn:->[?:Check]]
                                ]
                            } for c in [b->:HasCheck:->[?:Check]]
                        ],
                        "deployments": [
                            d.environment for d in [b->:HasDeployment:->[?:Deployment]]
                        ]
                    } for b in [here->:HasBuild:->[?:Build]]
                ]
            }
        );
    }
    can finish with Root exit {
        report {"releases": self.releases};
    }
}

walker CreateBuild {
    has release_id: str,
        label: str;

    can create with Root entry {
        r = jobj(self.release_id);
        if not _release(r) or not self.label.strip() {
            report {"ok": False, "error": "Select a release and build label"};
            return;
        }
        r = cast(Release, r);
        b = r +>:HasBuild:+> Build(label=self.label.strip());
        b +>:Produces:+> Artifact(
            digest="sha256:" + sha256(self.label.encode()).hexdigest()
        );
        unit = b +>:HasCheck:+> Check(name="unit");
        integration = b +>:HasCheck:+> Check(name="integration");
        security = b +>:HasCheck:+> Check(name="security");
        integration +>:DependsOn:+> unit;
        security +>:DependsOn:+> integration;
        report {"ok": True, "build_id": jid(b)};
    }
}

walker RecordCheck {
    has check_id: str,
        passed: bool;

    can record with Root entry {
        c = jobj(self.check_id);
        if not isinstance(c, Check)
            or not any(_build(b) for b in [c<-:HasCheck:<-[?:Build]]) {
            report {"ok": False, "error": "Check is not available"};
            return;
        }
        b = [c<-:HasCheck:<-[?:Build]][0];
        if b.status == "deployed"
            or any(d.status != "passed" for d in [c->:DependsOn:->[?:Check]]) {
            report {
                "ok": False,
                "error": "Pass prerequisite checks before recording an undeployed build check"
            };
            return;
        }
        c.status = "passed" if self.passed else "failed";
        if not self.passed {
            for dependent in [c<-:DependsOn:<-[?:Check]] {
                dependent.status = "pending";
                for child in [dependent<-:DependsOn:<-[?:Check]] {
                    child.status = "pending";
                }
            }
        }
        report {"ok": True};
    }
}

walker DeployBuild {
    has build_id: str,
        environment: str = "staging";

    can deploy with Root entry {
        b = jobj(self.build_id);
        if not _build(b) {
            report {"ok": False, "error": "Build is not available"};
            return;
        }
        b = cast(Build, b);
        if b.status == "deployed"
            or self.environment not in ["staging", "production"]
            or not all(c.status == "passed" for c in [b->:HasCheck:->[?:Check]]) {
            report {
                "ok": False,
                "error": "All required checks must pass before a single deployment"
            };
            return;
        }
        b +>:HasDeployment:+> Deployment(environment=self.environment);
        b.status = "deployed";
        report {"ok": True};
    }
}
