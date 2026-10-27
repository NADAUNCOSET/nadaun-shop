import unittest
from copy import deepcopy
from category_dedup import project
class CategoryProjectionTests(unittest.TestCase):
 def test_exact_paths_merge_membership_and_keep_old_url_alias(self):
  brands={'a':{'id':'a','name':'Maker','aliases':['MAKER'],'navigation_category_ids':['first:root','first:cage','second:root','second:cage']}}
  cats={'first:root':{'id':'first:root','name':'Maker','brand_id':'a','parent_id':None},'first:cage':{'id':'first:cage','name':'카메라 케이지','brand_id':'a','parent_id':'first:root'},'second:root':{'id':'second:root','name':'MAKER','brand_id':'a','parent_id':None},'second:cage':{'id':'second:cage','name':'카메라케이지','brand_id':'a','parent_id':'second:root'}}
  ps=[{'id':'one','name':'Actual item','price':50000,'kind':'purchase','category_ids':['second:root','second:cage'],'navigation_category_ids':['second:root','second:cage'],'type_ids':['type:rig']}];before=deepcopy(ps[0]);aliases,audit=project(ps,cats,brands,{'brands':{'a':{'preferred_source':'first'}}})
  self.assertEqual(aliases,{'second:root':'first:root','second:cage':'first:cage'});self.assertEqual(ps[0]['category_ids'],['first:root','first:cage']);self.assertEqual(ps[0]['price'],before['price']);self.assertEqual(ps[0]['type_ids'],before['type_ids']);self.assertEqual(audit['removed_category_nodes'],2)
 def test_different_parent_or_decimal_is_not_a_duplicate(self):
  brands={'a':{'id':'a','name':'Maker','aliases':[]}}
  cats={}
  for source,parent,child in [('one','카메라','1.4'),('two','렌즈','1.4'),('three','카메라','14')]:
   cats[source+':root']={'id':source+':root','name':parent,'brand_id':'a','parent_id':None};cats[source+':leaf']={'id':source+':leaf','name':child,'brand_id':'a','parent_id':source+':root'}
  aliases,_=project([],cats,brands,{});self.assertNotIn('two:leaf',aliases);self.assertNotIn('three:leaf',aliases);self.assertIn('one:leaf',cats)
 def test_rental_and_other_brand_are_not_merged(self):
  brands={'a':{'id':'a','name':'A','aliases':[]},'b':{'id':'b','name':'B','aliases':[]}};cats={'one:x':{'id':'one:x','name':'케이지','brand_id':'a','parent_id':None},'two:x':{'id':'two:x','name':'케이지','brand_id':'b','parent_id':None},'rental-brand:x':{'id':'rental-brand:x','name':'케이지','brand_id':'a','parent_id':None,'scope':'rental-brand'}}
  aliases,_=project([],cats,brands,{});self.assertFalse(aliases);self.assertEqual(len(cats),3)

 def test_existing_rental_category_id_is_preserved(self):
  brands={'a':{'id':'a','name':'Maker','aliases':[]}}
  cats={'one:x':{'id':'one:x','name':'케이지','brand_id':'a','parent_id':None},'two:x':{'id':'two:x','name':'케이지','brand_id':'a','parent_id':None}}
  ps=[{'id':'rental','brand_id':'a','kind':'rental','category_ids':['one:x'],'type_ids':[],'navigation_category_ids':[]}];before=deepcopy(ps)
  aliases,_=project(ps,cats,brands,{'brands':{'a':{'preferred_source':'two'}}});self.assertEqual(aliases,{'two:x':'one:x'});self.assertEqual(ps,before)

 def test_compatibility_brand_source_path_does_not_enter_manufacturer_menu(self):
  brands={'maker':{'id':'maker','name':'Maker','aliases':[]},'camera':{'id':'camera','name':'Camera','aliases':[]}}
  cats={'one:cage':{'id':'one:cage','name':'케이지','brand_id':'camera','parent_id':None},'two:cage':{'id':'two:cage','name':'케이지','brand_id':'camera','parent_id':None}}
  ps=[{'id':'accessory','brand_id':'maker','kind':'purchase','category_ids':['two:cage'],'navigation_category_ids':[],'type_ids':[]}]
  aliases,_=project(ps,cats,brands,{});self.assertTrue(aliases);self.assertEqual(ps[0]['navigation_category_ids'],[])
