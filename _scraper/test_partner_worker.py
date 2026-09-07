import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import partner_worker as worker


class PublishBoundaryTest(unittest.TestCase):
    def test_operator_generated_edit_prevents_build_and_publish(self):
        with patch.object(worker,'command',return_value=''),patch.object(worker,'changed_files',return_value={'index.html'}),\
             patch.object(worker,'managed_files',return_value=['index.html']),patch.object(worker,'run') as publish:
            with self.assertRaisesRegex(RuntimeError,'already have edits'):worker.publish_ready({})
            publish.assert_not_called()

    def test_staged_work_prevents_any_automatic_commit(self):
        with patch.object(worker,'command',return_value='operator.txt'),patch.object(worker,'run') as publish:
            with self.assertRaisesRegex(RuntimeError,'Staged operator'):worker.publish_ready({})
            publish.assert_not_called()

    def test_source_failure_never_reaches_publish(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(worker,'OUT',Path(tmp)),patch.object(worker,'WORK',Path(tmp)),\
             patch.object(worker,'collect_plthink',side_effect=RuntimeError('source incomplete')),patch.object(worker,'publish_ready') as publish:
            with self.assertRaisesRegex(RuntimeError,'source incomplete'):worker.work('plthink')
            publish.assert_not_called()


if __name__=='__main__':unittest.main()
