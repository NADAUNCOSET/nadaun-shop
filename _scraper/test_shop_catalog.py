"""Regression gates for import visibility, pagination and source separation."""
import json
import unittest
from pathlib import Path
from bs4 import BeautifulSoup
from sync_shop_sources import naver_public_product,imweb_public_price,flatten_categories,ROOT
from sync_kpp_catalog import parse_cards,category_tree
from build_catalog import model_key,brand_id
from enrich_shop_sources import source_fingerprint
from catalog_dedup import deduplicate, name_key

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
        self.assertNotEqual(model_key({'brand_id':'pgytech','kind':'purchase','name':'백팩 휠 P-CB-180-01'}),model_key({'brand_id':'pgytech','kind':'purchase','name':'백팩 P-CB-180'}))

    def merge_fixture(self,names,brand='smallrig',options=None):
        products={}
        details={}
        for i,name in enumerate(names):
            pid=f'smartstore-{i+1}'
            products[pid]={'id':pid,'name':name,'brand_id':brand,'kind':'purchase','source':'smartstore','source_id':str(i+1),'status':'sale','source_url':'https://example.com/'+pid,'category_ids':[str(i)],'type_ids':[],'offers':[{'id':pid}],'sale_price':10000}
            details[pid]={'images':{'main':[pid+'.jpg'],'detail':[]},'options':(options or {}).get(i,[])}
        return products,details

    def test_many_old_copies_merge_without_losing_paths_or_offers(self):
        p,d=self.merge_fixture(['SMALLRIG 2903C 모니터 마운트','스몰리그 모니터 마운트 SR2903C','2903C 모니터 마운트'])
        redirects,a=deduplicate(p,d,{'smallrig':{'name':'SMALLRIG','aliases':['스몰리그']}})
        self.assertEqual(len(p),1);self.assertEqual(len(redirects),2)
        primary=next(iter(p.values()));self.assertEqual(primary['id'],'smartstore-3')
        self.assertEqual(set(primary['category_ids']),{'0','1','2'})
        self.assertEqual(len(primary['offers']),3)
        self.assertEqual(a['duplicate_entries_removed'],2)

    def test_unknown_color_does_not_bridge_incompatible_variants(self):
        p,d=self.merge_fixture(['2903C 블랙','2903C','2903C 화이트'])
        redirects,a=deduplicate(p,d,{'smallrig':{'name':'SMALLRIG'}})
        self.assertEqual(len(p),2)
        for group in a['groups']:
            names=' '.join(m['name'] for m in group['members'])
            self.assertFalse('블랙' in names and '화이트' in names)

    def test_bundle_options_and_rental_never_collapse(self):
        cases=[(['BP-M300 배터리','BP-M300 배터리 + 충전기 풀세트'],'fxlion',{}),(['2903C 마운트','2903C 마운트 2개'],'smallrig',{}),(['2903C 마운트','2903C 마운트'],'smallrig',{1:[{'name':'블랙'}]})]
        for names,brand,options in cases:
            p,d=self.merge_fixture(names,brand,options)
            redirects,_=deduplicate(p,d,{brand:{'name':brand}})
            self.assertEqual(redirects,{})
        p,d=self.merge_fixture(['2903C 마운트','2903C 마운트']);p['smartstore-2']['kind']='rental'
        self.assertEqual(deduplicate(p,d,{'smallrig':{'name':'smallrig'}})[0],{})

    def test_reviewed_titles_fail_closed_on_source_change(self):
        p,d=self.merge_fixture(['다른 새 상품'])
        with self.assertRaises(RuntimeError):
            deduplicate(p,d,{}, {'corrections':{'smartstore-1':{'expected_name':'이전 상품','name':'수정 이름','reason':'검토'}}})

    def test_site_metadata_policies_and_chat_links(self):
        for filename in ['index.html','catalog.html','brands/dji.html','terms.html','privacy.html','shipping.html','cart.html','checkout.html']:
            soup=BeautifulSoup((ROOT/filename).read_text(),'lxml')
            self.assertNotIn('{{',(ROOT/filename).read_text())
            self.assertTrue(soup.select_one('main').get_text(strip=True))
            for tag in ['meta[name="description"]','meta[property="og:description"]']:
                self.assertTrue(0<len(soup.select_one(tag)['content'])<=80,filename)
            self.assertEqual(len(soup.select('.chat-dock a[href="https://talk.naver.com/ct/w4w1o8"]')),1)
            self.assertEqual(len(soup.select('.chat-dock a[href="https://pf.kakao.com/_pyNxnxb/chat"]')),1)
            for target in ['terms','privacy','shipping']:
                self.assertTrue(soup.select_one(f'.legacy-footer a[href="/{target}.html"]'))
        self.assertNotIn('기존 스토어에서 구매',(ROOT/'assets/shop/shop.js').read_text())
    def test_kpp_supplier_soldout_is_not_left_as_orderable_inquiry(self):
        catalog=json.loads((ROOT/'data/catalog/catalog.json').read_text())
        source=json.loads((ROOT/'data/catalog/sources/kpp.json').read_text())['products']
        checked=0
        for p in catalog['products']:
            if p['id'] not in source or source[p['id']]['supplier_status']!='soldout':continue
            self.assertEqual(p['status'],'soldout',p['id'])
            own=next(o for o in p['offers'] if o['id']==p['id'])
            self.assertEqual(own['status'],'soldout',p['id'])
            checked+=1
        self.assertGreater(checked,0)

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
                self.assertTrue(offer['url'].startswith(('https://smartstore.naver.com/rainbowbene/','https://rainbowshop.imweb.me/','https://kppkpp.co.kr/','https://www.l-mount.co.kr/goods/goods_view.php?goodsNo=','https://www.plthink.com/shop/shopdetail.html?branduid=','https://www.avx.co.kr/goods/view?no=')))
        self.assertTrue(set(d['redirects'].values())<=ids)
        offers=[o['id'] for p in d['products'] for o in p['offers']]
        self.assertEqual(len(offers),len(set(offers)))
        self.assertEqual(set(offers),ids|set(d['redirects']))
        self.assertEqual(len(offers),len(ids)+d['meta']['merged_count'])
        audit=json.loads((ROOT/'data/catalog/dedup-audit.json').read_text())
        self.assertEqual(audit['input_count'],len(offers))
        self.assertIn('kpp-1774590609',ids) # replacement wheel
        self.assertIn('kpp-1730958308',ids) # camera backpack itself
        listing=[p for p in d['products'] if p.get('listing_id',p['id'])==p['id']]
        brand_map={b['id']:b for b in d['brands']}
        keys=[(p['brand_id'],p['kind'],name_key(p,brand_map[p['brand_id']])) for p in listing]
        self.assertEqual(len(keys),len(set(keys)))
        self.assertEqual(len(listing),d['meta']['listing_count'])
        for p in d['products']:
            if p.get('listing_id'):
                self.assertIn(p['listing_id'],ids)
                detail=json.loads((ROOT/'data/catalog/details'/(p['detail_bucket']+'.json')).read_text())[p['id']]
                self.assertTrue(any(v['id']==p['id'] for v in detail['related_variants']))
        self.assertGreater(d['meta']['source_counts']['imweb-dji'],0)

    def test_avx_source_conservation_and_aputure_replacement(self):
        base=ROOT/'data/catalog/sources'
        path=next((base/name for name in ('avx.json','avx-aputure.json') if (base/name).exists()),None)
        if path is None:self.skipTest('AVX source not imported yet')
        source=json.loads(path.read_text())
        products=json.loads((ROOT/'data/catalog/catalog.json').read_text())['products']
        offers=[o['id'] for p in products for o in p['offers'] if o['source']=='avx']
        self.assertEqual(set(offers),set(source['products']))
        self.assertEqual(len(offers),source['product_count'])
        for p in products:
            if p['brand_id']=='aputure' and p['kind']=='purchase':
                self.assertTrue(all(o['source']=='avx' for o in p['offers']))
                self.assertFalse({'type:camera','type:lens','type:cinema-lens'} & set(p['type_ids']))
        original=json.loads((base/'smartstore.json').read_text())['products']
        rentals={pid for pid,p in original.items() if p['kind']=='rental'}
        actual={o['id'] for p in products if p['kind']=='rental' for o in p['offers']}
        self.assertEqual(actual,rentals)

    def test_partner_coverage_options_and_brand_images(self):
        from sync_partner_catalogs import normalize_ldl_options,ldl_categories
        fixture={'option_groups':[{'values':[{'name':'화이트 : +16,000원','value':'1||16000||||0^|^화이트'}]}]*2,'options_require_confirmation':True}
        normalized=normalize_ldl_options(fixture)
        self.assertEqual(normalized['options'],[{'id':'1','name':'화이트','additional_price':16000}])
        self.assertFalse(normalized['options_require_confirmation'])
        with self.assertRaises(RuntimeError):
            ldl_categories(BeautifulSoup('<a href="goods_list.php?cateCd=003001">누락된 상위 분류</a>','lxml'))
        source=json.loads((ROOT/'data/catalog/sources/l-mount.json').read_text())
        data=json.loads((ROOT/'data/catalog/catalog.json').read_text())
        brand_index=json.loads((ROOT/'data/catalog/brands.json').read_text())
        self.assertEqual(brand_index['brands'],data['brands'])
        self.assertEqual(brand_index['meta']['revision'],data['meta']['revision'])
        self.assertNotIn('products',brand_index)
        image_rules=json.loads((ROOT/'data/catalog/partner-image-rules.json').read_text())
        self.assertTrue(source['complete']);self.assertEqual(len(source['coverage']),len(source['categories']))
        for report in source['coverage']:self.assertEqual(report['unique'],report['expected'])
        ids={p['id']:p for p in data['products']}
        for pid,original in source['products'].items():
            p=ids[data['redirects'].get(pid,pid)]
            self.assertIn('l-mount', [o['source'] for o in p['offers']])
            self.assertTrue(p['category_ids'])
            detail=json.loads((ROOT/'data/catalog/details'/(p['detail_bucket']+'.json')).read_text())[p['id']]
            if original['options']:self.assertEqual(detail['options'],original['options'])
            self.assertFalse(set(detail['images']['main']+detail['images']['detail']) & set(image_rules))
            if any(rule.get('notice') and pid in rule['products'] for rule in image_rules.values()):
                self.assertTrue(detail.get('description_notice'))
        for b in data['brands']:
            representative=next(p for p in data['products'] if p['id']==b['representative_id'])
            self.assertEqual(representative['brand_id'],b['id'])
            detail=json.loads((ROOT/'data/catalog/details'/(representative['detail_bucket']+'.json')).read_text())[representative['id']]
            self.assertIn(b['representative_image'],[representative['image'],*detail['images']['main']])
            self.assertEqual(representative['name'],b['representative_name'])
            self.assertTrue(b['logo'],b['id']);self.assertIn(b['image_kind'],('logo','product'))
            if b['logo'].startswith('/'):self.assertTrue((ROOT/b['logo'].lstrip('/')).is_file(),b['id'])

    def test_gift_directory_keeps_bulk_order_context_and_internal_category_links(self):
        source=json.loads((ROOT/'data/gift/manifest.json').read_text())
        page=BeautifulSoup((ROOT/'gifts.html').read_text(),'lxml')
        links=page.select('.category-image-grid>a')
        roots=[c for c in source['categories'] if not c['parent_ids']]
        self.assertEqual(len(links),len(roots))
        self.assertEqual({a['href'] for a in links},{'/gifts.html?category='+c['id'] for c in roots})
        self.assertIn('수량',page.select_one('main').get_text())
        self.assertFalse(page.select_one('main a[href*="nadaun-gift.com"]'))
        self.assertFalse(page.select_one('main .brand-grid'))
        self.assertTrue(page.select_one('.navigation a[href="/gifts.html"]'))
        for selector in ('meta[name="description"]','meta[property="og:description"]'):
            self.assertTrue(0<len(page.select_one(selector)['content'])<=80)
        self.assertIn('https://shop.nadaun.co/gifts.html',(ROOT/'catalog-sitemap.xml').read_text())

if __name__=='__main__':unittest.main()
