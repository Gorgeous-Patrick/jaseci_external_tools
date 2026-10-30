import unittest
from reconcile_diagnostics import reconcile

def row(sql='SELECT $1',label='jac:123:run',db='perf_test',error=False):
    r=['']*23;r[2]=db;r[22]=label;r[11]='ERROR' if error else 'LOG'
    r[13]='parse error' if error else 'execute <unnamed>: '+sql
    r[19]=sql if error else '';return r

def call(sql='SELECT :x',error=None):return dict(sql=sql,send_ns=1,error=error)

class Tests(unittest.TestCase):
    def test_exact_backend_and_admin(self):
        result=reconcile([call()],[row(),row('SELECT 99',label='ttg-performance-owned-admin')],'perf_test')
        self.assertTrue(result['passed']);self.assertEqual(result['excluded_admin_records'],1)
    def test_expected_parse_error(self):
        self.assertTrue(reconcile([call(error='expected')],[row(error=True)],'perf_test')['passed'])
    def test_execution_error_with_execute(self):
        self.assertTrue(reconcile([call(error='expected')],[row(),row(error=True)],'perf_test')['passed'])
    def test_other_database_excluded(self):
        self.assertTrue(reconcile([call()],[row(),row('SELECT 99',db='other')],'perf_test')['passed'])
    def test_reject_old_and_unexpected_labels(self):
        for label in ('jac','jac:abc:run','jac:123:other','jac:123:run:extra','', 'unrelated'):
            with self.subTest(label=label),self.assertRaisesRegex(ValueError,'backend label'):
                reconcile([call()],[row(label=label)],'perf_test')
    def test_reject_server_extra(self):
        with self.assertRaises(ValueError):reconcile([call()],[row(),row('SELECT 99')],'perf_test')
    def test_reject_missing_server_query(self):
        with self.assertRaises(ValueError):reconcile([call(),call('SELECT 99')],[row()],'perf_test')
    def test_reject_wrong_error(self):
        with self.assertRaises(ValueError):reconcile([call(error='x')],[row('SELECT 99',error=True)],'perf_test')
    def test_reject_duplicate_execute(self):
        with self.assertRaises(ValueError):reconcile([call()],[row(),row()],'perf_test')

if __name__=='__main__':unittest.main()
