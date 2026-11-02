
            SELECT
                o_orderpriority,
                COUNT(*) AS order_count
            FROM orders
            WHERE o_orderdate >= ?
              AND o_orderdate < date(?, '+3 month')
              AND EXISTS (
                  SELECT 1
                  FROM lineitem
                  WHERE l_orderkey = o_orderkey
                    AND l_commitdate < l_receiptdate
              )
            GROUP BY o_orderpriority
            ORDER BY o_orderpriority
            
