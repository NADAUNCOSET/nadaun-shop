import json
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from catalog_checkpoint import restore, snapshot


class CheckpointTests(unittest.TestCase):
    def test_same_named_generations_in_different_workfolders_cannot_share_a_runtime_db(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);first=root/'nas/a/generation';second=root/'nas/b/generation'
            first.mkdir(parents=True);second.mkdir(parents=True)
            a=restore(first,'clmedia',root/'pc');b=restore(second,'clmedia',root/'pc')
            self.assertNotEqual(a,b)
            with closing(sqlite3.connect(a)) as connection:
                connection.execute('CREATE TABLE evidence(value TEXT)');connection.execute("INSERT INTO evidence VALUES('first work')");connection.commit()
            with closing(sqlite3.connect(b)) as connection:
                self.assertEqual(connection.execute("SELECT name FROM sqlite_master WHERE name='evidence'").fetchall(),[])

    def test_every_production_cafe24_source_uses_local_sqlite_and_closed_nas_snapshot(self):
        from sync_cafe24_partners import Collector, SITES
        import catalog_checkpoint
        for source in SITES:
            with self.subTest(source=source), tempfile.TemporaryDirectory() as temporary:
                root=Path(temporary);work=root/'nas'/source
                local_base=root/'pc'
                with patch('sync_cafe24_partners.ROOT',root/'nas'), patch.object(catalog_checkpoint,'runtime_root',return_value=local_base):
                    collector=Collector(source,work)
                    try:
                        self.assertTrue(collector.database_path.is_relative_to(local_base))
                        self.assertFalse((work/'checkpoint.sqlite3').exists())
                        collector.checkpoint_snapshot(force=True)
                        self.assertTrue((work/'checkpoint.sqlite3').exists())
                        location=json.loads((work/'checkpoint-location.json').read_text())
                        self.assertEqual(location['snapshot_integrity'],'ok')
                    finally:collector.db.close()

    def test_live_database_stays_on_pc_and_second_pc_restores_verified_nas_snapshot(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);work=root/'nas/ldnet';work.mkdir(parents=True)
            local=restore(work,'ldnet',root/'pc1')
            self.assertTrue(local.is_relative_to(root/'pc1'))
            with closing(sqlite3.connect(local)) as connection:
                connection.execute('CREATE TABLE pages(id INTEGER)');connection.execute('INSERT INTO pages VALUES(1)');connection.commit()
                metadata=snapshot(connection,work,local,'ldnet')
                self.assertEqual(metadata['snapshot_integrity'],'ok')
            second=restore(work,'ldnet',root/'pc2')
            with closing(sqlite3.connect(second)) as connection:self.assertEqual(connection.execute('SELECT * FROM pages').fetchall(),[(1,)])
            with closing(sqlite3.connect(local)) as connection:
                connection.execute('INSERT INTO pages VALUES(2)');connection.commit();snapshot(connection,work,local,'ldnet')
            restore(work,'ldnet',root/'pc2')
            self.assertEqual(len(list(second.parent.glob('before-restore-*.sqlite3'))),1)
            with closing(sqlite3.connect(second)) as connection:self.assertEqual(connection.execute('SELECT COUNT(*) FROM pages').fetchone()[0],2)

    def test_unverified_nas_snapshot_never_overwrites_pc_checkpoint(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);work=root/'nas/ldnet';work.mkdir(parents=True)
            local=restore(work,'ldnet',root/'pc')
            with closing(sqlite3.connect(local)) as connection:
                connection.execute('CREATE TABLE pages(id INTEGER)');connection.commit();snapshot(connection,work,local,'ldnet')
            before=local.read_bytes();metadata=json.loads((work/'checkpoint-location.json').read_text());metadata['snapshot_sha256']='bad'
            (work/'checkpoint-location.json').write_text(json.dumps(metadata))
            with self.assertRaisesRegex(ValueError,'digest differs'):restore(work,'ldnet',root/'pc')
            self.assertEqual(local.read_bytes(),before)


if __name__=='__main__':unittest.main()
