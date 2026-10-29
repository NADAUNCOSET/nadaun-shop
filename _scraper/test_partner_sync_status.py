import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from partner_sync_status import verified_receipt, report


class PartnerStatusTest(unittest.TestCase):
    def test_reviewed_receipt_uses_owner_allowed_ids_instead_of_raw_inventory_count(self):
        from copy import deepcopy
        from test_reviewed_source_worker import fixture
        from reviewed_source_worker import normalize
        from brand_source_policy import publishable_ids,policy_fingerprint
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);folder=root/'digitalcp';folder.mkdir()
            raw=fixture();extra=deepcopy(raw['products']['digitalcp-1'])
            extra.update(id='digitalcp-2',source_id='2',brand='NovaChips',source_url='https://www.digitalcp.co.kr/product/2')
            raw['products'][extra['id']]=extra;raw['product_count']=2;raw['source_inventory_count']=3
            raw['coverage'][0].update(expected=3,unique=3)
            snapshot=normalize(raw);path=root/'digitalcp.json';path.write_text(json.dumps(snapshot))
            expected=publishable_ids(snapshot);self.assertEqual(expected,{'digitalcp-1'})
            receipt={'source_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'verified_products':1,
                     'source_verified_products':2,'excluded_ids':['digitalcp-2'],'policy_sha256':policy_fingerprint(),
                     'commit':'a','deployment':'b','revision':'c','verified_at':'now'}
            (folder/'published.json').write_text(json.dumps(receipt))
            self.assertTrue(verified_receipt('digitalcp',root,root))
            receipt['excluded_ids']=[];(folder/'published.json').write_text(json.dumps(receipt))
            self.assertFalse(verified_receipt('digitalcp',root,root))

    def test_reviewed_adapter_exists_but_old_receipt_never_proves_current_schedule_or_live(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);folder=root/'sunphoto';folder.mkdir()
            (folder/'published.json').write_text(json.dumps({'source_collected_at':'2020-01-01T00:00:00+00:00'}))
            plan=root/'plan.json';plan.write_text(json.dumps({'sources':{'sunphoto':{'name':'썬포토','adapter':'reviewed_source_worker','refresh_interval_seconds':43200}}}))
            result=report(plan,root,root)['sources']['sunphoto']
            self.assertTrue(result['automatic_refresh_implemented'])
            self.assertFalse(result['scheduler_checked']);self.assertFalse(result['live_rechecked'])
            self.assertTrue(result['source_refresh_due'])

    def test_source_hold_and_unresolved_worker_error_override_old_success_phase(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);folder=root/'clmedia';folder.mkdir()
            plan=root/'plan.json';plan.write_text(json.dumps({'sources':{'clmedia':{'name':'씨엘미디어','adapter':'cafe24','collection_adapter':'cafe24'}}}))
            (folder/'progress.json').write_text(json.dumps({'phase':'live_verified'}))
            error=folder/'worker-error.json';error.write_text(json.dumps({'requires_review':True}))
            self.assertEqual(report(plan,root,root)['sources']['clmedia']['phase'],'error_requires_review')
            hold=folder/'source-suspended.json';hold.write_text(json.dumps({'suspended':True}))
            self.assertEqual(report(plan,root,root)['sources']['clmedia']['phase'],'source_suspended')
            hold.write_text(json.dumps({'suspended':False}));error.write_text(json.dumps({'requires_review':True,'resolved':True}))
            self.assertEqual(report(plan,root,root)['sources']['clmedia']['phase'],'live_verified')

    def test_private_collection_does_not_claim_recurring_live_sync(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);folder=root/'clmedia';folder.mkdir()
            (folder/'progress.json').write_text(json.dumps({'at':'now','phase':'inventory','products_found':56,'page':2,'pages_in_category':79}))
            plan=root/'plan.json';plan.write_text(json.dumps({'sources':{'clmedia':{'name':'씨엘미디어','adapter':None,'collection_adapter':'cafe24'}}}))
            result=report(plan,root,root)['sources']['clmedia']
            self.assertEqual(result['phase'],'inventory');self.assertTrue(result['collection_adapter_ready'])
            self.assertFalse(result['automatic_refresh_implemented']);self.assertFalse(result['last_snapshot_live_verified'])
            self.assertEqual(result['progress']['page'],2)

    def test_dji_refresh_reports_provider_progress_after_generation_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);folder=root/'dji-official';folder.mkdir()
            (folder/'generation.json').write_text(json.dumps({'directory':'generation-2'}))
            (folder/'progress.json').write_text(json.dumps({'phase':'details','at':'now','products_found':910,'details_verified':150}))
            plan=root/'plan.json';plan.write_text(json.dumps({'sources':{'dji-official':{'name':'DJI 공식 한국 스토어','adapter':'dji-official','refresh_interval_seconds':43200}}}))
            result=report(plan,root,root)['sources']['dji-official']
            self.assertEqual(result['progress']['details_verified'],150)
            self.assertEqual(result['progress']['products_found'],910)
            self.assertEqual(result['progress']['checked_at'],'now')
            self.assertFalse(result['last_snapshot_live_verified'])

    def test_partial_or_stale_snapshot_never_unlocks_the_next_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); (root/'plthink').mkdir()
            snap = root/'plthink.json'
            snap.write_text(json.dumps({'complete': True, 'product_count': 1, 'products': {'plthink-1': {'id':'plthink-1','source':'plthink','kind':'purchase','brand':'TEST','name':'test product'}}}))
            receipt = {'source_sha256': hashlib.sha256(snap.read_bytes()).hexdigest(), 'verified_products': 1,
                       'commit': 'a', 'deployment': 'b', 'revision': 'c', 'verified_at': 'now'}
            (root/'plthink/published.json').write_text(json.dumps(receipt))
            self.assertTrue(verified_receipt('plthink', root, root))
            snap.write_text(json.dumps({'complete': False, 'product_count': 1, 'products': {'plthink-1': {}}}))
            self.assertFalse(verified_receipt('plthink', root, root))
            self.assertFalse(verified_receipt('onnoff', root, root))

    def test_queue_configuration_cannot_claim_an_automatic_mirror(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); plan = root/'plan.json'
            plan.write_text(json.dumps({'sources': {'onnoff': {'name': '온앤오프', 'adapter': None, 'after_live_verified': 'plthink'}}}))
            result = report(plan, root, root)['sources']['onnoff']
            self.assertEqual(result['waiting_for_live_source'], 'plthink')
            self.assertEqual(result['phase'], 'awaiting_source_access')
            self.assertFalse(result['automatic_refresh_implemented'])
            self.assertIsNone(result['refresh_interval_seconds'])

    def test_avx_reports_current_generation_without_claiming_partial_as_full(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); folder=root/'avx'; generation=folder/'generation-1'
            generation.mkdir(parents=True)
            (folder/'generation.json').write_text(json.dumps({'directory':'generation-1'}))
            (generation/'progress.json').write_text(json.dumps({'phase':'details','at':'now','expected':1772,'verified_details':150}))
            plan=root/'plan.json';plan.write_text(json.dumps({'sources':{'avx':{'name':'AVX','adapter':'avx','refresh_interval_seconds':43200}}}))
            result=report(plan,root,root)['sources']['avx']
            self.assertTrue(result['automatic_refresh_implemented'])
            self.assertFalse(result['last_snapshot_live_verified'])
            self.assertEqual(result['progress']['details_verified'],150)
            self.assertEqual(result['progress']['products_found'],1772)
            snap=root/'avx.json'
            for scope in ('aputure','all'):
                snap.write_text(json.dumps({'complete':True,'scope':scope,'catalogue_complete':scope=='all','product_count':1,'products':{'avx-1':{}}}))
                receipt={'source_sha256':hashlib.sha256(snap.read_bytes()).hexdigest(),'verified_products':1,'commit':'a','deployment':'b','revision':'c','verified_at':'now'}
                (folder/'published.json').write_text(json.dumps(receipt))
                self.assertEqual(verified_receipt('avx',root,root),scope=='all')


if __name__ == '__main__': unittest.main()
