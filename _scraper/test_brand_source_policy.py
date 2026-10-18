import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import brand_source_policy as policy
from catalog_dedup import primary_key,deduplicate


class SourcePolicyTests(unittest.TestCase):
    def setUp(self):
        approval=patch.object(policy,'supplemental_source_approved',return_value=False)
        self.approval=approval.start();self.addCleanup(approval.stop)

    def test_retired_imweb_snapshots_are_preserved_but_never_selected(self):
        for source in policy.RETIRED_SOURCES:
            self.assertFalse(policy.purchase_source_allowed({'source':source,'kind':'purchase'},{}))
        with tempfile.TemporaryDirectory() as folder,patch.object(policy,'OUT',Path(folder)):
            p=Path(folder)/'imweb-dji.json';p.write_text('{"historical":true}')
            self.assertNotIn('imweb-dji',policy.snapshots())
            self.assertEqual(p.read_text(),'{"historical":true}')
            with self.assertRaises(ValueError):policy.snapshots({'source':'imweb','products':{}})

    def test_owner_all_brand_approval_resolves_avx_overlap_without_changing_primary(self):
        self.approval.side_effect=lambda source:source=='avx'
        counts={'smallrig':{'avx':1,'kpp':2},'sony':{'avx':1,'smartstore':2}}
        choices={'smallrig':{'source':'kpp','sources':['kpp','clmedia']}}
        with tempfile.TemporaryDirectory() as folder,patch.object(policy,'AUDIT',Path(folder)),patch.object(policy,'inventory',return_value=counts),patch.object(policy,'selections',return_value=choices):
            self.assertEqual(policy.pending({}),[])
            audit=policy.write_audit({'meta':{'revision':'approved'},'products':[]})
            self.assertTrue(all(not b['selection_pending'] for b in audit['brands']))
            self.assertTrue(all(b['approved_supplemental_sources']==['avx'] for b in audit['brands']))
            self.assertEqual(next(b for b in audit['brands'] if b['brand_id']=='smallrig')['selection']['source'],'kpp')

    def test_unselected_overlap_never_enters_publication(self):
        import avx_worker
        import avx_publication
        unresolved=[{'brand_id':'sony','sources':{'avx':1,'smartstore':2}}]
        selection={'held_ids':{'avx-1':'sony'},'excluded_ids':{},'pending_brands':{'sony':1},'content_review_ids':{}}
        with patch.object(avx_publication,'partition',return_value=({'products':{},'product_count':0},selection)),patch.object(policy,'pending',return_value=unresolved),patch.object(policy,'write_audit'),patch.object(avx_worker,'save_json') as save:
            result=avx_worker.publish({'products':{}})
            self.assertEqual(result['state'],'awaiting_brand_source_choices')
            self.assertEqual(save.call_args.args[0].name,'publication-waiting.json')

    def test_pending_overlap_is_explicit_and_confirmed_sources_are_honored(self):
        counts={'dji':{'avx':4,'plthink':3},'smallrig':{'avx':2,'kpp':7},'sony':{'avx':1,'smartstore':1}}
        with patch.object(policy,'inventory',return_value=counts),patch.object(policy,'selections',return_value={'dji':{'source':'avx'},'smallrig':{'source':'kpp'}}):
            self.assertEqual(policy.pending({}),[{'brand_id':'sony','sources':counts['sony']}])

    def test_selected_source_has_priority_for_the_same_identity(self):
        base={'status':'available','sale_price':None,'price':100,'name':'Smallrig 2903','id':'smartstore-1',
              'source':'smartstore','_preferred_source':'kpp','updated_at':''}
        selected={**base,'id':'kpp-1','source':'kpp','status':'soldout'}
        self.assertLess(primary_key(selected),primary_key(base))

    def test_owner_brand_limits_allow_all_selected_sources_and_preserve_rentals(self):
        choices=policy.selections()
        for brand,allowed in [('SmallRig',{'kpp','clmedia'}),('LEOFOTO',{'kpp'})]:
            for source in policy.NAMES:
                if source in policy.RETIRED_SOURCES:continue
                with self.subTest(brand=brand,source=source):
                    p={'brand':brand,'kind':'purchase','source':source}
                    self.assertEqual(policy.purchase_source_allowed(p,choices),source in allowed)
                    self.assertTrue(policy.purchase_source_allowed({**p,'kind':'rental'},choices))
        self.assertTrue(policy.purchase_source_allowed({'brand':'Sony','kind':'purchase','source':'clmedia'},choices))

    def test_exclusive_multi_source_build_requires_every_selected_snapshot(self):
        import build_catalog
        choices={'smallrig':{'source':'kpp','sources':['kpp','clmedia'],'exclusive':True}}
        with patch.object(build_catalog,'verified_sources',return_value={'kpp':{}}),patch.object(policy,'selections',return_value=choices):
            with self.assertRaisesRegex(RuntimeError,'Exclusive replacement.*smallrig'):
                build_catalog.build()

    def test_both_tilta_main_sources_beat_old_smartstore_main(self):
        choice=policy.selections()['tilta']
        base={'id':'smartstore-1','source':'smartstore','status':'sale',
              '_preferred_source':choice['source'],'_preferred_sources':choice['main_sources']}
        for source in ('avx','clmedia'):
            selected={**base,'id':source+'-1','source':source,'status':'soldout','_supplemental_source':True}
            self.assertLess(primary_key(selected),primary_key(base))
        for source in ('avx','clmedia','kpp','smartstore'):
            self.assertTrue(policy.purchase_source_allowed({'brand':'TILTA','kind':'purchase','source':source}))

    def test_generated_register_identifies_both_tilta_main_sources(self):
        from catalog_navigation import write_register
        offers=[{'id':s+'-1','source':s} for s in ('avx','clmedia','smartstore')]
        catalog={'meta':{'revision':'test'},'brands':[{'id':'tilta','name':'TILTA'}],
                 'products':[{'id':'avx-1','brand_id':'tilta','kind':'purchase','offers':offers}]}
        with tempfile.TemporaryDirectory() as folder:
            write_register(catalog,{},policy.selections(),Path(folder))
            report=json.loads((Path(folder)/'brand-source-register.json').read_text())
            self.assertEqual(report['brands'][0]['main_sources'],['avx','clmedia'])
            self.assertEqual(report['brands'][0]['supplemental_sources'],['smartstore'])
            self.assertEqual(report['publication_state'],'not_live_verified')
            self.assertIn('AVX, 씨엘미디어',(Path(folder)/'brand-source-register.md').read_text())

    def test_every_canonical_product_has_exact_primary_source_and_all_matches(self):
        offers=[{'id':'kpp-1','source':'kpp','url':'https://example.com/1'},
                {'id':'smartstore-2','source':'smartstore','url':'https://example.com/2'}]
        p={'id':'kpp-1','name':'Smallrig 2903','brand_id':'smallrig','kind':'purchase','offers':offers}
        with tempfile.TemporaryDirectory() as folder,patch.object(policy,'AUDIT',Path(folder)),patch.object(policy,'inventory',return_value={'smallrig':{'kpp':1,'smartstore':1}}),patch.object(policy,'selections',return_value={'smallrig':{'source':'kpp'}}):
            report=policy.write_audit({'meta':{'revision':'abc'},'products':[p]})
            saved=json.loads((Path(folder)/'source-matches.json').read_text())
            self.assertEqual(saved,report)
            row=saved['products'][0]
            self.assertEqual((row['primary_source'],row['primary_source_product_id']),('kpp','kpp-1'))
            self.assertEqual(row['matched_sources'],offers)
            with self.assertRaises(ValueError):policy.write_audit({'meta':{'revision':'abc'},'products':[{**p,'id':'missing'}]})

    def test_single_source_and_rental_only_brands_are_in_the_report(self):
        rows=[{'id':'smartstore-1','name':'렌탈 카메라','brand_id':'sony','kind':'rental',
               'offers':[{'id':'smartstore-1','source':'smartstore','url':'https://example.com/1'}]}]
        with tempfile.TemporaryDirectory() as folder,patch.object(policy,'AUDIT',Path(folder)),patch.object(policy,'inventory',return_value={'ldl-mount':{'l-mount':335}}),patch.object(policy,'selections',return_value={}):
            report=policy.write_audit({'meta':{'revision':'a'},'products':rows})
            brands={b['brand_id']:b for b in report['brands']}
            self.assertEqual(brands['sony']['published_primary_counts'],{'rental':{'smartstore':1}})
            self.assertFalse(brands['ldl-mount']['public'])
            markdown=(Path(folder)/'brand-source-review.md').read_text()
            self.assertIn('sony',markdown);self.assertIn('ldl-mount',markdown)

    def test_mixed_source_images_keep_their_actual_origin(self):
        products={};details={}
        for source,number in [('smartstore','1'),('kpp','2')]:
            pid=source+'-'+number
            p={'id':pid,'source_id':number,'source':source,'source_url':'https://example.com/'+number,
               'brand_id':'smallrig','name':'SmallRig 2903','kind':'purchase','price':100,'sale_price':100,
               'status':'inquiry','category_ids':[source+':test'],'type_ids':[],'promotion_ids':[],
               'offers':[{'id':pid,'source':source,'url':'https://example.com/'+number}]}
            d={'images':{'main':['https://example.com/'+number+'.jpg'],'detail':[] if source=='smartstore' else ['https://example.com/detail.jpg']}}
            p['_provenance']=policy.source_provenance(p,d,{'source':source,'collected_at':'2026-09-08T00:00:00+00:00'})
            products[pid]=p;details[pid]=d
        deduplicate(products,details,{'smallrig':{'name':'SMALLRIG'}})
        self.assertEqual(len(products),1)
        origin=products['smartstore-1']['_provenance']
        self.assertEqual(origin['fields']['price']['source'],'smartstore')
        self.assertEqual(origin['fields']['images.detail']['source'],'kpp')
        self.assertEqual(set(origin['source_categories']),{'smartstore:test','kpp:test'})

    def test_live_receipt_checks_all_prices_and_preserves_waiting_audit_provenance(self):
        p={'id':'kpp-1','name':'상품','brand_id':'smallrig','kind':'purchase','sale_price':100,
           'offers':[{'id':'kpp-1','source':'kpp','url':'https://example.com/1'}]}
        catalog={'meta':{'revision':'a'},'products':[p]};release={'revision':'a','commit':'abc','deployment':'dpl','verified_at':'checked'}
        with tempfile.TemporaryDirectory() as folder,patch.object(policy,'AUDIT',Path(folder)),patch.object(policy,'inventory',return_value={}),patch.object(policy,'selections',return_value={}):
            policy.write_audit(catalog,provenance={'kpp-1':{'record':{'source_id':'1'},'fields':{}}})
            receipt=policy.verify_audit_live(catalog,release)
            self.assertEqual(receipt['state'],'live_verified')
            saved=policy.write_audit(catalog,candidate={'products':{}})
            self.assertEqual(saved['publication'],receipt)
            self.assertEqual(saved['products'][0]['source_id'],'1')
            with self.assertRaises(ValueError):policy.verify_audit_live({**catalog,'products':[{**p,'sale_price':200}]},release)


if __name__=='__main__':unittest.main()
