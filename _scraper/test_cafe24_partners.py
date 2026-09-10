import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
import sync_cafe24_partners as c


def product_page(pid='10',price=1000,stock=None,options='',body='<img src="/detail.jpg">'):
    obj={'@type':'Product','name':'SmallRig 2903','image':['https://clmedia.co.kr/main.jpg'],
         'offers':{'url':'https://clmedia.co.kr/product/sample/'+pid+'/', 'priceCurrency':'KRW','price':price}}
    stock=stock if stock is not None else {'use_stock':True,'use_soldout':'T','stock_number':2}
    return c.soup('<script type="application/ld+json">'+json.dumps(obj)+'</script>'+
                  '<script>var product_price = "'+str(price)+'";var single_option_stock_data = '+repr(json.dumps(stock))+';</script>'+
                  '<div id="prdDetail">'+body+'</div>'+options)


def list_page(ids=(1,2),total=2,page=1):
    return c.soup('<p class="prdCount">총 '+str(total)+' 개</p><ul class="xans-product-listnormal">'+''.join(
        '<li id="anchorBoxId_'+str(i)+'"><a href="/product/sample/'+str(i)+'/"><img id="eListPrdImage'+str(i)+'" src="/image.jpg"></a><p class="name">Item '+str(i)+'</p></li>' for i in ids)+
        '</ul><div class="xans-product-normalpaging"><a class="this">'+str(page)+'</a></div>')


class Cafe24Tests(unittest.TestCase):
    def test_api_tree_contains_only_brand_descendants(self):
        values=[{'cate_no':i,'parent_cate_no':parent,'name':name} for i,parent,name in
                [(24,1,'브랜드'),(30,24,'SmallRig'),(31,30,'케이지'),(50,1,'개인결제')]]
        self.assertEqual(set(c.category_tree(values,'24')),{'24','30','31'})

    def test_pagination_uses_actual_page_size_and_advertised_total(self):
        r=c.listing(list_page(total=7),'clmedia','24',1)
        self.assertEqual(r['last'],4);self.assertEqual(r['total'],7)

    def test_wrong_page_duplicate_or_empty_page_rejected(self):
        for doc in (list_page(page=2),list_page(ids=(1,1)),list_page(ids=(),total=1)):
            with self.assertRaises(ValueError):c.listing(doc,'clmedia','24',1)

    def test_nested_fallback_menu_preserves_category_ancestry(self):
        doc=c.soup('<ul class="menuCategory"><li><a href="?cate_no=30">SmallRig (2)</a><ul><li><a href="?cate_no=31">케이지 (2)</a></li></ul></li></ul>')
        self.assertEqual(c.category_menu(doc,'24'),[{'id':'30','name':'SmallRig','parent_id':'24'},{'id':'31','name':'케이지','parent_id':'30'}])

    def parse(self,doc):
        return c.detail(doc,{'id':'clmedia-10','source':'clmedia','source_id':'10','name':'old','images':{}},'SmallRig')[0]

    def test_single_sku_price_stock_and_images_verified(self):
        p=self.parse(product_page());self.assertEqual(p['sale_price'],1000)
        self.assertEqual(p['supplier_status'],'available');self.assertEqual(p['detail_status'],'verified')
        self.assertEqual(p['images']['detail'],['https://clmedia.co.kr/detail.jpg'])

    def test_stock_zero_with_stock_tracking_disabled_is_not_soldout(self):
        p=self.parse(product_page(stock={'use_stock':False,'use_soldout':'T','stock_number':0}))
        self.assertEqual(p['supplier_status'],'available')
        p=self.parse(product_page(stock={'use_stock':True,'use_soldout':'T','stock_number':0}))
        self.assertEqual(p['status'],'soldout')

    def test_wrong_identity_and_price_disagreement_are_rejected(self):
        with self.assertRaises(ValueError):self.parse(product_page(pid='11'))
        doc=product_page();doc.append(c.soup('<script>var product_price="2000";</script>'))
        with self.assertRaises(ValueError):self.parse(doc)

    def test_unverified_option_combinations_stay_private_review(self):
        p=self.parse(product_page(options='<select id="product_option_id1" option_title="컬러"><option value="*">선택</option><option value="red">빨강 (+100원)</option></select>'))
        self.assertEqual(p['detail_status'],'review_required');self.assertTrue(p['options_require_confirmation'])
        self.assertEqual(p['option_groups'][0]['values'],[{'value':'red','label':'빨강 (+100원)'}])

    def test_missing_description_never_becomes_verified(self):
        self.assertEqual(self.parse(product_page(body=''))['content_issues'],['description_missing'])

    def test_js_parser_never_evaluates_function_calls(self):
        self.assertEqual(c.js_values(c.soup('<script>var price = dangerous();var safe="100";</script>')),{'safe':'100'})

    def test_provider_denial_latches_and_second_call_makes_no_request(self):
        with tempfile.TemporaryDirectory() as tmp:
            src=c.Source('clmedia',Path(tmp),interval=0);src.session.get=Mock(return_value=Mock(status_code=403,text='Forbidden'))
            with self.assertRaises(RuntimeError):src.get('/')
            with self.assertRaises(RuntimeError):src.get('/')
            self.assertEqual(src.session.get.call_count,1)
            self.assertTrue(json.loads((Path(tmp)/'source-suspended.json').read_text())['suspended'])

    def test_existing_suspension_or_malformed_state_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'source-suspended.json';src=c.Source('clmedia',Path(tmp),interval=0);src.session.get=Mock()
            for value in ('{}','broken'):
                path.write_text(value)
                with self.assertRaises((RuntimeError,ValueError)):src.get('/')
            src.session.get.assert_not_called()

    def test_saved_inventory_page_is_reused_without_network(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(c,'STATE',Path(tmp)):
            collector=c.Collector('clmedia')
            collector.source.get=Mock(return_value=str(list_page()).encode())
            first=collector.page('24',1);self.assertEqual(collector.page('24',1),first)
            self.assertEqual(collector.source.get.call_count,1);collector.db.close()


if __name__=='__main__':unittest.main()
