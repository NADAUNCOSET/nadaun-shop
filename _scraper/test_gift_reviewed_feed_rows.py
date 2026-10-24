from copy import deepcopy
import hashlib
import json
from pathlib import Path
import unittest
from unittest.mock import patch
import gift_official_feed as source


def raw(rows):
    return ('\t'.join(source.FIELDS)+'\n'+'\n'.join('\t'.join(r) for r in rows)+'\n').encode('euc-kr')


class ReviewedFeedRowTests(unittest.TestCase):
    def records(self): return list(source.reviewed_row_repairs().values())

    def test_only_exact_reviewed_rows_are_repaired_with_original_identity_and_set_price(self):
        records=self.records(); rows, rejected=source.parse_feed(raw([r['original_fields'] for r in records]))
        self.assertFalse(rejected);self.assertEqual(len(rows),3)
        for row, record in zip(rows,records):
            self.assertEqual({key:row[key] for key in source.FIELDS},dict(zip(source.FIELDS,record['canonical_fields'])))
            self.assertEqual(row['_reviewed_row_repair']['source_row_sha256'],record['source_row_sha256'])
            self.assertNotIn('unit_price',row);self.assertNotIn('supplier_id',row)

    def test_changed_malformed_source_row_is_not_covered_by_old_review(self):
        records=self.records(); changed=list(records[0]['original_fields']);changed[1]+=' changed'
        rows,rejected=source.parse_feed(raw([records[1]['canonical_fields'],changed]))
        self.assertEqual(len(rows),1);self.assertEqual(rejected[0]['raw_fields'],changed)
        self.assertEqual(rejected[0]['reason'],'column_count')

    def test_repaired_duplicate_id_still_stops_entire_import(self):
        row=self.records()[0]['original_fields']
        with self.assertRaisesRegex(ValueError,'Duplicate'):
            source.parse_feed(raw([row,row]))

    def test_unreviewed_embedded_tabs_never_receive_generic_automatic_alignment(self):
        record=self.records()[0]; changed=list(record['original_fields'])
        changed[0]='999999';changed[4]=changed[4].replace(record['id'],'999999')
        rows,rejected=source.parse_feed(raw([record['canonical_fields'],changed]))
        self.assertEqual(len(rows),1);self.assertEqual(len(rejected),1)

    def test_registry_cannot_change_price_outside_original_whitespace_alignment(self):
        path=Path(source.__file__).with_name('gift-reviewed-feed-rows.json')
        registry=json.loads(path.read_text());registry['rows'][0]['canonical_fields'][2]='1'
        with patch.object(Path,'read_text',return_value=json.dumps(registry)):
            with self.assertRaisesRegex(ValueError,'beyond whitespace'):
                source.reviewed_row_repairs()


if __name__=='__main__':unittest.main()
