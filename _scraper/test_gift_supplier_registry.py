from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from gift_supplier_registry import PROJECT, SupplierRegistry, private_path, validate_record


def sample(pid='123', email='contact@example.test', observed='2026-09-07T10:00:00+09:00'):
    return {'product_id': pid, 'product_name': '동일한 이름의 상품',
            'supplier': {'company': '테스트 공급처', 'email': email},
            'terms': {'shipping': '상품별 확인'},
            'evidence': {'kind': 'owner_screenshot', 'reference': 'test-fixture',
                         'observed_at': observed}}


class RegistryTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.registry = SupplierRegistry(Path(self.temp.name) / 'private')

    def tearDown(self):
        self.registry.close()
        self.temp.cleanup()

    def test_same_name_different_skus_keep_their_own_email(self):
        self.registry.import_records([sample('123'), sample('124', 'other@example.test')])
        self.assertEqual(self.registry.lookup('123')['supplier']['email'], 'contact@example.test')
        self.assertEqual(self.registry.lookup('124')['supplier']['email'], 'other@example.test')
        with self.assertRaises(LookupError):
            self.registry.lookup('125')

    def test_repeat_import_is_idempotent_and_does_not_claim_complete(self):
        self.registry.import_records([sample()])
        result = self.registry.import_records([sample()])
        self.assertEqual(result['unchanged'], 1)
        self.assertEqual(result['evidence_versions'], 1)
        self.assertFalse(result['catalog_complete'])
        self.assertFalse(result['mail_sending_enabled'])

    def test_partial_import_preserves_unseen_products(self):
        self.registry.import_records([sample('123'), sample('124')])
        self.registry.import_records([sample('125')])
        self.assertEqual(self.registry.status()['matched_products'], 3)
        self.assertEqual(self.registry.lookup('124')['product_id'], '124')

    def test_newer_contact_wins_but_history_is_preserved(self):
        newer = sample(email='new@example.test', observed='2026-09-07T11:00:00+09:00')
        self.registry.import_records([newer])
        result = self.registry.import_records([sample()])
        self.assertEqual(result['older_evidence'], 1)
        self.assertEqual(result['evidence_versions'], 2)
        result = self.registry.lookup('123')
        self.assertEqual(result['supplier']['email'], 'new@example.test')
        self.assertTrue(result['recheck_before_sending'])
        self.assertFalse(result['mail_sending_enabled'])

    def test_same_time_conflict_rolls_back_entire_batch(self):
        self.registry.import_records([sample()])
        with self.assertRaises(ValueError):
            self.registry.import_records([sample('124'), sample(email='wrong@example.test')])
        self.assertEqual(self.registry.status()['matched_products'], 1)
        self.assertEqual(self.registry.lookup('123')['supplier']['email'], 'contact@example.test')

    def test_unknown_and_credential_fields_rejected(self):
        for field in ('password', 'webhard', 'cookie', 'access_token', 'raw_html'):
            record = sample()
            record['supplier'][field] = 'SECRET-CANARY'
            with self.assertRaises(ValueError):
                self.registry.import_records([record])
        self.assertEqual(self.registry.status()['matched_products'], 0)

    def test_mail_header_injection_and_multiple_recipients_rejected(self):
        for email in ('a@example.test\r\nBcc: wrong@example.test',
                      'a@example.test,b@example.test', 'Name <a@example.test>', 'not-an-email'):
            with self.assertRaises(ValueError):
                validate_record(sample(email=email))

    def test_private_output_cannot_be_inside_public_repository(self):
        with self.assertRaises(ValueError):
            SupplierRegistry(PROJECT / 'data' / 'suppliers')
        alias = Path(self.temp.name) / 'shop-alias'
        alias.symlink_to(PROJECT, target_is_directory=True)
        with self.assertRaises(ValueError):
            private_path(alias / 'suppliers.json')

    def test_status_never_contains_private_values(self):
        record = sample(email='PRIVATE-CANARY@example.test')
        self.registry.import_records([record])
        self.assertNotIn('PRIVATE-CANARY', json.dumps(self.registry.status()))

    def test_invalid_batch_does_not_write_any_records(self):
        record = sample('124')
        record['evidence']['kind'] = 'guessed-from-name'
        with self.assertRaises(ValueError):
            self.registry.import_records([sample(), record])
        self.assertEqual(self.registry.status()['matched_products'], 0)

    def test_duplicate_product_rows_require_review(self):
        with self.assertRaises(ValueError):
            self.registry.import_records([sample(), deepcopy(sample())])

    def test_missing_email_does_not_invent_recipient(self):
        record = sample(email='')
        self.registry.import_records([record])
        self.assertFalse(self.registry.lookup('123')['email_present'])


if __name__ == '__main__':
    unittest.main()
