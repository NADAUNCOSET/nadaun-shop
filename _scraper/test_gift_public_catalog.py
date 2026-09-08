import json
import sqlite3
import unittest
from build_gift_catalog import project, image_url


class PublicGiftTests(unittest.TestCase):
    def fixture(self):
        db=sqlite3.connect(':memory:')
        db.executescript('CREATE TABLE roots(id TEXT,name TEXT,complete INTEGER);'
            'CREATE TABLE scan_state(key TEXT,value TEXT);'
            'CREATE TABLE products(id TEXT,record_json TEXT);'
            'CREATE TABLE memberships(root_id TEXT,product_id TEXT);'
            'CREATE TABLE public_details(id TEXT,record_json TEXT);')
        db.execute("INSERT INTO roots VALUES('1','생활용품',1)")
        db.execute("INSERT INTO scan_state VALUES('final_verified','1')")
        for pid in ('101','102'):
            p={'product_id':pid,'leaf_category_id':'11','name':'타올 '+pid,
               'image':'https://example.com/'+pid+'.jpg','observed_at':'2026-09-08',
               'supplier_email':'private@example.com','factory_price':1234}
            db.execute('INSERT INTO products VALUES(?,?)',(pid,json.dumps(p)))
            db.execute("INSERT INTO memberships VALUES('1',?)",(pid,))
        detail={'product_id':'101','detail_complete':True,'name':'타올 101','soldout':True,
            'main_images':['https://example.com/101-large.jpg'],'detail_images':[],
            'minimum_quantity':100,'specifications':[{'name':'규격','value':'30 × 60cm'}],
            'supplier_email':'private@example.com','factory_price':4567,'price_tiers':[999],
            'options':[{'selection':{'color':'화이트','printing':'1도'},'supplier':'secret','price':999}]}
        db.execute('INSERT INTO public_details VALUES(?,?)',('101',json.dumps(detail)))
        return db

    def test_public_projection_keeps_ids_categories_and_excludes_private_and_price_data(self):
        with self.fixture() as db:
            before=list(db.iterdump());catalog,details=project(db,[{'id':'11','name':'타올'}])
            self.assertEqual(list(db.iterdump()),before)
        self.assertEqual(catalog['meta']['product_count'],2)
        self.assertEqual(catalog['meta']['detail_count'],1)
        self.assertEqual({p['id'] for p in catalog['products']},{'101','102'})
        self.assertTrue(all(c['count']==2 for c in catalog['categories']))
        self.assertEqual(set(details),{'101'})
        encoded=json.dumps([catalog,details])
        for forbidden in ('private@example.com','factory_price','price_tiers','supplier','1234','4567','999'):
            self.assertNotIn(forbidden,encoded)
        self.assertTrue(next(p for p in catalog['products'] if p['id']=='101')['soldout'])
        self.assertEqual(details['101']['choices'],[{'color':'화이트','size':'','printing':'1도'}])

    def test_incomplete_inventory_and_orphan_memberships_fail_closed(self):
        with self.fixture() as db:
            db.execute('UPDATE roots SET complete=0')
            with self.assertRaises(ValueError):project(db,[{'id':'11','name':'타올'}])
        with self.fixture() as db:
            db.execute("DELETE FROM memberships WHERE product_id='102'")
            with self.assertRaises(ValueError):project(db,[{'id':'11','name':'타올'}])

    def test_wrong_detail_identity_is_not_attached_to_another_product(self):
        with self.fixture() as db:
            db.execute('UPDATE public_details SET record_json=?',(json.dumps({'product_id':'102','detail_complete':True}),))
            with self.assertRaises(ValueError):project(db,[{'id':'11','name':'타올'}])

    def test_image_urls_cannot_carry_scripts_or_credentials(self):
        for url in ('javascript:alert(1)','https://user:password@example.com/a.jpg','file:///private/a.jpg'):
            with self.assertRaises(ValueError):image_url(url)


if __name__=='__main__':unittest.main()
