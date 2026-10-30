import json,unittest
from manual_source_worker import motion9_detail,jsvar
from funomad_source import verify_page,navigation
from reviewed_supplier_sources import retail_product

class ManualSourceTests(unittest.TestCase):
    def group(self,variant_price=22500):
        stock={'P0001A':{'option_price':20000,'option_value':'15cm Rod','option_value_orginal':['15cm Rod'],'is_auto_soldout':'T'},
               'P0001B':{'option_price':22500,'option_value':'25cm Rod','option_value_orginal':['25cm Rod'],'is_auto_soldout':'F'}}
        schema={'@type':'ProductGroup','productGroupID':'cafe24_motionnine_1_47','name':'15mm 로드',
            'hasVariant':[{'sku':'cafe24_motionnine_1_47_'+code,'image':['https://supplier.example/original.jpg'],
                'offers':{'price':20000 if code=='P0001A' else variant_price}} for code in stock]}
        variables=''.join('var '+name+' = '+json.dumps(value)+';' for name,value in [
            ('product_price','20000'),('option_stock_data',json.dumps(stock)),('option_value_mapper',json.dumps({'15cm Rod':'P0001A','25cm Rod':'P0001B'}))])
        return ('<script type="application/ld+json">'+json.dumps(schema)+'</script><script>'+variables+'</script>'
            '<select id="product_option_id1" required="true"><option value="*">선택</option><option value="15cm Rod">15cm Rod</option><option value="25cm Rod">25cm Rod</option></select>').encode()
    def test_group_variants_map_exact_legacy_values_prices_and_stock(self):
        p,images=motion9_detail(self.group(),'https://motionnine.cafe24.com/product/rod/47/')
        self.assertEqual([o['price'] for o in p['options']],[20000,22500]);self.assertTrue(p['options'][0]['disabled']);self.assertFalse(p['options'][1]['disabled'])
        retail=retail_product(p);self.assertEqual(retail['price'],21000);self.assertEqual(retail['options'][1]['price'],23625);self.assertEqual(p['price'],20000)
    def test_disagreeing_variant_price_stops_publication(self):
        with self.assertRaisesRegex(ValueError,'schema and exact option price'):motion9_detail(self.group(99999),'https://motionnine.cafe24.com/product/rod/47/')
    def test_wrong_product_identity_stops_publication(self):
        with self.assertRaisesRegex(ValueError,'identity'):motion9_detail(self.group(),'https://motionnine.cafe24.com/product/rod/48/')
    def test_javascript_strings_are_decoded_without_execution(self):
        self.assertEqual(jsvar('var value = "a\\\"b";','value'),'a"b')
        self.assertIsNone(jsvar('var value = alert("x");','value'))
    def test_funomad_image_identity_change_requires_review(self):
        row={'id':'family','images':['https://funomad.com/original.png']}
        self.assertEqual(len(verify_page(b'<div class="entry-content"><img src="original.png"></div>','https://funomad.com/',[row])),64)
        with self.assertRaisesRegex(ValueError,'image changed'):verify_page(b'<div class="entry-content"><img src="other-model.png"></div>','https://funomad.com/',[row])
    def test_funomad_nested_menu_keeps_source_category_paths(self):
        rows=navigation('<nav class="et-menu-nav"><ul><li><a href="#">BRAND</a><ul><li><a href="https://funomad.com/model/">Model</a></li></ul></li></ul></nav>')
        self.assertEqual(rows[-1],{'label':'Model','path':['BRAND','Model'],'url':'https://funomad.com/model/'})

if __name__=='__main__':unittest.main()
