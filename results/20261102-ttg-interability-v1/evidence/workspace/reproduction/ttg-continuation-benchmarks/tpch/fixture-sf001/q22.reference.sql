
            SELECT
                cntrycode,
                COUNT(*) AS numcust,
                SUM(c_acctbal) AS totacctbal
            FROM (
                SELECT
                    substr(c_phone, 1, 2) AS cntrycode,
                    c_acctbal
                FROM customer
                WHERE substr(c_phone, 1, 2) IN (?, ?, ?, ?, ?, ?, ?)
                  AND c_acctbal > (
                      SELECT AVG(c_acctbal)
                      FROM customer
                      WHERE c_acctbal > 0.00
                        AND substr(c_phone, 1, 2) IN (?, ?, ?, ?, ?, ?, ?)
                  )
                  AND NOT EXISTS (
                      SELECT 1
                      FROM orders
                      WHERE o_custkey = c_custkey
                  )
            ) AS custsale
            GROUP BY cntrycode
            ORDER BY cntrycode
            
