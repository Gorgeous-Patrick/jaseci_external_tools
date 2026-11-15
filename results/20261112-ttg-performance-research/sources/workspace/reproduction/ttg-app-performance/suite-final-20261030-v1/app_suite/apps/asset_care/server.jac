"""Inspection-triggered maintenance with technician assignment and conserved parts."""
import from typing { cast }
node Asset {
    has name: str,
        status: str = "operational";
}
node Inspection {
    has issue: str,
        severity: int;
}
node WorkOrder {
    has number: int,
        status: str = "open";
}
node Technician {
    has name: str;
}
node Part {
    has name: str,
        initial: int,
        stock: int;
}
node PartUse {
    has quantity: int;
}
edge HasInspection {}
edge HasOrder {}
edge AssignedTech {}
edge UsesPart {}
edge PartRef {}
def _asset(a: object) -> bool {
    return isinstance(a, Asset) and jid(a) in [jid(x) for x in [root-->[?:Asset]]];
}
def _order(o: object) -> bool {
    return isinstance(o, WorkOrder)
        and any(_asset(a) for a in [o<-:HasOrder:<-[?:Asset]]);
}
walker Seed {
    has seed: int = 42;

    can seed with Root entry {
        if [-->[?:Asset]] {
            report {"ok": True};
            return;
        }
        here ++> Asset(name="Pump P-" + str(self.seed));
        here ++> Asset(name="Valve V1");
        here ++> Technician(name="Jordan");
        here ++> Part(name="Seal kit", initial=5, stock=5);
        report {"ok": True};
    }
}

walker AssetBoard {
    has assets: list[dict] = [],
        technicians: list[dict] = [],
        parts: list[dict] = [];

    can start with Root entry {
        visit [-->[?:Asset]];
        visit [-->[?:Technician]];
        visit [-->[?:Part]];
    }
    can asset with Asset entry {
        self.assets.append(
            {
                "id": jid(here),
                "name": here.name,
                "status": here.status,
                "inspections": [
                    {"issue": i.issue, "severity": i.severity}
                    for i in [here->:HasInspection:->[?:Inspection]]
                ],
                "orders": [
                    {
                        "id": jid(o),
                        "number": o.number,
                        "status": o.status,
                        "uses": [
                            {
                                "quantity": u.quantity,
                                "part_id": jid([u->:PartRef:->[?:Part]][0])
                            } for u in [o->:UsesPart:->[?:PartUse]]
                        ]
                    } for o in [here->:HasOrder:->[?:WorkOrder]]
                ]
            }
        );
    }
    can technician with Technician entry {
        self.technicians.append({"id": jid(here), "name": here.name});
    }
    can part with Part entry {
        self.parts.append(
            {
                "id": jid(here),
                "name": here.name,
                "initial": here.initial,
                "stock": here.stock
            }
        );
    }
    can finish with Root exit {
        report {
            "assets": self.assets,
            "parts": self.parts,
            "technicians": self.technicians
        };
    }
}

walker InspectAsset {
    has asset_id: str,
        issue: str,
        severity: int;

    can inspect with Root entry {
        a = jobj(self.asset_id);
        if not _asset(a)
            or not self.issue.strip()
            or self.severity < 1
            or self.severity > 5 {
            report {
                "ok": False,
                "error": "Select an asset, issue and severity from 1 to 5"
            };
            return;
        }
        a = cast(Asset, a);
        a +>:HasInspection:+> Inspection(
            issue=self.issue.strip(), severity=self.severity
        );
        if self.severity >= 3 {
            a.status = "needs_service";
        }
        report {"ok": True};
    }
}

walker OpenWorkOrder {
    has asset_id: str,
        technician_id: str;

    can open with Root entry {
        a = jobj(self.asset_id);
        t = jobj(self.technician_id);
        if not _asset(a)
            or not isinstance(t, Technician)
            or self.technician_id not in [jid(x) for x in [-->[?:Technician]]] {
            report {"ok": False, "error": "Asset or technician is not available"};
            return;
        }
        a = cast(Asset, a);
        if a.status != "needs_service"
            or any(o.status == "open" for o in [a->:HasOrder:->[?:WorkOrder]]) {
            report {
                "ok": False,
                "error": "Inspect a fault and close any existing work order first"
            };
            return;
        }
        o = a +>:HasOrder:+> WorkOrder(number=len([a->:HasOrder:->[?:WorkOrder]]) + 1);
        o +>:AssignedTech:+> t;
        report {"ok": True, "order_id": jid(o)};
    }
}

walker ConsumePart {
    has order_id: str,
        part_id: str,
        quantity: int;

    can consume with Root entry {
        o = jobj(self.order_id);
        p = jobj(self.part_id);
        if not _order(o)
            or not isinstance(p, Part)
            or self.part_id not in [jid(x) for x in [-->[?:Part]]] {
            report {"ok": False, "error": "Work order or part is not available"};
            return;
        }
        o = cast(WorkOrder, o);
        if o.status != "open" or self.quantity < 1 or self.quantity > p.stock {
            report {
                "ok": False,
                "error": "Use positive available parts on an open order"
            };
            return;
        }
        p.stock -= self.quantity;
        use = o +>:UsesPart:+> PartUse(quantity=self.quantity);
        use +>:PartRef:+> p;
        report {"ok": True};
    }
}

walker FinishWorkOrder {
    has order_id: str;

    can finish with Root entry {
        o = jobj(self.order_id);
        if not _order(o) {
            report {"ok": False, "error": "Work order is not available"};
            return;
        }
        o = cast(WorkOrder, o);
        if o.status != "open" or not [o->:UsesPart:->[?:PartUse]] {
            report {
                "ok": False,
                "error": "Record parts used before completing an open order"
            };
            return;
        }
        o.status = "closed";
        a = [o<-:HasOrder:<-[?:Asset]][0];
        a.status = "operational";
        report {"ok": True};
    }
}
