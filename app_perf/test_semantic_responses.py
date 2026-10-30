import copy
from datetime import datetime
import unittest
from semantic_responses import canonicalize

A='11111111-1111-4111-8111-111111111111'
B='22222222-2222-4222-8222-222222222222'
C='33333333-3333-4333-8333-333333333333'

class ResponseTests(unittest.TestCase):
    def fixture(self):
        return [dict(path='/walker/load_channel/'+A,phase='workflow',input={},output={'data':{'reports':[
            {'id':B,'content':'message 0','author_username':'user_0005','reply_count':0},
            {'id':C,'content':'message 1','author_username':'user_0000','reply_count':1}]}}),
            dict(path='/walker/SuiteInspect',input={'mapping':{'channel:0':A,'message:0:0':B,'message:0:1':C}},phase='verify')]

    def test_different_author_content_reply_count_or_order_fail(self):
        original=self.fixture();base=canonicalize(original)['full_semantic_sha256']
        for field,value in [('author_username','user_0004'),('content','wrong content'),('reply_count',9)]:
            changed=copy.deepcopy(original);changed[0]['output']['data']['reports'][0][field]=value
            self.assertNotEqual(base,canonicalize(changed)['full_semantic_sha256'])
        changed=copy.deepcopy(original);changed[0]['output']['data']['reports'].reverse()
        self.assertNotEqual(base,canonicalize(changed)['full_semantic_sha256'])

    def test_consistent_domain_identity_renaming_matches(self):
        import json
        original=self.fixture();text=json.dumps(original)
        renamed=json.loads(text.replace(A,'a'*32).replace(B,'b'*32).replace(C,'c'*32))
        self.assertEqual(canonicalize(original)['full_semantic_sha256'],canonicalize(renamed)['full_semantic_sha256'])

if __name__=='__main__':unittest.main()
