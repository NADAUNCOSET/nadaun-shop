import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import build_gift_catalog as builder
from gift_daily_sync import refresh_metadata, write_catalog


def current():
    c={'meta':{'detail_count':0,'priced_product_count':0,'price_option_count':0,'price_tier_count':0,
               'mirror':{'source':'nadaun-gift','last_feed_check_at':'2026-10-24T01:00:00Z'}},
       'categories':[{'id':'1','name':'품목','parent_ids':[],'count':0}],
       'products':[{'id':'101','name':'상품','image':'https://example.com/p.jpg','category_ids':['1'],
                    'detail_available':False,'source_status':'withdrawn','source_status_at':'2026-10-24T02:00:00Z'}]}
    refresh_metadata(c);return c


class GiftMirrorPreservationTests(unittest.TestCase):
    def test_equipment_rebuild_preserves_withdrawal_and_all_gift_file_bytes(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);c=current();write_catalog(root,c)
            before={p.relative_to(root):p.read_bytes() for p in root.rglob('*') if p.is_file()}
            with patch.object(builder,'ROOT',root),patch.object(builder,'PUBLIC',root/'data/gift'),patch.object(builder,'project',side_effect=AssertionError('Old inventory must not rebuild a live daily mirror')):
                self.assertEqual(builder.build(),c)
            after={p.relative_to(root):p.read_bytes() for p in root.rglob('*') if p.is_file()}
            self.assertEqual(before,after)

    def test_mismatching_mirror_artifacts_stop_rebuild_instead_of_resetting_state(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);c=current();write_catalog(root,c)
            (root/'data/gift/sync-status.json').write_text('{}')
            with patch.object(builder,'ROOT',root),patch.object(builder,'PUBLIC',root/'data/gift'):
                with self.assertRaisesRegex(ValueError,'artifacts'):
                    builder.build()


if __name__=='__main__':unittest.main()
