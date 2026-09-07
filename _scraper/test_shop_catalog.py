"""Regression gates for import visibility, pagination and source separation."""
import json
import unittest
from pathlib import Path
from bs4 import BeautifulSoup
from sync_shop_sources import naver_public_product,imweb_public_price,flatten_categories,ROOT
from sync_kpp_catalog import parse_cards,category_tree
from build_catalog import model_key,brand_id
from enrich_shop_sources import source_fingerprint

class SourceRules(unittest.TestCase):
    def channel(self,**extra):
        return {'channelServiceType':'STOREFARM','channelProductDisplayStatusType':'ON','statusType':'SALE','channelProductNo':123,'originProductNo':12,'name':'[대여] Sony camera','salePrice':3000,**extra}
    def test_nonpublic_inventory_never_published(self):
        for changed in ({'channelProductDisplayStatusType':'OFF'},{'statusType':'SUSPENSION'},{'statusType':'UNADMISSION'},{'channelServiceType':'WINDOW'}):
            self.assertIsNone(naver_public_product(self.channel(**changed)))
        self.assertEqual(naver_public_product(self.channel(statusType='OUTOFSTOCK'))['status'],'soldout')
        self.assertEqual(naver_public_product(self.channel())['kind'],'rental')
    def test_imweb_public_discount_only(self):
        p={'price':635000,'product_discount_options':['period'],'period_discount_data':[{'group_type':'비회원+회원','dc_type':'price','dc_price':37300}]}
        self.assertEqual(imweb_public_price(p),597700)
        p['period_discount_data'][0]['group_type']='회원';self.assertEqual(imweb_public_price(p),635000)
    def test_dji_root_and_tree(self):
        cats=flatten_categories([{'code':'tilta','name':'틸타','list':[{'code':'x','name':'DJI'}]},{'code':'dji','name':'디지아이','list':[{'code':'action','name':'액션캠'}]}])
        roots=[c for c in cats if c['parent_id'] is None and c['name']=='디지아이']
        self.assertEqual([c['id'] for c in roots],['dji']);self.assertEqual(cats[-1]['path_ids'],['dji','action'])
    def test_omitted_card_close_does_not_leak_stock(self):
        soup=BeautifulSoup('<ul id="sct"><li class="sct_li"><div class="sct_txt"><a href="item.php?it_id=123">첫 상품</a></div><div class="sct_cost">10,000원</div><li class="sct_li"><div class="sct_txt"><a href="item.php?it_id=456">둘째 상품</a></div><span class="stock_yn">Sold Out</span></ul>','lxml')
        cards=parse_cards(soup);self.assertEqual(len(cards),2);self.assertEqual(cards[0]['supplier_status'],'listed');self.assertEqual(cards[1]['supplier_status'],'soldout')
    def test_independent_brand_paths(self):
        soup=BeautifulSoup('<a href="list.php?ca_id=d210">케이지</a><a href="list.php?ca_id=d21010">SONY</a>','lxml')
        cats=category_tree(soup.select('a'),'brand:SMALLRIG');self.assertEqual(cats[1]['path_ids'],['d210','d21010']);self.assertEqual(cats[0]['scope'],'brand:SMALLRIG')
    def test_source_changes_invalidate_detail_cache(self):
        product={'name':'Cage','price':10000,'sale_price':9000,'supplier_status':'listed','images':{'thumb':'https://example.com/old.jpg'}}
        original=source_fingerprint(product)
        self.assertNotEqual(original,source_fingerprint({**product,'price':12000}))
        self.assertNotEqual(original,source_fingerprint({**product,'images':{'thumb':'https://example.com/new.jpg'}}))
        self.assertNotEqual(original,source_fingerprint({**product,'supplier_status':'soldout'}))
    def test_sync_cannot_commit_operator_or_legacy_files(self):
        from shop_sync import managed_files
        if not (ROOT/'data/catalog/catalog.json').exists():self.skipTest('Build catalogue first')
        files=managed_files()
        self.assertNotIn('data/catalog/overrides.json',files)
        self.assertFalse(any(p.startswith('data/products/') for p in files))
        self.assertFalse(any(p.startswith('_scraper/') for p in files))
    def test_exact_model_preserves_variants_and_rentals(self):
        self.assertEqual(model_key({'brand_id':'smallrig','kind':'purchase','name':'SMALLRIG 2903C 모니터 마운트'}),'2903C')
        self.assertNotEqual(model_key({'brand_id':'smallrig','kind':'purchase','name':'SMALLRIG 2903 모니터 마운트'}),'2903C')
        self.assertIsNone(model_key({'brand_id':'smallrig','kind':'rental','name':'SMALLRIG 2903C'}))
        self.assertIsNone(model_key({'brand_id':'smallrig','kind':'purchase','name':'세트 2903 2904'}))
        self.assertEqual(brand_id('스몰리그'),brand_id('SMALLRIG'))
        self.assertEqual(model_key({'brand_id':'tilta','kind':'purchase','name':'틸타 TA-BSP-15-G 그레이'}),'TA-BSP-15-G')
        self.assertNotEqual(model_key({'brand_id':'tilta','kind':'purchase','name':'틸타 TA-BSP-15-B 블랙'}),'TA-BSP-15-G')
    def test_generated_catalog_integrity(self):
        p=ROOT/'data/catalog/catalog.json'
        if not p.exists():self.skipTest('Build the catalogue first')
        d=json.loads(p.read_text());ids={p['id'] for p in d['products']};cats={c['id'] for c in d['categories']};brands={b['id'] for b in d['brands']}
        self.assertEqual(len(ids),len(d['products']))
        self.assertEqual(len(ids),d['meta']['product_count'])
        for p in d['products']:
            self.assertIn(p['brand_id'],brands)
            self.assertTrue(set(p['category_ids']+p['type_ids'])<=cats,p['id'])
            self.assertNotIn(p['id'],d['redirects'])
            for offer in p['offers']:
                self.assertTrue(offer['url'].startswith(('https://smartstore.naver.com/rainbowbene/','https://rainbowshop.imweb.me/','https://kppkpp.co.kr/')))
        self.assertTrue(set(d['redirects'].values())<=ids)
        self.assertGreater(d['meta']['source_counts']['imweb-dji'],0)

if __name__=='__main__':unittest.main()
