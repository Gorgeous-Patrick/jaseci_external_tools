# ApprovalDesk

ApprovalDesk records itemized expenses, computes an approval route from native
line-item traversal, enforces ordered decisions, and permits exactly one payment.
All amounts are integer cents.

Graph: `Expense -> HasLine -> LineItem`, `Expense -> HasStep -> ApprovalStep`,
`ApprovalStep -> AssignedApprover -> Approver`, and `Expense -> HasPayment -> Payment`.
Expenses share the manager Jordan and finance approver Casey. Each expense stays
private to its authenticated owner's root.

Seed 42 creates Conference travel with a 10000-cent rail ticket and 5000-cent
registration. Seeds 43 and 44 increase the ticket by 1000 and 2000 cents.
SubmitExpense visits LineItem nodes, accumulates quantity times unit price, then
uses that computed value in its Expense exit ability to choose one approval
step or two. Amounts above 50000 cents require manager approval followed by finance.
Drafts need at least one item; submitted lines cannot be edited. A rejection
ends the request without payment; approved expenses can be paid once.

The owner operates this evaluation workflow, including recording decisions for
named approvers. Separate authenticated approver-role accounts are not modeled.

```sh
python3 app_suite/evaluate.py --apps approval_desk --seed 42 --browser --output /tmp/approval-desk-seed42
python3 app_suite/launch.py --state /tmp/approval-desk-seed42 --app approval_desk --port 18702
```

Run from external-tools; suite README lists prerequisites. Sign in as `user_0000`
with `isolated-suite-seed-password`. Create an expense, add line items, submit,
record approvals in order and pay. The browser oracle also attempts finance
approval before manager approval and checks the rejection.

Native correctness checks cover seed idempotence, item validation, both routes,
exact totals, editing restrictions, approval ordering, rejection, early/double
payment prevention, payout conservation and cross-user isolation. Exact board
state must survive restart. Browser-created payment is checked through native
walkers after another restart. Native and browser acceptance remain pending until
the corresponding run's summary records passed gates.
