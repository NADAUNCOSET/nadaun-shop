import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import brand_source_policy as policy
from catalog_dedup import primary_key


class SourcePolicyTests(unittest.TestCase):
    def test_unselected_overlap_never_enters_publication(self):
        import avx_worker
        unresolved=[{'brand_id':'sony','sources':{'avx':1,'smartstore':2}}]
        with patch.object(policy,'pending',return_value=unresolved),patch.object(policy,'write_audit'),patch.object(avx_worker,'save_json') as save:
            result=avx_worker.publish({'products':{}})
            self.assertEqual(result['state'],'awaiting_brand_source_choices')
            self.assertEqual(save.call_args.args[0].name,'publication-waiting.json')

    def test_pending_overlap_is_explicit_and_confirmed_sources_are_honored(self):
        counts={'dji':{'avx':4,'plthink':3},'smallrig':{'avx':2,'kpp':7},'sony':{'avx':1,'smartstore':1}}
        with patch.object(policy,'inventory',return_value=counts),patch.object(policy,'selections',return_value={'dji':{'source':'avx'},'smallrig':{'source':'kpp'}}):
            self.assertEqual(policy.pending({}),[{'brand_id':'sony','sources':counts['sony']}])

    def test_selected_source_has_priority_for_the_same_identity(self):
        base={'status':'available','sale_price':None,'price':100,'name':'Smallrig 2903','id':'smartstore-1',
              'source':'smartstore','_preferred_source':'kpp','updated_at':''}
        selected={**base,'id':'kpp-1','source':'kpp','status':'soldout'}
        self.assertLess(primary_key(selected),primary_key(base))

    def test_every_canonical_product_has_exact_primary_source_and_all_matches(self):
        offers=[{'id':'kpp-1','source':'kpp','url':'https://example.com/1'},
                {'id':'smartstore-2','source':'smartstore','url':'https://example.com/2'}]
        p={'id':'kpp-1','name':'Smallrig 2903','brand_id':'smallrig','kind':'purchase','offers':offers}
        with tempfile.TemporaryDirectory() as folder,patch.object(policy,'AUDIT',Path(folder)),patch.object(policy,'inventory',return_value={'smallrig':{'kpp':1,'smartstore':1}}),patch.object(policy,'selections',return_value={'smallrig':{'source':'kpp'}}):
            report=policy.write_audit({'meta':{'revision':'abc'},'products':[p]})
            saved=json.loads((Path(folder)/'source-matches.json').read_text())
            self.assertEqual(saved,report)
            row=saved['products'][0]
            self.assertEqual((row['primary_source'],row['primary_source_product_id']),('kpp','kpp-1'))
            self.assertEqual(row['matched_sources'],offers)
            with self.assertRaises(ValueError):policy.write_audit({'meta':{'revision':'abc'},'products':[{**p,'id':'missing'}]})


if __name__=='__main__':unittest.main()
