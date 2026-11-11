# StockRoom

StockRoom receives SKU lots, reserves quantities in FIFO order, restores released
allocations and creates dispatch records. It stores Warehouse, SKU, Lot,
Reservation, Allocation and Dispatch as native Jac nodes with typed relationships.
Lots and reservations share SKU targets through allocations.

`Warehouse -> Stocks -> Lot -> ForSKU -> SKU`,
`Warehouse -> Holds -> Reservation -> HasAllocation -> Allocation -> FromLot -> Lot`,
and `Warehouse -> HasDispatch -> Dispatch -> ForReservation -> Reservation`
form the persistent stock ledger. ReleaseReservation and DispatchReservation use
native visit abilities across allocations before updating reservation state.

Seed 42 creates Research Store, Sensor and Cable SKUs, two Sensor lots of 5 and 7
units, and a Cable lot of 4. Seeds 43 and 44 add 1 and 2 units to the first Sensor
lot. Seed is idempotent. Reservations span lots in ascending receipt order.
Insufficient stock rejects the whole request before any allocation. Released or
dispatched reservations cannot be dispatched again; released stock is available
to subsequent orders. Order references identify reservations uniquely.

```sh
python3 app_suite/evaluate.py --apps stock_room --seed 42 --browser --output /tmp/stock-room-seed42
python3 app_suite/launch.py --state /tmp/stock-room-seed42 --app stock_room --port 18703
```

Run from external-tools with the suite README prerequisites. Sign in as
`user_0000`, password `isolated-suite-seed-password`. Select a SKU, receive stock,
reserve an order, then release or dispatch it. The inventory shows available,
reserved and dispatched quantities and the contributing lots.

The independent native oracle reconstructs active and dispatched allocations
from reservation records. For every lot it verifies:
`received = available + active allocations + dispatched allocations`.
It checks FIFO splits, exact order totals, rejected partial allocations, release
restoration, double-dispatch prevention, receipt changes and cross-user isolation.
Browser validation receives stock, rejects an excessive order, reserves a valid
order and dispatches it. Native inspection after restart checks that shipment
and stock conservation again. Concurrent reservation contention is outside this
sequential workload's validation scope.
