import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from plthink_checkpoint import Checkpoint
from catalog_dedup import conflict
import build_catalog


class ResumeTests(unittest.TestCase):
    def test_reopen_preserves_generation_pages_and_details(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'resume.sqlite3';state=Checkpoint(path)
            state.menu([{'id':'1'}]);generation=state.run
            state.save_page('1',1,[{'123':{'id':'plthink-123'}},1,1,[]])
            listing={'id':'plthink-123','sale_price':100}
            verified={**listing,'detail_status':'verified'}
            state.save_detail(listing,verified);state.close()
            state=Checkpoint(path)
            self.assertEqual(state.run,generation)
            self.assertIsNotNone(state.page('1',1));self.assertEqual(state.detail(listing),verified)
            self.assertIsNone(state.detail({**listing,'sale_price':200}))
            with self.assertRaises(ValueError):state.menu([{'id':'2'}])
            state.finish();state.close()
            state=Checkpoint(path)
            self.assertNotEqual(state.run,generation);self.assertIsNone(state.detail(listing))
            state.close()

    def test_wrong_or_incomplete_detail_cannot_enter_resume_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            state=Checkpoint(Path(tmp)/'resume.sqlite3')
            for product in ({'id':'1'},{'id':'2','detail_status':'verified'}):
                with self.assertRaises(ValueError):state.save_detail({'id':'1'},product)
            self.assertIsNone(state.detail({'id':'1'}));state.close()

    def test_source_change_recollects_only_changed_brand_and_keeps_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            state=Checkpoint(Path(tmp)/'resume.sqlite3')
            brands=[{'id':'1'},{'id':'2'}];state.menu(brands)
            for brand in brands:state.save_page(brand['id'],1,[{},0,1,[]])
            previous=state.run;state.restart(brands,['2'])
            self.assertIsNotNone(state.page('1',1));self.assertIsNone(state.page('2',1))
            self.assertEqual(state.db.execute('SELECT count(*) FROM pages WHERE run=?',(previous,)).fetchone()[0],2)
            state.close()

    def test_pending_option_equivalence_blocks_cross_source_merge(self):
        a={'id':'a','brand_id':'nanlite','kind':'purchase','source':'smartstore'}
        b={**a,'id':'b','source':'plthink'}
        self.assertEqual(conflict(a,b,{'b':{'options_require_confirmation':True}}),'unverified_option_equivalence')

    def test_only_fully_verified_partner_snapshot_enters_builder(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(build_catalog,'OUT',Path(tmp)):
            for name in ('kpp','smartstore','imweb-dji','imweb-promotions','l-mount'):
                (Path(tmp)/(name+'.json')).write_text('{"complete":true}')
            self.assertNotIn('plthink',build_catalog.verified_sources())
            path=Path(tmp)/'plthink.json'
            snapshot={'complete':True,'brands':[{'id':'1'}],'coverage':[{'brand_id':'1','expected':1,'unique':1}],
                      'product_count':1,'products':{'plthink-1':{'detail_status':'verified'}}}
            path.write_text(json.dumps(snapshot));self.assertIn('plthink',build_catalog.verified_sources())
            snapshot['products']['plthink-1']['detail_status']='pending'
            path.write_text(json.dumps(snapshot))
            with self.assertRaises(RuntimeError):build_catalog.verified_sources()


if __name__=='__main__':unittest.main()
