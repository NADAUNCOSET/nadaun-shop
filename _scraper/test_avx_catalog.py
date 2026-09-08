import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from sync_avx_catalog import Source, SourceSuspended, Importer, CatalogueChanged, parse_list, parse_detail


def listing(price='54,000', state='', sid='3034'):
    return f'''<script>var items = '[{{"item_id":"{sid}","item_category":"조명","item_category2":"APUTURE","item_category3":"조명 액세서리","item_brand":"Aputure"}}]';</script>
    <li class="goods_list_style2"><div class="item_img_area"><a><img src="/data/goods/{sid}_list.png"></a>{state}</div>
    <ul><li class="brand_name_area">Aputure</li><li class="goods_name_area"><a href="/goods/view?no={sid}">STORM 변환 어댑터</a></li>
    <li><span class="sale_price"><b class="num">{price}</b></span></li></ul></li>
    <script>$("a.total span.num").html('1');</script>'''


class AvxTests(unittest.TestCase):
    def test_list_uses_vat_inclusive_display_price_and_excludes_unrelated_links(self):
        total, products = parse_list('<a href="/goods/view?no=999">추천</a>'+listing())
        self.assertEqual((total,set(products)), (1,{'3034'}))
        self.assertEqual(products['3034']['price'],54000)
        self.assertEqual(products['3034']['source_category_path'],['조명','APUTURE','조명 액세서리'])

    def test_soldout_is_preserved_but_available_supplier_is_not_our_stock(self):
        self.assertEqual(parse_list(listing(state='재고확보중'))[1]['3034']['status'],'soldout')
        p = parse_list(listing())[1]['3034']
        self.assertEqual((p['status'],p['supplier_status']),('inquiry','available'))

    def test_missing_total_empty_or_duplicate_cannot_be_completed(self):
        for bad in ('<p>차단</p>',listing()+listing(),'<script>$("a.total span.num").html("10");</script>'):
            with self.assertRaises(ValueError): parse_list(bad)

    def test_protection_latches_and_blocks_next_request(self):
        with tempfile.TemporaryDirectory() as directory:
            session=Mock();session.get.return_value=Mock(status_code=429,text='limit')
            source=Source(Path(directory),session)
            for _ in range(2):
                with self.assertRaises(SourceSuspended): source.get('/goods/search_list')
            self.assertEqual(session.get.call_count,1)

    def test_detail_rejects_wrong_product_or_price_and_keeps_options_unconfirmed(self):
        p=parse_list(listing())[1]['3034']
        html='''<script>var gl_goods_seq=3034;var gl_goods_price=0;gl_goods_price=54000;</script>
        <div id="goods_thumbs"><div class="viewImgWrap"><img src="/data/goods/3034_view.png"></div></div>
        <div class="goods_option_select_area"><select name="viewOptions[]"><option value="">선택</option><option value="white">화이트</option></select></div>'''
        desc='<img src="/data/editor/light.jpg"><p>조명용 변환 어댑터</p>'
        parsed=parse_detail(p,html,desc)
        self.assertTrue(parsed['options_require_confirmation'])
        self.assertEqual(parsed['images']['detail'],['https://www.avx.co.kr/data/editor/light.jpg'])
        for bad in (html.replace('3034;', '3000;'),html.replace('54000;', '1000;')):
            with self.assertRaises(ValueError):parse_detail(p,bad,desc)
        p['price']=p['sale_price']=None
        inquiry=html.replace('54000;','99999999;')+'<script>gl_string_price_use = 1;</script>'
        self.assertIsNone(parse_detail(p,inquiry,desc)['price'])

    def test_changing_inventory_can_resume_without_losing_verified_details(self):
        with tempfile.TemporaryDirectory() as directory:
            importer=Importer(Path(directory))
            importer.db.execute('INSERT INTO pages VALUES (?,?,?)', ('/1',41,json.dumps({'3034':{'id':'3034'}})))
            importer.db.execute('INSERT INTO details VALUES (?,?,?)', ('3034','verified','{}'))
            importer.db.commit()
            importer.source.get=Mock(return_value=listing(sid='3035'))
            with self.assertRaises(CatalogueChanged):importer.listing()
            self.assertEqual(importer.db.execute('SELECT count(*) FROM pages').fetchone()[0],0)
            self.assertEqual(importer.db.execute('SELECT count(*) FROM details').fetchone()[0],1)
            self.assertEqual(set(importer.listing()),{'3035'})
            importer.db.close()

    def test_manufacturer_hosted_images_are_preserved_without_executing_source_html(self):
        p=parse_list(listing())[1]['3034']
        page='<script>gl_goods_seq=3034;gl_goods_price=54000;</script><div id="goods_thumbs"><div class="viewImgWrap"><img src="/data/goods/3034.png"></div></div>'
        desc='<div class="goods_desc_contents goods_description"><img src="https://contents.sony.co.kr/sony/contents/2478/ilme-fx2_960.jpg"><img src="javascript:bad()"></div>'
        parsed=parse_detail(p,page,desc)
        self.assertEqual(parsed['images']['detail'],['https://contents.sony.co.kr/sony/contents/2478/ilme-fx2_960.jpg'])
        self.assertEqual(parsed['content_status'],'complete')

    def test_confirmed_empty_source_is_review_required_but_missing_markup_still_fails(self):
        p=parse_list(listing())[1]['3034']
        page='<script>gl_goods_seq=3034;gl_goods_price=54000;</script><div id="goods_thumbs"></div>'
        desc='<div class="goods_desc_contents goods_description"></div>'
        parsed=parse_detail(p,page,desc)
        self.assertEqual(parsed['content_status'],'review_required')
        self.assertEqual(parsed['content_issues'],['source_gallery_empty','source_description_empty'])
        self.assertEqual(parsed['detail_status'],'verified')
        self.assertEqual(parsed['images']['main'],[])
        for html,body in [(page,'<html>\n</html>'),(page.replace('id="goods_thumbs"','id="changed"'),desc)]:
            with self.assertRaises(ValueError):parse_detail(p,html,body)

    def test_changed_final_inventory_keeps_previous_published_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory); importer=Importer(folder)
            importer.db.execute('INSERT INTO pages VALUES (?,?,?)', ('/1',1,json.dumps({'3034':{}})))
            importer.db.commit()
            importer.source.get=Mock(return_value=listing(sid='3035'))
            previous=folder/'avx.json';previous.write_text('{"previous":"verified"}')
            with patch('sync_avx_catalog.OUT',folder):
                with self.assertRaises(CatalogueChanged):importer.export({'3034':{}},{},'all')
            self.assertEqual(previous.read_text(),'{"previous":"verified"}')
            self.assertEqual(importer.db.execute('SELECT count(*) FROM pages').fetchone()[0],0)
            change=json.loads((folder/'reconciliation-change.json').read_text())
            self.assertEqual(change['added_first_page_ids'],['3035'])
            self.assertEqual(change['removed_first_page_ids'],['3034'])
            importer.db.close()

    def test_cached_progress_is_throttled_but_final_count_is_always_saved(self):
        with tempfile.TemporaryDirectory() as directory:
            importer=Importer(Path(directory))
            with patch('sync_avx_catalog.time.monotonic',side_effect=[1,1.2,2.1,2.2]),patch('sync_avx_catalog.save_json') as save:
                for found in (1,2,3,4):importer.report('details',found=found,expected=4)
                self.assertEqual(save.call_count,3)
                self.assertEqual(save.call_args.args[1]['found'],4)
            importer.db.close()


if __name__=='__main__':unittest.main()
