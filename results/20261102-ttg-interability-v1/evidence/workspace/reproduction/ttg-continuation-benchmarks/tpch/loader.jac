"""Provision the same eight entity/FK graph through current native Jac APIs.

Loading is outside query execution. The pinned historical loader is retained in
vendor/jac_tpch. It indexed connect results, an API changed in the tested compiler.
"""
include models;
import from fixture_loader { load_tables }

def load_tpch_graph(directory: str) -> dict {
    return load_tables(directory,
        {"region": Region, "nation": Nation, "supplier": Supplier,
         "customer": Customer, "part": Part, "partsupp": PartSupp,
         "orders": Order, "lineitem": LineItem},
        {"nation": region_has_nation, "supplier": nation_has_supplier,
         "customer": nation_has_customer, "supplier_ps": supplier_supplies,
         "part_ps": part_supplied_by, "orders": customer_ordered,
         "lineitem": order_has_lineitem, "line_ps": lineitem_partsupp});
}
