"""Account activities, qualification, accepted quotes and revenue forecasts."""
import from typing { cast }
node Account {
    has name: str;
}
node Contact {
    has name: str;
}
node Opportunity {
    has title: str,
        stage: str = "open",
        amount_cents: int = 0;
}
node Activity {
    has note: str,
        sequence: int;
}
node Quote {
    has quantity: int,
        unit_cents: int,
        accepted: bool = False;
}
edge HasContact {}
edge HasOpportunity {}
edge HasActivity {}
edge HasQuote {}
def _account(a: object) -> bool {
    return isinstance(a, Account) and jid(a) in [jid(x) for x in [root-->[?:Account]]];
}
def _opportunity(o: object) -> bool {
    return isinstance(o, Opportunity)
        and any(_account(a) for a in [o<-:HasOpportunity:<-[?:Account]]);
}
walker Seed {
    has seed: int = 42;

    can seed with Root entry {
        if [-->[?:Account]] {
            report {"ok": True};
            return;
        }
        a = here ++> Account(name="North Lab");
        a +>:HasContact:+> Contact(name="Taylor");
        a +>:HasOpportunity:+> Opportunity(title="Sensor renewal");
        b = here ++> Account(name="South Lab");
        b +>:HasContact:+> Contact(name="Blake");
        report {"ok": True, "seed": self.seed};
    }
}

walker SalesBoard {
    has accounts: list[dict] = [],
        won_cents: int = 0;

    can start with Root entry {
        visit [-->[?:Account]];
    }
    can account with Account entry {
        opportunities = [];
        for o in [here->:HasOpportunity:->[?:Opportunity]] {
            opportunities.append(
                {
                    "id": jid(o),
                    "title": o.title,
                    "stage": o.stage,
                    "amount_cents": o.amount_cents,
                    "activities": [a.note for a in [o->:HasActivity:->[?:Activity]]],
                    "quotes": [
                        {
                            "id": jid(q),
                            "total_cents": q.quantity * q.unit_cents,
                            "accepted": q.accepted
                        } for q in [o->:HasQuote:->[?:Quote]]
                    ]
                }
            );
            if o.stage == "won" {
                self.won_cents += o.amount_cents;
            }
        }
        self.accounts.append(
            {
                "id": jid(here),
                "name": here.name,
                "contacts": [c.name for c in [here->:HasContact:->[?:Contact]]],
                "opportunities": opportunities
            }
        );
    }

    can finish with Root exit {
        report {"accounts": self.accounts, "won_cents": self.won_cents};
    }
}

walker CreateOpportunity {
    has account_id: str,
        title: str;

    can create with Root entry {
        a = jobj(self.account_id);
        if not _account(a) or not self.title.strip() {
            report {
                "ok": False,
                "error": "Select an account and enter an opportunity title"
            };
            return;
        }
        a = cast(Account, a);
        o = a +>:HasOpportunity:+> Opportunity(title=self.title.strip());
        report {"ok": True, "opportunity_id": jid(o)};
    }
}

walker LogActivity {
    has opportunity_id: str,
        note: str;

    can log with Root entry {
        o = jobj(self.opportunity_id);
        if not _opportunity(o) or not self.note.strip() {
            report {
                "ok": False,
                "error": "Select an opportunity and enter an activity"
            };
            return;
        }
        o = cast(Opportunity, o);
        if o.stage in ["won", "lost"] {
            report {"ok": False, "error": "Closed opportunities cannot be edited"};
            return;
        }
        o +>:HasActivity:+> Activity(
            note=self.note.strip(), sequence=len([o->:HasActivity:->[?:Activity]]) + 1
        );
        report {"ok": True};
    }
}

walker QualifyOpportunity {
    has opportunity_id: str;

    can qualify with Root entry {
        o = jobj(self.opportunity_id);
        if not _opportunity(o) {
            report {"ok": False, "error": "Opportunity is not available"};
            return;
        }
        o = cast(Opportunity, o);
        if o.stage != "open" or not [o->:HasActivity:->[?:Activity]] {
            report {
                "ok": False,
                "error": "Record an activity before qualifying an open opportunity"
            };
            return;
        }
        o.stage = "qualified";
        report {"ok": True};
    }
}

walker CreateQuote {
    has opportunity_id: str,
        quantity: int,
        unit_cents: int;

    can quote with Root entry {
        o = jobj(self.opportunity_id);
        if not _opportunity(o) {
            report {"ok": False, "error": "Opportunity is not available"};
            return;
        }
        o = cast(Opportunity, o);
        if o.stage != "qualified" or self.quantity < 1 or self.unit_cents < 1 {
            report {
                "ok": False,
                "error": "Qualify the opportunity and enter positive quote values"
            };
            return;
        }
        q = o +>:HasQuote:+> Quote(quantity=self.quantity, unit_cents=self.unit_cents);
        report {"ok": True, "quote_id": jid(q)};
    }
}

walker AcceptQuote {
    has quote_id: str;

    can accept with Root entry {
        q = jobj(self.quote_id);
        if not isinstance(q, Quote)
            or not any(_opportunity(o) for o in [q<-:HasQuote:<-[?:Opportunity]]) {
            report {"ok": False, "error": "Quote is not available"};
            return;
        }
        o = [q<-:HasQuote:<-[?:Opportunity]][0];
        if o.stage != "qualified"
            or any(x.accepted for x in [o->:HasQuote:->[?:Quote]]) {
            report {
                "ok": False,
                "error": "Accept one quote for a qualified opportunity"
            };
            return;
        }
        q.accepted = True;
        report {"ok": True};
    }
}

walker CloseWon {
    has opportunity_id: str;

    can close with Root entry {
        o = jobj(self.opportunity_id);
        if not _opportunity(o) {
            report {"ok": False, "error": "Opportunity is not available"};
            return;
        }
        o = cast(Opportunity, o);
        quotes = [
            q
            for q in [o->:HasQuote:->[?:Quote]]
            if q.accepted
        ];
        if o.stage != "qualified" or len(quotes) != 1 {
            report {
                "ok": False,
                "error": "Accept a quote before closing a qualified opportunity"
            };
            return;
        }
        o.amount_cents = quotes[0].quantity * quotes[0].unit_cents;
        o.stage = "won";
        report {"ok": True};
    }
}
