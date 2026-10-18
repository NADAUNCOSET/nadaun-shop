import unittest
from reviewed_supplier_sources import markup_won,retail_product,reference_price_overrides,validate_snapshot
class PricingRules(unittest.TestCase):
 def test_exact_markup_and_no_mutation(self):
  raw={'source':'motion9','price':1870000,'sale_price':1870000,'options':[{'price':1320000,'additional_price':-550000}]}
  p=retail_product(raw)
  self.assertEqual((p['price'],p['options'][0]['price'],p['options'][0]['additional_price']),(1963500,1386000,-577500));self.assertEqual(raw['price'],1870000)
 def test_invalid_money_is_rejected(self):
  for v in [-1,1.2,True,'100']:
   with self.assertRaises(ValueError):markup_won(v)
 def test_inquiry_never_leaks_amounts(self):
  p=retail_product({'source':'funomad','price':100,'sale_price':99,'options':[{'price':90,'additional_price':-10}]})
  self.assertIsNone(p['price']);self.assertIsNone(p['sale_price']);self.assertIsNone(p['options'][0]['price']);self.assertEqual(p['options'][0]['additional_price'],0);self.assertTrue(p['options_require_confirmation'])
 def test_independent_addons_cannot_be_cheap_base_variants(self):
  p=retail_product({'source':'motion9','price':891000,'independent_option_groups':True,'options_require_confirmation':True,'options':[{'price':110000,'role':'addon','group_name':'클램프','label':'35Clamp'}]})
  self.assertEqual(p['options'][0]['additional_price'],0);self.assertIn('115,500원',p['options'][0]['name']);self.assertTrue(p['options_require_confirmation'])
 def test_reference_identity_fails_closed(self):
  p={'x':{'_provenance':{'fields':{}}}};rules={'x':{'price_source':'smartstore','reference_product_id':'smartstore-1','reference_expected_name':'GR4'}}
  with self.assertRaises(ValueError):reference_price_overrides(p,{}, {},rules)
  reference_price_overrides(p,{}, {'smartstore':{'products':{'smartstore-1':{'kind':'purchase','name':'GR4','sale_price':2600000,'source_url':'https://smartstore.naver.com/rainbowbene/products/1'}}}},rules)
  self.assertEqual(p['x']['price'],2600000)
 def test_dealer_priority_preserves_explicit_main(self):
  from catalog_dedup import primary_key
  own={'id':'smartstore-1','source':'smartstore','_prefer_supplier':True,'status':'sale'}
  supplier={'id':'kpp-2','source':'kpp','_prefer_supplier':True,'status':'inquiry'}
  self.assertLess(primary_key(supplier),primary_key(own))
  own['_preferred_sources']=['smartstore']
  self.assertLess(primary_key(own),primary_key(supplier))
 def test_partial_source_rejected(self):
  with self.assertRaises(ValueError):validate_snapshot({'source':'funomad','complete':False})
 def test_retired_link_requires_exact_reviewed_target(self):
  from reviewed_supplier_sources import apply_retired_redirects
  p={'new':{'name':'Model A','brand_id':'brand','kind':'purchase'}}
  rule={'old':{'target_id':'new','expected_target_name':'Model A','expected_brand_id':'brand','expected_kind':'purchase','evidence':'reviewed same offer'}};redirects={}
  apply_retired_redirects(p,redirects,rule);self.assertEqual(redirects,{'old':'new'})
  p['new']['name']='Model B'
  with self.assertRaises(ValueError):apply_retired_redirects(p,{},rule)
  p['old']={'hidden':False}
  with self.assertRaises(ValueError):apply_retired_redirects(p,{},rule)
if __name__=='__main__':unittest.main()
