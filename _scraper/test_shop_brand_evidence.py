import unittest
from build_catalog import reviewed_brand
class ReviewedVersions(unittest.TestCase):
 def test_only_exact_reviewed_source_versions_are_accepted(self):
  rules={'p':{'expected_name':'previous','expected_brand':'supplier','brand':'OLD','evidence':['https://example.invalid/old'],'reviewed_versions':[{'expected_name':'current','expected_brand':'NEW','brand':'NEW','evidence':['https://example.invalid/current']}]}}
  self.assertEqual(reviewed_brand({'id':'p','name':'previous','brand':'supplier'},rules),'OLD')
  self.assertEqual(reviewed_brand({'id':'p','name':'current','brand':'NEW'},rules),'NEW')
  for name,brand in [('current','supplier'),('changed','NEW'),('previous','NEW')]:
   with self.assertRaises(ValueError):reviewed_brand({'id':'p','name':name,'brand':brand},rules)
  rules['p']['reviewed_versions'][0]['evidence']=[]
  with self.assertRaises(ValueError):reviewed_brand({'id':'p','name':'current','brand':'NEW'},rules)
if __name__=='__main__':unittest.main()
