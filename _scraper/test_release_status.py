"""Never publish an unannounced product as a zero-price or sold-out purchase."""
import unittest
from bs4 import BeautifulSoup
from build_catalog import public_release_fields
from catalog_seo import product_discovery
from storefront_pages import card


class ReleaseStatus(unittest.TestCase):
    def product(self, **changes):
        return {'id': 'saeki-coming', 'name': '신제품 카메라', 'brand_id': 'test', 'kind': 'purchase',
                'release_status': 'coming_soon', 'price': None, 'sale_price': None,
                'status': 'inquiry', 'supplier_status': 'inquiry', 'category_ids': [],
                'image': '/assets/shop/nadaun-logo.png', 'offers': [{'source': 'saeki'}], **changes}

    def test_release_projection_fails_closed_for_priced_or_soldout_state(self):
        self.assertEqual(public_release_fields(self.product()), {'release_status': 'coming_soon'})
        self.assertEqual(public_release_fields({'kind': 'purchase', 'price': 100}), {})
        for change in [{'price': 0}, {'sale_price': 0}, {'price': 100}, {'status': 'soldout'},
                       {'supplier_status': 'soldout'}, {'kind': 'rental'}, {'release_status': 'unknown'}]:
            with self.subTest(change=change), self.assertRaises(ValueError):
                public_release_fields(self.product(**change))

    def test_static_card_never_shows_zero_or_soldout_for_coming_soon(self):
        # The renderer must remain clear even if handed stale source fields.
        page = BeautifulSoup(card(self.product(price=0, sale_price=0, status='soldout')), 'html.parser')
        self.assertEqual(page.select_one('.product-price').text, '출시 예정 · 가격 미공개')
        self.assertIn('출시 일정 상담', page.get_text())
        self.assertNotIn('품절', page.get_text())
        self.assertNotIn('0원', page.get_text())
        normal = BeautifulSoup(card(self.product(release_status=None, price=10000)), 'html.parser')
        self.assertIn('10,000원', normal.get_text())
        self.assertNotIn('출시 예정', normal.get_text())

    def test_release_discovery_is_explicit_without_fabricated_price(self):
        discovery = product_discovery(self.product(), {'name': 'TEST', 'aliases': []}, {})
        self.assertIn('출시 예정 · 가격 미공개', discovery['description'])
        self.assertIn('출시 일정 상담', discovery['description'])
        self.assertIn('출시 예정', discovery['search_terms'])
        self.assertLessEqual(len(discovery['description']), 80)


if __name__ == '__main__':
    unittest.main()
