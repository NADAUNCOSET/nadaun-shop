from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import avx_publication as publication
from partner_sync_status import verified_receipt


def source():
    brands=['DJI','Aputure','SmallRig','Tilta','Sony','Newbrand']
    products={f'avx-{i}':{'id':f'avx-{i}','brand':brand,'detail_status':'verified','brand_category_ids':[str(i)],'sale_price':100+i} for i,brand in enumerate(brands)}
    return {'source':'avx','scope':'all','complete':True,'catalogue_complete':True,'collected_at':'2026-09-08T00:00:00+00:00',
        'product_count':6,'coverage':{'expected':6,'unique':6},'products':products,
        'categories':[{'id':str(i),'parent_id':None,'name':brand,'brand':brand} for i,brand in enumerate(brands)],'brands':brands}


class PublicationTests(unittest.TestCase):
    def partition(self):
        counts={b:{'avx':1,'smartstore':1} for b in ('dji','aputure','smallrig','tilta','sony')}
        counts['newbrand']={'avx':1}
        choices={'dji':{'source':'avx'},'aputure':{'source':'avx'},
                 'smallrig':{'source':'kpp','sources':['kpp','clmedia']},
                 'tilta':{'source':'smartstore','sources':['smartstore','clmedia','cinemall']}}
        with patch.object(publication,'inventory',return_value=counts),patch.object(publication,'selections',return_value=choices),patch.object(publication,'policy_fingerprint',return_value='policy'):
            return publication.partition(source())

    def test_approved_brands_publish_without_unresolved_or_owner_excluded_offers(self):
        public,decisions=self.partition()
        self.assertEqual(set(public['products']),{'avx-0','avx-1','avx-5'})
        self.assertEqual(decisions['held_ids'],{'avx-4':'sony'})
        self.assertEqual(decisions['excluded_ids'],{'avx-2':'smallrig','avx-3':'tilta'})
        self.assertEqual({c['id'] for c in public['categories']},{'0','1','5'})
        self.assertEqual(public['products']['avx-0'],source()['products']['avx-0'])
        self.assertFalse(public['catalogue_complete'])
        self.assertEqual(public['publication']['source_product_count'],6)
        self.assertEqual(sum(public['publication'][k] for k in ('accepted_product_count','pending_product_count','owner_excluded_product_count')),6)

    def test_partial_collection_and_unverified_details_cannot_be_published(self):
        for bad in ('scope','detail','coverage'):
            snapshot=source()
            if bad=='scope':snapshot['scope']='aputure'
            elif bad=='detail':snapshot['products']['avx-0']['detail_status']='pending'
            else:snapshot['coverage']['expected']=7
            with self.assertRaises(ValueError):publication.partition(snapshot)

    def test_pending_choice_cannot_unlock_complete_dependency_and_policy_changes_invalidate_receipt(self):
        public,_=self.partition()
        with tempfile.TemporaryDirectory() as tmp,patch.object(publication,'policy_fingerprint',return_value='policy'):
            root=Path(tmp);(root/'avx').mkdir();path=root/'avx-approved.json'
            def write():
                path.write_text(json.dumps(public))
                receipt={'scope':public['scope'],'verified_products':public['product_count'],
                         'source_verified_products':public['publication']['source_product_count'],
                         'pending_brand_count':public['publication']['pending_brand_count'],
                         'policy_sha256':'policy','source_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                         'commit':'a','deployment':'b','revision':'c','verified_at':'now'}
                (root/'avx/published.json').write_text(json.dumps(receipt))
            write();self.assertFalse(verified_receipt('avx',root,root))
            # Owner chooses the existing supplier for Sony; the AVX item is
            # explicitly excluded, not silently dropped from the source total.
            public['publication'].update(pending_brand_count=0,pending_product_count=0,owner_excluded_product_count=3)
            write();self.assertTrue(verified_receipt('avx',root,root))
            with patch.object(publication,'policy_fingerprint',return_value='new-policy'):
                self.assertFalse(verified_receipt('avx',root,root))


if __name__=='__main__':unittest.main()
