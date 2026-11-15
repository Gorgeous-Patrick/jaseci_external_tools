"""StockRoom: FIFO lot allocation, reservation release and conserved dispatches."""

import from typing { cast }

node Warehouse {
    has name: str;
}
node SKU {
    has name: str,
        code: str;
}
node Lot {
    has sequence: int,
        received: int,
        available: int,
        dispatched: int = 0;
}
node Reservation {
    has reference: str,
        quantity: int,
        status: str = "reserved";
}
node Allocation {
    has quantity: int;
}
node Dispatch {
    has quantity: int,
        reference: str;
}
edge HasSKU {}
edge Stocks {}
edge ForSKU {}
edge Holds {}
edge HasAllocation {}
edge FromLot {}
edge HasDispatch {}
edge ForReservation {}

def _warehouse() -> Warehouse | None {
    items = [root-->[?:Warehouse]];
    return items[0] if items else None;
}

def _owned_sku(sku: object) -> bool {
    warehouse = _warehouse();
    return warehouse is not None
        and isinstance(sku, SKU)
        and jid(sku) in [jid(item) for item in [warehouse->:HasSKU:->[?:SKU]]];
}

def _owned_reservation(reservation: object) -> bool {
    warehouse = _warehouse();
    return warehouse is not None
        and isinstance(reservation, Reservation)
        and jid(reservation)
            in [jid(item) for item in [warehouse->:Holds:->[?:Reservation]]];
}

def _reservation_view(reservation: Reservation) -> dict {
    allocations = [];
    for allocation in [reservation->:HasAllocation:->[?:Allocation]] {
        lot = [allocation->:FromLot:->[?:Lot]][0];
        sku = [lot->:ForSKU:->[?:SKU]][0];
        allocations.append(
            {
                "lot_id": jid(lot),
                "sequence": lot.sequence,
                "sku_id": jid(sku),
                "quantity": allocation.quantity
            }
        );
    }
    return {
        "id": jid(reservation),
        "reference": reservation.reference,
        "quantity": reservation.quantity,
        "status": reservation.status,
        "allocations": allocations
    };
}

walker Seed {
    has seed: int = 42;

    can seed with Root entry {
        if [-->[?:Warehouse]] {
            report {"ok": True, "created": False};
            return;
        }
        warehouse = here ++> Warehouse(name="Research Store");
        sensor = warehouse +>:HasSKU:+> SKU(name="Sensor", code="SEN-01");
        cable = warehouse +>:HasSKU:+> SKU(name="Cable", code="CAB-01");
        first = warehouse +>:Stocks:+> Lot(
            sequence=1, received=5 + self.seed % 3, available=5 + self.seed % 3
        );
        first +>:ForSKU:+> sensor;
        second = warehouse +>:Stocks:+> Lot(sequence=2, received=7, available=7);
        second +>:ForSKU:+> sensor;
        third = warehouse +>:Stocks:+> Lot(sequence=3, received=4, available=4);
        third +>:ForSKU:+> cable;
        report {"ok": True, "created": True};
    }
}

walker Inventory {
    has warehouses: list[dict] = [],
        skus: list[dict] = [],
        lots: list[dict] = [],
        reservations: list[dict] = [],
        dispatches: list[dict] = [];

    can start with Root entry {
        visit [-->[?:Warehouse]];
    }
    can warehouse with Warehouse entry {
        self.warehouses.append({"id": jid(here), "name": here.name});
        visit [->:HasSKU:->[?:SKU]];
        visit [->:Stocks:->[?:Lot]];
        visit [->:Holds:->[?:Reservation]];
        visit [->:HasDispatch:->[?:Dispatch]];
    }

    can sku with SKU entry {
        self.skus.append({"id": jid(here), "name": here.name, "code": here.code});
    }
    can lot with Lot entry {
        sku = [here->:ForSKU:->[?:SKU]][0];
        self.lots.append(
            {
                "id": jid(here),
                "sku_id": jid(sku),
                "sequence": here.sequence,
                "received": here.received,
                "available": here.available,
                "dispatched": here.dispatched
            }
        );
    }

    can reservation with Reservation entry {
        self.reservations.append(_reservation_view(here));
    }
    can dispatch with Dispatch entry {
        reservation = [here->:ForReservation:->[?:Reservation]][0];
        self.dispatches.append(
            {
                "id": jid(here),
                "reservation_id": jid(reservation),
                "quantity": here.quantity,
                "reference": here.reference
            }
        );
    }

    can finish with Root exit {
        report {
            "warehouses": self.warehouses,
            "skus": self.skus,
            "lots": self.lots,
            "reservations": self.reservations,
            "dispatches": self.dispatches
        };
    }
}

walker ReceiveStock {
    has sku_id: str,
        quantity: int;

    can receive with Root entry {
        sku = jobj(self.sku_id);
        if not _owned_sku(sku) or self.quantity < 1 {
            report {
                "ok": False,
                "error": "Select an available SKU and a positive receipt quantity"
            };
            return;
        }
        warehouse = cast(Warehouse, _warehouse());
        sequence = len([warehouse->:Stocks:->[?:Lot]]) + 1;
        lot = warehouse +>:Stocks:+> Lot(
            sequence=sequence, received=self.quantity, available=self.quantity
        );
        lot +>:ForSKU:+> sku;
        report {"ok": True, "lot_id": jid(lot)};
    }
}

walker ReserveStock {
    has sku_id: str,
        quantity: int,
        reference: str;

    can reserve with Root entry {
        sku = jobj(self.sku_id);
        if not _owned_sku(sku) or self.quantity < 1 or not self.reference.strip() {
            report {
                "ok": False,
                "error": "Select an available SKU, positive quantity and order reference"
            };
            return;
        }
        warehouse = cast(Warehouse, _warehouse());
        if any(
            item.reference == self.reference.strip()
            for item in [warehouse->:Holds:->[?:Reservation]]
        ) {
            report {"ok": False, "error": "Order reference already has a reservation"};
            return;
        }
        lots = [
            lot
            for lot in [sku<-:ForSKU:<-[?:Lot]]
            if lot.available > 0
        ];
        lots.sort(key=lambda (lot: Lot) { lot.sequence; });
        if sum(lot.available for lot in lots) < self.quantity {
            report {"ok": False, "error": "Insufficient available stock"};
            return;
        }
        reservation = warehouse +>:Holds:+> Reservation(
            reference=self.reference.strip(), quantity=self.quantity
        );
        remaining = self.quantity;
        for lot in lots {
            if remaining == 0 {
                break;
            }
            take = min(remaining, lot.available);
            allocation = reservation +>:HasAllocation:+> Allocation(quantity=take);
            allocation +>:FromLot:+> lot;
            lot.available -= take;
            remaining -= take;
        }
        report {"ok": True, "reservation": _reservation_view(reservation)};
    }
}

walker ReleaseReservation {
    has reservation_id: str;

    can start with Root entry {
        reservation = jobj(self.reservation_id);
        if not _owned_reservation(reservation) {
            report {"ok": False, "error": "Reservation is not available to this user"};
            return;
        }
        reservation = cast(Reservation, reservation);
        if reservation.status != "reserved" {
            report {"ok": False, "error": "Only active reservations can be released"};
            return;
        }
        visit [reservation];
    }

    can reservation with Reservation entry {
        visit [->:HasAllocation:->[?:Allocation]];
    }
    can restore with Allocation entry {
        lot = [->:FromLot:->[?:Lot]][0];
        lot.available += here.quantity;
    }

    can finish with Reservation exit {
        here.status = "released";
        report {"ok": True, "reservation": _reservation_view(here)};
    }
}

walker DispatchReservation {
    has reservation_id: str;

    can start with Root entry {
        reservation = jobj(self.reservation_id);
        if not _owned_reservation(reservation) {
            report {"ok": False, "error": "Reservation is not available to this user"};
            return;
        }
        reservation = cast(Reservation, reservation);
        if reservation.status != "reserved" {
            report {"ok": False, "error": "Only active reservations can be dispatched"};
            return;
        }
        visit [reservation];
    }

    can reservation with Reservation entry {
        visit [->:HasAllocation:->[?:Allocation]];
    }
    can consume with Allocation entry {
        lot = [->:FromLot:->[?:Lot]][0];
        lot.dispatched += here.quantity;
    }

    can finish with Reservation exit {
        here.status = "dispatched";
        warehouse = cast(Warehouse, _warehouse());
        dispatch = warehouse +>:HasDispatch:+> Dispatch(
            quantity=here.quantity, reference="SHIP-" + here.reference
        );
        dispatch +>:ForReservation:+> here;
        report {"ok": True, "reservation": _reservation_view(here)};
    }
}
