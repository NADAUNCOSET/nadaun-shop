import copy
import json
import unittest
from unittest.mock import patch

from sync_dji_official import SOURCE, STORE, DEPARTMENTS, list_key, listing, refurbished_listing, normalize_product, validate_snapshot, official_dji_ids
from sync_shop_sources import ROOT
from brand_source_policy import purchase_source_allowed
from catalog_dedup import conflict


class OfficialDjiTests(unittest.TestCase):
    def fixture(self):
        item={'ean':'6937224121973','variantId':192291,'slug':'dji-romo-p-water-tank-version',
              'type':'SKU','priceCents':1299000,'status':{'code':'on_sale'}}
        variant={'id':192291,'slug':item['slug'],'ean':item['ean'],'productId':192290,'title':'DJI ROMO P (물탱크 버전)',
                 'priceCents':1299000,'originalPriceCents':1940000,'status':{'code':'on_sale'},
                 'cover':{'original':'//se-cdn.djiits.com/romo.png?format=webp'}}
        product={'id':192290,'description':'<p>공식 제품 설명</p>','pcOverview':'<img src="//se-cdn.djiits.com/details.jpg">'}
        return item,variant,product

    def test_krw_price_stock_identity_and_own_images(self):
        item,v,p=self.fixture()
        row=normalize_product(item,v,p,{'robot-vacuums'},'now')
        self.assertEqual(row['sale_price'],1299000)
        self.assertEqual(row['source_original_price'],1940000)
        self.assertEqual(row['images']['main'],['https://se-cdn.djiits.com/romo.png?format=webp'])
        self.assertIn('https://se-cdn.djiits.com/details.jpg',row['images']['detail'])
        item['status']=v['status']={'code':'out_of_stock'}
        self.assertEqual(normalize_product(item,v,p,{'robot-vacuums'},'now')['status'],'soldout')

    def test_price_stock_and_product_mismatches_stop_publication(self):
        for mutation in ({'ean':'different'},{'slug':'different'},{'priceCents':1},{'status':{'code':'unknown'}},{'productId':1}):
            item,v,p=self.fixture();v.update(mutation)
            with self.assertRaises(ValueError):normalize_product(item,v,p,{'robot-vacuums'},'now')

    def test_legacy_cms_ids_preserve_both_service_identities(self):
        item,v,p=self.fixture();item['variantId']=30948;v['id']=39441
        row=normalize_product(item,v,p,{'robot-vacuums'},'now')
        self.assertEqual(row['source_verification']['listing_variant_id'],30948)
        self.assertEqual(row['source_verification']['variant_id'],39441)

    def test_structured_details_preserve_third_party_brand(self):
        item,v,p=self.fixture();v['title']='Lexar Professional SILVER PLUS 128GB'
        p={'id':v['productId'],'structuredOverview':[{'label':'개요','content':'<p>128GB 메모리카드</p>'}]}
        row=normalize_product(item,v,p,{'accessories'},'now')
        self.assertEqual(row['brand'],'Lexar')
        self.assertIn('128GB 메모리카드',row['description_text'])
        self.assertEqual(official_dji_ids({'products':{row['id']:row}}),set())

    def test_refurbished_on_sale_flag_does_not_make_soldout_stock_available(self):
        item,_,_=self.fixture();item.update(id=item['variantId'],status={'code':'out_of_stock'})
        state={'localization':{'country':'kr','language':'ko','currency':{'code':'KRW'}},
               'event':{'items':[{'slug':'drones','items':[
                   {'render':'TextSection','item':{'title':'드론'}},
                   {'render':'ProductRow','item':{'products':[item]}}]}]}}
        html='<a href="/kr/product/'+item['slug']+'">제품</a><script>window.__PRELOADED_STATE__ = '+json.dumps(state)+'</script>'
        class Fake:
            def get(self,url,params=None,**kwargs):
                if '/pages/' in url:return html
                return [{'ean':item['ean'],'slug':item['slug'],'on_sale':True,'price_cents':1299000,'original_price_cents':1940000}]
        rows,_,_=refurbished_listing(Fake())
        self.assertEqual(rows[item['ean']]['status']['code'],'out_of_stock')

    def test_source_created_combo_identifiers_are_not_dropped(self):
        item,_,_=self.fixture();item['ean']='EAN2026061101'
        self.assertEqual(list_key(item),'EAN2026061101')
        item['ean']=''
        with self.assertRaises(ValueError):list_key(item)

    def test_different_official_variants_never_merge_by_title(self):
        p={'id':'one','brand_id':'dji','kind':'purchase','source':SOURCE,'ean':'one','name':'Same title'}
        self.assertEqual(conflict(p,{**p,'id':'two','ean':'two'},{}),'different_official_variant')

    def test_duplicate_pages_and_incomplete_pages_are_rejected(self):
        item,_,_=self.fixture()
        class Fake:
            def get(self,*args,**kwargs):
                return {'success':True,'data':{'items':[item,item],'page':{'current':1,'pageSize':48,'total':2}}}
        with self.assertRaises(ValueError):listing(Fake(),'robot-vacuums','robot')
        class Partial:
            def get(self,*args,**kwargs):
                return {'success':True,'data':{'items':[item],'page':{'current':1,'pageSize':48,'total':2}}}
        with self.assertRaises(ValueError):listing(Partial(),'robot-vacuums','robot')

    def test_exclusive_dji_selection_preserves_rentals_and_other_brands(self):
        choices={'dji':{'source':SOURCE,'exclusive':True,'scope':'purchase'}}
        p={'brand':'디지아이','kind':'purchase','source':'plthink'}
        self.assertFalse(purchase_source_allowed(p,choices))
        self.assertFalse(purchase_source_allowed({**p,'source':'avx'},choices))
        self.assertTrue(purchase_source_allowed({**p,'source':SOURCE},choices))
        self.assertTrue(purchase_source_allowed({**p,'kind':'rental'},choices))
        self.assertTrue(purchase_source_allowed({**p,'brand':'SmallRig'},choices))

    def snapshot(self):
        item,v,p=self.fixture();row=normalize_product(item,v,p,{'robot-vacuums'},'now')
        return {'source':SOURCE,'complete':True,'catalogue_complete':True,'country':'kr','language':'ko','currency':'KRW',
            'product_count':1,'products':{row['id']:row},'coverage':{'expected':1,'unique':1},
            'categories':[{'id':'robot-vacuums','name':'로봇 청소기','parent_id':None}],
            'category_checks':[{'slug':slug,'category':None,'expected_cards':1,'verified_cards':1} for slug,_ in DEPARTMENTS+[('refurbished','공식 리퍼브 제품')]]}

    def test_incomplete_locale_categories_and_detail_never_replace_snapshot(self):
        good=self.snapshot();validate_snapshot(good)
        mutations=[{'complete':False},{'currency':'USD'},{'product_count':2},{'category_checks':[]},{'categories':[]}]
        for change in mutations:
            with self.assertRaises(ValueError):validate_snapshot({**good,**change})
        changed=copy.deepcopy(good);next(iter(changed['products'].values()))['detail_status']='pending'
        with self.assertRaises(ValueError):validate_snapshot(changed)

    def test_live_build_is_exclusively_official_and_robots_are_not_lighting(self):
        path=ROOT/'data/catalog/sources/dji-official.json'
        if not path.exists():self.skipTest('Official source is not activated yet')
        source=validate_snapshot(json.loads(path.read_text()))
        catalog=json.loads((ROOT/'data/catalog/catalog.json').read_text())
        products=[p for p in catalog['products'] if p['brand_id']=='dji' and p['kind']=='purchase']
        self.assertEqual({p['id'] for p in products},official_dji_ids(source))
        for p in products:
            self.assertEqual({o['source'] for o in p['offers']},{SOURCE})
            self.assertTrue(all(c.startswith(SOURCE+':') for c in p['navigation_category_ids']))
            self.assertEqual(p['sale_price'],source['products'][p['id']]['sale_price'])
            self.assertEqual(p['status'],source['products'][p['id']]['status'])
            if p['name'].startswith('DJI ROMO'):
                self.assertIn('type:robot-vacuum',p['type_ids'])
                self.assertNotIn('type:kpp:07',p['type_ids'])
        brand=next(b for b in catalog['brands'] if b['id']=='dji')
        by_id={c['id']:c for c in catalog['categories']}
        roots=[by_id[c]['name'] for c in brand['navigation_category_ids'] if by_id[c]['parent_id'] is None]
        self.assertEqual(len(roots),len(set(roots)))
        self.assertIn('로봇 청소기',roots)


if __name__=='__main__':unittest.main()
