from copy import deepcopy
import json
from pathlib import Path
import unittest
from brand_category_policy import choose_navigation
from catalog_dedup import conflict


class BrandNavigationTest(unittest.TestCase):
    def fixture(self):
        brands = {'smallrig': {'name': 'SmallRig', 'aliases': ['스몰리그']}}
        cats = {}
        for source, names in [('kpp', ['케이지', 'SONY']), ('onnoff', ['전체 상품', '기타카메라/캠코더용품'])]:
            for i, name in enumerate(names):
                cid = f'{source}:{i}'
                cats[cid] = {'id': cid, 'name': name, 'parent_id': f'{source}:0' if i else None, 'brand_id': 'smallrig'}
        rows = [{'id': 'p1', 'kind': 'purchase', 'brand_id': 'smallrig', 'category_ids': list(cats), 'offers': [{'source': 'onnoff', 'price': 99}]}]
        return rows, cats, brands

    def test_specific_tree_wins_without_changing_price_or_original_membership(self):
        rows, cats, brands = self.fixture(); before = deepcopy(rows)
        audit = choose_navigation(rows, cats, brands)
        self.assertEqual(audit['brands']['smallrig']['preferred_source'], 'kpp')
        self.assertEqual(rows[0]['navigation_category_ids'], ['kpp:0', 'kpp:1'])
        self.assertEqual(rows[0]['category_ids'], before[0]['category_ids'])
        self.assertEqual(rows[0]['offers'], before[0]['offers'])

    def test_better_onnoff_tree_is_selected_after_refresh(self):
        rows, cats, brands = self.fixture()
        cats['onnoff:0']['name'] = '카메라 케이지'; cats['onnoff:1']['name'] = 'SONY'
        cats['onnoff:2'] = {'id': 'onnoff:2', 'name': 'FX3', 'parent_id': 'onnoff:1', 'brand_id': 'smallrig'}
        rows[0]['category_ids'].append('onnoff:2')
        self.assertEqual(choose_navigation(rows, cats, brands)['brands']['smallrig']['preferred_source'], 'onnoff')
        cats['onnoff:2']['name'] = '전체'; cats['onnoff:1']['name'] = '기타'
        self.assertEqual(choose_navigation(rows, cats, brands)['brands']['smallrig']['preferred_source'], 'kpp')

    def test_fallback_preserves_products_not_carried_by_preferred_source(self):
        rows, cats, brands = self.fixture()
        rows.append({'id': 'p2', 'kind': 'purchase', 'brand_id': 'smallrig', 'category_ids': ['onnoff:1']})
        report = choose_navigation(rows, cats, brands)['brands']['smallrig']
        self.assertEqual(report['fallback_products'], 1)
        self.assertEqual(report['unclassified_products'], 0)
        self.assertEqual(rows[1]['navigation_category_ids'], ['onnoff:0', 'onnoff:1'])

    def test_brand_override_is_preserved_and_missing_source_fails_closed(self):
        rows, cats, brands = self.fixture()
        self.assertEqual(choose_navigation(rows, cats, brands, {'smallrig': 'onnoff'})['brands']['smallrig']['preferred_source'], 'onnoff')
        with self.assertRaises(ValueError): choose_navigation(rows, cats, brands, {'smallrig': 'unknown'})

    def test_rentals_and_other_brand_categories_are_isolated(self):
        rows, cats, brands = self.fixture()
        rental = {'id': 'r1', 'kind': 'rental', 'brand_id': 'smallrig', 'category_ids': ['rental:1']}
        rows.append(deepcopy(rental))
        cats['kpp:other'] = {'id': 'kpp:other', 'name': '필터', 'parent_id': None, 'brand_id': 'hoya'}
        rows[0]['category_ids'].append('kpp:other')
        report = choose_navigation(rows, cats, brands)['brands']['smallrig']
        self.assertEqual(rows[1], rental)
        self.assertNotIn('kpp:other', rows[0]['navigation_category_ids'])
        self.assertEqual(len(report['other_brand_paths_excluded']), 1)

    def test_broken_or_cyclic_ancestry_stops_build(self):
        for parent in ('missing', 'kpp:1'):
            rows, cats, brands = self.fixture(); cats['kpp:0']['parent_id'] = parent
            with self.assertRaises(ValueError): choose_navigation(rows, cats, brands)

    def test_option_families_share_navigation_and_do_not_inflate_quality(self):
        rows, cats, brands = self.fixture()
        rows[0]['listing_id'] = 'p1'; rows.append({**deepcopy(rows[0]), 'id': 'p2'})
        audit = choose_navigation(rows, cats, brands)['brands']['smallrig']
        self.assertEqual(audit['listing_count'], 1)
        self.assertEqual(audit['candidates']['kpp']['covered_products'], 1)
        self.assertEqual(rows[0]['navigation_category_ids'], rows[1]['navigation_category_ids'])

    def test_generated_navigation_has_complete_ancestry_and_preserves_all_listings(self):
        data = json.loads((Path(__file__).resolve().parent.parent/'data/catalog/catalog.json').read_text())
        categories = {c['id']: c for c in data['categories']}
        brands = {b['id']: b for b in data['brands']}
        for p in data['products']:
            if p['kind'] != 'purchase': continue
            self.assertIn('navigation_category_ids', p)
            ids = set(p['navigation_category_ids'])
            self.assertTrue(ids <= set(brands[p['brand_id']]['navigation_category_ids']))
            for cid in ids:
                self.assertEqual(categories[cid]['brand_id'], p['brand_id'])
                self.assertTrue(not categories[cid]['parent_id'] or categories[cid]['parent_id'] in ids)
        self.assertEqual(len({p.get('listing_id',p['id']) for p in data['products']}),data['meta']['listing_count'])


class PartnerDuplicateTest(unittest.TestCase):
    def test_same_verified_model_is_not_split_by_title_translation_alone(self):
        a = {'id': 'kpp-1', 'brand_id': 'smallrig', 'kind': 'purchase', 'name': '2903C 마운트'}
        b = {**a, 'id': 'onnoff-2', 'name': '2903C Mount Kit'}
        self.assertIsNone(conflict(a, b, {}))

    def test_unresolved_partner_options_cannot_merge(self):
        a = {'id': 'kpp-1', 'brand_id': 'smallrig', 'kind': 'purchase', 'name': '2903C 마운트'}
        b = {**a, 'id': 'onnoff-2'}
        self.assertEqual(conflict(a, b, {b['id']: {'options_require_confirmation': True}}), 'unverified_option_equivalence')


if __name__ == '__main__': unittest.main()
