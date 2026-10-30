import copy
import unittest
from identity import Identities

A = '11111111-1111-4111-8111-111111111111'
B = '22222222-2222-4222-8222-222222222222'
C = '33333333-3333-4333-8333-333333333333'
D = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
E = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb'
F = 'cccccccc-cccc-4ccc-8ccc-cccccccccccc'

class IdentityTests(unittest.TestCase):
    def setUp(self):
        self.transcript = [
            {'walker': 'Board', 'input': {}, 'output': {'nodes': [
                {'id': A, 'name': 'release', 'status': 'open'},
                {'id': B, 'name': 'build', 'status': 'created'},
                {'id': C, 'name': 'check', 'amount': 17}], 'edges': [[A, B], [B, C]]}},
            {'walker': 'Deploy', 'input': {'build_id': B}, 'output': {
                'artifact': 'sha256:' + B.replace('-', ''),
                'payment_reference': 'PAY-' + A,
                'url': f'https://example.test/walker/View/{B}?owner={A}',
                'encoded_url': 'https://example.test/' + C.replace('-', '%2D'), 'status': 'deployed'}}]

    def normalized(self, value):
        return Identities({A: 'release', B: 'build', C: 'check'}).normalize(value)

    def test_consistent_renaming_including_embedded_references(self):
        renamed = copy.deepcopy(self.transcript)
        import json
        text = json.dumps(renamed)
        for old, new in [(A, D), (B, E), (C, F)]:
            text = text.replace(old, new).replace(old.replace('-', ''), new.replace('-', ''))
            text = text.replace(old.replace('-', '%2D'), new.replace('-', '%2D'))
        other = json.loads(text)
        self.assertEqual(self.normalized(self.transcript), Identities({D: 'release', E: 'build', F: 'check'}).normalize(other))

    def test_changed_topology_fails(self):
        changed = copy.deepcopy(self.transcript)
        changed[0]['output']['edges'][1] = [A, C]
        self.assertNotEqual(self.normalized(self.transcript), self.normalized(changed))

    def test_changed_order_amount_status_action_sequence_fail(self):
        mutations = []
        order = copy.deepcopy(self.transcript)
        order[0]['output']['nodes'].reverse()
        mutations.append(order)
        amount = copy.deepcopy(self.transcript)
        amount[0]['output']['nodes'][2]['amount'] = 18
        mutations.append(amount)
        status = copy.deepcopy(self.transcript)
        status[1]['output']['status'] = 'failed'
        mutations.append(status)
        mutations.append(list(reversed(self.transcript)))
        for changed in mutations:
            self.assertNotEqual(self.normalized(self.transcript), self.normalized(changed))

    def test_wrong_embedded_id_fails(self):
        changed = copy.deepcopy(self.transcript)
        changed[1]['output']['artifact'] = 'sha256:' + C.replace('-', '')
        self.assertNotEqual(self.normalized(self.transcript), self.normalized(changed))

    def test_true_64_hex_digest_is_semantic(self):
        value = {'digest': 'sha256:' + 'a' * 64}
        self.assertEqual(Identities().normalize(value), value)
        self.assertNotEqual(Identities().normalize(value), Identities().normalize({'digest': 'sha256:' + 'b' * 64}))

    def test_no_identity_collapse(self):
        normalized = Identities().normalize({'ids': [A, B, C, B]})
        ids = normalized['ids']
        self.assertEqual(len(set(ids)), 3)
        self.assertEqual(ids[1], ids[3])

if __name__ == '__main__':
    unittest.main(verbosity=2)
