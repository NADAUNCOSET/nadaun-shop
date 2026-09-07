import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from partner_sync_status import verified_receipt, report


class PartnerStatusTest(unittest.TestCase):
    def test_partial_or_stale_snapshot_never_unlocks_the_next_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); (root/'plthink').mkdir()
            snap = root/'plthink.json'
            snap.write_text(json.dumps({'complete': True, 'product_count': 1, 'products': {'plthink-1': {}}}))
            receipt = {'source_sha256': hashlib.sha256(snap.read_bytes()).hexdigest(), 'verified_products': 1,
                       'commit': 'a', 'deployment': 'b', 'revision': 'c', 'verified_at': 'now'}
            (root/'plthink/published.json').write_text(json.dumps(receipt))
            self.assertTrue(verified_receipt('plthink', root, root))
            snap.write_text(json.dumps({'complete': False, 'product_count': 1, 'products': {'plthink-1': {}}}))
            self.assertFalse(verified_receipt('plthink', root, root))
            self.assertFalse(verified_receipt('onnoff', root, root))

    def test_queue_configuration_cannot_claim_an_automatic_mirror(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); plan = root/'plan.json'
            plan.write_text(json.dumps({'sources': {'onnoff': {'name': '온앤오프', 'adapter': None, 'after_live_verified': 'plthink'}}}))
            result = report(plan, root, root)['sources']['onnoff']
            self.assertEqual(result['waiting_for_live_source'], 'plthink')
            self.assertEqual(result['phase'], 'awaiting_source_access')
            self.assertFalse(result['automatic_refresh_implemented'])
            self.assertIsNone(result['refresh_interval_seconds'])


if __name__ == '__main__': unittest.main()
