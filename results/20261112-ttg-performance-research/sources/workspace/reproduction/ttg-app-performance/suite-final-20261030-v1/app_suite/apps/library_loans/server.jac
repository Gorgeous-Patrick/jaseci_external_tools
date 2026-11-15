"""LibraryLoans: copy loans, FIFO holds and automatic fulfillment on return."""

import from typing { cast }

node Library {
    has name: str;
}
node Patron {
    has name: str;
}
node Title {
    has name: str,
        edition: str;
}
node Copy {
    has barcode: str,
        available: bool = True;
}
node Loan {
    has status: str = "active";
}
node Hold {
    has position: int,
        status: str = "queued";
}
edge HasPatron {}
edge HasTitle {}
edge HasCopy {}
edge HasLoan {}
edge Borrower {}
edge LoanCopy {}
edge HasHold {}
edge RequestedBy {}

def _library -> Library | None {
    items = [root-->[?:Library]];
    return items[0] if items else None;
}

def _owns_title(title: object) -> bool {
    library = _library();
    return library is not None
        and isinstance(title, Title)
        and jid(title) in [jid(item) for item in [library->:HasTitle:->[?:Title]]];
}

def _owns_patron(patron: object) -> bool {
    library = _library();
    return library is not None
        and isinstance(patron, Patron)
        and jid(patron) in [jid(item) for item in [library->:HasPatron:->[?:Patron]]];
}

def _borrowed_title(patron: Patron, title: Title) -> bool {
    for loan in [patron<-:Borrower:<-[?:Loan]] {
        if loan.status == "active" {
            copy = [loan->:LoanCopy:->[?:Copy]][0];
            if jid(title) in [jid(item) for item in [copy<-:HasCopy:<-[?:Title]]] {
                return True;
            }
        }
    }
    return False;
}

def _lend(library: Library, copy: Copy, patron: Patron) -> str {
    loan = library +>:HasLoan:+> Loan();
    loan +>:LoanCopy:+> copy;
    loan +>:Borrower:+> patron;
    copy.available = False;
    return jid(loan);
}

walker Seed {
    has seed: int = 42;

    can seed with Root entry {
        if [-->[?:Library]] {
            report {"ok": True, "created": False};
            return;
        }
        library = here ++> Library(name="Research Library");
        for name in ["Avery", "Morgan", "Jordan", "Casey"] {
            library +>:HasPatron:+> Patron(name=name);
        }
        graph = library +>:HasTitle:+> Title(
            name="Graph Thinking", edition="Edition " + str(self.seed)
        );
        graph +>:HasCopy:+> Copy(barcode="GT-001");
        graph +>:HasCopy:+> Copy(barcode="GT-002");
        data = library +>:HasTitle:+> Title(
            name="Data Systems", edition="Edition " + str(self.seed)
        );
        data +>:HasCopy:+> Copy(barcode="DS-001");
        report {"ok": True, "created": True};
    }
}

walker LibraryCatalog {
    has libraries: list[dict] = [],
        patrons: list[dict] = [],
        titles: list[dict] = [],
        loans: list[dict] = [];

    can start with Root entry {
        visit [-->[?:Library]];
    }
    can library with Library entry {
        self.libraries.append({"id": jid(here), "name": here.name});
        visit [->:HasPatron:->[?:Patron]];
        visit [->:HasTitle:->[?:Title]];
        visit [->:HasLoan:->[?:Loan]];
    }

    can patron with Patron entry {
        self.patrons.append({"id": jid(here), "name": here.name});
    }
    can title with Title entry {
        holds = [];
        for hold in [here->:HasHold:->[?:Hold]] {
            patron = [hold->:RequestedBy:->[?:Patron]][0];
            holds.append(
                {
                    "id": jid(hold),
                    "patron_id": jid(patron),
                    "patron": patron.name,
                    "position": hold.position,
                    "status": hold.status
                }
            );
        }
        self.titles.append(
            {
                "id": jid(here),
                "name": here.name,
                "edition": here.edition,
                "copies": [
                    {
                        "id": jid(copy),
                        "barcode": copy.barcode,
                        "available": copy.available
                    } for copy in [here->:HasCopy:->[?:Copy]]
                ],
                "holds": holds
            }
        );
    }

    can loan with Loan entry {
        patron = [here->:Borrower:->[?:Patron]][0];
        copy = [here->:LoanCopy:->[?:Copy]][0];
        title = [copy<-:HasCopy:<-[?:Title]][0];
        self.loans.append(
            {
                "id": jid(here),
                "patron_id": jid(patron),
                "patron": patron.name,
                "copy_id": jid(copy),
                "title_id": jid(title),
                "title": title.name,
                "status": here.status
            }
        );
    }

    can finish with Root exit {
        report {
            "libraries": self.libraries,
            "patrons": self.patrons,
            "titles": self.titles,
            "loans": self.loans
        };
    }
}

walker BorrowTitle {
    has title_id: str,
        patron_id: str;

    can borrow with Root entry {
        title = jobj(self.title_id);
        patron = jobj(self.patron_id);
        if not _owns_title(title) or not _owns_patron(patron) {
            report {"ok": False, "error": "Select an available title and patron"};
            return;
        }
        title = cast(Title, title);
        patron = cast(Patron, patron);
        if _borrowed_title(patron, title) {
            report {
                "ok": False,
                "error": "Patron already has an active loan for this title"
            };
            return;
        }
        if [title->:HasHold:->[?:Hold, status=="queued"]] {
            report {"ok": False, "error": "Queued holds have priority"};
            return;
        }
        available = [title->:HasCopy:->[?:Copy, available==True]];
        if not available {
            report {"ok": False, "error": "No copy is available; place a hold"};
            return;
        }
        report {
            "ok": True,
            "loan_id": _lend(cast(Library, _library()), available[0], patron)
        };
    }
}

walker PlaceHold {
    has title_id: str,
        patron_id: str;

    can hold with Root entry {
        title = jobj(self.title_id);
        patron = jobj(self.patron_id);
        if not _owns_title(title) or not _owns_patron(patron) {
            report {"ok": False, "error": "Select an available title and patron"};
            return;
        }
        title = cast(Title, title);
        patron = cast(Patron, patron);
        if [title->:HasCopy:->[?:Copy, available==True]] {
            report {"ok": False, "error": "An available copy can be borrowed directly"};
            return;
        }
        if _borrowed_title(patron, title) {
            report {
                "ok": False,
                "error": "Patron already has an active loan for this title"
            };
            return;
        }
        holds = [title->:HasHold:->[?:Hold]];
        for hold in holds {
            if hold.status == "queued"
                and self.patron_id
                    in [jid(item) for item in [hold->:RequestedBy:->[?:Patron]]] {
                report {"ok": False, "error": "Patron already has a queued hold"};
                return;
            }
        }
        hold = title +>:HasHold:+> Hold(position=len(holds) + 1);
        hold +>:RequestedBy:+> patron;
        report {"ok": True, "hold_id": jid(hold)};
    }
}

walker CancelHold {
    has hold_id: str;

    can cancel with Root entry {
        hold = jobj(self.hold_id);
        if not isinstance(hold, Hold) {
            report {"ok": False, "error": "Hold is not available"};
            return;
        }
        titles = [hold<-:HasHold:<-[?:Title]];
        if not titles or not _owns_title(titles[0]) {
            report {"ok": False, "error": "Hold is not available to this user"};
            return;
        }
        if hold.status != "queued" {
            report {"ok": False, "error": "Only queued holds can be cancelled"};
            return;
        }
        hold.status = "cancelled";
        report {"ok": True};
    }
}

walker ReturnLoan {
    has loan_id: str;

    can return_loan with Root entry {
        loan = jobj(self.loan_id);
        library = _library();
        if library is None
            or not isinstance(loan, Loan)
            or jid(loan)
                not in [jid(item) for item in [library->:HasLoan:->[?:Loan]]] {
            report {"ok": False, "error": "Loan is not available to this user"};
            return;
        }
        if loan.status != "active" {
            report {"ok": False, "error": "Only active loans can be returned"};
            return;
        }
        copy = [loan->:LoanCopy:->[?:Copy]][0];
        title = [copy<-:HasCopy:<-[?:Title]][0];
        loan.status = "returned";
        copy.available = True;
        pending = [title->:HasHold:->[?:Hold, status=="queued"]];
        pending.sort(key=lambda (hold: Hold) { hold.position; });
        next_loan = "";
        if pending {
            hold = pending[0];
            patron = [hold->:RequestedBy:->[?:Patron]][0];
            next_loan = _lend(library, copy, patron);
            hold.status = "fulfilled";
        }
        report {"ok": True, "fulfilled_loan_id": next_loan};
    }
}
