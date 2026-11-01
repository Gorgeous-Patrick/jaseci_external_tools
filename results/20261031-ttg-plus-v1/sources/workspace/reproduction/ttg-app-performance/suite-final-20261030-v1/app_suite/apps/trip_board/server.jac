"""Ordered daily journeys with capacity-limited stay reservations."""
import from typing { cast }
node Journey {
    has name: str,
        days: int;
}
node Stop {
    has name: str,
        day: int,
        position: int,
        capacity: int = 4;
}
node Stay {
    has guests: int,
        active: bool = True;
}
edge HasStop {}
edge HasStay {}
def _owns(journey: object) -> bool {
    return isinstance(journey, Journey)
        and jid(journey) in [jid(j) for j in [root-->[?:Journey]]];
}
def _stop_owned(stop: object) -> bool {
    return isinstance(stop, Stop)
        and any(_owns(j) for j in [stop<-:HasStop:<-[?:Journey]]);
}
walker Seed {
    has seed: int = 42;

    can seed with Root entry {
        if [-->[?:Journey]] {
            report {"ok": True};
            return;
        }
        journey = here ++> Journey(name="Research retreat", days=3);
        journey +>:HasStop:+> Stop(
            name="Lakeside lodge", day=1, position=1, capacity=4 + self.seed % 3
        );
        journey +>:HasStop:+> Stop(name="Museum visit", day=2, position=2);
        report {"ok": True};
    }
}

walker Itinerary {
    has journeys: list[dict] = [];

    can start with Root entry {
        visit [-->[?:Journey]];
    }
    can journey with Journey entry {
        stops = [
            {
                "id": jid(s),
                "name": s.name,
                "day": s.day,
                "position": s.position,
                "capacity": s.capacity,
                "booked": sum(
                    b.guests
                    for b in [s->:HasStay:->[?:Stay]]
                    if b.active
                ),
                "bookings": [
                    {"id": jid(b), "guests": b.guests, "active": b.active}
                    for b in [s->:HasStay:->[?:Stay]]
                ]
            } for s in [here->:HasStop:->[?:Stop]]
        ];
        stops.sort(key=lambda (s: dict) { s["position"]; });
        self.journeys.append(
            {"id": jid(here), "name": here.name, "days": here.days, "stops": stops}
        );
    }

    can finish with Root exit {
        report {"journeys": self.journeys};
    }
}

walker AddStop {
    has journey_id: str,
        name: str,
        day: int;

    can add with Root entry {
        journey = jobj(self.journey_id);
        if not _owns(journey) {
            report {"ok": False, "error": "Journey is not available"};
            return;
        }
        journey = cast(Journey, journey);
        if not self.name.strip() or self.day < 1 or self.day > journey.days {
            report {
                "ok": False,
                "error": "Enter a stop name and day within the journey"
            };
            return;
        }
        rows = [journey->:HasStop:->[?:Stop]];
        position = len(
            [
                s
                for s in rows
                if s.day <= self.day
            ]
        )
            + 1;
        for sibling in rows {
            if sibling.position >= position {
                sibling.position += 1;
            }
        }
        stop = journey +>:HasStop:+> Stop(
            name=self.name.strip(), day=self.day, position=position
        );
        report {"ok": True, "stop_id": jid(stop)};
    }
}

walker ReserveStay {
    has stop_id: str,
        guests: int;

    can reserve with Root entry {
        stop = jobj(self.stop_id);
        if not _stop_owned(stop) {
            report {"ok": False, "error": "Stop is not available"};
            return;
        }
        stop = cast(Stop, stop);
        if self.guests < 1
            or self.guests
                + sum(
                    b.guests
                    for b in [stop->:HasStay:->[?:Stay]]
                    if b.active
                )
                > stop.capacity {
            report {"ok": False, "error": "Stay capacity would be exceeded"};
            return;
        }
        booking = stop +>:HasStay:+> Stay(guests=self.guests);
        report {"ok": True, "booking_id": jid(booking)};
    }
}

walker CancelStay {
    has booking_id: str;

    can cancel with Root entry {
        booking = jobj(self.booking_id);
        if not isinstance(booking, Stay)
            or not any(_stop_owned(s) for s in [booking<-:HasStay:<-[?:Stop]]) {
            report {"ok": False, "error": "Booking is not available"};
            return;
        }
        if not booking.active {
            report {"ok": False, "error": "Stay is already cancelled"};
            return;
        }
        booking.active = False;
        report {"ok": True};
    }
}

walker MoveStop {
    has stop_id: str,
        position: int;

    can move with Root entry {
        stop = jobj(self.stop_id);
        if not _stop_owned(stop) {
            report {"ok": False, "error": "Stop is not available"};
            return;
        }
        stop = cast(Stop, stop);
        journey = [stop<-:HasStop:<-[?:Journey]][0];
        stops = [journey->:HasStop:->[?:Stop]];
        if self.position < 1 or self.position > len(stops) {
            report {"ok": False, "error": "Position must be within the itinerary"};
            return;
        }
        proposed = sorted(stops, key=lambda (s: Stop) { s.position; });
        proposed.remove(stop);
        proposed.insert(self.position - 1, stop);
        if [s.day for s in proposed] != sorted(s.day for s in proposed) {
            report {"ok": False, "error": "Reorder stops within their scheduled day"};
            return;
        }
        old = stop.position;
        for other in stops {
            if jid(other) != jid(stop) {
                if self.position <= other.position and other.position < old {
                    other.position += 1;
                } elif old < other.position and other.position <= self.position {
                    other.position -= 1;
                }
            }
        }
        stop.position = self.position;
        report {"ok": True};
    }
}
