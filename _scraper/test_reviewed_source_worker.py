from copy import deepcopy
from datetime import datetime,timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest
import reviewed_source_worker as worker
from sync_shop_sources import save_json

def fixture(source='digitalcp'):
    pid=source+'-1';host='www.digitalcp.co.kr' if source=='digitalcp' else 'sunphoto.kr'
    p={'id':pid,'source_id':'1','source':source,'source_url':'https://'+host+'/product/1',
       'name':'제품','brand':'Nikon' if source=='digitalcp' else 'TAMRON','kind':'purchase',
       'price':10000,'sale_price':10000,'detail_status':'verified','evidence_sha256':'a'*64,
       'images':{'main':['https://example.com/product.png']},'brand_category_ids':['root']}
    return {'source':source,'collected_at':datetime.now(timezone.utc).isoformat(),'complete':True,
        'product_count':1,'products':{pid:p},'categories':[{'id':'root','name':'제품','parent_id':None}],
        'coverage':[{'id':'root','expected':2 if source=='digitalcp' else 1,'unique':2 if source=='digitalcp' else 1}],
        'source_inventory_count':2,'excluded_counts':{'DJI':1},'owner_brand_roots':__import__('sync_sunphoto_catalog').ROOTS}

class ReviewedWorkerTests(unittest.TestCase):
    def test_normalization_preserves_original_category_coverage_and_checks_complete_partition(self):
        s=fixture();before=deepcopy(s);result=worker.normalize(s)
        self.assertEqual(s,before);self.assertEqual(result['source_category_coverage'],s['coverage'])
        self.assertEqual(result['coverage']['count'],1)
        for patch_value in [{'complete':False},{'source_inventory_count':3},{'coverage':[{'expected':2,'unique':1}]}]:
            with self.assertRaises(ValueError):worker.normalize(s|patch_value)

    def test_owner_exclusions_and_sunphoto_manufacturer_scope_cannot_be_published(self):
        for source,brand in [('digitalcp','DJI'),('digitalcp','NiSi'),('sunphoto','SIGMA')]:
            s=fixture(source);next(iter(s['products'].values()))['brand']=brand
            with self.assertRaises(ValueError):worker.normalize(s)
        with self.assertRaises(ValueError):worker.normalize(fixture('sunphoto')|{'owner_brand_roots':{'30':'Voigtlander'}})

    def test_current_snapshot_without_a_live_receipt_does_not_self_certify_or_recollect(self):
        with TemporaryDirectory() as d,patch.object(worker,'ROOT',Path(d)),patch.object(worker,'OUT',Path(d)/'sources'):
            save_json(worker.OUT/'digitalcp.json',worker.normalize(fixture()))
            with patch.object(worker,'publish',side_effect=AssertionError('Unverified initial publication')):
                self.assertEqual(worker.work('digitalcp'),{'phase':'awaiting_initial_live_verification','requests':0})

    def test_protection_and_review_latches_block_requests_before_any_collection(self):
        for filename in ['source-suspended.json','worker-error.json']:
            with TemporaryDirectory() as d,patch.object(worker,'ROOT',Path(d)),patch.object(worker,'OUT',Path(d)/'sources'):
                save_json(Path(d)/'_scraper/.sync-state/digitalcp'/filename,{'requires_review':True})
                self.assertEqual(worker.work('digitalcp')['requests'],0)

if __name__=='__main__':unittest.main()
