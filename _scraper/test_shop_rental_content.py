import unittest
from rental_content import presentation


class RentalContentTests(unittest.TestCase):
    def product(self,**kwargs):return {'id':'smartstore-1','name':'NANLITE MixPanel 60','price':10000,'sale_price':10000,**kwargs}

    def test_real_period_options_become_full_prices_and_visible_packing(self):
        detail={'options':[{'name':'12시간','additional_price':0},{'name':'24시간','additional_price':5000}],
                'description_text':'\u200b\n구성품\nMixPanel 60\n// 1ea\nA-Stand // 1ea\n1.00\n*10세트 이상 대여 가능합니다.'}
        summary,content,audit=presentation(self.product(),detail)
        self.assertEqual(summary['period'],'12시간');self.assertEqual(summary['price'],10000)
        self.assertEqual([r['price'] for r in content['rates']],[10000,15000])
        self.assertEqual(content['components'],[{'name':'MixPanel 60','quantity':1},{'name':'A-Stand','quantity':1}])
        self.assertEqual(content['notes'],['*10세트 이상 대여 가능합니다.'])
        self.assertEqual(audit['issues'],[])

    def test_unknown_period_never_becomes_an_invented_day_rate(self):
        summary,content,audit=presentation(self.product(),{'description_text':'카메라 // 1ea'})
        self.assertIsNone(summary['period']);self.assertEqual(summary['price'],10000)
        self.assertEqual(content['rates'],[]);self.assertTrue(content['period_confirmation_required'])
        self.assertIn('missing_period',audit['issues'])

    def test_combined_period_and_equipment_options_are_not_collapsed(self):
        detail={'options':[{'name':'12시간 / 삼각대','additional_price':0},{'name':'12시간 / 모노포드','additional_price':2000},{'name':'24시간 / 삼각대','additional_price':5000},{'name':'24시간 / 모노포드','additional_price':7000}], 'description_text':'Kit // 1ea'}
        _,content,_=presentation(self.product(),detail)
        self.assertEqual([r['price'] for r in content['rates']],[10000,12000,15000,17000])
        self.assertEqual(content['rates'][1]['label'],'12시간 · 모노포드')

    def test_conflicting_source_component_is_flagged_without_inventing_a_replacement(self):
        _,content,audit=presentation(self.product(name='스몰리그 SR4702 수직수평 변환플레이트키트'),{'description_text':'구성품\nSmallrig SR4702 Monopod // 1ea'})
        self.assertEqual(content['components'],[]);self.assertTrue(content['packing_confirmation_required'])
        self.assertIn('packing_list_conflict',audit['issues'])
        self.assertEqual(audit['conflicts'][0]['name'],'Smallrig SR4702 Monopod')


if __name__=='__main__':unittest.main()
