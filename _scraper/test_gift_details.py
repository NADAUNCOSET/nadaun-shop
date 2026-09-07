import json
import unittest
from sync_gift_inventory import document
from gift_product_details import parse_detail


def fixture():
    schema={'@type':'Product','sku':'187684','offers':{'availability':'https://schema.org/InStock'}}
    return '''<script type="application/ld+json">'''+json.dumps(schema)+'''</script>
    <span id="goods_name">라인플러스 컴퓨터용싸인펜</span><img class="magnified-image" src="/main.jpg">
    <div id="md_chu_bg"><img src="/unrelated.jpg"></div>
    <div class="detail_bimg"><img src="/detail.jpg"><img src="/DATA/EVENT/common.jpg">
    <div class="gdet_table"><table><tr><th>포장 방법</th><td>기본 포장</td></tr></table></div></div>
    <script>
    var minquantity = 1000;
    var discountrate = 0.97;
    var is_outpotal = "Y";
    function atpriceToint(atprice){return Math.ceil(atprice * 0.97);}
    matierial[0] = "인쇄 없음";
    quantity[0] = "50000";
    atprice[0] = "101";
    matierial[1] = "인쇄 없음";
    quantity[1] = "1000";
    atprice[1] = "118";
    </script>'''


class PublicGiftDetailsTest(unittest.TestCase):
    def test_exact_customer_prices_and_product_images_are_preserved(self):
        p=parse_detail(document(fixture()),'187684')
        self.assertEqual(p['options'][0]['tiers'],[
            {'minimum_quantity':1000,'unit_price_ex_vat':115},
            {'minimum_quantity':50000,'unit_price_ex_vat':98}])
        self.assertEqual(p['detail_images'],['https://www.nadaun-gift.com/detail.jpg'])
        self.assertEqual(p['specifications'],[{'name':'포장 방법','value':'기본 포장'}])
        self.assertFalse(p['supplier_complete']);self.assertFalse(p['selling_price_approved'])

    def test_mismatched_product_and_unrecognized_pricing_fail_closed(self):
        for html in (fixture().replace('187684','999'),fixture().replace('Math.ceil','Math.floor'),
                     fixture().replace('quantity[1] = "1000";',''),fixture().replace('atprice[1] = "118";','atprice[1] = fetch("https://invalid.test");')):
            with self.assertRaises(ValueError):parse_detail(document(html),'187684')

    def test_supplier_availability_and_external_display_flag_survive(self):
        html=fixture().replace('InStock','OutOfStock').replace('is_outpotal = "Y"','is_outpotal = "N"')
        p=parse_detail(document(html),'187684')
        self.assertTrue(p['soldout']);self.assertFalse(p['external_display_allowed'])


if __name__=='__main__':unittest.main()
