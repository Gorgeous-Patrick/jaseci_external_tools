"""EventSeats: exclusive seat holds, confirmation, cancellation and exact refunds."""

import from typing { cast }

node Venue {
    has name: str;
}
node Event {
    has title: str;
}
node Section {
    has name: str;
}
node Seat {
    has label: str,
        price_cents: int,
        status: str = "available";
}
node Booking {
    has reference: str,
        total_cents: int,
        status: str = "held";
}
node Refund {
    has amount_cents: int;
}
edge Hosts {}
edge HasSection {}
edge HasSeat {}
edge HasBooking {}
edge Reserves {}
edge HasRefund {}

def _owned_event(event: object) -> bool {
    if not isinstance(event, Event) {
        return False;
    }
    return any(
        jid(event) in [jid(item) for item in [venue->:Hosts:->[?:Event]]]
        for venue in [root-->[?:Venue]]
    );
}

def _seats(event: Event) -> list[Seat] {
    result: list[Seat] = [];
    for section in [event->:HasSection:->[?:Section]] {
        result.extend([section->:HasSeat:->[?:Seat]]);
    }
    return result;
}

def _owned_booking(booking: object) -> bool {
    return isinstance(booking, Booking)
        and any(_owned_event(event) for event in [booking<-:HasBooking:<-[?:Event]]);
}

def _booking_view(booking: Booking) -> dict {
    return {
        "id": jid(booking),
        "reference": booking.reference,
        "status": booking.status,
        "total_cents": booking.total_cents,
        "seat_ids": [jid(seat) for seat in [booking->:Reserves:->[?:Seat]]],
        "refunds": [
            {"id": jid(refund), "amount_cents": refund.amount_cents}
            for refund in [booking->:HasRefund:->[?:Refund]]
        ]
    };
}

walker Seed {
    has seed: int = 42;

    can seed with Root entry {
        if [-->[?:Venue]] {
            report {"ok": True, "created": False};
            return;
        }
        venue = here ++> Venue(name="Research Hall");
        event = venue +>:Hosts:+> Event(title="Graph Summit");
        section = event +>:HasSection:+> Section(name="Main");
        for i in range(3) {
            section +>:HasSeat:+> Seat(
                label="A" + str(i + 1), price_cents=1000 + self.seed % 3 * 100 + i * 200
            );
        }
        workshop = venue +>:Hosts:+> Event(title="Data Workshop");
        workshop_section = workshop +>:HasSection:+> Section(name="Studio");
        workshop_section +>:HasSeat:+> Seat(label="B1", price_cents=500);
        report {"ok": True, "created": True};
    }
}

walker EventCatalog {
    has venues: list[dict] = [],
        events: list[dict] = [];

    can start with Root entry {
        visit [-->[?:Venue]];
    }
    can venue with Venue entry {
        self.venues.append({"id": jid(here), "name": here.name});
        visit [->:Hosts:->[?:Event]];
    }
    can event with Event entry {
        sections = [];
        for section in [here->:HasSection:->[?:Section]] {
            sections.append(
                {
                    "id": jid(section),
                    "name": section.name,
                    "seats": [
                        {
                            "id": jid(seat),
                            "label": seat.label,
                            "price_cents": seat.price_cents,
                            "status": seat.status
                        } for seat in [section->:HasSeat:->[?:Seat]]
                    ]
                }
            );
        }
        self.events.append(
            {
                "id": jid(here),
                "title": here.title,
                "sections": sections,
                "bookings": [
                    _booking_view(booking)
                    for booking in [here->:HasBooking:->[?:Booking]]
                ]
            }
        );
    }

    can finish with Root exit {
        report {"venues": self.venues, "events": self.events};
    }
}

walker HoldSeats {
    has event_id: str,
        seat_ids: list[str],
        reference: str;

    can hold with Root entry {
        event = jobj(self.event_id);
        if not _owned_event(event) {
            report {"ok": False, "error": "Event is not available to this user"};
            return;
        }
        event = cast(Event, event);
        if not self.reference.strip()
            or not self.seat_ids
            or len(set(self.seat_ids)) != len(self.seat_ids) {
            report {
                "ok": False,
                "error": "Select distinct seats and enter a booking reference"
            };
            return;
        }
        if any(
            booking.reference == self.reference.strip()
            for booking in [event->:HasBooking:->[?:Booking]]
        ) {
            report {"ok": False, "error": "Booking reference already exists"};
            return;
        }
        available = {jid(seat): seat for seat in _seats(event)};
        if any(
            uid not in available or available[uid].status != "available"
            for uid in self.seat_ids
        ) {
            report {
                "ok": False,
                "error": "Every selected seat must be available in this event"
            };
            return;
        }
        total = sum(available[uid].price_cents for uid in self.seat_ids);
        booking = event +>:HasBooking:+> Booking(
            reference=self.reference.strip(), total_cents=total
        );
        for uid in self.seat_ids {
            booking +>:Reserves:+> available[uid];
            available[uid].status = "held";
        }
        report {"ok": True, "booking": _booking_view(booking)};
    }
}

walker ConfirmBooking {
    has booking_id: str;

    can confirm with Root entry {
        booking = jobj(self.booking_id);
        if not _owned_booking(booking) {
            report {"ok": False, "error": "Booking is not available to this user"};
            return;
        }
        booking = cast(Booking, booking);
        if booking.status != "held" {
            report {"ok": False, "error": "Only held bookings can be confirmed"};
            return;
        }
        booking.status = "confirmed";
        for seat in [booking->:Reserves:->[?:Seat]] {
            seat.status = "sold";
        }
        report {"ok": True, "booking": _booking_view(booking)};
    }
}

walker CancelBooking {
    has booking_id: str;

    can cancel with Root entry {
        booking = jobj(self.booking_id);
        if not _owned_booking(booking) {
            report {"ok": False, "error": "Booking is not available to this user"};
            return;
        }
        booking = cast(Booking, booking);
        if booking.status == "cancelled" {
            report {"ok": False, "error": "Booking is already cancelled"};
            return;
        }
        if booking.status == "confirmed" {
            booking +>:HasRefund:+> Refund(amount_cents=booking.total_cents);
        }
        booking.status = "cancelled";
        for seat in [booking->:Reserves:->[?:Seat]] {
            seat.status = "available";
        }
        report {"ok": True, "booking": _booking_view(booking)};
    }
}
