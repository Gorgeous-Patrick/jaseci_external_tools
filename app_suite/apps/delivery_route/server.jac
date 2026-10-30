"""Capacity-limited parcel routes with ordered attempts and explicit retries."""
import from typing { cast }
node Depot {
    has name: str;
}
node Route {
    has name: str,
        capacity: int,
        loaded: bool = False;
}
node Parcel {
    has label: str,
        weight: int,
        status: str = "waiting";
}
node Stop {
    has position: int,
        status: str = "pending";
}
node Scan {
    has kind: str,
        note: str = "";
}
edge HasRoute {}
edge HasParcel {}
edge HasStop {}
edge Carries {}
edge HasScan {}
def _depot -> Depot | None {
    rows = [root-->[?:Depot]];
    return rows[0] if rows else None;
}
def _owns_route(route: object) -> bool {
    d = _depot();
    return d is not None
        and isinstance(route, Route)
        and jid(route) in [jid(r) for r in [d->:HasRoute:->[?:Route]]];
}
walker Seed {
    has seed: int = 42;

    can seed with Root entry {
        if [-->[?:Depot]] {
            report {"ok": True};
            return;
        }
        depot = here ++> Depot(name="Campus depot");
        depot +>:HasRoute:+> Route(name="Morning route", capacity=10);
        depot +>:HasParcel:+> Parcel(label="Sensors", weight=2);
        depot +>:HasParcel:+> Parcel(label="Cables", weight=3 + self.seed % 3);
        depot +>:HasParcel:+> Parcel(label="Spare crate", weight=8);
        report {"ok": True};
    }
}

walker RouteBoard {
    has depots: list[dict] = [],
        routes: list[dict] = [],
        parcels: list[dict] = [];

    can start with Root entry {
        visit [-->[?:Depot]];
    }
    can depot with Depot entry {
        self.depots.append({"id": jid(here), "name": here.name});
        visit [->:HasRoute:->[?:Route]];
        visit [->:HasParcel:->[?:Parcel]];
    }
    can parcel with Parcel entry {
        self.parcels.append(
            {
                "id": jid(here),
                "label": here.label,
                "weight": here.weight,
                "status": here.status,
                "scans": [s.kind for s in [here->:HasScan:->[?:Scan]]]
            }
        );
    }
    can route with Route entry {
        stops = [];
        for s in [here->:HasStop:->[?:Stop]] {
            p = [s->:Carries:->[?:Parcel]][0];
            stops.append(
                {
                    "id": jid(s),
                    "position": s.position,
                    "status": s.status,
                    "parcel_id": jid(p),
                    "label": p.label
                }
            );
        }
        stops.sort(key=lambda (s: dict) { s["position"]; });
        self.routes.append(
            {
                "id": jid(here),
                "name": here.name,
                "capacity": here.capacity,
                "loaded": here.loaded,
                "stops": stops,
                "complete": bool(stops)
                    and all(s["status"] == "delivered" for s in stops)
            }
        );
    }

    can finish with Root exit {
        report {"depots": self.depots, "routes": self.routes, "parcels": self.parcels};
    }
}

walker CreateRoute {
    has name: str,
        capacity: int;

    can create with Root entry {
        depot = _depot();
        if depot is None or not self.name.strip() or self.capacity < 1 {
            report {"ok": False, "error": "Enter a route name and positive capacity"};
            return;
        }
        route = depot +>:HasRoute:+> Route(
            name=self.name.strip(), capacity=self.capacity
        );
        report {"ok": True, "route_id": jid(route)};
    }
}

walker AssignParcel {
    has route_id: str,
        parcel_id: str;

    can assign with Root entry {
        route = jobj(self.route_id);
        parcel = jobj(self.parcel_id);
        depot = _depot();
        if not _owns_route(route)
            or not isinstance(parcel, Parcel)
            or depot is None
            or self.parcel_id
                not in [jid(p) for p in [depot->:HasParcel:->[?:Parcel]]] {
            report {"ok": False, "error": "Route or parcel is not available"};
            return;
        }
        route = cast(Route, route);
        weight = sum(
            [s->:Carries:->[?:Parcel]][0].weight for s in [route->:HasStop:->[?:Stop]]
        );
        if route.loaded
            or parcel.status != "waiting"
            or weight + parcel.weight > route.capacity {
            report {
                "ok": False,
                "error": "Route is loaded, parcel assigned or capacity exceeded"
            };
            return;
        }
        stop = route +>:HasStop:+> Stop(position=len([route->:HasStop:->[?:Stop]]) + 1);
        stop +>:Carries:+> parcel;
        parcel.status = "assigned";
        report {"ok": True};
    }
}

walker LoadRoute {
    has route_id: str;

    can load with Root entry {
        route = jobj(self.route_id);
        if not _owns_route(route) {
            report {"ok": False, "error": "Route is not available"};
            return;
        }
        route = cast(Route, route);
        stops = [route->:HasStop:->[?:Stop]];
        if route.loaded or not stops {
            report {
                "ok": False,
                "error": "Only a nonempty unloaded route can be loaded"
            };
            return;
        }
        route.loaded = True;
        for s in stops {
            p = [s->:Carries:->[?:Parcel]][0];
            p.status = "loaded";
            p +>:HasScan:+> Scan(kind="loaded");
        }
        report {"ok": True};
    }
}

walker DeliveryAttempt {
    has route_id: str,
        success: bool = True,
        note: str = "";

    can attempt with Root entry {
        route = jobj(self.route_id);
        if not _owns_route(route) {
            report {"ok": False, "error": "Route is not available"};
            return;
        }
        route = cast(Route, route);
        stops = [
            s
            for s in [route->:HasStop:->[?:Stop]]
            if s.status != "delivered"
        ];
        stops.sort(key=lambda (s: Stop) { s.position; });
        if not route.loaded or not stops or stops[0].status == "failed" {
            report {
                "ok": False,
                "error": "Load the route and retry any failed stop before continuing"
            };
            return;
        }
        if not self.success and not self.note.strip() {
            report {"ok": False, "error": "Enter a failed-delivery reason"};
            return;
        }
        stop = stops[0];
        parcel = [stop->:Carries:->[?:Parcel]][0];
        stop.status = "delivered" if self.success else "failed";
        parcel.status = stop.status;
        parcel +>:HasScan:+> Scan(kind=stop.status, note=self.note);
        report {"ok": True};
    }
}

walker RetryStop {
    has stop_id: str;

    can retry with Root entry {
        stop = jobj(self.stop_id);
        if not isinstance(stop, Stop)
            or not any(_owns_route(r) for r in [stop<-:HasStop:<-[?:Route]]) {
            report {"ok": False, "error": "Stop is not available"};
            return;
        }
        if stop.status != "failed" {
            report {"ok": False, "error": "Only failed stops can be retried"};
            return;
        }
        stop.status = "pending";
        parcel = [stop->:Carries:->[?:Parcel]][0];
        parcel.status = "loaded";
        parcel +>:HasScan:+> Scan(kind="retried");
        report {"ok": True};
    }
}
