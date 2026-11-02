"""TPC-H Benchmark: Node and Edge definitions.

Each TPC-H table maps to one node type. Edges represent the foreign key
relationships defined in the TPC-H specification (dss.ri).

TPC-H Entity-Relationship overview:
    Region -[has_nation]-> Nation
    Nation -[has_supplier]-> Supplier
    Nation -[has_customer]-> Customer
    Supplier -[supplies]-> PartSupp
    Part -[supplied_by]-> PartSupp
    Customer -[ordered]-> Order
    Order -[has_lineitem]-> LineItem
    LineItem -[partsupp_link]-> PartSupp
"""

# ──────────────────────────────────────────────
#  Node types — one per TPC-H table
# ──────────────────────────────────────────────

node Region {
    has r_regionkey: int,
        r_name: str,
        r_comment: str;
}

node Nation {
    has n_nationkey: int,
        n_name: str,
        n_comment: str;
}

node Part {
    has p_partkey: int,
        p_name: str,
        p_mfgr: str,
        p_brand: str,
        p_type: str,
        p_size: int,
        p_container: str,
        p_retailprice: float,
        p_comment: str;
}

node Supplier {
    has s_suppkey: int,
        s_name: str,
        s_address: str,
        s_phone: str,
        s_acctbal: float,
        s_comment: str;
}

node PartSupp {
    has ps_partkey: int,
        ps_suppkey: int,
        ps_availqty: int,
        ps_supplycost: float,
        ps_comment: str;
}

node Customer {
    has c_custkey: int,
        c_name: str,
        c_address: str,
        c_phone: str,
        c_acctbal: float,
        c_mktsegment: str,
        c_comment: str;
}

node Order {
    has o_orderkey: int,
        o_custkey: int,
        o_orderstatus: str,
        o_totalprice: float,
        o_orderdate: str,
        o_orderpriority: str,
        o_clerk: str,
        o_shippriority: int,
        o_comment: str;
}

node LineItem {
    has l_orderkey: int,
        l_partkey: int,
        l_suppkey: int,
        l_linenumber: int,
        l_quantity: float,
        l_extendedprice: float,
        l_discount: float,
        l_tax: float,
        l_returnflag: str,
        l_linestatus: str,
        l_shipdate: str,
        l_commitdate: str,
        l_receiptdate: str,
        l_shipinstruct: str,
        l_shipmode: str,
        l_comment: str;
}

# ──────────────────────────────────────────────
#  Edge types — foreign key relationships
# ──────────────────────────────────────────────

# Region -> Nation  (NATION.N_REGIONKEY references REGION)
edge region_has_nation {}

# Nation -> Supplier  (SUPPLIER.S_NATIONKEY references NATION)
edge nation_has_supplier {}

# Nation -> Customer  (CUSTOMER.C_NATIONKEY references NATION)
edge nation_has_customer {}

# Supplier -> PartSupp  (PARTSUPP.PS_SUPPKEY references SUPPLIER)
edge supplier_supplies {}

# Part -> PartSupp  (PARTSUPP.PS_PARTKEY references PART)
edge part_supplied_by {}

# Customer -> Order  (ORDERS.O_CUSTKEY references CUSTOMER)
edge customer_ordered {}

# Order -> LineItem  (LINEITEM.L_ORDERKEY references ORDERS)
edge order_has_lineitem {}

# LineItem -> PartSupp  (LINEITEM.L_PARTKEY,L_SUPPKEY references PARTSUPP)
edge lineitem_partsupp {}
