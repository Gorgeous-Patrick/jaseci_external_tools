"""Quantity-bounded merchandise returns, inspection decisions and single refunds."""
import from typing { cast }
node Order {
    has reference: str;
}
node OrderLine {
    has name: str,
        quantity: int,
        unit_cents: int;
}
node ReturnRequest {
    has reference: str,
        quantity: int,
        status: str = "requested";
}
node Inspection {
    has accepted: bool;
}
node Refund {
    has cents: int;
}
edge HasLine {}
edge HasReturn {}
edge HasInspection {}
edge HasRefund {}
def _line(l: object) -> bool {
    return isinstance(l, OrderLine)
        and any(
            jid(o) in [jid(x) for x in [root-->[?:Order]]]
            for o in [l<-:HasLine:<-[?:Order]]
        );
}
def _return(r: object) -> bool {
    return isinstance(r, ReturnRequest)
        and any(_line(l) for l in [r<-:HasReturn:<-[?:OrderLine]]);
}
walker Seed {
    has seed: int = 42;

    can seed with Root entry {
        if [-->[?:Order]] {
            report {"ok": True};
            return;
        }
        o = here ++> Order(reference="ORDER-" + str(self.seed));
        o +>:HasLine:+> OrderLine(
            name="Sensor pack", quantity=3, unit_cents=1000 + self.seed % 3 * 100
        );
        o +>:HasLine:+> OrderLine(name="Cable pack", quantity=5, unit_cents=200);
        report {"ok": True};
    }
}

walker ReturnBoard {
    has orders: list[dict] = [];

    can start with Root entry {
        visit [-->[?:Order]];
    }
    can order with Order entry {
        self.orders.append(
            {
                "id": jid(here),
                "reference": here.reference,
                "lines": [
                    {
                        "id": jid(l),
                        "name": l.name,
                        "quantity": l.quantity,
                        "unit_cents": l.unit_cents,
                        "returns": [
                            {
                                "id": jid(r),
                                "reference": r.reference,
                                "quantity": r.quantity,
                                "status": r.status,
                                "refunds": [
                                    f.cents for f in [r->:HasRefund:->[?:Refund]]
                                ]
                            } for r in [l->:HasReturn:->[?:ReturnRequest]]
                        ]
                    } for l in [here->:HasLine:->[?:OrderLine]]
                ]
            }
        );
    }
    can finish with Root exit {
        report {"orders": self.orders};
    }
}

walker RequestReturn {
    has line_id: str,
        quantity: int,
        reference: str;

    can request with Root entry {
        l = jobj(self.line_id);
        if not _line(l) {
            report {"ok": False, "error": "Order line is not available"};
            return;
        }
        l = cast(OrderLine, l);
        rows = [l->:HasReturn:->[?:ReturnRequest]];
        used = sum(
            r.quantity
            for r in rows
            if r.status != "rejected"
        );
        if self.quantity < 1
            or used + self.quantity > l.quantity
            or not self.reference.strip()
            or any(r.reference == self.reference.strip() for r in rows) {
            report {
                "ok": False,
                "error": "Return quantity exceeds remaining purchased units or reference is duplicated"
            };
            return;
        }
        r = l +>:HasReturn:+> ReturnRequest(
            reference=self.reference.strip(), quantity=self.quantity
        );
        report {"ok": True, "return_id": jid(r)};
    }
}

walker InspectReturn {
    has return_id: str,
        accepted: bool;

    can inspect with Root entry {
        r = jobj(self.return_id);
        if not _return(r) {
            report {"ok": False, "error": "Return is not available"};
            return;
        }
        r = cast(ReturnRequest, r);
        if r.status != "requested" {
            report {"ok": False, "error": "Only requested returns may be inspected"};
            return;
        }
        r +>:HasInspection:+> Inspection(accepted=self.accepted);
        r.status = "approved" if self.accepted else "rejected";
        report {"ok": True};
    }
}

walker RefundReturn {
    has return_id: str;

    can refund with Root entry {
        r = jobj(self.return_id);
        if not _return(r) {
            report {"ok": False, "error": "Return is not available"};
            return;
        }
        r = cast(ReturnRequest, r);
        if r.status != "approved" or [r->:HasRefund:->[?:Refund]] {
            report {
                "ok": False,
                "error": "Refund an inspected approved return only once"
            };
            return;
        }
        l = [r<-:HasReturn:<-[?:OrderLine]][0];
        cents = r.quantity * l.unit_cents;
        r +>:HasRefund:+> Refund(cents=cents);
        r.status = "refunded";
        report {"ok": True, "cents": cents};
    }
}
