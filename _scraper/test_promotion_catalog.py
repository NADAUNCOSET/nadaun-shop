from copy import deepcopy
import unittest
from promotion_catalog import apply_promotions,validate_campaign,consignment_used

class PromotionsTest(unittest.TestCase):
    def setUp(self):
        self.c={'id':'provider-autumn-202610','title':'기간 행사','type':'supplier_event','source':'digitalcp','source_url':'https://www.digitalcp.co.kr/event','start_at':'2026-10-12T00:00:00+09:00','end_at':'2026-11-16T00:00:00+09:00','observed_at':'2026-10-27T16:00:00+09:00','evidence_sha256':'a'*64,'source_product_ids':['digitalcp-123'],'terms':'적립 혜택은 공급처 조건 확인'}
    def test_exact_offer_match_preserves_prices_and_marks_collection(self):
        p={'id':'merged-1','kind':'purchase','price':10000,'sale_price':10000,'promotion_ids':[],'offers':[{'id':'digitalcp-123','source':'digitalcp'}]};products={'merged-1':p};cats={}
        apply_promotions(products,cats,{'campaigns':[self.c]})
        self.assertEqual((p['price'],p['sale_price']),(10000,10000));self.assertEqual(p['promotions'][0]['terms'],self.c['terms']);self.assertEqual(cats['promotion:'+self.c['id']]['count'],1)
    def test_no_ambiguous_identity_or_other_supplier_matching(self):
        p={'id':'digitalcp-123','kind':'purchase','offers':[{'id':'digitalcp-123','source':'other'}]}
        with self.assertRaises(ValueError):apply_promotions({'x':p},{},{'campaigns':[self.c]})
    def test_hidden_and_rental_products_never_enter_campaign(self):
        for change in [{'hidden':True},{'kind':'rental'}]:
            p={'id':'digitalcp-123','source':'digitalcp','kind':'purchase',**change}
            with self.assertRaises(ValueError):apply_promotions({'x':p},{},{'campaigns':[self.c]})
    def test_timezone_period_proof_and_source_are_required(self):
        for patch in [{'start_at':'2026-10-12'},{'end_at':self.c['start_at']},{'evidence_sha256':''},{'source_product_ids':['other-123']}]:
            with self.subTest(patch=patch),self.assertRaises(ValueError):validate_campaign(self.c|patch)
    def test_consignment_is_explicit_own_purchase_stock(self):
        p={'name':'[위탁중고] 카메라','kind':'purchase','offers':[{'source':'smartstore'}]}
        self.assertTrue(consignment_used(p))
        for patch in [{'kind':'rental'},{'offers':[{'source':'dji-official'}]},{'name':'새 제품 / 중고 카메라 호환 케이스'},{'name':'[리퍼비시] 카메라'}]:self.assertFalse(consignment_used(p|patch))

if __name__=='__main__':unittest.main()
