from datetime import datetime,timezone
import json
from pathlib import Path
import tempfile
import unittest
from source_refresh_state import SOURCES,record_refresh,recent_refresh


class RefreshReceiptTests(unittest.TestCase):
    def test_ui_deployment_never_counts_as_supplier_refresh(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            (root/'last-success.json').write_text(json.dumps({'verified_at':datetime.now(timezone.utc).isoformat()}))
            self.assertFalse(recent_refresh(root/'source-refresh-success.json',root))

    def test_only_verified_unchanged_recent_sources_can_skip(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);receipt=root/'source-refresh-success.json'
            for source in SOURCES:(root/(source+'.json')).write_text(json.dumps({'collected_at':'2026-09-08T00:00:00+00:00','products':{}}))
            with self.assertRaises(ValueError):record_refresh({'revision':'test'},receipt,root)
            data=record_refresh({'commit':'abc','deployment':'dpl','revision':'rev','verified_at':'checked'},receipt,root)
            now=datetime.fromisoformat(data['completed_at']).timestamp()
            self.assertTrue(recent_refresh(receipt,root,now+1))
            self.assertFalse(recent_refresh(receipt,root,now+21600))
            self.assertFalse(recent_refresh(receipt,root,now-1))
            (root/'kpp.json').write_text('{}')
            self.assertFalse(recent_refresh(receipt,root,now+1))


if __name__=='__main__':unittest.main()
