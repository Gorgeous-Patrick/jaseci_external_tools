# EventSeats

EventSeats holds exclusive physical seats, confirms bookings, releases cancelled
seats and records exact refunds for confirmed bookings. A held booking can be
cancelled without a refund; a confirmed booking produces one refund equal to its
total. Repeat cancellation cannot create a second refund.

Native graph: `Venue -> Hosts -> Event -> HasSection -> Section -> HasSeat -> Seat`,
`Event -> HasBooking -> Booking -> Reserves -> Seat`, and
`Booking -> HasRefund -> Refund`. Cancelled bookings retain their seat references
for history; the oracle checks uniqueness among active bookings only.

Seed 42 creates Research Hall, Graph Summit with seats A1/A2/A3 priced at
1000/1200/1400 cents, and a separate Data Workshop with seat B1. Seeds 43/44 add
100/200 cents to each Graph Summit seat. A booking cannot mix seats from events,
repeat a seat, or claim an unavailable seat. Validation precedes every mutation.

```sh
python3 app_suite/evaluate.py --apps event_seats --seed 42 --browser --runtime-source /tmp/ttg-app-suite-runtime-frozen-20261029 --output /tmp/event-seats-seed42
python3 app_suite/launch.py --state /tmp/event-seats-seed42 --app event_seats --port 18707
```

Run from external-tools with suite prerequisites. Sign in as `user_0000` using
`isolated-suite-seed-password`. Check seats, enter a booking reference, hold,
confirm and cancel. The frontend reflects held/sold/available state and refunds.
The authenticated venue operator controls this synthetic booking workflow.

The native oracle checks exact totals, no partial mutation on invalid selections,
seat exclusivity, event boundaries, reference uniqueness, cancellation/refund
rules and ownership. Browser checks the entire hold/confirm/cancel flow; native
inspection after restart checks refunded amount and available seats. Concurrent
contention and external payment processing are outside this sequential workload.
