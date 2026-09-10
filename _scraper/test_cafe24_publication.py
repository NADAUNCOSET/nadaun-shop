from copy import deepcopy
from datetime import datetime,timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import cafe24_publication as publication
import cafe24_worker as worker
from catalog_dedup import primary_key


def candidate():
    return {'source':'onnoff','complete':True,'collected_at':'2026-09-11T00:00:00+00:00','product_count':1,
        'categories':[{'id':'23','parent_id':None,'name':'브랜드'},{'id':'24','parent_id':'23','name':'Sony'}],
        'coverage':[{'id':cid,'expected':1,'unique':1,'pages':1} for cid in ('23','24')],
        'changed_categories':[],'detail_errors':{},'content_reviews':{},
        'products':{'onnoff-10':{'id':'onnoff-10','source_id':'10','source':'onnoff','kind':'purchase',
            'brand':'Sony','name':'Sony Test','detail_status':'verified','content_issues':[],
            'detail_checked_at':'2026-09-10T00:00:00+00:00','brand_category_ids':['24']}}}


class PublicationTests(unittest.TestCase):
    def test_full_coverage_and_original_tree_are_preserved(self):
        raw=candidate();prepared=publication.prepare(raw)
        self.assertEqual(prepared['original_categories'],raw['categories'])
        self.assertEqual(prepared['categories'],[{'id':'24','parent_id':None,'name':'Sony','brand':'Sony'}])
        publication.validate_candidate(prepared)
        self.assertEqual(publication.prepare(prepared),prepared)
        self.assertNotIn('normalized_for_shop',raw)

    def test_incomplete_identity_content_or_category_coverage_blocks_publication(self):
        for change in ('complete','coverage','identity','detail','changed','timestamp'):
            raw=candidate()
            if change=='complete':raw['complete']=False
            elif change=='coverage':raw['coverage'][0]['unique']=0
            elif change=='identity':raw['products']['onnoff-10']['source_id']='11'
            elif change=='detail':raw['products']['onnoff-10']['detail_status']='review_required'
            elif change=='changed':raw['changed_categories']=['24']
            else:raw['products']['onnoff-10']['detail_checked_at']=None
            with self.subTest(change=change),self.assertRaises(ValueError):publication.prepare(raw)

    def test_schema_brand_without_menu_gets_only_a_brand_root(self):
        raw=candidate();raw['products']['onnoff-10'].update(brand='DZOFILM',brand_category_ids=[])
        result=publication.prepare(raw)
        cid=result['products']['onnoff-10']['brand_category_ids'][0]
        node=next(node for node in result['categories'] if node['id']==cid)
        self.assertEqual(node['name'],'DZOFILM');self.assertIsNone(node['parent_id'])

    def test_nested_brand_paths_keep_consistent_ancestry(self):
        raw=candidate()
        raw['categories']=[{'id':'23','parent_id':None,'name':'브랜드'},
            {'id':'24','parent_id':'23','name':'DZOFILM'}, {'id':'25','parent_id':'24','name':'Thypoch'},
            {'id':'26','parent_id':'25','name':'Simera'}, {'id':'27','parent_id':'23','name':'Thypoch'}]
        raw['coverage']=[{'id':node['id'],'expected':1,'unique':1,'pages':1} for node in raw['categories']]
        raw['products']['onnoff-10'].update(brand='Thypoch',brand_category_ids=['25','26','27'])
        result=publication.prepare(raw);nodes={node['id']:node for node in result['categories']}
        self.assertIsNone(nodes['25']['parent_id']);self.assertEqual(nodes['26']['parent_id'],'25')
        self.assertEqual(nodes['26']['brand'],'Thypoch')

    def test_existing_primary_source_wins_even_if_new_supplement_has_larger_id(self):
        existing={'id':'plthink-1','source':'plthink','status':'inquiry'}
        new={'id':'onnoff-99999','source':'onnoff','status':'inquiry','_supplemental_source':True}
        self.assertLess(primary_key(existing),primary_key(new))

    def test_protection_latch_prevents_collector_and_publication(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(worker,'STATE',Path(tmp)):
            root=Path(tmp)/'onnoff';root.mkdir();(root/'source-suspended.json').write_text('{"suspended":true}')
            with patch.object(worker,'Collector') as collector,patch.object(worker,'publish') as publish:
                self.assertEqual(worker.work('onnoff')['phase'],'source_suspended')
                collector.assert_not_called();publish.assert_not_called()

    def test_wrong_live_ids_never_create_success_receipt(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(worker,'STATE',Path(tmp)):
            with patch('brand_source_policy.supplemental_source_approved',return_value=True),\
                 patch('brand_source_policy.publishable_ids',return_value={'onnoff-10'}),\
                 patch('shop_sync.run',return_value={'revision':'test'}),\
                 patch('shop_sync.request',return_value=Mock(json=lambda:{'products':[]})):
                with self.assertRaisesRegex(RuntimeError,'live product IDs'):worker.publish(candidate())
                self.assertFalse((Path(tmp)/'onnoff/published.json').exists())

    def test_successful_receipt_inside_refresh_window_makes_no_source_requests(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(worker,'STATE',Path(tmp)),patch.object(worker,'parser_revision',return_value='parser'):
            root=Path(tmp)/'onnoff';root.mkdir();raw=candidate()
            raw['collected_at']=datetime.now(timezone.utc).isoformat()
            (root/'catalogue-candidate.json').write_text(json.dumps(raw))
            (root/'published.json').write_text(json.dumps({'candidate_sha256':publication.digest(raw),'policy_sha256':'policy'}))
            with patch('brand_source_policy.policy_fingerprint',return_value='policy'),patch.object(worker,'Collector') as collect,patch.object(worker,'publish') as publish:
                result=worker.work('onnoff')
                self.assertEqual(result['phase'],'current')
                collect.assert_not_called();publish.assert_not_called()

    def test_successful_publish_receipts_only_live_verified_ids_and_source_digest(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(worker,'STATE',Path(tmp)/'state'),patch.object(worker,'OUT',Path(tmp)/'sources'):
            (Path(tmp)/'sources').mkdir()
            def run(**kwargs):
                value=kwargs['source_updates']['onnoff']
                (Path(tmp)/'sources/onnoff.json').write_text(json.dumps(value))
                return {'revision':'live','commit':'abc','deployment':'deployment','verified_at':'2026-09-11'}
            live={'products':[{'offers':[{'source':'onnoff','id':'onnoff-10'}]}]}
            with patch('brand_source_policy.supplemental_source_approved',return_value=True),patch('brand_source_policy.publishable_ids',return_value={'onnoff-10'}),patch('shop_sync.run',side_effect=run),patch('shop_sync.request',return_value=Mock(json=lambda:live)):
                receipt=worker.publish(candidate())
            self.assertEqual(receipt['verified_products'],1)
            self.assertEqual(receipt['source_verified_products'],1)
            self.assertEqual(receipt['excluded_ids'],[])
            self.assertTrue(receipt['source_sha256'])
            self.assertEqual(json.loads((Path(tmp)/'state/onnoff/published.json').read_text()),receipt)


if __name__=='__main__':unittest.main()
