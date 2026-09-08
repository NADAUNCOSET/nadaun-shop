import json
from pathlib import Path
import re
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import private_storage
from gift_supplier_registry import PRIVATE_ROOT
from brand_source_policy import AUDIT


class PrivateStorageTest(unittest.TestCase):
    def test_all_default_records_belong_to_project(self):
        project = private_storage.PROJECT
        self.assertEqual(PRIVATE_ROOT, project / '_private/gift')
        self.assertEqual(AUDIT, project / '_private/catalog')
        self.assertEqual(private_storage.private_path(PRIVATE_ROOT / 'suppliers.sqlite3'),
                         project / '_private/gift/suppliers.sqlite3')

    def test_public_paths_and_aliases_cannot_receive_private_data(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary) / 'shop'
            protected = project / '_private'
            protected.mkdir(parents=True)
            (project / 'data').mkdir()
            (protected / 'public-alias').symlink_to(project / 'data')
            (protected / 'outside-alias').symlink_to(Path(temporary))
            (Path(temporary) / 'shop-alias').symlink_to(project)
            with patch.object(private_storage, 'PROJECT', project):
                self.assertEqual(private_storage.private_path(protected / 'gift/file.json'),
                                 (protected / 'gift/file.json').resolve())
                for path in (project, project / 'data/file.json',
                             protected / 'public-alias/file.json',
                             protected / 'outside-alias/file.json',
                             Path(temporary) / 'shop-alias/data/file.json'):
                    with self.subTest(path=path), self.assertRaises(ValueError):
                        private_storage.private_path(path)

    def test_git_excludes_nested_private_files(self):
        project = private_storage.PROJECT
        for relative in ('_private/commerce/configuration.json',
                         '_private/commerce/owner-login.private',
                         '_private/gift/suppliers.sqlite3',
                         '_private/catalog/source-matches.json'):
            result = subprocess.run(['git', 'check-ignore', '--no-index', '-q', '--', relative],
                                    cwd=project, capture_output=True)
            self.assertEqual(result.returncode, 0, relative)
        tracked = subprocess.check_output(['git', 'ls-files', '--', '_private'], cwd=project)
        self.assertEqual(tracked, b'', 'Private records must never enter the Git index')

    def test_deployment_excludes_and_denies_private_routes(self):
        project = private_storage.PROJECT
        rules = (project / '.vercelignore').read_text().splitlines()
        self.assertIn('_private/', rules)
        routes = json.loads((project / 'vercel.json').read_text())['routes']
        filesystem = next(i for i, row in enumerate(routes) if row.get('handle') == 'filesystem')
        for url in ('/_private', '/_private/', '/_private/gift/suppliers.sqlite3',
                    '/_private/commerce/owner-login.private'):
            terminal = next((row for row in routes[:filesystem]
                             if not row.get('continue') and row.get('src')
                             and re.fullmatch(row['src'], url)), None)
            self.assertIsNotNone(terminal, url)
            self.assertEqual(terminal['status'], 404)
            self.assertEqual(terminal['headers']['Cache-Control'], 'no-store')


if __name__ == '__main__':
    unittest.main()
