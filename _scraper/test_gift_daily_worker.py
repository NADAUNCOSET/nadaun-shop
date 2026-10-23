from datetime import datetime, timezone
import json
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import run_gift_daily as worker


class GiftWorkerTests(unittest.TestCase):
    def setup_root(self, folder):
        root = Path(folder); state = root/'_private/gift/daily-sync'
        state.mkdir(parents=True); (root/'_scraper/.sync-state').mkdir(parents=True)
        return root, state

    def test_browser_policy_block_cannot_trigger_requests_or_publication(self):
        with tempfile.TemporaryDirectory() as d:
            root, state = self.setup_root(d)
            worker.save(state/'source-access.json', {'state': 'blocked_browser_policy', 'reason': 'policy_unavailable'})
            with patch.object(worker, 'ROOT', root), patch.object(worker, 'STATE', state), patch.object(worker, 'download') as download, patch.object(worker, 'publish') as publish:
                worker.main()
                download.assert_not_called(); publish.assert_not_called()
                self.assertEqual(json.loads((state/'status.json').read_text())['requests'], 0)

    def test_failed_job_does_not_repeat_source_requests_on_next_timer_tick(self):
        with tempfile.TemporaryDirectory() as d:
            root, state = self.setup_root(d)
            worker.save(state/'status.json', {'state': 'requires_review'})
            with patch.object(worker, 'ROOT', root), patch.object(worker, 'STATE', state), patch.object(worker, 'download') as download:
                worker.main(); download.assert_not_called()

    def test_other_catalog_worker_prevents_source_request(self):
        with tempfile.TemporaryDirectory() as d:
            root, state = self.setup_root(d); (root/'_scraper/.sync-state/run.lock').write_text('another worker')
            with patch.object(worker, 'ROOT', root), patch.object(worker, 'STATE', state), patch.object(worker, 'download') as download:
                worker.main(); download.assert_not_called()

    def test_successful_daily_run_is_not_repeated_same_day(self):
        with tempfile.TemporaryDirectory() as d:
            root, state = self.setup_root(d)
            worker.save(state/'source-access.json', {'state': 'ready', 'supported_feed_url': worker.SOURCE, 'verified_at': '2026-10-24T00:00:00Z'})
            worker.save(state/'last-success.json', {'date_kst': datetime.now(worker.KST).date().isoformat()})
            with patch.object(worker, 'ROOT', root), patch.object(worker, 'STATE', state), patch.object(worker, 'download') as download:
                worker.main(); download.assert_not_called()

    def test_availability_import_requires_unchanged_original_and_removes_only_confirmed_id(self):
        from test_gift_daily_sync import apply, evidence
        with tempfile.TemporaryDirectory() as d:
            root, state = self.setup_root(d); folder=state/'availability'; folder.mkdir()
            original=b'provider export product 101 withdrawn'
            (folder/'source.txt').write_bytes(original)
            proof=evidence([{'id':'101','status':'withdrawn'}],source_sha256=hashlib.sha256(original).hexdigest())
            worker.save(folder/'current.json',{'source_file':'source.txt','evidence':proof})
            with patch.object(worker,'STATE',state):
                catalog,_=apply(); result,changes=worker.reconcile_availability(catalog)
                self.assertEqual(changes,['101']);self.assertEqual(result['meta']['active_product_count'],2)
                (folder/'source.txt').write_bytes(b'changed')
                with self.assertRaisesRegex(RuntimeError,'checksum'):worker.reconcile_availability(catalog)


if __name__ == '__main__': unittest.main()
