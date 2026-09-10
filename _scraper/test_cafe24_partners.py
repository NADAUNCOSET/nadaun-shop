import json
import gzip
from contextlib import closing
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
import sync_cafe24_partners as c
from review_cafe24_checkpoint import review


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


def variant_page():
    doc=product_page()
    schema=json.loads(doc.select_one('script[type="application/ld+json"]').string)
    stocks={};offers=[]
    for code,color,delta,quantity in [('P000A001','검정',0,2),('P000A002','흰색',200,0)]:
        stocks[code]={'option_name_original':['색상'],'option_value_orginal':[color],
                      'option_price':1000+delta,'stock_price':str(delta)+'.00',
                      'use_stock':True,'use_soldout':'T','stock_number':quantity,
                      'is_display':'T','is_selling':'T'}
        offers.append({'url':'https://clmedia.co.kr/product/detail.html?product_no=10&item_code='+code,
                       'priceCurrency':'KRW','price':1000+delta})
    schema['offers']=offers
    doc.select_one('script[type="application/ld+json"]').string=json.dumps(schema)
    doc.select_one('script:not([type])').string=(
        'var product_price="1000";var is_soldout_icon="F";var option_stock_data='+repr(json.dumps(stocks))+';')
    return doc,stocks


def replace_stock(doc,stocks):
    doc.append(c.soup('<script>var option_stock_data='+repr(json.dumps(stocks))+';</script>'))


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
        return c.detail(c.soup(str(doc)),{'id':'clmedia-10','source':'clmedia','source_id':'10','name':'old','images':{}},'SmallRig')[0]

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

    def test_variants_preserve_combination_price_and_individual_soldout(self):
        doc,_=variant_page();p=self.parse(doc)
        self.assertEqual(p['detail_status'],'verified')
        self.assertFalse(p['options_require_confirmation'])
        self.assertEqual([(o['price'],o['disabled']) for o in p['options']],[(1000,False),(1200,True)])
        self.assertEqual(p['options'][1]['selection'],[{'name':'색상','value':'흰색'}])

    def test_variant_identity_and_contradictory_prices_are_rejected(self):
        for mutation in ('identity','price','delta'):
            doc,stocks=variant_page()
            if mutation=='delta':
                stocks['P000A002']['stock_price']='100';replace_stock(doc,stocks)
            else:
                node=doc.select_one('script[type="application/ld+json"]');schema=json.loads(node.string)
                schema['offers'][1]['url' if mutation=='identity' else 'price']='https://clmedia.co.kr/product/detail.html?product_no=11&item_code=P000A002' if mutation=='identity' else 1000
                node.string=json.dumps(schema)
            with self.assertRaises(ValueError):self.parse(doc)

    def test_global_instock_does_not_invent_each_variant_stock(self):
        doc,stocks=variant_page()
        for row in stocks.values():
            for key in ('use_stock','use_soldout','stock_number'):row.pop(key)
        replace_stock(doc,stocks);p=self.parse(doc)
        self.assertEqual(p['detail_status'],'review_required')
        self.assertTrue(all(o['disabled'] for o in p['options']))

    def test_hidden_variants_and_global_soldout_cannot_be_purchased(self):
        doc,stocks=variant_page();stocks['P000A001']['is_display']='F';replace_stock(doc,stocks)
        p=self.parse(doc);self.assertEqual(p['supplier_status'],'soldout')
        self.assertFalse(p['options'][0]['displayed']);self.assertTrue(p['options'][0]['disabled'])
        doc,_=variant_page();doc.append(c.soup('<script>var is_soldout_icon="T";</script>'))
        self.assertTrue(all(o['disabled'] for o in self.parse(doc)['options']))

    def test_inquiry_price_is_not_free_and_requires_confirmation(self):
        doc=product_page(price='가격문의')
        doc.append(c.soup('<script>var product_price="0";var product_price_content="1";</script>'))
        p=self.parse(doc)
        self.assertEqual(p['detail_status'],'verified')
        self.assertIsNone(p['price']);self.assertIsNone(p['sale_price'])
        self.assertTrue(p['price_inquiry']);self.assertTrue(p['options_require_confirmation'])
        self.assertEqual(p['status'],'inquiry')

    def test_unconfirmed_text_price_and_fractional_won_are_rejected(self):
        for value in ('가격문의',1000.5,True):
            with self.assertRaises(ValueError):self.parse(product_page(price=value))

    def test_nested_named_brand_wins_over_distributor_category(self):
        nodes={str(i):{'id':str(i),'name':name,'parent_id':str(parent) if parent else None} for i,name,parent in
               [(24,'브랜드',None),(30,'DZOFILM',24),(31,'Thypoch',30),(40,'Thypoch',24),(41,'Simera',40)]}
        self.assertEqual(c.inventory_brand(['30','31','40','41'],nodes,'24'),'Thypoch')
        self.assertEqual(c.inventory_brand(['30','40'],nodes,'24'),'')

    def test_schema_brand_can_fill_missing_menu_but_seller_name_cannot(self):
        for name,expected in [('DZOFILM','DZOFILM'),('씨엘미디어(주)','미분류')]:
            doc=product_page();script=doc.select_one('script[type="application/ld+json"]')
            data=json.loads(script.string);data['brand']={'@type':'Brand','name':name};script.string=json.dumps(data)
            record,_=c.detail(c.soup(str(doc)),{'id':'clmedia-10','source':'clmedia','source_id':'10'},'')
            self.assertEqual(record['brand'],expected)

    def test_explicit_price_inquiry_never_publishes_internal_variant_prices(self):
        doc,_=variant_page()
        doc.append(c.soup('<script>var product_price="0";var product_price_content="1";</script><table class="xans-product-detaildesign"><tr><th>판매가</th><td>가격문의</td></tr></table>'))
        record=self.parse(doc)
        self.assertIsNone(record['price']);self.assertTrue(record['options_require_confirmation'])
        self.assertEqual(record['detail_status'],'verified')
        self.assertTrue(all(option['price'] is None for option in record['options']))

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

    def test_cinemall_newest_sort_does_not_reuse_or_destroy_default_rank_cache(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(c,'STATE',Path(tmp)):
            collector=c.Collector('cinemall')
            original=c.listing(list_page(ids=(1,2)),'cinemall','56',1)
            with collector.db:collector.db.execute('INSERT INTO pages VALUES(?,?,?)',('56',1,json.dumps(original)))
            collector.source.get=Mock(return_value=str(list_page(ids=(2,1))).encode())
            fresh=collector.page('56',1)
            self.assertEqual(list(fresh['products']),['2','1'])
            collector.source.get.assert_called_once_with('/product/list.html',cate_no='56',page=1,sort_method='5')
            self.assertEqual(collector.page('56',1),fresh)
            self.assertEqual(collector.source.get.call_count,1)
            self.assertEqual(json.loads(collector.db.execute('SELECT record FROM pages').fetchone()[0]),original)
            collector.db.close()

    def test_reconciliation_matches_current_ids_and_preserves_old_checkpoint_rows(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(c,'STATE',Path(tmp)):
            collector=c.Collector('clmedia')
            record=self.parse(product_page())
            with collector.db:
                collector.db.execute('INSERT INTO details VALUES(?,?,?)',('10',json.dumps(record),'{}'))
                collector.db.execute('INSERT INTO details VALUES(?,?,?)',('old',json.dumps({**record,'id':'clmedia-old'}),'{}'))
                collector.db.execute('INSERT INTO errors VALUES(?,?,?)',('old-error','Preserved old error','2026-09-10'))
            collector.inventory=Mock(return_value={'products':{'10':record},'product_count':1,'coverage':[]})
            collector.source.get=Mock(side_effect=AssertionError('Unexpected network call'))
            result=collector.collect()
            self.assertTrue(result['complete']);self.assertEqual(set(result['products']),{'clmedia-10'})
            self.assertEqual(collector.db.execute('SELECT COUNT(*) FROM details').fetchone()[0],2)
            self.assertEqual(collector.db.execute('SELECT COUNT(*) FROM errors').fetchone()[0],1)
            collector.db.close()

    def test_cached_review_backs_up_preserves_dates_and_requires_reconciliation(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(c,'STATE',Path(tmp)),patch.object(c,'ROOT',Path(tmp)):
            collector=c.Collector('clmedia');work=collector.work
            original_at='2026-09-10T01:00:00+00:00'
            product={'id':'clmedia-10','source':'clmedia','source_id':'10','brand':'SmallRig'}
            c.save_json(work/'inventory-candidate.json',{'products':{'10':product},'product_count':1})
            c.save_json(work/'catalogue-candidate.json',{'complete':False,'changed_categories':['24']})
            (work/'review-pages').mkdir()
            (work/'review-pages/10.html.gz').write_bytes(gzip.compress(str(product_page()).encode()))
            with collector.db:collector.db.execute('INSERT INTO errors VALUES(?,?,?)',('10','Old parser error',original_at))
            collector.db.close()
            with patch.object(c.Source,'get',side_effect=AssertionError('Offline review contacted source')):
                preview=review('clmedia')
                self.assertEqual(preview['summary'],{'verified':1})
                self.assertFalse((work/'parser-backups').exists())
                result=review('clmedia',apply=True)
            self.assertEqual(result['progress']['phase'],'reconciliation_required')
            self.assertEqual(result['progress']['changed_categories'],['24'])
            self.assertFalse(result['progress']['complete'])
            with closing(c.sqlite3.connect(Path(tmp)/result['backup'])) as backup:
                self.assertEqual(backup.execute('SELECT COUNT(*) FROM errors').fetchone()[0],1)
                self.assertEqual(backup.execute('SELECT COUNT(*) FROM details').fetchone()[0],0)
            with closing(c.sqlite3.connect(work/'checkpoint.sqlite3')) as db:
                record=json.loads(db.execute('SELECT record FROM details').fetchone()[0])
                self.assertEqual(record['detail_checked_at'],original_at)
                self.assertIn('local_reparsed_at',record)
                self.assertEqual(db.execute('SELECT COUNT(*) FROM errors').fetchone()[0],0)
            candidate=json.loads((work/'catalogue-candidate.json').read_text())
            self.assertTrue(candidate['reconciliation_required']);self.assertFalse(candidate['complete'])


if __name__=='__main__':unittest.main()
