"""TPC-C on jac (jaseci-pg arm): warehouse account root owns the operational
graph (Warehouse -> District -> Customer -> Order -> OrderLine, Warehouse ->
Stock); the item catalog lives under a SEPARATE catalog account root and is
read cross-root (Stock -:Of:-> Item edges + price reads inside New-Order).

Transaction rollback note (phase 4 work-leveling, 2026-08-14): the jac-lti
arm's validate-first rewrite (resolve every item/stock before ANY mutation)
was a workaround for LTI having no declarative abort surface. The pg-native
runtime DOES have one: an unhandled exception raised inside a walker's `can
run` body is caught by the server's request handler, which calls
`ctx.mem.abort()` -> `Session.abort()` -> `self.store.rollback()` (a real
Postgres ROLLBACK of the whole in-flight transaction, plus eviction of the
dirty in-memory cache) before returning `{"error": ...}` to the client -
see jaclang/runtimelib/impl/server.impl.jac:_run_function_with_occ and
jaclang/runtimelib/impl/session.impl.jac:Session.abort. New-Order below
processes order lines IN ORDER (mutating Stock + creating OrderLine as it
goes, matching the TPC-C spec's own sequencing) and `raise`s on the first
missing item/stock instead of pre-scanning; the driver's 1%-invalid-item
case always puts the bad item LAST in the line list, so this exercises a
genuine half-applied-then-rolled-back transaction (some OrderLines + Stock
mutations + the Order node itself are created, then reverted by the real
ROLLBACK) rather than validate-first's write-nothing shortcut. Burden delta:
hand-tuning 1 -> 0, dbloc 48 -> 41 (no separate resolved-list pre-pass).
"""

# burden: bench=tpcc feature=schema arm=jaseci-pg
# burden: dbloc=54 notations=[jac] entity-reps=1 hand-tuning=0

import time;
import datetime;
import from typing { cast }

def _now -> str {
    return datetime.datetime.now(datetime.UTC).replace(tzinfo=None).isoformat() + "Z";
}

edge Placed {}
edge Of {}

node Warehouse {
    has w_id: int = 0,
        w_name: str = "",
        w_street_1: str = "",
        w_street_2: str = "",
        w_city: str = "",
        w_state: str = "",
        w_zip: str = "",
        w_tax: float = 0.0,
        w_ytd: float = 0.0;
}

node District {
    has d_id: int = 0,
        d_name: str = "",
        d_street_1: str = "",
        d_street_2: str = "",
        d_city: str = "",
        d_state: str = "",
        d_zip: str = "",
        d_tax: float = 0.0,
        d_ytd: float = 0.0,
        d_next_o_id: int = 1;
}

node Customer {
    has c_id: int = 0,
        c_first: str = "",
        c_middle: str = "",
        c_last: str = "",
        c_street_1: str = "",
        c_street_2: str = "",
        c_city: str = "",
        c_state: str = "",
        c_zip: str = "",
        c_phone: str = "",
        c_since: str = "",
        c_credit: str = "",
        c_credit_lim: float = 0.0,
        c_discount: float = 0.0,
        c_balance: float = 0.0,
        c_ytd_payment: float = 0.0,
        c_payment_cnt: int = 0,
        c_delivery_cnt: int = 0,
        c_data: str = "";
}

node History {
    has h_d_id: int = 0,
        h_w_id: int = 0,
        h_date: str = "",
        h_amount: float = 0.0,
        h_data: str = "";
}

node Item {
    has i_id: int = 0,
        i_im_id: int = 0,
        i_name: str = "",
        i_price: float = 0.0,
        i_data: str = "";
}

node Stock {
    has s_i_id: int = 0,
        s_quantity: int = 0,
        s_dist: list[str] = [],
        s_ytd: int = 0,
        s_order_cnt: int = 0,
        s_remote_cnt: int = 0,
        s_data: str = "";
}

node Order {
    has o_id: int = 0,
        o_c_id: int = 0,
        o_d_id: int = 0,
        o_entry_d: str = "",
        o_carrier_id: int = 0,
        o_ol_cnt: int = 0,
        o_all_local: int = 1,
        new_order: bool = False;
}

node OrderLine {
    has ol_number: int = 0,
        ol_i_id: int = 0,
        ol_supply_w_id: int = 0,
        ol_delivery_d: str = "",
        ol_quantity: int = 0,
        ol_amount: float = 0.0,
        ol_dist_info: str = "";
}

# burden: bench=tpcc feature=new_order arm=jaseci-pg
# burden: dbloc=41 notations=[jac] entity-reps=1 hand-tuning=0
walker new_order {
    has district_id: str = "",
        customer_id: str = "",
        lines: list[dict] = [],
        t0: float = 0.0;

    can run with Root entry {
        self.t0 = time.perf_counter();
        wh_list = [-->[?:Warehouse]];
        if not wh_list {
            report {"success": False, "error": "no warehouse"};
            return;
        }
        wh = wh_list[0];

        district = jobj(self.district_id);
        customer = jobj(self.customer_id);
        if not isinstance(district, District) or not isinstance(customer, Customer) {
            report {"success": False, "error": "bad district/customer"};
            return;
        }

        o_id = district.d_next_o_id;
        district.d_next_o_id += 1;

        all_local = int(all(l["supply_w_id"] == wh.w_id for l in self.lines));

        order = cast(Order, customer +>:Placed():+> Order(
            o_id=o_id,
            o_c_id=customer.c_id,
            o_d_id=district.d_id,
            o_entry_d=_now(),
            o_carrier_id=0,
            o_ol_cnt=len(self.lines),
            o_all_local=all_local,
            new_order=True
        ));

        total = 0.0;
        for (num, l) in enumerate(self.lines, 1) {
            item = jobj(l["item_id"]);
            stock = jobj(l["stock_id"]);
            if not isinstance(item, Item) or not isinstance(stock, Stock) {
                # native abort: the server's exception handler rolls back the
                # WHOLE transaction (order + any earlier lines already
                # created in this loop) via ctx.mem.abort() -> real Postgres
                # ROLLBACK. See module docstring.
                raise ValueError("item not found");
            }
            qty = l["quantity"];
            new_q = stock.s_quantity - qty;
            stock.s_quantity = new_q + 91 if new_q < 10 else new_q;
            stock.s_ytd += qty;
            stock.s_order_cnt += 1;
            if l["supply_w_id"] != wh.w_id {
                stock.s_remote_cnt += 1;
            }
            amount = round(qty * item.i_price, 2);
            total += amount;
            order ++> OrderLine(
                ol_number=num,
                ol_i_id=item.i_id,
                ol_supply_w_id=l["supply_w_id"],
                ol_delivery_d="",
                ol_quantity=qty,
                ol_amount=amount,
                ol_dist_info=stock.s_dist[district.d_id - 1]
            );
        }
        total = round(total * (1 - customer.c_discount) * (1 + wh.w_tax + district.d_tax), 2);
        report {"success": True, "o_id": o_id, "total": total, "ol_cnt": len(self.lines)};
    }
}

# burden: bench=tpcc feature=payment arm=jaseci-pg
# burden: dbloc=37 notations=[jac] entity-reps=1 hand-tuning=0
# (by-last-name lookup rewritten from a python for-loop filter to a
#  compiler-pushdown archetype filter -- see work-leveling note inline)
walker payment {
    has district_id: str = "",
        c_district_id: str = "",
        customer_id: str = "",
        c_last: str = "",
        amount: float = 0.0,
        t0: float = 0.0;

    can run with Root entry {
        self.t0 = time.perf_counter();
        wh_list = [-->[?:Warehouse]];
        if not wh_list {
            report {"success": False, "error": "no warehouse"};
            return;
        }
        wh = wh_list[0];
        district = jobj(self.district_id);
        if not isinstance(district, District) {
            report {"success": False, "error": "bad district"};
            return;
        }

        customer = None;
        if self.customer_id {
            c = jobj(self.customer_id);
            if isinstance(c, Customer) {
                customer = c;
            }
        } else {
            c_district = jobj(self.c_district_id);
            if isinstance(c_district, District) {
                # compiler-pushdown filter (not a python loop): compiles
                # through compile_query()/sqlcompile and, with c_last
                # promoted in jac.toml [database.indexes], resolves via the
                # generated+indexed column under JAC_PROMOTED_PREDICATES
                # instead of a jsonb-path scan. See work-leveling note below.
                matches = [c_district-->[?:Customer, c_last == self.c_last]];
                if matches {
                    matches.sort(key=lambda (c: Customer) { c.c_first; });
                    customer = matches[len(matches) // 2];
                }
            }
        }
        if customer is None {
            report {"success": False, "error": "customer not found"};
            return;
        }

        wh.w_ytd += self.amount;
        district.d_ytd += self.amount;
        customer.c_balance -= self.amount;
        customer.c_ytd_payment += self.amount;
        customer.c_payment_cnt += 1;
        if customer.c_credit == "BC" {
            history_prefix = str(customer.c_id) + "," + str(district.d_id) + "," + str(wh.w_id) + "," + str(round(self.amount, 2)) + "|";
            customer.c_data = (history_prefix + customer.c_data)[:500];
        }
        customer ++> History(
            h_d_id=district.d_id,
            h_w_id=wh.w_id,
            h_date=_now(),
            h_amount=self.amount,
            h_data=wh.w_name + "    " + district.d_name
        );
        report {"success": True, "c_id": customer.c_id, "amount": self.amount};
    }
}

# ---- read-only support queries (used by bulk-loader oracle + future
# order-status/stock-level features) ----

# burden: bench=tpcc feature=district_fetch arm=jac-lti
# burden: dbloc=8 notations=[jac] entity-reps=1 hand-tuning=0
walker get_district {
    has district_id: str = "";

    can run with Root entry {
        d = jobj(self.district_id);
        if not isinstance(d, District) {
            report {"error": "not found"};
            return;
        }
        report {"d_id": d.d_id, "d_name": d.d_name, "d_tax": d.d_tax,
                "d_ytd": d.d_ytd, "d_next_o_id": d.d_next_o_id};
    }
}

# burden: bench=tpcc feature=customer_lookup arm=jac-lti
# burden: dbloc=8 notations=[jac] entity-reps=1 hand-tuning=0
walker get_customer {
    has customer_id: str = "";

    can run with Root entry {
        c = jobj(self.customer_id);
        if not isinstance(c, Customer) {
            report {"error": "not found"};
            return;
        }
        report {"c_id": c.c_id, "c_last": c.c_last, "c_credit": c.c_credit,
                "c_balance": c.c_balance, "c_ytd_payment": c.c_ytd_payment};
    }
}

# burden: bench=tpcc feature=stock_check arm=jac-lti
# burden: dbloc=12 notations=[jac] entity-reps=1 hand-tuning=0
# (hand-tuning: cross-root Of hop to read the catalog price alongside stock)
walker get_stock {
    has stock_id: str = "";

    can run with Root entry {
        s = jobj(self.stock_id);
        if not isinstance(s, Stock) {
            report {"error": "not found"};
            return;
        }
        price = -1.0;
        items = [s->:Of:->[?:Item]];
        if items {
            price = items[0].i_price;
        }
        report {"s_i_id": s.s_i_id, "s_quantity": s.s_quantity,
                "s_ytd": s.s_ytd, "i_price": price};
    }
}

# burden: bench=tpcc feature=item_lookup arm=jac-lti
# burden: dbloc=6 notations=[jac] entity-reps=1 hand-tuning=0
walker get_item {
    has item_id: str = "";

    can run with Root entry {
        i = jobj(self.item_id);
        if not isinstance(i, Item) {
            report {"error": "not found"};
            return;
        }
        report {"i_id": i.i_id, "i_name": i.i_name, "i_price": i.i_price};
    }
}

# New ports below are separate from the inherited two-transaction source.
import from fixture_loader { seed_graph }
walker Seed {
    has directory: str, catalog_root_jid: str;
    can seed with Root entry {
        if [-->[?:Warehouse]] { raise ValueError("Warehouse fixture already exists"); }
        report seed_graph(self.directory, self.catalog_root_jid,
            {"Warehouse": Warehouse, "District": District, "Customer": Customer,
             "History": History, "Item": Item, "Stock": Stock, "Order": Order, "OrderLine": OrderLine},
            {"Placed": Placed, "Of": Of});
    }
}
walker order_status {
    has district_id: str, customer_id: str = "", c_last: str = "";
    can run with Root entry {
        district = cast(District, jobj(self.district_id));
        customers: list[Customer] = [];
        if self.customer_id { customers = [cast(Customer, jobj(self.customer_id))]; }
        else {
            customers = [district-->[?:Customer, c_last == self.c_last]];
            customers.sort(key=lambda (c: Customer) { c.c_first; });
        }
        if not customers { raise ValueError("Customer not found"); }
        customer = customers[(len(customers) - 1) // 2];
        orders = [customer->:Placed:->[?:Order]];
        orders.sort(key=lambda (o: Order) { -o.o_id; });
        if not orders { raise ValueError("Order not found"); }
        order = orders[0];
        lines = [order-->[?:OrderLine]];
        lines.sort(key=lambda (line: OrderLine) { line.ol_number; });
        report {"customer": {"id": customer.c_id, "first": customer.c_first,
            "middle": customer.c_middle, "last": customer.c_last, "balance": customer.c_balance},
            "order": {"id": order.o_id, "entry_date": order.o_entry_d, "carrier_id": order.o_carrier_id},
            "lines": [{"item_id": line.ol_i_id, "supply_warehouse_id": line.ol_supply_w_id,
                "quantity": line.ol_quantity, "amount": line.ol_amount,
                "delivery_date": line.ol_delivery_d} for line in lines]};
    }
}
walker delivery {
    has carrier_id: int;
    can run with Root entry {
        warehouses = [-->[?:Warehouse]];
        if len(warehouses) != 1 or self.carrier_id < 1 or self.carrier_id > 10 { raise ValueError("Invalid warehouse or carrier"); }
        warehouse = warehouses[0];
        timestamp = _now(); completed: list[dict] = [];
        for district in [warehouse-->[?:District]] {
            candidates: list[Order] = [];
            for customer in [district-->[?:Customer]] {
                candidates.extend([customer->:Placed:->[?:Order, new_order == True]]);
            }
            candidates.sort(key=lambda (o: Order) { o.o_id; });
            if candidates {
                order = candidates[0]; order.new_order = False; order.o_carrier_id = self.carrier_id;
                amount = 0.0;
                for line in [order-->[?:OrderLine]] { line.ol_delivery_d = timestamp; amount += line.ol_amount; }
                customers = [order<-:Placed:<-[?:Customer]];
                if len(customers) != 1 { raise ValueError("Order owner missing"); }
                customers[0].c_balance += amount; customers[0].c_delivery_cnt += 1;
                completed.append({"district_id": district.d_id, "order_id": order.o_id});
            }
        }
        completed.sort(key=lambda (row: dict) { row["district_id"]; });
        report {"delivered": completed};
    }
}
walker stock_level {
    has district_id: str, threshold: int;
    can run with Root entry {
        district = cast(District, jobj(self.district_id));
        warehouses = [-->[?:Warehouse]];
        if len(warehouses) != 1 { raise ValueError("Warehouse missing"); }
        warehouse = warehouses[0];
        item_ids: dict = {};
        for customer in [district-->[?:Customer]] {
            for order in [customer->:Placed:->[?:Order,
                o_id >= district.d_next_o_id - 20, o_id < district.d_next_o_id]] {
                for line in [order-->[?:OrderLine]] { item_ids[str(line.ol_i_id)] = True; }
            }
        }
        low_stock = [s for s in [warehouse-->[?:Stock, s_quantity < self.threshold]] if str(s.s_i_id) in item_ids];
        report {"low_stock_count": len(low_stock)};
    }
}
