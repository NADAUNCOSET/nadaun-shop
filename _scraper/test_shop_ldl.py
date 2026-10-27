import json
import unittest
from sync_ldl_catalog import product_detail, exact_legacy_map

class LDLCurrentCatalog(unittest.TestCase):
    def fixture(self, **change):
        row={'code':'APL-GS501','priceVal':10000,'purchasable':True,'soldOut':False}
        schema={'@type':'Product','sku':row['code'],'name':'엘디엘마운트 APL-GS501','url':'https://www.l-mount.co.kr/products/APL-GS501','category':'모니터암','offers':{'priceCurrency':'KRW','price':'10000','url':'https://www.l-mount.co.kr/products/APL-GS501'},'image':['/main.jpg']}
        schema.update(change)
        raw='<script type="application/ld+json">'+json.dumps(schema)+'</script><div class="detail-info"><p>APL-GS501</p><h1>모니터암</h1></div><div id="tab-info">원본 설명</div>'
        return raw,row
    def test_new_layout_accepts_separate_visible_model_label(self):
        raw,row=self.fixture();p,c=product_detail(raw,row,'ldl-old')
        self.assertEqual(p['price'],10000);self.assertEqual(p['supplier_status'],'available');self.assertEqual(p['id'],'ldl-old');self.assertEqual(c['name'],'모니터암')
    def test_schema_price_currency_and_url_must_match_current_inventory(self):
        for offer in [{'priceCurrency':'USD','price':'10000'}, {'priceCurrency':'KRW','price':'9999'}, {'priceCurrency':'KRW','price':'10000','url':'https://evil.invalid'}]:
            raw,row=self.fixture(offers=offer)
            with self.assertRaises(ValueError):product_detail(raw,row,'ldl-old')
        raw,row=self.fixture(url='https://www.l-mount.co.kr/products/OTHER',offers={'priceCurrency':'KRW','price':'10000','url':'https://www.l-mount.co.kr/products/OTHER'})
        with self.assertRaises(ValueError):product_detail(raw,row,'ldl-old')
    def test_unknown_variants_never_receive_invented_prices(self):
        raw,row=self.fixture();raw+='<div class="color-opt"><span>블랙</span><span>화이트</span></div>'
        p,_=product_detail(raw,row,'ldl-old');self.assertTrue(p['options_require_confirmation']);self.assertEqual(p['options'],[])
        row['soldOut']=True;p,_=product_detail(raw,row,'ldl-old');self.assertEqual(p['status'],'soldout');self.assertEqual(p['supplier_status'],'soldout')
    def test_stale_api_price_requires_current_visible_price_and_schema_agreement(self):
        raw,row=self.fixture();row['priceVal']=9900
        with self.assertRaises(ValueError):product_detail(raw,row,'ldl-old')
        p,_=product_detail(raw+'<p class="detail-price">₩10,000</p>',row,'ldl-old')
        self.assertEqual(p['price'],10000);self.assertEqual(p['source_price_evidence']['api_price'],9900)
        with self.assertRaises(ValueError):product_detail(raw+'<p class="detail-price">₩9,900</p>',row,'ldl-old')
    def test_legacy_id_matching_requires_unique_full_model_code(self):
        previous={'products':{'one':{'id':'one','name':'APL-64PHS PLUS 모니터'},'two':{'id':'two','name':'APL-64PHS 모니터'},'three':{'id':'three','name':'APL-64PHS 모니터'}}}
        rows=[{'code':'APL-64PHS'},{'code':'APL-64PHS PLUS'}]
        self.assertEqual(exact_legacy_map(previous,rows),{'APL-64PHS PLUS':'one'})
    def test_source_omitted_category_retains_only_exact_previously_verified_model(self):
        raw,row=self.fixture(category='')
        prior={'id':'ldl-old','model_code':row['code'],'source':'l-mount','source_category_name':'모니터암'}
        p,c=product_detail(raw,row,'ldl-old',prior,'2026-10-18T00:00:00+00:00')
        self.assertEqual(c['name'],'모니터암')
        self.assertTrue(p['source_category_evidence']['current_source_category_missing'])
        for change in ({'model_code':'OTHER'},{'id':'another'},{'source':'other'},{'source_category_name':''}):
            with self.assertRaises(ValueError):product_detail(raw,row,'ldl-old',dict(prior,**change),'2026-10-18T00:00:00+00:00')
        with self.assertRaises(ValueError):product_detail(raw,row,'ldl-old',prior)

if __name__=='__main__':unittest.main()
