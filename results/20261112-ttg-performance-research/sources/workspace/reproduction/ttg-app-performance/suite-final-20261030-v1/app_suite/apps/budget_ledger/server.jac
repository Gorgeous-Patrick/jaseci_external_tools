"""Envelope budgeting with categorical expenses and balanced transfer entries."""
import from typing { cast }
node Budget {
    has name: str,
        initial: int,
        unallocated: int;
}
node Envelope {
    has name: str,
        balance: int = 0;
}
node Category {
    has name: str;
}
node Entry {
    has amount: int,
        kind: str;
}
node Transfer {
    has reference: str,
        amount: int;
}
edge HasEnvelope {}
edge HasCategory {}
edge HasEntry {}
edge CategoryRef {}
edge HasTransfer {}
edge FromEnvelope {}
edge ToEnvelope {}
def _budget -> Budget | None {
    b = [root-->[?:Budget]];
    return b[0] if b else None;
}
def _envelope(e: object) -> bool {
    b = _budget();
    return b is not None
        and isinstance(e, Envelope)
        and jid(e) in [jid(x) for x in [b->:HasEnvelope:->[?:Envelope]]];
}
walker Seed {
    has seed: int = 42;

    can seed with Root entry {
        if [-->[?:Budget]] {
            report {"ok": True};
            return;
        }
        total = 100000 + self.seed % 3 * 10000;
        b = here ++> Budget(name="Lab budget", initial=total, unallocated=total);
        b +>:HasEnvelope:+> Envelope(name="Equipment");
        b +>:HasEnvelope:+> Envelope(name="Travel");
        b +>:HasCategory:+> Category(name="Supplies");
        b +>:HasCategory:+> Category(name="Transport");
        report {"ok": True};
    }
}

walker BudgetBoard {
    has budgets: list[dict] = [],
        envelopes: list[dict] = [],
        categories: list[dict] = [],
        transfers: list[dict] = [];

    can start with Root entry {
        visit [-->[?:Budget]];
    }
    can budget with Budget entry {
        self.budgets.append(
            {
                "id": jid(here),
                "name": here.name,
                "initial": here.initial,
                "unallocated": here.unallocated
            }
        );
        visit [->:HasEnvelope:->[?:Envelope]];
        visit [->:HasCategory:->[?:Category]];
        visit [->:HasTransfer:->[?:Transfer]];
    }
    can envelope with Envelope entry {
        self.envelopes.append(
            {
                "id": jid(here),
                "name": here.name,
                "balance": here.balance,
                "entries": [
                    {"amount": e.amount, "kind": e.kind}
                    for e in [here->:HasEntry:->[?:Entry]]
                ]
            }
        );
    }
    can category with Category entry {
        self.categories.append({"id": jid(here), "name": here.name});
    }
    can transfer with Transfer entry {
        self.transfers.append({"reference": here.reference, "amount": here.amount});
    }
    can finish with Root exit {
        report {
            "budgets": self.budgets,
            "envelopes": self.envelopes,
            "categories": self.categories,
            "transfers": self.transfers
        };
    }
}

walker AllocateBudget {
    has envelope_id: str,
        amount: int;

    can allocate with Root entry {
        e = jobj(self.envelope_id);
        b = _budget();
        if b is None
            or not _envelope(e)
            or self.amount < 1
            or self.amount > b.unallocated {
            report {"ok": False, "error": "Allocation exceeds unallocated budget"};
            return;
        }
        e = cast(Envelope, e);
        b.unallocated -= self.amount;
        e.balance += self.amount;
        e +>:HasEntry:+> Entry(amount=self.amount, kind="allocation");
        report {"ok": True};
    }
}

walker SpendEnvelope {
    has envelope_id: str,
        category_id: str,
        amount: int;

    can spend with Root entry {
        e = jobj(self.envelope_id);
        c = jobj(self.category_id);
        b = _budget();
        if b is None
            or not _envelope(e)
            or not isinstance(c, Category)
            or self.category_id
                not in [jid(x) for x in [b->:HasCategory:->[?:Category]]] {
            report {"ok": False, "error": "Envelope or category is not available"};
            return;
        }
        e = cast(Envelope, e);
        if self.amount < 1 or self.amount > e.balance {
            report {"ok": False, "error": "Expense exceeds envelope balance"};
            return;
        }
        e.balance -= self.amount;
        ledger_entry = e +>:HasEntry:+> Entry(amount=-self.amount, kind="expense");
        ledger_entry +>:CategoryRef:+> c;
        report {"ok": True};
    }
}

walker TransferBudget {
    has source_id: str,
        target_id: str,
        amount: int,
        reference: str;

    can transfer with Root entry {
        source = jobj(self.source_id);
        target = jobj(self.target_id);
        b = _budget();
        if b is None or not _envelope(source) or not _envelope(target) {
            report {"ok": False, "error": "Transfer envelopes are not available"};
            return;
        }
        source = cast(Envelope, source);
        target = cast(Envelope, target);
        if self.source_id == self.target_id
            or self.amount < 1
            or self.amount > source.balance
            or not self.reference.strip()
            or any(
                t.reference == self.reference.strip()
                for t in [b->:HasTransfer:->[?:Transfer]]
            ) {
            report {
                "ok": False,
                "error": "Transfer needs distinct envelopes, available funds and a unique reference"
            };
            return;
        }
        source.balance -= self.amount;
        target.balance += self.amount;
        source +>:HasEntry:+> Entry(amount=-self.amount, kind="transfer");
        target +>:HasEntry:+> Entry(amount=self.amount, kind="transfer");
        t = b +>:HasTransfer:+> Transfer(
            reference=self.reference.strip(), amount=self.amount
        );
        t +>:FromEnvelope:+> source;
        t +>:ToEnvelope:+> target;
        report {"ok": True};
    }
}
