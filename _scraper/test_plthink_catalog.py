import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from bs4 import BeautifulSoup
import sync_plthink_catalog as source


class PLThinkImportTests(unittest.TestCase):
    def setUp(self):source._halt.clear()
    def tearDown(self):source._halt.clear()

    def test_mixed_source_encodings_preserve_korean_without_replacements(self):
        markup='<meta charset="utf-8"><h3>[유쾌한생각] 천장 설치 이동형배경</h3>'
        for encoding in ('utf-8','cp949'):
            self.assertEqual(source.decode_page(markup.encode(encoding)),markup)
        with self.assertRaises(ValueError):source.decode_page(b'\xff\xff')

    def test_reading_scope_excludes_global_recommendations(self):
        markup='''<a href="/shop/shopdetail.html?branduid=999"><h3>공통 추천</h3></a>
        <div id="productClass"><div class="item-total">Total : 1</div><div class="item-list-2021">
        <div class="item-list"><a href="/shop/shopdetail.html?branduid=123&amp;mcode=095&amp;scode=004">
        <div class="item-img"><img src="/shopimages/plthink/photo.jpg"></div><h3>[NANLITE] Miro 60C</h3>
        <div class="price"><strike>245,000</strike><h4>179,000 원</h4></div></a></div></div>
        <div class="class-list"><a href="/shop/shopbrand.html?mcode=095&amp;scode=004">미로</a></div></div>'''
        rows,total,pages,cats=source.list_page(BeautifulSoup(markup,'lxml'),{'id':'095','name':'NANLITE','label':'NANLITE(난라이트)'})
        self.assertEqual(set(rows),{'123'});self.assertEqual(total,1)
        self.assertEqual(rows['123']['price'],245000);self.assertEqual(rows['123']['sale_price'],179000)
        self.assertEqual(cats[1]['parent_id'],'095');self.assertEqual(rows['123']['brand_category_ids'],['095','095:004'])

    def test_partial_lists_never_pass_total_reconciliation(self):
        doc=BeautifulSoup('<div id="productClass"><div class="item-total">Total : 2</div></div>','lxml')
        with patch.object(source,'page',return_value=doc):
            with self.assertRaisesRegex(RuntimeError,'empty/repeated'):
                source.collect_brand({'id':'095','name':'NANLITE','label':'난라이트'})

    def test_sold_out_schema_and_complex_options_are_preserved_without_inventing_our_stock(self):
        schema={'@type':'Product','@id':'https://www.plthink.com/shop/shopdetail.html?branduid=123','name':'NANLITE Miro','offers':{'price':179000,'availability':'https://schema.org/OutOfStock'}}
        doc=BeautifulSoup('<script type="application/ld+json">'+json.dumps(schema)+'</script><div class="thumb"><img src="/shopimages/plthink/p.jpg"></div><div id="optionWrap"><select name="size"><option value="">선택</option><option value="L">Large</option></select></div><div class="detail-con-img"><img src="http://image.plthink.com/GOODS/ALL_COMMON/Makeshop-Notice.jpg"><img src="http://image.plthink.com/NANLITE/miro/01.jpg">제품 설명</div>','lxml')
        p=source.detail(doc,{'id':'plthink-123','source_id':'123','sale_price':None,'images':{}})
        self.assertEqual(p['status'],'soldout');self.assertEqual(p['supplier_status'],'soldout')
        self.assertEqual(p['images']['detail'],['https://image.plthink.com/NANLITE/miro/01.jpg'])
        self.assertTrue(p['options_require_confirmation']);self.assertEqual(p['options'],[])
        self.assertIn('제품 설명',p['description_text']);self.assertEqual(p['detail_status'],'verified')

    def test_rate_limit_stops_queued_requests_and_records_cooldown(self):
        class Response:
            status_code=302;apparent_encoding='utf-8';headers={}
            text='페이지를 너무 많이 요청을 하였습니다. 서버보호차원에서 차단 됩니다.'
        with tempfile.TemporaryDirectory() as tmp, patch.object(source,'RATE_STATE',Path(tmp)/'rate.json'), patch.object(source,'_next_request',0), patch.object(source.requests,'get',return_value=Response()) as get:
            with self.assertRaises(source.SourceRateLimited):source.page(source.BASE)
            with self.assertRaises(source.SourceRateLimited):source.page(source.BASE)
            self.assertEqual(get.call_count,1)
            self.assertGreater(json.loads(source.RATE_STATE.read_text())['retry_not_before'],source.time.time())

    def test_literal_newlines_and_html_in_service_names_do_not_block_the_catalogue(self):
        schema={'@type':'Product','@id':'https://www.plthink.com/shop/shopdetail.html?branduid=123','name':'<font color="blue">[스튜디오 시공]</font>\n오픈 스튜디오','description':'<b>설치 상담</b>\n일정 확인','offers':{'price':0,'availability':'https://schema.org/InStock'}}
        raw=json.dumps(schema,ensure_ascii=False).replace('\\n','\n')
        doc=BeautifulSoup('<script type="application/ld+json">'+raw+'</script><div class="thumb"><img src="/p.jpg"></div><div class="table-opt"><h4>가격문의</h4></div><div class="detail-con-img"><img src="/studio.jpg"></div>','lxml')
        p=source.detail(doc,{'id':'plthink-123','source_id':'123','sale_price':None,'images':{}})
        self.assertEqual(p['name'],'[스튜디오 시공] 오픈 스튜디오');self.assertEqual(p['description_text'],'설치 상담 일정 확인')
        self.assertIsNone(p['price']);self.assertIsNone(p['sale_price']);self.assertEqual(p['source_sale_price'],0);self.assertEqual(p['status'],'inquiry')

    def test_relaxed_string_control_parser_still_rejects_other_product_identity(self):
        schema={'@type':'Product','@id':'https://www.plthink.com/shop/shopdetail.html?branduid=999','name':'다른\n상품','offers':{'price':100}}
        doc=BeautifulSoup('<script type="application/ld+json">'+json.dumps(schema).replace('\\n','\n')+'</script><div class="thumb"><img src="/p.jpg"></div>','lxml')
        with self.assertRaisesRegex(RuntimeError,'identity mismatch'):
            source.detail(doc,{'id':'plthink-123','source_id':'123','images':{}})

    def test_source_apostrophe_escape_preserves_actual_product_dimensions(self):
        schema={'@type':'Product','@id':'https://www.plthink.com/shop/shopdetail.html?branduid=123','name':"플랙 4'x4' 확산판",'offers':{'price':1000}}
        raw=json.dumps(schema,ensure_ascii=False).replace("'","\\'")
        doc=BeautifulSoup('<script type="application/ld+json">'+raw+'</script><div class="thumb"><img src="/p.jpg"></div><div class="detail-con-img">확산판</div>','lxml')
        p=source.detail(doc,{'id':'plthink-123','source_id':'123','sale_price':None,'images':{}})
        self.assertEqual(p['name'],"플랙 4'x4' 확산판");self.assertEqual(p['price'],1000)

    def test_single_invalid_detail_does_not_prevent_later_valid_products_from_being_saved(self):
        brands=[{'id':'1','name':'브랜드'}]
        rows={str(n):{'id':'plthink-'+str(n),'source_id':str(n),'brand_category_ids':['1'],'source_url':source.BASE+'/shop/shopdetail.html?branduid='+str(n)} for n in (1,2)}
        valid={**rows['2'],'detail_status':'verified','detail_checked_at':source.stamp()}
        with tempfile.TemporaryDirectory() as tmp:
            cp=source.Checkpoint(Path(tmp)/'checkpoint.db')
            try:
                with patch.object(source,'WORK',Path(tmp)),patch.object(source,'OUT',Path(tmp)),patch.object(source,'page'),patch.object(source,'brand_menu',return_value=brands),patch.object(source,'collect_brand',return_value=(rows,[{'id':'1'}],{})),patch.object(source,'detail',side_effect=[RuntimeError('format changed'),valid]),patch.object(source,'report'):
                    with self.assertRaisesRegex(RuntimeError,'1 details need review'):source._collect_plthink(cp)
                self.assertIsNotNone(cp.detail(rows['2']));self.assertIsNone(cp.detail(rows['1']))
                self.assertFalse((Path(tmp)/'plthink.json').exists())
            finally:cp.close()


if __name__=='__main__':unittest.main()
