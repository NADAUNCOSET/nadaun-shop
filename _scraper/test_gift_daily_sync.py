import copy
import hashlib
import tempfile
from pathlib import Path
import unittest
from gift_daily_sync import apply_feed, apply_availability, write_catalog, validate_download
from gift_official_feed import FIELDS


def feed(ids=('101', '102'), title='테스트 상품'):
    rows = [[pid, title+' '+pid, '100000', 'https://nadaun-gift.com/new/shop/detail.php?code='+pid,
             'https://cloudfront.imggift.com/'+pid+'.jpg', '타올', '신상품', '도매', '제조사', '', '', 'set', '4400', 'N'] for pid in ids]
    return ('\t'.join(FIELDS)+'\n'+'\n'.join('\t'.join(row) for row in rows)+'\n').encode('euc-kr')


def catalog():
    return {'meta': {'product_count': 3, 'detail_count': 1, 'official_feed_count': 0},
            'categories': [{'id': '1', 'name': '생활용품', 'parent_ids': [], 'count': 3},
                           {'id': '2', 'name': '타올', 'parent_ids': ['1'], 'count': 3}],
            'products': [{'id': pid, 'name': '이전 '+pid, 'image': 'https://example.com/'+pid+'.jpg',
                          'category_ids': ['1', '2'], 'detail_available': pid == '101', 'soldout': None,
                          **({'pricing_available': True, 'pricing_observed_at': '2026-09-08T01:00:00Z'} if pid == '101' else {})}
                         for pid in ('101', '102', '103')]}


def apply(c=None, raw=None, modified='2026-10-24T01:00:00Z', observed='2026-10-24T02:00:00Z'):
    return apply_feed(c or catalog(), raw or feed(), modified_at=modified, observed_at=observed, minimum_count=1)


def evidence(products, **changes):
    return {'source': 'nadaun-gift', 'kind': 'explicit_product_status', 'source_sha256': 'a'*64,
            'observed_at': '2026-10-24T03:00:00Z', 'products': products, **changes}


class GiftDailySyncTests(unittest.TestCase):
    def test_exact_ids_preserve_details_and_never_interpret_set_price_as_unit_price(self):
        old = catalog(); before = copy.deepcopy(old)
        new, receipt = apply(old, feed(('101', '102', '104')))
        self.assertEqual(old, before)
        self.assertEqual(receipt['added_ids'], ['104'])
        p = next(p for p in new['products'] if p['id'] == '101')
        self.assertTrue(p['pricing_available'])
        self.assertEqual(p['pricing_observed_at'], '2026-09-08T01:00:00Z')
        self.assertNotIn('price', p); self.assertNotIn('supplier', p)
        self.assertEqual(new['meta']['mirror']['exact_id_matches'], 3)
        self.assertFalse(new['meta']['mirror']['full_source_inventory_verified'])

    def test_channel_absence_never_withdraws_and_same_snapshot_is_idempotent(self):
        first, _ = apply()
        first['meta']['official_feed_count'] = 0  # Small fixture, not a production drop.
        new, _ = apply(first, feed(('101',)), modified='2026-10-25T01:00:00Z', observed='2026-10-25T02:00:00Z')
        by_id = {p['id']: p for p in new['products']}
        self.assertEqual(by_id['102']['source_status'], 'pending_absence')
        self.assertEqual(by_id['103']['source_status'], 'unverified')
        self.assertEqual(new['meta']['active_product_count'], 3)
        again, _ = apply(new, feed(('101',)), modified='2026-10-25T01:00:00Z', observed='2026-10-25T02:00:00Z')
        self.assertEqual(again, new)

    def test_truncated_html_duplicate_and_large_drop_do_not_modify_catalog(self):
        old = catalog(); before = copy.deepcopy(old)
        for raw in (b'<html>blocked</html>\n', feed()[:-1], feed(('101', '101'))):
            with self.assertRaises(ValueError): apply(old, raw)
        with self.assertRaisesRegex(ValueError, 'drop'):
            validate_download(feed(), prior_count=100, minimum_count=1)
        self.assertEqual(old, before)

    def test_quarantined_known_id_is_never_treated_as_missing(self):
        first, _ = apply(); first['meta']['official_feed_count'] = 0
        raw = feed().decode('euc-kr').replace('테스트 상품 102', '잘못된\t상품 102').encode('euc-kr')
        second, r = apply(first, raw, modified='2026-10-25T01:00:00Z', observed='2026-10-25T02:00:00Z')
        self.assertEqual(r['quarantined_ids'], ['102'])
        self.assertEqual(next(p for p in second['products'] if p['id'] == '102')['source_status'], 'feed_present')

    def test_explicit_withdrawal_hides_but_retains_identity_and_detail_snapshot(self):
        first, _ = apply()
        new, changed = apply_availability(first, evidence([{'id': '101', 'status': 'withdrawn'}]))
        self.assertEqual(changed, ['101'])
        self.assertEqual(new['meta']['product_count'], 3)
        self.assertEqual(new['meta']['active_product_count'], 2)
        self.assertTrue(next(p for p in new['products'] if p['id'] == '101')['detail_available'])
        with tempfile.TemporaryDirectory() as d:
            write_catalog(d, new)
            self.assertNotIn('id=101', (Path(d)/'gift-sitemap-1.xml').read_text())
            self.assertIn('id=102', (Path(d)/'gift-sitemap-1.xml').read_text())

    def test_complete_inventory_removes_absent_ids_only_with_full_proof(self):
        first, _ = apply(); first['meta']['official_feed_count'] = 0
        rows = [{'id': '101', 'status': 'active'}, {'id': '102', 'status': 'soldout'}]
        for patch in ({'kind': 'naver_feed'}, {'kind': 'authenticated_full_inventory'},
                      {'kind': 'authenticated_full_inventory', 'complete': True, 'advertised_total': 3}):
            with self.assertRaises(ValueError): apply_availability(first, evidence(rows, **patch))
        new, _ = apply_availability(first, evidence(rows, kind='authenticated_full_inventory', complete=True, advertised_total=2))
        by_id = {p['id']: p for p in new['products']}
        self.assertEqual(by_id['103']['source_status'], 'withdrawn')
        self.assertTrue(by_id['102']['soldout'])
        self.assertTrue(new['meta']['mirror']['full_source_inventory_verified'])

    def test_stale_snapshots_and_duplicate_availability_are_rejected(self):
        first, _ = apply()
        with self.assertRaises(ValueError): apply(first, modified='2026-10-23T00:00:00Z')
        with self.assertRaises(ValueError): apply_availability(first, evidence([{'id': '101', 'status': 'withdrawn'}], observed_at='2026-10-23T00:00:00Z'))
        with self.assertRaises(ValueError): apply_availability(first, evidence([{'id': '101', 'status': 'active'}, {'id': '101', 'status': 'withdrawn'}]))

    def test_newer_explicit_reappearance_restores_without_losing_old_prices(self):
        first, _ = apply()
        removed, _ = apply_availability(first, evidence([{'id': '101', 'status': 'withdrawn'}]))
        restored, _ = apply(removed, modified='2026-10-25T01:00:00Z', observed='2026-10-25T02:00:00Z')
        p = next(p for p in restored['products'] if p['id'] == '101')
        self.assertEqual(p['source_status'], 'feed_present')
        self.assertEqual(p['pricing_observed_at'], '2026-09-08T01:00:00Z')

    def test_older_feed_cannot_reset_newer_explicit_stock_timestamp(self):
        first,_=apply()
        checked,_=apply_availability(first,evidence([{'id':'101','status':'soldout'}]))
        again,_=apply(checked)
        p=next(p for p in again['products'] if p['id']=='101')
        self.assertTrue(p['soldout'])
        self.assertEqual(p['source_status_at'],'2026-10-24T03:00:00Z')
        self.assertEqual(again['meta']['mirror']['last_availability_check_at'],'2026-10-24T03:00:00Z')
        with self.assertRaisesRegex(ValueError,'Older availability'):
            apply_availability(again,evidence([{'id':'101','status':'active'}],observed_at='2026-10-24T02:30:00Z'))

    def test_older_channel_absence_preserves_a_newer_confirmed_active_product(self):
        first,_=apply()
        checked,_=apply_availability(first,evidence([{'id':'103','status':'active'}]))
        again,_=apply(checked)
        self.assertEqual(next(p for p in again['products'] if p['id']=='103')['source_status'],'feed_present')

    def test_new_feed_keeps_availability_cursor_but_invalidates_older_full_freshness(self):
        first,_=apply();first['meta']['official_feed_count']=0
        rows=[{'id':pid,'status':'active'} for pid in ('101','102','103')]
        checked,_=apply_availability(first,evidence(rows,kind='authenticated_full_inventory',complete=True,advertised_total=3))
        again,_=apply(checked)
        self.assertTrue(again['meta']['mirror']['full_source_inventory_verified'])
        newer,_=apply(checked,modified='2026-10-25T01:00:00Z',observed='2026-10-25T02:00:00Z')
        self.assertFalse(newer['meta']['mirror']['full_source_inventory_verified'])
        self.assertEqual(newer['meta']['mirror']['last_availability_check_at'],'2026-10-24T03:00:00Z')


if __name__ == '__main__': unittest.main()
