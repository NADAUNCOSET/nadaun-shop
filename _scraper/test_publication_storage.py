import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from publication_storage import promote_updates, stage_generated, validate_updates


class PublicationStorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.out = self.root / 'sources'
        self.out.mkdir()
        self.state = self.root / '.state'
        self.state.mkdir()
        self.cmd('git', 'init', '-q')
        self.cmd('git', 'config', 'user.name', 'Publication Test')
        self.cmd('git', 'config', 'user.email', 'test@example.invalid')
        (self.root / 'catalog.html').write_text('revision A\n')
        (self.root / 'operator.md').write_text('original\n')
        (self.root / '.gitignore').write_text('.state/\n')
        self.cmd('git', 'add', '--', 'catalog.html', 'operator.md', '.gitignore')
        self.cmd('git', '-c', 'commit.gpgsign=false', 'commit', '-qm', 'Fixture')
        self.candidate = {'source': 'plthink', 'complete': True, 'product_count': 1,
                          'products': {'plthink-1': {'id': 'plthink-1'}}}
        self.writes = []

    def cmd(self, *args):
        return subprocess.check_output(args, cwd=self.root, text=True, stderr=subprocess.PIPE).strip()

    def lock(self, **overrides):
        (self.state / 'run.lock').write_text(json.dumps(
            {'host': socket.gethostname(), 'pid': os.getpid(), **overrides}))

    def promote(self, updates=None):
        promote_updates(updates or {'plthink': self.candidate}, self.root, self.out,
                        self.state, ['catalog.html', 'sources/plthink.json'],
                        lambda path, data: self.writes.append((path, data)))

    def test_missing_or_other_process_lock_cannot_write_public_sources(self):
        with self.assertRaises(RuntimeError):
            self.promote()
        self.lock(pid=-1)
        with self.assertRaises(RuntimeError):
            self.promote()
        self.lock(host='another-computer')
        with self.assertRaises(RuntimeError):
            self.promote()
        self.assertEqual(self.writes, [])

    def test_operator_staging_and_generated_edits_block_promotion(self):
        self.lock()
        (self.root / 'operator.md').write_text('operator update\n')
        self.cmd('git', 'add', '--', 'operator.md')
        with self.assertRaises(RuntimeError):
            self.promote()
        self.cmd('git', 'restore', '--staged', '--', 'operator.md')
        (self.root / 'catalog.html').write_text('manual catalogue edit\n')
        with self.assertRaises(RuntimeError):
            self.promote()
        self.assertEqual(self.writes, [])

    def test_unrelated_unstaged_edits_are_preserved_during_promotion(self):
        self.lock()
        (self.root / 'operator.md').write_text('operator update\n')
        self.promote()
        self.assertEqual(self.writes, [(self.out / 'plthink.json', self.candidate)])
        self.assertEqual((self.root / 'operator.md').read_text(), 'operator update\n')
        self.assertEqual(self.cmd('git', 'diff', '--cached', '--name-only'), '')

    def test_all_candidates_validated_before_any_public_write(self):
        self.lock()
        bad = self.candidate | {'complete': False}
        with self.assertRaises(ValueError):
            self.promote({'plthink': self.candidate, 'dji-official': bad})
        self.assertEqual(self.writes, [])
        for name, snapshot in [('../escape', self.candidate),
                               ('plthink', self.candidate | {'product_count': 2}),
                               ('plthink', self.candidate | {'product_count': True}),
                               ('plthink', self.candidate | {'complete': False})]:
            with self.subTest(name=name, snapshot=snapshot), self.assertRaises(ValueError):
                validate_updates({name: snapshot})

    def test_same_size_rewrite_with_preserved_mtime_is_staged_exactly(self):
        path = self.root / 'catalog.html'
        old = path.stat()
        path.write_text('revision B\n')
        os.utime(path, ns=(old.st_atime_ns, old.st_mtime_ns))
        (self.root / 'operator.md').write_text('unrelated update\n')
        (self.root / 'untracked.md').write_text('unrelated new file\n')
        (self.root / 'new-brand.html').write_text('new brand\n')
        stage_generated(['catalog.html', 'new-brand.html'], self.cmd)
        self.assertEqual(self.cmd('git', 'show', ':catalog.html'), 'revision B')
        self.assertEqual(set(self.cmd('git', 'diff', '--cached', '--name-only').splitlines()),
                         {'catalog.html', 'new-brand.html'})
        self.assertEqual((self.root / 'operator.md').read_text(), 'unrelated update\n')
        self.assertEqual((self.root / 'untracked.md').read_text(), 'unrelated new file\n')

    def test_changed_bytes_after_staging_fail_verification(self):
        def interrupted_command(*args):
            if args[:2] == ('git', 'hash-object'):
                (self.root / 'catalog.html').write_text('changed during staging\n')
            return self.cmd(*args)
        with self.assertRaisesRegex(RuntimeError, 'differ'):
            stage_generated(['catalog.html'], interrupted_command)

    def test_busy_publisher_never_promotes_a_candidate(self):
        import shop_sync
        self.lock()
        with patch.object(shop_sync, 'STATE', self.state), patch('publication_storage.promote_updates') as promote:
            with self.assertRaisesRegex(RuntimeError, 'Another catalogue sync'):
                shop_sync.run(existing=True, source_updates={'plthink': self.candidate})
        promote.assert_not_called()
        self.assertTrue((self.state / 'run.lock').exists())


if __name__ == '__main__':
    unittest.main()
