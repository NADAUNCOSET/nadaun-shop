from pathlib import Path
from unittest.mock import patch
import json,tempfile,unittest
import requests
from full_refresh import validate_private_candidate,request_guard,source_delta,ROOT

class FullRefreshTests(unittest.TestCase):
    def candidate(self):return {'source':'test','complete':True,'product_count':1,'collected_at':'2026-10-30T01:00:00Z','products':{'test-1':{'id':'test-1','source':'test'}}}
    def test_incomplete_counts_errors_and_foreign_ids_cannot_be_marked_collected(self):
        base=self.candidate();self.assertIs(validate_private_candidate(base,'test'),base)
        for change in [{'complete':False},{'product_count':2},{'detail_errors':{'1':'missing'}},{'collected_at':'today'},{'products':{'other':{'id':'test-1','source':'test'}}}]:
            with self.assertRaises(ValueError):validate_private_candidate(base|change,'test')
    def test_own_sites_are_blocked_before_any_request(self):
        base=ROOT/'_private/catalog/test-runtime/full-refresh';base.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=base)as tmp,patch('requests.sessions.Session.request')as remote:
            with request_guard('test',Path(tmp)):
                with self.assertRaisesRegex(RuntimeError,'outside this supplier'):requests.get('https://shop.nadaun.co/data/catalog/catalog.json')
            remote.assert_not_called()
    def test_full_inventory_delta_keeps_price_option_and_missing_identity_distinct(self):
        before=self.candidate();before['products']['test-1'].update(price=100,options=[{'id':'black','price':100}]);before['products']['test-retired']={'id':'test-retired','source':'test'}
        after=self.candidate();after['products']['test-1'].update(price=200,options=[{'id':'white','price':200}]);after['products']['test-new']={'id':'test-new','source':'test'}
        delta=source_delta(before,after);self.assertEqual(delta['added'],['test-new']);self.assertEqual(delta['absent_from_new_inventory'],['test-retired']);self.assertEqual(delta['changed'][0]['fields'],['price','options']);self.assertFalse(delta['automatic_removal_approved'])
    def test_access_protection_stops_future_requests_and_persists_the_hold(self):
        base=ROOT/'_private/catalog/test-runtime/full-refresh';base.mkdir(parents=True,exist_ok=True)
        response=requests.Response();response.status_code=403
        with tempfile.TemporaryDirectory(dir=base)as tmp:
            root=Path(tmp);work=root/'_private/work';work.mkdir(parents=True)
            with patch('full_refresh.master',return_value=root),patch('requests.sessions.Session.request',return_value=response)as remote:
                with request_guard('test',work):
                    self.assertEqual(requests.get('https://supplier.example/').status_code,403)
                    with self.assertRaises(RuntimeError):requests.get('https://supplier.example/next')
                self.assertEqual(remote.call_count,1);self.assertFalse(remote.call_args.kwargs['allow_redirects'])
            hold=json.loads((root/'_scraper/.sync-state/test/source-suspended.json').read_text());self.assertFalse(hold['automatic_resume'])

if __name__=='__main__':unittest.main()
