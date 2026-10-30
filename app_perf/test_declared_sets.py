import unittest
from identity import Identities

A='11111111-1111-4111-8111-111111111111'
B='22222222-2222-4222-8222-222222222222'
SCHEMA={'ExploreLinks':{'seen':{'element_type':'str'}}}

class DeclaredSetTests(unittest.TestCase):
    def normalize(self,value):return Identities({A:'article:a',B:'article:b'},set_schema=SCHEMA).normalize(value)
    def state(self,seen):return {'_jac_type':'ExploreLinks','_jac_archetype':'walker','seen':seen}
    def test_declared_set_repr_order_is_not_semantic(self):
        self.assertEqual(self.normalize(self.state("{'"+A+"', '"+B+"'}")),
            self.normalize(self.state("{'"+B+"', '"+A+"'}")))
    def test_missing_or_changed_members_fail(self):
        original=self.normalize(self.state("{'"+A+"', '"+B+"'}"))
        self.assertNotEqual(original,self.normalize(self.state("{'"+A+"'}")))
        self.assertNotEqual(original,self.normalize(self.state("{'"+A+"', 'different literal'}")))
        with self.assertRaisesRegex(ValueError,'unknown UUID'):
            self.normalize(self.state("{'"+A+"', '33333333333343338333333333333333'}"))
    def test_ordinary_strings_and_lists_keep_order(self):
        first={'seen':"{'"+A+"', '"+B+"'}",'ordered':[A,B]}
        reverse={'seen':"{'"+B+"', '"+A+"'}",'ordered':[B,A]}
        self.assertNotEqual(self.normalize(first),self.normalize(reverse))
        self.assertNotEqual(self.normalize({'_jac_type':'Other','_jac_archetype':'walker',**first}),
            self.normalize({'_jac_type':'Other','_jac_archetype':'walker',**reverse}))
    def test_wrong_element_type_container_and_code_are_rejected(self):
        for value in ("{1,2}","['a','b']","{}","__import__('os').getcwd()","{'a','a'}"):
            with self.subTest(value=value),self.assertRaises(ValueError):self.normalize(self.state(value))
        self.assertEqual(self.normalize(self.state('set()'))['seen']['members'],[])
    def test_reports_remain_ordered(self):
        first={'result':self.state("{'"+A+"', '"+B+"'}"),'reports':[A,B]}
        other={'result':self.state("{'"+B+"', '"+A+"'}"),'reports':[B,A]}
        self.assertNotEqual(self.normalize(first),self.normalize(other))

if __name__=='__main__':unittest.main()
