"""ApprovalDesk: itemized expenses, computed approval routes and single payouts."""

import from typing { cast }

node Expense {
    has title: str,
        status: str = "draft",
        total_cents: int = 0;
}
node LineItem {
    has description: str,
        quantity: int,
        unit_cents: int;
}
node Approver {
    has name: str,
        role: str;
}
node ApprovalStep {
    has position: int,
        decision: str = "pending";
}
node Payment {
    has amount_cents: int,
        reference: str;
}
edge HasLine {}
edge HasStep {}
edge AssignedApprover {}
edge HasPayment {}

def _owns(expense: object) -> bool {
    return isinstance(expense, Expense)
        and jid(expense) in [jid(item) for item in [root-->[?:Expense]]];
}

def _expense_view(expense: Expense) -> dict {
    steps = [];
    for step in [expense->:HasStep:->[?:ApprovalStep]] {
        assigned = [step->:AssignedApprover:->[?:Approver]];
        steps.append(
            {
                "id": jid(step),
                "position": step.position,
                "decision": step.decision,
                "approver": assigned[0].name,
                "role": assigned[0].role
            }
        );
    }
    steps.sort(key=lambda (item: dict) { item["position"]; });
    return {
        "id": jid(expense),
        "title": expense.title,
        "status": expense.status,
        "total_cents": expense.total_cents,
        "lines": [
            {
                "id": jid(line),
                "description": line.description,
                "quantity": line.quantity,
                "unit_cents": line.unit_cents
            } for line in [expense->:HasLine:->[?:LineItem]]
        ],
        "steps": steps,
        "payments": [
            {
                "id": jid(payment),
                "amount_cents": payment.amount_cents,
                "reference": payment.reference
            } for payment in [expense->:HasPayment:->[?:Payment]]
        ]
    };
}

walker Seed {
    has seed: int = 42;

    can seed with Root entry {
        existing = [-->[?:Expense]];
        if existing {
            report {"ok": True, "created": False};
            return;
        }
        here ++> Approver(name="Jordan", role="manager");
        here ++> Approver(name="Casey", role="finance");
        expense = here ++> Expense(title="Conference travel");
        expense +>:HasLine:+> LineItem(
            description="Rail ticket",
            quantity=1,
            unit_cents=10000 + self.seed % 3 * 1000
        );
        expense +>:HasLine:+> LineItem(
            description="Registration", quantity=1, unit_cents=5000
        );
        report {"ok": True, "created": True};
    }
}

walker ExpenseBoard {
    has expenses: list[dict] = [];

    can start with Root entry {
        visit [-->[?:Expense]];
    }
    can collect with Expense entry {
        self.expenses.append(_expense_view(here));
    }
    can finish with Root exit {
        report {"expenses": self.expenses};
    }
}

walker CreateExpense {
    has title: str;

    can create with Root entry {
        if not self.title.strip() {
            report {"ok": False, "error": "Enter an expense title"};
            return;
        }
        expense = here ++> Expense(title=self.title.strip());
        report {"ok": True, "expense": _expense_view(expense)};
    }
}

walker AddLineItem {
    has expense_id: str,
        description: str,
        quantity: int,
        unit_cents: int;

    can add with Root entry {
        expense = jobj(self.expense_id);
        if not _owns(expense) {
            report {"ok": False, "error": "Expense is not available to this user"};
            return;
        }
        expense = cast(Expense, expense);
        if expense.status != "draft" {
            report {"ok": False, "error": "Only draft expenses can be edited"};
            return;
        }
        if not self.description.strip()
            or self.quantity < 1
            or self.quantity > 1000
            or self.unit_cents < 1
            or self.unit_cents > 1000000 {
            report {
                "ok": False,
                "error": "Enter a description, quantity from 1 to 1000 and positive unit price up to 1000000 cents"
            };
            return;
        }
        expense +>:HasLine:+> LineItem(
            description=self.description.strip(),
            quantity=self.quantity,
            unit_cents=self.unit_cents
        );
        report {"ok": True, "expense": _expense_view(expense)};
    }
}

walker SubmitExpense {
    has expense_id: str,
        total: int = 0;

    can start with Root entry {
        expense = jobj(self.expense_id);
        if not _owns(expense) {
            report {"ok": False, "error": "Expense is not available to this user"};
            return;
        }
        expense = cast(Expense, expense);
        if expense.status != "draft" {
            report {"ok": False, "error": "Only draft expenses can be submitted"};
            return;
        }
        visit [expense];
    }

    can expense with Expense entry {
        visit [->:HasLine:->[?:LineItem]];
    }
    can accumulate with LineItem entry {
        self.total += here.quantity * here.unit_cents;
    }
    can route with Expense exit {
        if self.total == 0 {
            report {
                "ok": False,
                "error": "Add at least one line item before submitting"
            };
            return;
        }
        here.total_cents = self.total;
        here.status = "submitted";
        roles = ["manager", "finance"] if self.total > 50000 else ["manager"];
        for i in range(len(roles)) {
            approvers = [
                person
                for person in [root-->[?:Approver]]
                if person.role == roles[i]
            ];
            step = here +>:HasStep:+> ApprovalStep(position=i + 1);
            step +>:AssignedApprover:+> approvers[0];
        }
        report {"ok": True, "expense": _expense_view(here)};
    }
}

walker DecideApproval {
    has step_id: str,
        approve: bool = True;

    can decide with Root entry {
        step = jobj(self.step_id);
        if not isinstance(step, ApprovalStep) {
            report {"ok": False, "error": "Approval step is not available"};
            return;
        }
        requests = [step<-:HasStep:<-[?:Expense]];
        if not requests or not _owns(requests[0]) {
            report {"ok": False, "error": "Expense is not available to this user"};
            return;
        }
        expense = requests[0];
        if expense.status != "submitted" or step.decision != "pending" {
            report {
                "ok": False,
                "error": "Only pending steps in submitted expenses can be decided"
            };
            return;
        }
        steps = [expense->:HasStep:->[?:ApprovalStep]];
        if any(
            item.position < step.position and item.decision != "approved"
            for item in steps
        ) {
            report {"ok": False, "error": "Approval must follow step order"};
            return;
        }
        step.decision = "approved" if self.approve else "rejected";
        if not self.approve {
            expense.status = "rejected";
        } elif all(item.decision == "approved" for item in steps) {
            expense.status = "approved";
        }
        report {"ok": True, "expense": _expense_view(expense)};
    }
}

walker PayExpense {
    has expense_id: str;

    can pay with Root entry {
        expense = jobj(self.expense_id);
        if not _owns(expense) {
            report {"ok": False, "error": "Expense is not available to this user"};
            return;
        }
        expense = cast(Expense, expense);
        if expense.status != "approved" or [expense->:HasPayment:->[?:Payment]] {
            report {
                "ok": False,
                "error": "An expense can be paid once after final approval"
            };
            return;
        }
        expense +>:HasPayment:+> Payment(
            amount_cents=expense.total_cents, reference="PAY-" + jid(expense)
        );
        expense.status = "paid";
        report {"ok": True, "expense": _expense_view(expense)};
    }
}
