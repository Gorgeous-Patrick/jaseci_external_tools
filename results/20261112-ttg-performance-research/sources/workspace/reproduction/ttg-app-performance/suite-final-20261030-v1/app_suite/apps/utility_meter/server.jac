"""Monotone meter readings, unbilled corrections and exact tiered invoices."""
import from typing { cast }
node Building {
    has name: str;
}
node Meter {
    has name: str;
}
node Reading {
    has position: int,
        value: int;
}
node Tariff {
    has threshold: int,
        low: int,
        high: int;
}
node Invoice {
    has units: int,
        cents: int;
}
edge HasMeter {}
edge HasTariff {}
edge HasReading {}
edge HasInvoice {}
edge EndReading {}
def _meter(m: object) -> bool {
    return isinstance(m, Meter)
        and any(
            jid(b) in [jid(x) for x in [root-->[?:Building]]]
            for b in [m<-:HasMeter:<-[?:Building]]
        );
}
walker Seed {
    has seed: int = 42;

    can seed with Root entry {
        if [-->[?:Building]] {
            report {"ok": True};
            return;
        }
        b = here ++> Building(name="Research Annex");
        b +>:HasTariff:+> Tariff(threshold=100, low=2, high=5);
        m = b +>:HasMeter:+> Meter(name="Power");
        m +>:HasReading:+> Reading(position=1, value=1000);
        m +>:HasReading:+> Reading(position=2, value=1150 + self.seed % 3);
        report {"ok": True};
    }
}

walker MeterBoard {
    has buildings: list[dict] = [],
        meters: list[dict] = [];

    can start with Root entry {
        visit [-->[?:Building]];
    }
    can building with Building entry {
        self.buildings.append({"id": jid(here), "name": here.name});
        visit [->:HasMeter:->[?:Meter]];
    }
    can meter with Meter entry {
        self.meters.append(
            {
                "id": jid(here),
                "name": here.name,
                "readings": [
                    {"id": jid(r), "position": r.position, "value": r.value}
                    for r in [here->:HasReading:->[?:Reading]]
                ],
                "invoices": [
                    {"id": jid(i), "units": i.units, "cents": i.cents}
                    for i in [here->:HasInvoice:->[?:Invoice]]
                ]
            }
        );
    }
    can finish with Root exit {
        report {"buildings": self.buildings, "meters": self.meters};
    }
}

walker AddReading {
    has meter_id: str,
        value: int;

    can add with Root entry {
        m = jobj(self.meter_id);
        if not _meter(m) {
            report {"ok": False, "error": "Meter is not available"};
            return;
        }
        m = cast(Meter, m);
        rows = [m->:HasReading:->[?:Reading]];
        if self.value < rows[-1].value {
            report {"ok": False, "error": "Meter readings cannot decrease"};
            return;
        }
        r = m +>:HasReading:+> Reading(position=len(rows) + 1, value=self.value);
        report {"ok": True, "reading_id": jid(r)};
    }
}

walker CorrectReading {
    has reading_id: str,
        value: int;

    can correct with Root entry {
        r = jobj(self.reading_id);
        if not isinstance(r, Reading)
            or not any(_meter(m) for m in [r<-:HasReading:<-[?:Meter]]) {
            report {"ok": False, "error": "Reading is not available"};
            return;
        }
        m = [r<-:HasReading:<-[?:Meter]][0];
        rows = [m->:HasReading:->[?:Reading]];
        if jid(rows[-1]) != jid(r)
            or len(rows) < 2
            or [r<-:EndReading:<-[?:Invoice]]
            or self.value < rows[-2].value {
            report {
                "ok": False,
                "error": "Only the latest unbilled monotone reading can be corrected"
            };
            return;
        }
        r.value = self.value;
        report {"ok": True};
    }
}

walker BillMeter {
    has meter_id: str;

    can bill with Root entry {
        m = jobj(self.meter_id);
        if not _meter(m) {
            report {"ok": False, "error": "Meter is not available"};
            return;
        }
        m = cast(Meter, m);
        rows = [m->:HasReading:->[?:Reading]];
        if len(rows) < 2 or [rows[-1]<-:EndReading:<-[?:Invoice]] {
            report {"ok": False, "error": "An unbilled reading interval is required"};
            return;
        }
        b = [m<-:HasMeter:<-[?:Building]][0];
        t = [b->:HasTariff:->[?:Tariff]][0];
        units = rows[-1].value - rows[-2].value;
        cents = min(units, t.threshold) * t.low + max(0, units - t.threshold) * t.high;
        i = m +>:HasInvoice:+> Invoice(units=units, cents=cents);
        i +>:EndReading:+> rows[-1];
        report {"ok": True, "cents": cents};
    }
}
