"""Private, exact-SKU supplier directory. This module never sends mail.

The database and imported records live outside the deployed shop and Git tree.
Only data explicitly supplied by the owner or a verified authenticated export
belongs here. Browser cookies, passwords and Webhard accounts are not imported.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sqlite3


PROJECT = Path(__file__).resolve().parents[1]
PRIVATE_ROOT = PROJECT.parent / '_private' / PROJECT.name / 'gift'
SOURCE = 'nadaun-gift'
FIELDS = {'product_id', 'product_name', 'supplier', 'terms', 'evidence'}
SUPPLIER_FIELDS = {'company', 'business_number', 'representative', 'contact_name',
                   'phone', 'mobile', 'fax', 'email'}
TERM_FIELDS = {'supplier_product_name', 'supplier_product_code', 'shipping',
               'printing', 'notes', 'commission_percent'}
EVIDENCE_FIELDS = {'kind', 'reference', 'observed_at'}
EVIDENCE_KINDS = {'owner_screenshot', 'authenticated_supplier_page', 'owner_export'}
EMAIL = re.compile(r'[^\s@,;<>]+@[^\s@,;<>]+\.[^\s@,;<>]+\Z')


def private_path(path: Path) -> Path:
    resolved = Path(path).expanduser().resolve()
    if resolved == PROJECT or PROJECT in resolved.parents:
        raise ValueError('Private supplier data must be outside the shop repository')
    return resolved


def object_fields(value, allowed, required=()):
    if not isinstance(value, dict) or set(value) - allowed or set(required) - set(value):
        raise ValueError('Missing or unsupported record fields')
    result = {}
    for key, item in value.items():
        if not isinstance(item, str) or len(item) > 10000 or '\x00' in item:
            raise ValueError('Record values must be bounded text')
        result[key] = item.strip()
    return result


def validate_record(record):
    if not isinstance(record, dict) or set(record) != FIELDS:
        raise ValueError('Expected product, supplier, terms and evidence fields')
    pid = record['product_id']
    if not isinstance(pid, str) or not re.fullmatch(r'[1-9]\d{0,11}', pid):
        raise ValueError('A numeric source product ID is required; names are not keys')
    name = record['product_name']
    if not isinstance(name, str) or not name.strip() or len(name) > 500:
        raise ValueError('Product name is required')
    supplier = object_fields(record['supplier'], SUPPLIER_FIELDS, {'company'})
    if not supplier['company']:
        raise ValueError('Supplier company is required')
    email = supplier.get('email', '')
    if email and not EMAIL.fullmatch(email):
        raise ValueError('Expected one valid email address, without header characters')
    if any('\n' in v or '\r' in v for v in supplier.values()):
        raise ValueError('Supplier contact fields must be single-line text')
    terms = object_fields(record['terms'], TERM_FIELDS)
    evidence = object_fields(record['evidence'], EVIDENCE_FIELDS, EVIDENCE_FIELDS)
    if evidence['kind'] not in EVIDENCE_KINDS or not evidence['reference']:
        raise ValueError('Verified source evidence is required')
    observed = datetime.fromisoformat(evidence['observed_at'])
    if observed.tzinfo is None or observed > datetime.now(timezone.utc):
        raise ValueError('Evidence date must include timezone and not be in the future')
    return {'product_id': pid, 'product_name': name.strip(), 'supplier': supplier,
            'terms': terms, 'evidence': evidence}


def encoded(record):
    return json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


class SupplierRegistry:
    def __init__(self, root=PRIVATE_ROOT):
        self.root = private_path(root)
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        db_path = private_path(self.root / 'suppliers.sqlite3')
        self.connection = sqlite3.connect(db_path, timeout=30)
        # NAS: keep rollback journaling. Do not enable WAL on shared SMB files.
        self.connection.execute('PRAGMA journal_mode=DELETE')
        self.connection.execute('PRAGMA synchronous=FULL')
        self.connection.executescript('''
            CREATE TABLE IF NOT EXISTS supplier_history (
                product_id TEXT NOT NULL,
                digest TEXT NOT NULL,
                observed_at TEXT NOT NULL,
                imported_at TEXT NOT NULL,
                record_json TEXT NOT NULL,
                PRIMARY KEY (product_id, digest)
            );
            CREATE TABLE IF NOT EXISTS supplier_current (
                product_id TEXT PRIMARY KEY,
                digest TEXT NOT NULL
            );
        ''')
        db_path.chmod(0o600)

    def close(self):
        self.connection.close()

    def import_records(self, records):
        if not isinstance(records, list) or not records:
            raise ValueError('A nonempty record list is required')
        rows = [validate_record(r) for r in records]
        if len({r['product_id'] for r in rows}) != len(rows):
            raise ValueError('Duplicate product IDs in one import require review')
        inserted = unchanged = older = 0
        imported_at = datetime.now(timezone.utc).isoformat()
        with self.connection:
            # Serialize read/compare/write across importers, including other PCs.
            self.connection.execute('BEGIN IMMEDIATE')
            for row in rows:
                body = encoded(row)
                digest = hashlib.sha256(body.encode()).hexdigest()
                pid = row['product_id']
                current = self.connection.execute('''
                    SELECT h.digest, h.observed_at FROM supplier_current c
                    JOIN supplier_history h ON h.product_id=c.product_id AND h.digest=c.digest
                    WHERE c.product_id=?
                ''', (pid,)).fetchone()
                observed = datetime.fromisoformat(row['evidence']['observed_at'])
                if current and current[0] == digest:
                    unchanged += 1
                    continue
                if current and observed == datetime.fromisoformat(current[1]):
                    raise ValueError('Conflicting records at the same evidence time require review')
                self.connection.execute('''
                    INSERT OR IGNORE INTO supplier_history VALUES (?, ?, ?, ?, ?)
                ''', (pid, digest, row['evidence']['observed_at'], imported_at, body))
                if current and observed < datetime.fromisoformat(current[1]):
                    older += 1
                    continue
                self.connection.execute('''
                    INSERT INTO supplier_current VALUES (?, ?)
                    ON CONFLICT(product_id) DO UPDATE SET digest=excluded.digest
                ''', (pid, digest))
                inserted += 1
        return {'updated': inserted, 'unchanged': unchanged, 'older_evidence': older,
                **self.status()}

    def status(self):
        matched = self.connection.execute('SELECT COUNT(*) FROM supplier_current').fetchone()[0]
        versions = self.connection.execute('SELECT COUNT(*) FROM supplier_history').fetchone()[0]
        return {'source': SOURCE, 'matched_products': matched, 'evidence_versions': versions,
                'catalog_complete': False, 'mail_sending_enabled': False}

    def lookup(self, product_id):
        if not isinstance(product_id, str) or not re.fullmatch(r'[1-9]\d{0,11}', product_id):
            raise ValueError('Use the exact numeric source product ID')
        found = self.connection.execute('''
            SELECT h.record_json FROM supplier_current c
            JOIN supplier_history h ON h.product_id=c.product_id AND h.digest=c.digest
            WHERE c.product_id=?
        ''', (product_id,)).fetchone()
        if found is None:
            raise LookupError('No verified supplier match for this product ID')
        record = json.loads(found[0])
        observed = datetime.fromisoformat(record['evidence']['observed_at'])
        return {**record, 'source': SOURCE,
                'product_url': f'https://www.nadaun-gift.com/new/shop/detail.php?code={product_id}',
                'email_present': bool(record['supplier'].get('email')),
                'age_days': max(0, (datetime.now(timezone.utc) - observed).days),
                'recheck_before_sending': True, 'mail_sending_enabled': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--private-root', type=Path, default=PRIVATE_ROOT)
    subs = parser.add_subparsers(dest='command', required=True)
    importer = subs.add_parser('import')
    importer.add_argument('--input', type=Path, required=True)
    lookup = subs.add_parser('lookup')
    lookup.add_argument('--product', required=True)
    lookup.add_argument('--output', type=Path, required=True,
                        help='New private JSON file; contacts are never printed in terminal logs')
    subs.add_parser('status')
    args = parser.parse_args()
    registry = SupplierRegistry(args.private_root)
    try:
        if args.command == 'import':
            rows = json.loads(private_path(args.input).read_text(encoding='utf-8'))
            result = registry.import_records(rows)
        elif args.command == 'lookup':
            record = registry.lookup(args.product)
            output = private_path(args.output)
            output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            # Exclusive creation preserves previous exports and unrelated files.
            with output.open('x', encoding='utf-8') as stream:
                output.chmod(0o600)
                stream.write(json.dumps(record, ensure_ascii=False, indent=2) + '\n')
            result = {'found': True, 'product_id': args.product,
                      'email_present': record['email_present'], 'mail_sending_enabled': False}
        else:
            result = registry.status()
        print(json.dumps(result, ensure_ascii=False))
    finally:
        registry.close()


if __name__ == '__main__':
    main()
