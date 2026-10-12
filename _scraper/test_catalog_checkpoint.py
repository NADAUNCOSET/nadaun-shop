import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from catalog_checkpoint import restore, snapshot


class CheckpointTests(unittest.TestCase):
    def test_live_database_stays_on_pc_and_second_pc_restores_verified_nas_snapshot(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);work=root/'nas/ldnet';work.mkdir(parents=True)
            local=restore(work,'ldnet',root/'pc1')
            self.assertTrue(local.is_relative_to(root/'pc1'))
            with sqlite3.connect(local) as connection:
                connection.execute('CREATE TABLE pages(id INTEGER)');connection.execute('INSERT INTO pages VALUES(1)');connection.commit()
                metadata=snapshot(connection,work,local,'ldnet')
                self.assertEqual(metadata['snapshot_integrity'],'ok')
            second=restore(work,'ldnet',root/'pc2')
            with sqlite3.connect(second) as connection:self.assertEqual(connection.execute('SELECT * FROM pages').fetchall(),[(1,)])
            with sqlite3.connect(local) as connection:
                connection.execute('INSERT INTO pages VALUES(2)');connection.commit();snapshot(connection,work,local,'ldnet')
            restore(work,'ldnet',root/'pc2')
            self.assertEqual(len(list(second.parent.glob('before-restore-*.sqlite3'))),1)
            with sqlite3.connect(second) as connection:self.assertEqual(connection.execute('SELECT COUNT(*) FROM pages').fetchone()[0],2)

    def test_unverified_nas_snapshot_never_overwrites_pc_checkpoint(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);work=root/'nas/ldnet';work.mkdir(parents=True)
            local=restore(work,'ldnet',root/'pc')
            with sqlite3.connect(local) as connection:
                connection.execute('CREATE TABLE pages(id INTEGER)');connection.commit();snapshot(connection,work,local,'ldnet')
            before=local.read_bytes();metadata=json.loads((work/'checkpoint-location.json').read_text());metadata['snapshot_sha256']='bad'
            (work/'checkpoint-location.json').write_text(json.dumps(metadata))
            with self.assertRaisesRegex(ValueError,'digest differs'):restore(work,'ldnet',root/'pc')
            self.assertEqual(local.read_bytes(),before)


if __name__=='__main__':unittest.main()
