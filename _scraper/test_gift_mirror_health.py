from copy import deepcopy
from datetime import datetime
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import gift_mirror_health as health


def fixture():
    product = {'id': '101', 'category_ids': ['c1'], 'pricing_available': True, 'source_status': 'feed_present'}
    catalog = {'products': [product], 'categories': [{'id': 'c1', 'parent_ids': []}],
               'meta': {'product_count': 1, 'category_count': 1, 'detail_count': 1,
                        'priced_product_count': 1, 'price_option_count': 1, 'price_tier_count': 1}}
    details = {'101': {'pricing': {'revision': 'r1', 'observed_at': '2026-10-24T00:00:00+09:00',
                'options': [{'id': 'o1', 'tiers': [{'minimum_quantity': 100, 'unit_price_ex_vat': 1000}]}]}}}
    return catalog, details


class GiftHealthTests(unittest.TestCase):
    def test_price_and_category_coverage_is_checked_for_every_product(self):
        c, d = fixture()
        result = health.inspect(c, d)
        self.assertEqual(result['errors'], [])
        self.assertEqual(result['counts']['price_tiers'], 1)
        c['products'][0]['category_ids'] = ['missing']
        c['meta']['product_count'] = 2
        result = health.inspect(c, d)
        self.assertIn('category_reference_missing', result['errors'])
        self.assertIn('metadata_count_mismatch:product_count', result['errors'])

    def test_duplicate_id_and_missing_projected_price_are_detected(self):
        c, d = fixture()
        c['products'].append(deepcopy(c['products'][0]))
        c['products'][0]['pricing_available'] = c['products'][1]['pricing_available'] = False
        result = health.inspect(c, d)
        self.assertIn('product_identity_conflict', result['errors'])
        self.assertIn('pricing_projection_missing', result['errors'])

    def test_invalid_or_duplicate_quantity_tier_is_detected(self):
        c, d = fixture()
        tiers = d['101']['pricing']['options'][0]['tiers']
        tiers.append({'minimum_quantity': 100, 'unit_price_ex_vat': -1})
        result = health.inspect(c, d)
        self.assertIn('price_tier_invalid:101', result['errors'])
        self.assertIn('price_tier_identity_conflict:101', result['errors'])

    def test_same_day_timer_does_not_repeat_http_or_admin_login(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); state = root / '_private/gift/daily-sync'; state.mkdir(parents=True)
            prior = {'date_kst': datetime.now(health.KST).date().isoformat(), 'state': 'requires_attention'}
            (state / 'health.json').write_text(json.dumps(prior))
            with patch.object(health.requests, 'get') as get, patch.object(health.requests, 'Session') as session:
                self.assertEqual(health.run(root), prior)
                get.assert_not_called(); session.assert_not_called()


if __name__ == '__main__': unittest.main()
