"""Cycle-safe service-impact discovery and evidence-gated incident resolution."""
import from typing { cast }
node Service {
    has name: str;
}
node Incident {
    has summary: str,
        status: str = "open";
}
node Alert {
    has acknowledged: bool = False;
}
node Action {
    has name: str,
        done: bool = False;
}
edge DependsOn {}
edge Affects {}
edge HasAlert {}
edge AtService {}
edge HasAction {}
def _service(s: object) -> bool {
    return isinstance(s, Service) and jid(s) in [jid(x) for x in [root-->[?:Service]]];
}
def _incident(i: object) -> bool {
    return isinstance(i, Incident)
        and jid(i) in [jid(x) for x in [root-->[?:Incident]]];
}
walker ImpactTrace {
    has seen: set[str] = set(),
        services: list[Service] = [];

    can service with Service entry {
        if jid(here) in self.seen {
            return;
        }
        self.seen.add(jid(here));
        self.services.append(here);
        visit [<-:DependsOn:<-[?:Service]];
    }
}

walker Seed {
    has seed: int = 42;

    can seed with Root entry {
        if [-->[?:Service]] {
            report {"ok": True};
            return;
        }
        api = here ++> Service(name="API");
        db = here ++> Service(name="Database");
        cache = here ++> Service(name="Cache");
        api +>:DependsOn:+> db;
        cache +>:DependsOn:+> api;
        db +>:DependsOn:+> cache;
        report {"ok": True, "seed": self.seed};
    }
}

walker IncidentBoard {
    has services: list[dict] = [],
        incidents: list[dict] = [];

    can start with Root entry {
        visit [-->[?:Service]];
        visit [-->[?:Incident]];
    }
    can service with Service entry {
        self.services.append(
            {
                "id": jid(here),
                "name": here.name,
                "dependencies": [jid(s) for s in [here->:DependsOn:->[?:Service]]]
            }
        );
    }
    can incident with Incident entry {
        self.incidents.append(
            {
                "id": jid(here),
                "summary": here.summary,
                "status": here.status,
                "alerts": [
                    {
                        "id": jid(a),
                        "acknowledged": a.acknowledged,
                        "service": [a->:AtService:->[?:Service]][0].name
                    } for a in [here->:HasAlert:->[?:Alert]]
                ],
                "actions": [
                    {"id": jid(a), "name": a.name, "done": a.done}
                    for a in [here->:HasAction:->[?:Action]]
                ]
            }
        );
    }
    can finish with Root exit {
        report {"services": self.services, "incidents": self.incidents};
    }
}

walker OpenIncident {
    has service_id: str,
        summary: str;

    can open with Root entry {
        s = jobj(self.service_id);
        if not _service(s) or not self.summary.strip() {
            report {
                "ok": False,
                "error": "Select a service and enter an incident summary"
            };
            return;
        }
        s = cast(Service, s);
        trace = ImpactTrace();
        s spawn trace;
        i = here ++> Incident(summary=self.summary.strip());
        i +>:Affects:+> s;
        for impacted in trace.services {
            a = i +>:HasAlert:+> Alert();
            a +>:AtService:+> impacted;
        }
        i +>:HasAction:+> Action(name="Investigate cause");
        report {"ok": True, "incident_id": jid(i)};
    }
}

walker AcknowledgeAlert {
    has alert_id: str;

    can acknowledge with Root entry {
        a = jobj(self.alert_id);
        if not isinstance(a, Alert)
            or not any(_incident(i) for i in [a<-:HasAlert:<-[?:Incident]]) {
            report {"ok": False, "error": "Alert is not available"};
            return;
        }
        a.acknowledged = True;
        report {"ok": True};
    }
}

walker AddAction {
    has incident_id: str,
        name: str;

    can add with Root entry {
        i = jobj(self.incident_id);
        if not _incident(i) or not self.name.strip() {
            report {"ok": False, "error": "Select an incident and action name"};
            return;
        }
        i = cast(Incident, i);
        if i.status != "open" {
            report {"ok": False, "error": "Closed incidents cannot receive actions"};
            return;
        }
        a = i +>:HasAction:+> Action(name=self.name.strip());
        report {"ok": True, "action_id": jid(a)};
    }
}

walker CompleteAction {
    has action_id: str;

    can complete with Root entry {
        a = jobj(self.action_id);
        if not isinstance(a, Action)
            or not any(_incident(i) for i in [a<-:HasAction:<-[?:Incident]]) {
            report {"ok": False, "error": "Action is not available"};
            return;
        }
        if a.done {
            report {"ok": False, "error": "Action is already completed"};
            return;
        }
        a.done = True;
        report {"ok": True};
    }
}

walker ResolveIncident {
    has incident_id: str;

    can resolve with Root entry {
        i = jobj(self.incident_id);
        if not _incident(i) {
            report {"ok": False, "error": "Incident is not available"};
            return;
        }
        i = cast(Incident, i);
        if i.status != "open"
            or not all(a.acknowledged for a in [i->:HasAlert:->[?:Alert]])
            or not all(a.done for a in [i->:HasAction:->[?:Action]]) {
            report {
                "ok": False,
                "error": "Acknowledge every alert and complete every action before resolution"
            };
            return;
        }
        i.status = "resolved";
        report {"ok": True};
    }
}
