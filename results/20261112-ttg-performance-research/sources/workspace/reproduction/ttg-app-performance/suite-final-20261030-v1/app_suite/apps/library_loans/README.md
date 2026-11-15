# LibraryLoans

LibraryLoans tracks book titles, physical copies, patrons, active/returned loans
and FIFO holds. Returning a copy automatically creates a new loan for the first
queued patron; cancelling a hold removes it from that queue while preserving its
history. A copy has at most one active loan, and a patron cannot borrow or queue
the same title twice while their first loan/hold remains active.

Native graph: Library owns Patron, Title and Loan nodes. Title owns Copy and Hold
nodes; Loan links to its Borrower and LoanCopy; Hold links to RequestedBy. Shared
patrons and copies are resolved through actual typed edges. All catalog data is
private to its authenticated librarian user's root.

Seed 42 creates Research Library, Avery/Morgan/Jordan/Casey, two Graph Thinking
copies and one Data Systems copy. Edition strings include the selected seed.
The librarian operates borrowing and holds for the patron records; patrons are
not separate authenticated accounts in this synthetic workload.

```sh
python3 app_suite/evaluate.py --apps library_loans --seed 42 --browser --output /tmp/library-loans-seed42
python3 app_suite/launch.py --state /tmp/library-loans-seed42 --app library_loans --port 18706
```

Run from external-tools with suite prerequisites. Sign in as `user_0000` using
`isolated-suite-seed-password`. Select a patron on a title card, borrow available
copies, queue another patron when all copies are loaned, and return a loan.
The catalog immediately shows the automatic queue fulfillment and new borrower.

The native oracle checks copy uniqueness, duplicate loan/hold rejection, FIFO
position, cancelled-hold skipping, automatic lending, repeat-return prevention,
and cross-user isolation. Browser validation loans both copies, queues a third
patron and returns one copy to trigger fulfillment. Native inspection after
restart verifies the two active borrowers and conserved physical-copy count.
