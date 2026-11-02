include models;

# ============================================================
# Helper walkers — rewritten with multi-hop traversal
# ============================================================

walker _BuildSuppNationMap {
    has result: dict = {};

    can on_root with Root entry {
        visit [-->[?:Region]->:region_has_nation:->[?:Nation]];
    }
    can on_nation with Nation entry {
        for supp in [->:nation_has_supplier:->][?:Supplier] {
            self.result[supp.s_suppkey] = here.n_name;
        }
    }
}

walker _BuildCustNationMap {
    has target_nations: list = [];
    has result: dict = {};

    can on_root with Root entry {
        visit [-->[?:Region]->:region_has_nation:->[?:Nation]];
    }
    can on_nation with Nation entry {
        if len(self.target_nations) == 0 or here.n_name in self.target_nations {
            for cust in [->:nation_has_customer:->][?:Customer] {
                self.result[cust.c_custkey] = here.n_name;
            }
        }
    }
}

walker _BuildRegionSuppMap {
    has region_name: str = "";
    has result: dict = {};

    can on_root with Root entry {
        visit [-->[?:Region]];
    }
    can on_region with Region entry {
        if here.r_name == self.region_name {
            visit [->:region_has_nation:->[?:Nation]];
        }
    }
    can on_nation with Nation entry {
        if here.n_name not in self.result {
            self.result[here.n_name] = [];
        }
        for supp in [->:nation_has_supplier:->][?:Supplier] {
            self.result[here.n_name].append(supp.s_suppkey);
        }
    }
}

walker _BuildNationSupplierMap {
    has nation_name: str = "";
    has result: dict = {};

    can on_root with Root entry {
        visit [-->[?:Region]->:region_has_nation:->[?:Nation]];
    }
    can on_nation with Nation entry {
        if here.n_name == self.nation_name {
            for supp in [->:nation_has_supplier:->][?:Supplier] {
                self.result[supp.s_suppkey] = supp;
            }
        }
    }
}

walker _BuildPartCostMap {
    has color: str = "";
    has matching_parts: dict = {};
    has ps_cost: dict = {};

    can on_root with Root entry {
        visit [-->[?:Part]];
    }
    can on_part with Part entry {
        if self.color in here.p_name {
            self.matching_parts[here.p_partkey] = True;
            for ps in [->:part_supplied_by:->][?:PartSupp] {
                self.ps_cost[f"{ps.ps_partkey}_{ps.ps_suppkey}"] = ps.ps_supplycost;
            }
        }
    }
}

walker _BuildPartTypeMap {
    has result: dict = {};

    can on_root with Root entry {
        for part in [-->[?:Part]] {
            self.result[part.p_partkey] = part.p_type;
        }
    }
}

walker _BuildPartInfoMap {
    has result: dict = {};

    can on_root with Root entry {
        for part in [-->[?:Part]] {
            self.result[part.p_partkey] = {
                "brand": part.p_brand,
                "container": part.p_container,
                "size": part.p_size
            };
        }
    }
}

walker _BuildNationSuppKeys {
    has nation_name: str = "";
    has result: dict = {};

    can on_root with Root entry {
        visit [-->[?:Region]->:region_has_nation:->[?:Nation]];
    }
    can on_nation with Nation entry {
        if here.n_name == self.nation_name {
            for supp in [->:nation_has_supplier:->][?:Supplier] {
                self.result[supp.s_suppkey] = True;
            }
        }
    }
}

walker _BuildNationSuppNames {
    has nation_name: str = "";
    has result: dict = {};

    can on_root with Root entry {
        visit [-->[?:Region]->:region_has_nation:->[?:Nation]];
    }
    can on_nation with Nation entry {
        if here.n_name == self.nation_name {
            for supp in [->:nation_has_supplier:->][?:Supplier] {
                self.result[supp.s_suppkey] = supp.s_name;
            }
        }
    }
}

walker _BuildComplaintSuppKeys {
    has result: dict = {};

    can on_root with Root entry {
        for supp in [-->[?:Region]->:region_has_nation:->[?:Nation]->:nation_has_supplier:->[?:Supplier]] {
            if "Customer" in supp.s_comment and "Complaints" in supp.s_comment.split("Customer", 1)[1] {
                self.result[supp.s_suppkey] = True;
            }
        }
    }
}

walker _BuildSuppInfoMap {
    has result: dict = {};

    can on_root with Root entry {
        for supp in [-->[?:Region]->:region_has_nation:->[?:Nation]->:nation_has_supplier:->[?:Supplier]] {
            self.result[supp.s_suppkey] = {
                "s_suppkey": supp.s_suppkey,
                "s_name": supp.s_name,
                "s_address": supp.s_address,
                "s_phone": supp.s_phone
            };
        }
    }
}

walker _BuildMatchingPartKeys {
    has color: str = "";
    has result: dict = {};

    can on_root with Root entry {
        for part in [-->[?:Part]] {
            if part.p_name.startswith(self.color) {
                self.result[part.p_partkey] = True;
            }
        }
    }
}

walker _BuildMatchingPartKeysType {
    has p_type: str = "";
    has result: dict = {};

    can on_root with Root entry {
        for part in [-->[?:Part]] {
            if part.p_type == self.p_type {
                self.result[part.p_partkey] = True;
            }
        }
    }
}

walker _BuildMatchingPartKeysQ17 {
    has brand: str = "";
    has container: str = "";
    has result: dict = {};

    can on_root with Root entry {
        for part in [-->[?:Part]] {
            if part.p_brand == self.brand and part.p_container == self.container {
                self.result[part.p_partkey] = True;
            }
        }
    }
}

walker _BuildSuppRegionInfo {
    has region_name: str = "";
    has result: dict = {};

    can on_root with Root entry {
        visit [-->[?:Region]];
    }
    can on_region with Region entry {
        if here.r_name == self.region_name {
            visit [->:region_has_nation:->[?:Nation]];
        }
    }
    can on_nation with Nation entry {
        for supp in [->:nation_has_supplier:->][?:Supplier] {
            self.result[supp.s_suppkey] = {
                "s_acctbal": supp.s_acctbal,
                "s_name": supp.s_name,
                "s_address": supp.s_address,
                "s_phone": supp.s_phone,
                "s_comment": supp.s_comment,
                "n_name": here.n_name
            };
        }
    }
}

walker _Q2Compute {
    has p_size: int = 15;
    has p_type_suffix: str = "BRASS";
    has supp_info: dict = {};
    has part_info: dict = {};
    has part_min_cost: dict = {};
    has part_min_supps: dict = {};
    has results: list = [];

    can on_root with Root entry {
        visit [-->[?:Part]];
    }
    can on_part with Part entry {
        if here.p_size == self.p_size and here.p_type.endswith(self.p_type_suffix) {
            self.part_info[here.p_partkey] = {
                "p_partkey": here.p_partkey,
                "p_mfgr": here.p_mfgr
            };
            self.part_min_cost[here.p_partkey] = 1e18;
            self.part_min_supps[here.p_partkey] = {};
            visit [->:part_supplied_by:->[?:PartSupp]];
        }
    }
    can on_partsupp with PartSupp entry {
        partkey = here.ps_partkey;
        if partkey not in self.part_info {
            return;
        }
        if here.ps_suppkey not in self.supp_info {
            return;
        }
        cur_min = self.part_min_cost.get(partkey, 1e18);
        if here.ps_supplycost < cur_min {
            self.part_min_cost[partkey] = here.ps_supplycost;
            self.part_min_supps[partkey] = {here.ps_suppkey: True};
        } elif here.ps_supplycost == cur_min {
            self.part_min_supps[partkey][here.ps_suppkey] = True;
        }
    }
    can finish with Root exit {
        for (partkey, suppkeys) in self.part_min_supps.items() {
            for suppkey in suppkeys {
                si = self.supp_info[suppkey];
                pi = self.part_info[partkey];
                self.results.append({
                    "s_acctbal": si["s_acctbal"],
                    "s_name": si["s_name"],
                    "n_name": si["n_name"],
                    "p_partkey": pi["p_partkey"],
                    "p_mfgr": pi["p_mfgr"],
                    "s_address": si["s_address"],
                    "s_phone": si["s_phone"],
                    "s_comment": si["s_comment"]
                });
            }
        }
        self.results.sort(key=lambda (x: dict) { (-x["s_acctbal"], x["n_name"], x["s_name"], x["p_partkey"]); });
        self.results = self.results[:100];
    }
}

walker _Q11Compute {
    has target_suppkeys: dict = {};
    has ps_values: dict = {};
    has total_value: float = 0.0;

    can on_root with Root entry {
        visit [-->[?:Part]];
    }
    can on_part with Part entry {
        visit [->:part_supplied_by:->[?:PartSupp]];
    }
    can on_partsupp with PartSupp entry {
        if here.ps_suppkey in self.target_suppkeys {
            val = here.ps_supplycost * here.ps_availqty;
            self.total_value += val;
            if here.ps_partkey not in self.ps_values {
                self.ps_values[here.ps_partkey] = 0.0;
            }
            self.ps_values[here.ps_partkey] += val;
        }
    }
}

walker _Q16Compute {
    has brand: str = "";
    has type_prefix: str = "";
    has sizes: list = [];
    has complaint_suppkeys: dict = {};
    has part_combo: dict = {};
    has agg: dict = {};
    has result: list = [];

    can on_root with Root entry {
        visit [-->[?:Part]];
    }
    can on_part with Part entry {
        if (here.p_brand != self.brand
            and not here.p_type.startswith(self.type_prefix)
            and here.p_size in self.sizes) {
            key = f"{here.p_brand}|{here.p_type}|{here.p_size}";
            self.part_combo[here.p_partkey] = key;
            if key not in self.agg {
                self.agg[key] = {
                    "p_brand": here.p_brand,
                    "p_type": here.p_type,
                    "p_size": here.p_size,
                    "suppkeys": {}
                };
            }
            visit [->:part_supplied_by:->[?:PartSupp]];
        }
    }
    can on_partsupp with PartSupp entry {
        partkey = here.ps_partkey;
        if partkey not in self.part_combo {
            return;
        }
        if here.ps_suppkey in self.complaint_suppkeys {
            return;
        }
        combo = self.part_combo[partkey];
        self.agg[combo]["suppkeys"][here.ps_suppkey] = True;
    }
    can finish with Root exit {
        self.result = [
            {
                "p_brand": v["p_brand"],
                "p_type": v["p_type"],
                "p_size": v["p_size"],
                "supplier_cnt": len(v["suppkeys"])
            }
            for (k, v) in self.agg.items() if len(v["suppkeys"]) > 0
        ];
        self.result.sort(key=lambda (x: dict) { (-x["supplier_cnt"], x["p_brand"], x["p_type"], x["p_size"]); });
    }
}

walker _Q20Phase2 {
    has nation_name: str = "";
    has matching_partkeys: dict = {};
    has li_qtys: dict = {};
    has supplier_map: dict = {};
    has qualifying: dict = {};
    has result: list = [];

    can on_root with Root entry {
        visit [-->[?:Region]->:region_has_nation:->[?:Nation]];
    }
    can on_nation with Nation entry {
        if here.n_name == self.nation_name {
            visit [->:nation_has_supplier:->[?:Supplier]];
        }
    }
    can on_supplier with Supplier entry {
        self.supplier_map[here.s_suppkey] = here;
        visit [->:supplier_supplies:->[?:PartSupp]];
    }
    can on_partsupp with PartSupp entry {
        if here.ps_partkey not in self.matching_partkeys {
            return;
        }
        key = f"{here.ps_partkey}_{here.ps_suppkey}";
        if key not in self.li_qtys {
            return;
        }
        threshold = 0.5 * self.li_qtys[key];
        if here.ps_availqty > threshold and here.ps_suppkey in self.supplier_map {
            self.qualifying[here.ps_suppkey] = self.supplier_map[here.ps_suppkey];
        }
    }
    can finish with Root exit {
        self.result = [
            {"s_name": s.s_name, "s_address": s.s_address}
            for s in self.qualifying.values()
        ];
        self.result.sort(key=lambda (x: dict) { x["s_name"]; });
    }
}

walker _HasOrders {
    has result: bool = False;

    can on_customer with Customer entry {
        self.result = len([->:customer_ordered:->][?:Order]) > 0;
    }
}

# ============================================================
# TPC-H Queries — rewritten with multi-hop traversal
# ============================================================

# Q1 — Only needs LineItem data. Multi-hop visit from root to LineItem.
walker Q1_PricingSummary {
    has delta: int = 90;
    has agg: dict = {};
    has cutoff: str = "";

    can on_root with Root entry {
        import datetime;
        self.cutoff = (datetime.date(1998, 12, 1) - datetime.timedelta(days=self.delta)).isoformat();
        visit [-->[?:Region]->:region_has_nation:->[?:Nation]->:nation_has_customer:->[?:Customer]->:customer_ordered:->[?:Order]->:order_has_lineitem:->[?:LineItem]];
    }
    can on_lineitem with LineItem entry {
        if here.l_shipdate <= self.cutoff {
            key = f"{here.l_returnflag}|{here.l_linestatus}";
            if key not in self.agg {
                self.agg[key] = {
                    "l_returnflag": here.l_returnflag,
                    "l_linestatus": here.l_linestatus,
                    "sum_qty": 0.0,
                    "sum_base_price": 0.0,
                    "sum_disc_price": 0.0,
                    "sum_charge": 0.0,
                    "sum_discount": 0.0,
                    "count": 0
                };
            }
            rec = self.agg[key];
            rec["sum_qty"] += here.l_quantity;
            rec["sum_base_price"] += here.l_extendedprice;
            disc_price = here.l_extendedprice * (1.0 - here.l_discount);
            rec["sum_disc_price"] += disc_price;
            rec["sum_charge"] += disc_price * (1.0 + here.l_tax);
            rec["sum_discount"] += here.l_discount;
            rec["count"] += 1;
        }
    }
    can finish with Root exit {
        results: list = [];
        for (key, rec) in self.agg.items() {
            cnt = rec["count"];
            results.append({
                "l_returnflag": rec["l_returnflag"],
                "l_linestatus": rec["l_linestatus"],
                "sum_qty": rec["sum_qty"],
                "sum_base_price": rec["sum_base_price"],
                "sum_disc_price": rec["sum_disc_price"],
                "sum_charge": rec["sum_charge"],
                "avg_qty": rec["sum_qty"] / cnt if cnt > 0 else 0.0,
                "avg_price": rec["sum_base_price"] / cnt if cnt > 0 else 0.0,
                "avg_disc": rec["sum_discount"] / cnt if cnt > 0 else 0.0,
                "count_order": cnt
            });
        }
        results.sort(key=lambda (x: dict) { (x["l_returnflag"], x["l_linestatus"]); });
        report results;
    }
}

# Q2 — Traverses Part tree. Uses helper for region supplier info.
walker Q2_MinCostSupplier {
    has p_size: int = 15,
        p_type_suffix: str = "BRASS",
        region_name: str = "EUROPE";

    can run with Root entry {
        supp_helper = root spawn _BuildSuppRegionInfo(region_name=self.region_name);
        q2_helper = root spawn _Q2Compute(
            p_size=self.p_size,
            p_type_suffix=self.p_type_suffix,
            supp_info=supp_helper.result
        );
        report q2_helper.results;
    }
}

# Q3 — Needs order data at lineitem level. Visit to Customer (with filter),
#       then Order, then LineItem.
walker Q3_ShippingPriority {
    has segment: str = "BUILDING",
        date: str = "1995-03-15";
    has order_map: dict = {};
    has agg: dict = {};

    can on_root with Root entry {
        visit [-->[?:Region]->:region_has_nation:->[?:Nation]->:nation_has_customer:->[?:Customer]];
    }
    can on_customer with Customer entry {
        if here.c_mktsegment == self.segment {
            visit [->:customer_ordered:->[?:Order]];
        }
    }
    can on_order with Order entry {
        if here.o_orderdate < self.date {
            self.order_map[here.o_orderkey] = {
                "o_orderdate": here.o_orderdate,
                "o_shippriority": here.o_shippriority
            };
            visit [->:order_has_lineitem:->[?:LineItem]];
        }
    }
    can on_lineitem with LineItem entry {
        if here.l_shipdate <= self.date {
            return;
        }
        order_info = self.order_map.get(here.l_orderkey, {});
        if not order_info {
            return;
        }
        key = f"{here.l_orderkey}|{order_info['o_orderdate']}|{order_info['o_shippriority']}";
        if key not in self.agg {
            self.agg[key] = {
                "l_orderkey": here.l_orderkey,
                "o_orderdate": order_info["o_orderdate"],
                "o_shippriority": order_info["o_shippriority"],
                "revenue": 0.0
            };
        }
        self.agg[key]["revenue"] += here.l_extendedprice * (1.0 - here.l_discount);
    }
    can finish with Root exit {
        results = list(self.agg.values());
        results.sort(key=lambda (x: dict) { (-x["revenue"], x["o_orderdate"]); });
        report results[:10];
    }
}

# Q4 — Needs order data. Visit to Order, then LineItem.
walker Q4_OrderPriority {
    has date: str = "1993-07-01";
    has end_date: str = "";
    has order_prio: dict = {};
    has order_has_late: dict = {};

    can on_root with Root entry {
        import datetime;
        start = datetime.date.fromisoformat(self.date);
        self.end_date = (start + datetime.timedelta(days=92)).isoformat();
        visit [-->[?:Region]->:region_has_nation:->[?:Nation]->:nation_has_customer:->[?:Customer]->:customer_ordered:->[?:Order]];
    }
    can on_order with Order entry {
        if here.o_orderdate >= self.date and here.o_orderdate < self.end_date {
            self.order_prio[here.o_orderkey] = here.o_orderpriority;
            self.order_has_late[here.o_orderkey] = False;
            visit [->:order_has_lineitem:->[?:LineItem]];
        }
    }
    can on_lineitem with LineItem entry {
        if here.l_orderkey in self.order_has_late and here.l_commitdate < here.l_receiptdate {
            self.order_has_late[here.l_orderkey] = True;
        }
    }
    can finish with Root exit {
        agg: dict = {};
        for (orderkey, has_late) in self.order_has_late.items() {
            if not has_late {
                continue;
            }
            prio = self.order_prio[orderkey];
            if prio not in agg {
                agg[prio] = 0;
            }
            agg[prio] += 1;
        }
        results = [{"o_orderpriority": k, "order_count": v} for (k, v) in agg.items()];
        results.sort(key=lambda (x: dict) { x["o_orderpriority"]; });
        report results;
    }
}

# Q5 — Needs order + lineitem + nation mapping. Visit to Order then LineItem.
walker Q5_LocalSupplierVolume {
    has region_name: str = "ASIA",
        date: str = "1994-01-01";
    has end_date: str = "";
    has cust_nation: dict = {};
    has supp_nation: dict = {};
    has order_cust: dict = {};
    has agg: dict = {};

    can on_root with Root entry {
        import datetime;
        start = datetime.date.fromisoformat(self.date);
        self.end_date = (start.replace(year=start.year + 1)).isoformat();

        ns_helper = root spawn _BuildRegionSuppMap(region_name=self.region_name);
        nation_suppliers = ns_helper.result;

        target_nations: list = [];
        for n_name in nation_suppliers {
            target_nations.append(n_name);
            for suppkey in nation_suppliers[n_name] {
                self.supp_nation[suppkey] = n_name;
            }
        }

        cn_helper = root spawn _BuildCustNationMap(target_nations=target_nations);
        self.cust_nation = cn_helper.result;

        visit [-->[?:Region]->:region_has_nation:->[?:Nation]->:nation_has_customer:->[?:Customer]->:customer_ordered:->[?:Order]];
    }
    can on_order with Order entry {
        if here.o_orderdate >= self.date and here.o_orderdate < self.end_date {
            self.order_cust[here.o_orderkey] = here.o_custkey;
            visit [->:order_has_lineitem:->[?:LineItem]];
        }
    }
    can on_lineitem with LineItem entry {
        custkey = self.order_cust.get(here.l_orderkey, 0);
        if custkey == 0 {
            return;
        }
        cust_nation = self.cust_nation.get(custkey, "");
        if cust_nation == "" {
            return;
        }
        supp_nation = self.supp_nation.get(here.l_suppkey, "");
        if supp_nation != cust_nation {
            return;
        }
        if cust_nation not in self.agg {
            self.agg[cust_nation] = 0.0;
        }
        self.agg[cust_nation] += here.l_extendedprice * (1.0 - here.l_discount);
    }
    can finish with Root exit {
        results = [{"n_name": k, "revenue": v} for (k, v) in self.agg.items()];
        results.sort(key=lambda (x: dict) { -x["revenue"]; });
        report results;
    }
}

# Q6 — Only needs LineItem data. Multi-hop visit from root to LineItem.
walker Q6_ForecastingRevenue {
    has date: str = "1994-01-01",
        discount: float = 0.06,
        quantity: float = 24.0;
    has revenue: float = 0.0;
    has end_date: str = "";
    has lo_disc: float = 0.0;
    has hi_disc: float = 0.0;

    can on_root with Root entry {
        import datetime;
        start = datetime.date.fromisoformat(self.date);
        self.end_date = (start.replace(year=start.year + 1)).isoformat();
        self.lo_disc = self.discount - 0.01;
        self.hi_disc = self.discount + 0.01;
        visit [-->[?:Region]->:region_has_nation:->[?:Nation]->:nation_has_customer:->[?:Customer]->:customer_ordered:->[?:Order]->:order_has_lineitem:->[?:LineItem]];
    }
    can on_lineitem with LineItem entry {
        if (here.l_shipdate >= self.date
            and here.l_shipdate < self.end_date
            and here.l_discount >= self.lo_disc
            and here.l_discount <= self.hi_disc
            and here.l_quantity < self.quantity) {
            self.revenue += here.l_extendedprice * here.l_discount;
        }
    }
    can finish with Root exit {
        report {"revenue": self.revenue};
    }
}

# Q7 — Needs order + lineitem + nation mapping. Visit to Customer then Order then LineItem.
walker Q7_VolumeShipping {
    has nation1: str = "FRANCE",
        nation2: str = "GERMANY";
    has supp_nation: dict = {};
    has cust_nation: dict = {};
    has order_cust_nation: dict = {};
    has agg: dict = {};

    can on_root with Root entry {
        sn_helper = root spawn _BuildSuppNationMap();
        self.supp_nation = sn_helper.result;

        cn_helper = root spawn _BuildCustNationMap(target_nations=[self.nation1, self.nation2]);
        self.cust_nation = cn_helper.result;

        visit [-->[?:Region]->:region_has_nation:->[?:Nation]];
    }
    can on_nation with Nation entry {
        if here.n_name == self.nation1 or here.n_name == self.nation2 {
            visit [->:nation_has_customer:->[?:Customer]->:customer_ordered:->[?:Order]];
        }
    }
    can on_order with Order entry {
        c_nat = self.cust_nation.get(here.o_custkey, "");
        if c_nat != "" {
            self.order_cust_nation[here.o_orderkey] = c_nat;
            visit [->:order_has_lineitem:->[?:LineItem]];
        }
    }
    can on_lineitem with LineItem entry {
        if here.l_shipdate < "1995-01-01" or here.l_shipdate > "1996-12-31" {
            return;
        }
        c_nat = self.order_cust_nation.get(here.l_orderkey, "");
        if c_nat == "" {
            return;
        }
        s_nat = self.supp_nation.get(here.l_suppkey, "");
        if ((s_nat == self.nation1 and c_nat == self.nation2)
            or (s_nat == self.nation2 and c_nat == self.nation1)) {
            l_year = here.l_shipdate[:4];
            key = f"{s_nat}|{c_nat}|{l_year}";
            if key not in self.agg {
                self.agg[key] = {
                    "supp_nation": s_nat,
                    "cust_nation": c_nat,
                    "l_year": int(l_year),
                    "revenue": 0.0
                };
            }
            self.agg[key]["revenue"] += here.l_extendedprice * (1.0 - here.l_discount);
        }
    }
    can finish with Root exit {
        results = list(self.agg.values());
        results.sort(key=lambda (x: dict) { (x["supp_nation"], x["cust_nation"], x["l_year"]); });
        report results;
    }
}

# Q8 — Needs order year + lineitem. Visit to Region (filter), then down to Order, then LineItem.
walker Q8_NationalMarketShare {
    has nation_name: str = "BRAZIL",
        region_name: str = "AMERICA",
        p_type: str = "ECONOMY ANODIZED STEEL";
    has supp_nation: dict = {};
    has matching_parts: dict = {};
    has order_year: dict = {};
    has agg: dict = {};

    can on_root with Root entry {
        sn_helper = root spawn _BuildSuppNationMap();
        self.supp_nation = sn_helper.result;

        pt_helper = root spawn _BuildMatchingPartKeysType(p_type=self.p_type);
        self.matching_parts = pt_helper.result;

        visit [-->[?:Region]];
    }
    can on_region with Region entry {
        if here.r_name == self.region_name {
            visit [->:region_has_nation:->[?:Nation]->:nation_has_customer:->[?:Customer]->:customer_ordered:->[?:Order]];
        }
    }
    can on_order with Order entry {
        if here.o_orderdate >= "1995-01-01" and here.o_orderdate <= "1996-12-31" {
            self.order_year[here.o_orderkey] = here.o_orderdate[:4];
            visit [->:order_has_lineitem:->[?:LineItem]];
        }
    }
    can on_lineitem with LineItem entry {
        if here.l_partkey not in self.matching_parts {
            return;
        }
        o_year = self.order_year.get(here.l_orderkey, "");
        if o_year == "" {
            return;
        }
        volume = here.l_extendedprice * (1.0 - here.l_discount);
        if o_year not in self.agg {
            self.agg[o_year] = {"total": 0.0, "nation": 0.0};
        }
        self.agg[o_year]["total"] += volume;
        if self.supp_nation.get(here.l_suppkey, "") == self.nation_name {
            self.agg[o_year]["nation"] += volume;
        }
    }
    can finish with Root exit {
        results: list = [];
        for (year, val) in sorted(self.agg.items()) {
            mkt_share = val["nation"] / val["total"] if val["total"] > 0 else 0.0;
            results.append({"o_year": int(year), "mkt_share": mkt_share});
        }
        report results;
    }
}

# Q9 — Needs order year + lineitem. Visit to Order then LineItem.
walker Q9_ProductTypeProfit {
    has color: str = "green";
    has supp_nation: dict = {};
    has matching_parts: dict = {};
    has ps_cost: dict = {};
    has order_year: dict = {};
    has agg: dict = {};

    can on_root with Root entry {
        sn_helper = root spawn _BuildSuppNationMap();
        self.supp_nation = sn_helper.result;

        pc_helper = root spawn _BuildPartCostMap(color=self.color);
        self.matching_parts = pc_helper.matching_parts;
        self.ps_cost = pc_helper.ps_cost;

        visit [-->[?:Region]->:region_has_nation:->[?:Nation]->:nation_has_customer:->[?:Customer]->:customer_ordered:->[?:Order]];
    }
    can on_order with Order entry {
        self.order_year[here.o_orderkey] = here.o_orderdate[:4];
        visit [->:order_has_lineitem:->[?:LineItem]];
    }
    can on_lineitem with LineItem entry {
        if here.l_partkey not in self.matching_parts {
            return;
        }
        s_nat = self.supp_nation.get(here.l_suppkey, "");
        if s_nat == "" {
            return;
        }
        o_year = self.order_year.get(here.l_orderkey, "");
        if o_year == "" {
            return;
        }
        cost_key = f"{here.l_partkey}_{here.l_suppkey}";
        supplycost = self.ps_cost.get(cost_key, 0.0);
        amount = here.l_extendedprice * (1.0 - here.l_discount) - supplycost * here.l_quantity;
        key = f"{s_nat}|{o_year}";
        if key not in self.agg {
            self.agg[key] = {"nation": s_nat, "o_year": int(o_year), "sum_profit": 0.0};
        }
        self.agg[key]["sum_profit"] += amount;
    }
    can finish with Root exit {
        results = list(self.agg.values());
        results.sort(key=lambda (x: dict) { (x["nation"], -x["o_year"]); });
        report results;
    }
}

# Q10 — Needs customer info + order dates. Visit to Customer, then Order, then LineItem.
walker Q10_ReturnedItemReporting {
    has date: str = "1993-10-01";
    has end_date: str = "";
    has cust_nation: dict = {};
    has cust_info: dict = {};
    has order_cust: dict = {};
    has revenue_by_cust: dict = {};

    can on_root with Root entry {
        import datetime;
        start = datetime.date.fromisoformat(self.date);
        self.end_date = (start + datetime.timedelta(days=92)).isoformat();

        cn_helper = root spawn _BuildCustNationMap();
        self.cust_nation = cn_helper.result;

        visit [-->[?:Region]->:region_has_nation:->[?:Nation]->:nation_has_customer:->[?:Customer]];
    }
    can on_customer with Customer entry {
        self.cust_info[here.c_custkey] = {
            "c_custkey": here.c_custkey,
            "c_name": here.c_name,
            "c_acctbal": here.c_acctbal,
            "c_address": here.c_address,
            "c_phone": here.c_phone,
            "c_comment": here.c_comment,
            "n_name": self.cust_nation.get(here.c_custkey, "")
        };
        visit [->:customer_ordered:->[?:Order]];
    }
    can on_order with Order entry {
        if here.o_orderdate >= self.date and here.o_orderdate < self.end_date {
            self.order_cust[here.o_orderkey] = here.o_custkey;
            visit [->:order_has_lineitem:->[?:LineItem]];
        }
    }
    can on_lineitem with LineItem entry {
        if here.l_returnflag != "R" {
            return;
        }
        custkey = self.order_cust.get(here.l_orderkey, 0);
        if custkey == 0 {
            return;
        }
        if custkey not in self.revenue_by_cust {
            self.revenue_by_cust[custkey] = 0.0;
        }
        self.revenue_by_cust[custkey] += here.l_extendedprice * (1.0 - here.l_discount);
    }
    can finish with Root exit {
        results: list = [];
        for (custkey, revenue) in self.revenue_by_cust.items() {
            if revenue <= 0.0 or custkey not in self.cust_info {
                continue;
            }
            ci = self.cust_info[custkey];
            results.append({
                "c_custkey": ci["c_custkey"],
                "c_name": ci["c_name"],
                "revenue": revenue,
                "c_acctbal": ci["c_acctbal"],
                "n_name": ci["n_name"],
                "c_address": ci["c_address"],
                "c_phone": ci["c_phone"],
                "c_comment": ci["c_comment"]
            });
        }
        results.sort(key=lambda (x: dict) { -x["revenue"]; });
        report results[:20];
    }
}

# Q11 — Traverses Part tree. Uses helper for nation supplier keys.
walker Q11_ImportantStock {
    has nation_name: str = "GERMANY",
        fraction: float = 0.0001;

    can run with Root entry {
        sk_helper = root spawn _BuildNationSuppKeys(nation_name=self.nation_name);
        ps_helper = root spawn _Q11Compute(target_suppkeys=sk_helper.result);

        threshold = ps_helper.total_value * self.fraction;
        results = [
            {"ps_partkey": k, "value": v}
            for (k, v) in ps_helper.ps_values.items()
            if v > threshold
        ];
        results.sort(key=lambda (x: dict) { -x["value"]; });
        report results;
    }
}

# Q12 — Needs order priority at lineitem level. Visit to Order, then LineItem.
walker Q12_ShippingModes {
    has shipmode1: str = "MAIL",
        shipmode2: str = "SHIP",
        date: str = "1994-01-01";
    has end_date: str = "";
    has order_prio: dict = {};
    has agg: dict = {};

    can on_root with Root entry {
        import datetime;
        start = datetime.date.fromisoformat(self.date);
        self.end_date = (start.replace(year=start.year + 1)).isoformat();
        visit [-->[?:Region]->:region_has_nation:->[?:Nation]->:nation_has_customer:->[?:Customer]->:customer_ordered:->[?:Order]];
    }
    can on_order with Order entry {
        self.order_prio[here.o_orderkey] = here.o_orderpriority;
        visit [->:order_has_lineitem:->[?:LineItem]];
    }
    can on_lineitem with LineItem entry {
        if ((here.l_shipmode == self.shipmode1 or here.l_shipmode == self.shipmode2)
            and here.l_commitdate < here.l_receiptdate
            and here.l_shipdate < here.l_commitdate
            and here.l_receiptdate >= self.date
            and here.l_receiptdate < self.end_date) {
            mode = here.l_shipmode;
            if mode not in self.agg {
                self.agg[mode] = {"high_line_count": 0, "low_line_count": 0};
            }
            prio = self.order_prio.get(here.l_orderkey, "");
            if prio == "1-URGENT" or prio == "2-HIGH" {
                self.agg[mode]["high_line_count"] += 1;
            } else {
                self.agg[mode]["low_line_count"] += 1;
            }
        }
    }
    can finish with Root exit {
        results = [
            {"l_shipmode": k, "high_line_count": v["high_line_count"], "low_line_count": v["low_line_count"]}
            for (k, v) in self.agg.items()
        ];
        results.sort(key=lambda (x: dict) { x["l_shipmode"]; });
        report results;
    }
}

# Q13 — Needs customer + order data. Visit to Customer, then Order.
walker Q13_CustomerDistribution {
    has word1: str = "special",
        word2: str = "requests";
    has cust_order_count: dict = {};

    can on_root with Root entry {
        visit [-->[?:Region]->:region_has_nation:->[?:Nation]->:nation_has_customer:->[?:Customer]];
    }
    can on_customer with Customer entry {
        if here.c_custkey not in self.cust_order_count {
            self.cust_order_count[here.c_custkey] = 0;
        }
        visit [->:customer_ordered:->[?:Order]];
    }
    can on_order with Order entry {
        comment = here.o_comment;
        idx1 = comment.find(self.word1);
        excluded = idx1 >= 0 and comment.find(self.word2, idx1 + len(self.word1)) >= 0;
        if not excluded {
            if here.o_custkey not in self.cust_order_count {
                self.cust_order_count[here.o_custkey] = 0;
            }
            self.cust_order_count[here.o_custkey] += 1;
        }
    }
    can finish with Root exit {
        dist: dict = {};
        for cnt in self.cust_order_count.values() {
            if cnt not in dist {
                dist[cnt] = 0;
            }
            dist[cnt] += 1;
        }
        results = [{"c_count": k, "custdist": v} for (k, v) in dist.items()];
        results.sort(key=lambda (x: dict) { (-x["custdist"], -x["c_count"]); });
        report results;
    }
}

# Q14 — Only needs LineItem data (+ part type map). Multi-hop visit to LineItem.
walker Q14_PromotionEffect {
    has date: str = "1995-09-01";
    has end_date: str = "";
    has part_types: dict = {};
    has promo_revenue: float = 0.0;
    has total_revenue: float = 0.0;

    can on_root with Root entry {
        import datetime;
        start = datetime.date.fromisoformat(self.date);
        if start.month == 12 {
            self.end_date = start.replace(year=start.year + 1, month=1).isoformat();
        } else {
            self.end_date = start.replace(month=start.month + 1).isoformat();
        }

        pt_helper = root spawn _BuildPartTypeMap();
        self.part_types = pt_helper.result;

        visit [-->[?:Region]->:region_has_nation:->[?:Nation]->:nation_has_customer:->[?:Customer]->:customer_ordered:->[?:Order]->:order_has_lineitem:->[?:LineItem]];
    }
    can on_lineitem with LineItem entry {
        if here.l_shipdate >= self.date and here.l_shipdate < self.end_date {
            rev = here.l_extendedprice * (1.0 - here.l_discount);
            self.total_revenue += rev;
            p_type = self.part_types.get(here.l_partkey, "");
            if p_type.startswith("PROMO") {
                self.promo_revenue += rev;
            }
        }
    }
    can finish with Root exit {
        result = 100.0 * self.promo_revenue / self.total_revenue if self.total_revenue > 0 else 0.0;
        report {"promo_revenue": result};
    }
}

# Q15 — Only needs LineItem data (for supplier revenue). Multi-hop visit to LineItem.
walker Q15_TopSupplier {
    has date: str = "1996-01-01";
    has supp_revenue: dict = {};
    has end_date: str = "";

    can on_root with Root entry {
        import datetime;
        start = datetime.date.fromisoformat(self.date);
        end_month = start.month + 3;
        end_year = start.year;
        if end_month > 12 {
            end_month -= 12;
            end_year += 1;
        }
        self.end_date = datetime.date(end_year, end_month, 1).isoformat();
        visit [-->[?:Region]->:region_has_nation:->[?:Nation]->:nation_has_customer:->[?:Customer]->:customer_ordered:->[?:Order]->:order_has_lineitem:->[?:LineItem]];
    }
    can on_lineitem with LineItem entry {
        if here.l_shipdate >= self.date and here.l_shipdate < self.end_date {
            suppkey = here.l_suppkey;
            if suppkey not in self.supp_revenue {
                self.supp_revenue[suppkey] = 0.0;
            }
            self.supp_revenue[suppkey] += here.l_extendedprice * (1.0 - here.l_discount);
        }
    }
    can finish with Root exit {
        if not self.supp_revenue {
            report [];
            return;
        }
        max_rev = max(self.supp_revenue.values());
        si_helper = root spawn _BuildSuppInfoMap();
        supp_map = si_helper.result;

        results: list = [];
        for (sk, rev) in self.supp_revenue.items() {
            if rev == max_rev and sk in supp_map {
                s = supp_map[sk];
                results.append({
                    "s_suppkey": s["s_suppkey"],
                    "s_name": s["s_name"],
                    "s_address": s["s_address"],
                    "s_phone": s["s_phone"],
                    "total_revenue": rev
                });
            }
        }
        results.sort(key=lambda (x: dict) { x["s_suppkey"]; });
        report results;
    }
}

# Q16 — Traverses Part tree. Uses helper for complaint supplier keys.
walker Q16_PartsSupplierRelation {
    has brand: str = "Brand#45",
        type_prefix: str = "MEDIUM POLISHED",
        sizes: list = [49, 14, 23, 45, 19, 3, 36, 9];

    can run with Root entry {
        cs_helper = root spawn _BuildComplaintSuppKeys();
        q16_helper = root spawn _Q16Compute(
            brand=self.brand,
            type_prefix=self.type_prefix,
            sizes=self.sizes,
            complaint_suppkeys=cs_helper.result
        );
        report q16_helper.result;
    }
}

# Q17 — Only needs LineItem data (+ matching part keys). Multi-hop visit to LineItem.
walker Q17_SmallQuantityOrder {
    has brand: str = "Brand#23",
        container: str = "MED BOX";
    has matching_partkeys: dict = {};
    has part_qtys: dict = {};
    has li_data: list = [];

    can on_root with Root entry {
        pk_helper = root spawn _BuildMatchingPartKeysQ17(brand=self.brand, container=self.container);
        self.matching_partkeys = pk_helper.result;
        if len(self.matching_partkeys) == 0 {
            report [];
            disengage;
        }
        for pk in self.matching_partkeys {
            self.part_qtys[pk] = [];
        }
        visit [-->[?:Region]->:region_has_nation:->[?:Nation]->:nation_has_customer:->[?:Customer]->:customer_ordered:->[?:Order]->:order_has_lineitem:->[?:LineItem]];
    }
    can on_lineitem with LineItem entry {
        if here.l_partkey in self.matching_partkeys {
            self.part_qtys[here.l_partkey].append(here.l_quantity);
            self.li_data.append([here.l_partkey, here.l_quantity, here.l_extendedprice]);
        }
    }
    can finish with Root exit {
        if len(self.matching_partkeys) == 0 {
            report [];
            return;
        }
        part_avg: dict = {};
        for (pk, qtys) in self.part_qtys.items() {
            if len(qtys) > 0 {
                part_avg[pk] = sum(qtys) / len(qtys);
            }
        }

        total_revenue = 0.0;
        has_qualifying = False;
        for item in self.li_data {
            pk = item[0];
            qty = item[1];
            price = item[2];
            avg = part_avg.get(pk, 0.0);
            if qty < 0.2 * avg {
                total_revenue += price;
                has_qualifying = True;
            }
        }
        if has_qualifying {
            report {"avg_yearly": total_revenue / 7.0};
        } else {
            report [];
        }
    }
}

# Q18 — Needs customer + order data at lineitem level. Visit to Customer, then Order, then LineItem.
walker Q18_LargeVolumeCustomer {
    has quantity_threshold: float = 300.0;
    has cust_info: dict = {};
    has order_info: dict = {};
    has order_qty: dict = {};

    can on_root with Root entry {
        visit [-->[?:Region]->:region_has_nation:->[?:Nation]->:nation_has_customer:->[?:Customer]];
    }
    can on_customer with Customer entry {
        self.cust_info[here.c_custkey] = {
            "c_name": here.c_name,
            "c_custkey": here.c_custkey
        };
        visit [->:customer_ordered:->[?:Order]];
    }
    can on_order with Order entry {
        self.order_info[here.o_orderkey] = {
            "o_orderkey": here.o_orderkey,
            "o_orderdate": here.o_orderdate,
            "o_totalprice": here.o_totalprice,
            "o_custkey": here.o_custkey
        };
        if here.o_orderkey not in self.order_qty {
            self.order_qty[here.o_orderkey] = 0.0;
        }
        visit [->:order_has_lineitem:->[?:LineItem]];
    }
    can on_lineitem with LineItem entry {
        if here.l_orderkey not in self.order_qty {
            self.order_qty[here.l_orderkey] = 0.0;
        }
        self.order_qty[here.l_orderkey] += here.l_quantity;
    }
    can finish with Root exit {
        results: list = [];
        for (orderkey, qty) in self.order_qty.items() {
            if qty <= self.quantity_threshold {
                continue;
            }
            oi = self.order_info.get(orderkey, {});
            if not oi {
                continue;
            }
            ci = self.cust_info.get(oi["o_custkey"], {});
            if not ci {
                continue;
            }
            results.append({
                "c_name": ci["c_name"],
                "c_custkey": ci["c_custkey"],
                "o_orderkey": oi["o_orderkey"],
                "o_orderdate": oi["o_orderdate"],
                "o_totalprice": oi["o_totalprice"],
                "sum_quantity": qty
            });
        }
        results.sort(key=lambda (x: dict) { (-x["o_totalprice"], x["o_orderdate"]); });
        report results[:100];
    }
}

# Q19 — Only needs LineItem data (+ part info map). Multi-hop visit to LineItem.
walker Q19_DiscountedRevenue {
    has brand1: str = "Brand#12",
        brand2: str = "Brand#23",
        brand3: str = "Brand#34",
        quantity1: float = 1.0,
        quantity2: float = 10.0,
        quantity3: float = 20.0;
    has part_info: dict = {};
    has revenue: float = 0.0;

    can on_root with Root entry {
        pi_helper = root spawn _BuildPartInfoMap();
        self.part_info = pi_helper.result;
        visit [-->[?:Region]->:region_has_nation:->[?:Nation]->:nation_has_customer:->[?:Customer]->:customer_ordered:->[?:Order]->:order_has_lineitem:->[?:LineItem]];
    }
    can on_lineitem with LineItem entry {
        if (here.l_shipmode not in ["AIR", "AIR REG"]
            or here.l_shipinstruct != "DELIVER IN PERSON") {
            return;
        }

        pi = self.part_info.get(here.l_partkey, {});
        if not pi {
            return;
        }

        sm_containers = ["SM CASE", "SM BOX", "SM PACK", "SM PKG"];
        med_containers = ["MED BAG", "MED BOX", "MED PKG", "MED PACK"];
        lg_containers = ["LG CASE", "LG BOX", "LG PACK", "LG PKG"];

        matched = False;
        if (pi["brand"] == self.brand1
            and pi["container"] in sm_containers
            and here.l_quantity >= self.quantity1
            and here.l_quantity <= self.quantity1 + 10
            and pi["size"] >= 1 and pi["size"] <= 5) {
            matched = True;
        } elif (pi["brand"] == self.brand2
            and pi["container"] in med_containers
            and here.l_quantity >= self.quantity2
            and here.l_quantity <= self.quantity2 + 10
            and pi["size"] >= 1 and pi["size"] <= 10) {
            matched = True;
        } elif (pi["brand"] == self.brand3
            and pi["container"] in lg_containers
            and here.l_quantity >= self.quantity3
            and here.l_quantity <= self.quantity3 + 10
            and pi["size"] >= 1 and pi["size"] <= 15) {
            matched = True;
        }

        if matched {
            self.revenue += here.l_extendedprice * (1.0 - here.l_discount);
        }
    }
    can finish with Root exit {
        report {"revenue": self.revenue};
    }
}

# Q20 — Needs lineitem data first (for quantities), then Part-Supplier tree. Multi-hop visit to LineItem.
walker Q20_PotentialPartPromotion {
    has color: str = "forest",
        date: str = "1994-01-01",
        nation_name: str = "CANADA";
    has matching_partkeys: dict = {};
    has li_qtys: dict = {};
    has end_date: str = "";

    can on_root with Root entry {
        import datetime;
        start = datetime.date.fromisoformat(self.date);
        self.end_date = start.replace(year=start.year + 1).isoformat();

        pk_helper = root spawn _BuildMatchingPartKeys(color=self.color);
        self.matching_partkeys = pk_helper.result;

        visit [-->[?:Region]->:region_has_nation:->[?:Nation]->:nation_has_customer:->[?:Customer]->:customer_ordered:->[?:Order]->:order_has_lineitem:->[?:LineItem]];
    }
    can on_lineitem with LineItem entry {
        if (here.l_partkey in self.matching_partkeys
            and here.l_shipdate >= self.date
            and here.l_shipdate < self.end_date) {
            key = f"{here.l_partkey}_{here.l_suppkey}";
            if key not in self.li_qtys {
                self.li_qtys[key] = 0.0;
            }
            self.li_qtys[key] += here.l_quantity;
        }
    }
    can finish with Root exit {
        q20_helper = root spawn _Q20Phase2(
            nation_name=self.nation_name,
            matching_partkeys=self.matching_partkeys,
            li_qtys=self.li_qtys
        );
        report q20_helper.result;
    }
}

# Q21 — Needs order status + lineitem data. Visit to Order (filter status), then LineItem.
walker Q21_SuppliersWhoKeptOrdersWaiting {
    has nation_name: str = "SAUDI ARABIA";
    has target_suppliers: dict = {};
    has order_final: dict = {};
    has order_lineitems: dict = {};
    has supp_counts: dict = {};

    can on_root with Root entry {
        ts_helper = root spawn _BuildNationSuppNames(nation_name=self.nation_name);
        self.target_suppliers = ts_helper.result;
        visit [-->[?:Region]->:region_has_nation:->[?:Nation]->:nation_has_customer:->[?:Customer]->:customer_ordered:->[?:Order]];
    }
    can on_order with Order entry {
        if here.o_orderstatus == "F" {
            self.order_final[here.o_orderkey] = True;
            self.order_lineitems[here.o_orderkey] = [];
            visit [->:order_has_lineitem:->[?:LineItem]];
        }
    }
    can on_lineitem with LineItem entry {
        if here.l_orderkey in self.order_final {
            self.order_lineitems[here.l_orderkey].append({
                "l_suppkey": here.l_suppkey,
                "late": here.l_receiptdate > here.l_commitdate
            });
        }
    }
    can finish with Root exit {
        for (orderkey, lineitems) in self.order_lineitems.items() {
            all_suppkeys: dict = {};
            late_suppkeys: dict = {};

            for li_info in lineitems {
                sk = li_info["l_suppkey"];
                all_suppkeys[sk] = True;
                if li_info["late"] {
                    late_suppkeys[sk] = late_suppkeys.get(sk, 0) + 1;
                }
            }

            for sk in late_suppkeys {
                if sk not in self.target_suppliers {
                    continue;
                }

                has_other = False;
                for osk in all_suppkeys {
                    if osk != sk {
                        has_other = True;
                        break;
                    }
                }
                if not has_other {
                    continue;
                }

                other_late = False;
                for osk in late_suppkeys {
                    if osk != sk {
                        other_late = True;
                        break;
                    }
                }
                if other_late {
                    continue;
                }

                if sk not in self.supp_counts {
                    self.supp_counts[sk] = 0;
                }
                self.supp_counts[sk] += late_suppkeys[sk];
            }
        }

        results = [
            {"s_name": self.target_suppliers[sk], "numwait": cnt}
            for (sk, cnt) in self.supp_counts.items()
        ];
        results.sort(key=lambda (x: dict) { (-x["numwait"], x["s_name"]); });
        report results[:100];
    }
}

# Q22 — Only needs Customer data. Multi-hop visit to Customer.
walker Q22_GlobalSalesOpportunity {
    has country_codes: list = ["13", "31", "23", "29", "30", "18", "17"];
    has sum_bal: float = 0.0;
    has count_bal: int = 0;
    has matching_customers: list = [];

    can on_root with Root entry {
        visit [-->[?:Region]->:region_has_nation:->[?:Nation]->:nation_has_customer:->[?:Customer]];
    }
    can on_customer with Customer entry {
        cntrycode = here.c_phone[:2];
        if cntrycode in self.country_codes {
            self.matching_customers.append(here);
            if here.c_acctbal > 0.0 {
                self.sum_bal += here.c_acctbal;
                self.count_bal += 1;
            }
        }
    }
    can finish with Root exit {
        avg_bal = self.sum_bal / self.count_bal if self.count_bal > 0 else 0.0;
        agg: dict = {};

        for cust in self.matching_customers {
            if cust.c_acctbal <= avg_bal {
                continue;
            }
            order_check = _HasOrders();
            cust spawn order_check;
            if order_check.result {
                continue;
            }

            cntrycode = cust.c_phone[:2];
            if cntrycode not in agg {
                agg[cntrycode] = {"numcust": 0, "totacctbal": 0.0};
            }
            agg[cntrycode]["numcust"] += 1;
            agg[cntrycode]["totacctbal"] += cust.c_acctbal;
        }

        results = [
            {"cntrycode": k, "numcust": v["numcust"], "totacctbal": v["totacctbal"]}
            for (k, v) in agg.items()
        ];
        results.sort(key=lambda (x: dict) { x["cntrycode"]; });
        report results;
    }
}
