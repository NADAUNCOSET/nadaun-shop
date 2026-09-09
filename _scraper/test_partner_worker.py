import tempfile
import unittest
import json
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
import partner_worker as worker
import shop_sync


class PublishBoundaryTest(unittest.TestCase):
    def assert_shared_guard_stops_build(self, error):
        with tempfile.TemporaryDirectory() as tmp,patch.object(shop_sync,'STATE',Path(tmp)),\
             patch.object(shop_sync,'command',return_value=''),patch.object(shop_sync,'managed_files',return_value=[]),\
             patch('publication_storage.promote_updates',side_effect=RuntimeError(error)) as promote,\
             patch.object(shop_sync,'build') as build,patch.object(worker,'request') as request:
            with self.assertRaisesRegex(RuntimeError,error):worker.publish_ready({})
            promote.assert_called_once()
            build.assert_not_called()
            request.assert_not_called()
            self.assertFalse((Path(tmp)/'run.lock').exists())

    def test_operator_generated_edit_prevents_build_and_publish(self):
        self.assert_shared_guard_stops_build('Existing generated edits')

    def test_staged_work_prevents_any_automatic_commit(self):
        self.assert_shared_guard_stops_build('Staged operator')

    def test_source_failure_never_reaches_publish(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(worker,'OUT',Path(tmp)),patch.object(worker,'WORK',Path(tmp)),\
             patch.object(worker,'collect_plthink',side_effect=RuntimeError('source incomplete')),patch.object(worker,'publish_ready') as publish:
            with self.assertRaisesRegex(RuntimeError,'source incomplete'):worker.work('plthink')
            publish.assert_not_called()

    def test_verified_pending_candidate_resumes_without_collecting_again(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(worker,'OUT',Path(tmp)),patch.object(worker,'WORK',Path(tmp)),\
             patch.object(worker,'collect_plthink') as collect,patch.object(worker,'publish_ready') as publish:
            candidate={'collected_at':'2026-09-09T10:00:00+00:00','complete':True}
            (Path(tmp)/'catalogue-candidate.json').write_text(json.dumps(candidate))
            worker.work('plthink')
            collect.assert_not_called()
            publish.assert_called_once_with(candidate)

    def test_old_candidate_never_rolls_back_a_newer_verified_publication(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(worker,'OUT',Path(tmp)),patch.object(worker,'WORK',Path(tmp)),\
             patch.object(worker,'policy_fingerprint',return_value='policy'),\
             patch.object(worker,'collect_plthink') as collect,patch.object(worker,'publish_ready') as publish:
            root=Path(tmp)
            published_at=datetime.now(timezone.utc).isoformat()
            (root/'plthink.json').write_text(json.dumps({'collected_at':published_at,'complete':True}))
            (root/'published.json').write_text(json.dumps({'source_collected_at':published_at,'policy_sha256':'policy',
                'source_sha256':hashlib.sha256((root/'plthink.json').read_bytes()).hexdigest()}))
            (root/'catalogue-candidate.json').write_text(json.dumps({'collected_at':'2020-01-01T00:00:00+00:00'}))
            worker.work('plthink')
            collect.assert_not_called()
            publish.assert_not_called()


if __name__=='__main__':unittest.main()
