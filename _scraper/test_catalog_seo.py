"""SEO contract: real services, distinct intents, safe structured data and links."""
import json
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from bs4 import BeautifulSoup
from catalog_seo import PAGE_METADATA, SITE, page_metadata, page_structured_data, product_discovery, root_sitemap

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / '_scraper/shop_templates'


class CatalogSEO(unittest.TestCase):
    def test_public_page_titles_and_descriptions_are_distinct_and_bounded(self):
        self.assertEqual(len(PAGE_METADATA), len({v[0] for v in PAGE_METADATA.values()}))
        self.assertEqual(len(PAGE_METADATA), len({v[1] for v in PAGE_METADATA.values()}))
        for filename, (title, description) in PAGE_METADATA.items():
            with self.subTest(filename=filename):
                self.assertLessEqual(len(description), 80)
                self.assertTrue(title and description)
                self.assertNotRegex(title + description, r'검색량\s*1위|최고\s*검색량|최저가|당일\s*확정')
        self.assertIn('영등포', PAGE_METADATA['rental-guide.html'][0])
        self.assertIn('스튜디오', PAGE_METADATA['studio.html'][0])
        self.assertNotIn('렌탈샵', PAGE_METADATA['gifts.html'][1])
        self.assertEqual(page_metadata('orders.html', '주문 조회', '주문 내용'), ('주문 조회', '주문 내용'))

    def test_discovery_preserves_purchase_rental_and_studio_intent(self):
        brand = {'name': 'SONY', 'aliases': ['소니']}
        product = {'name': 'SONY FX3 카메라', 'category_ids': [], 'kind': 'purchase'}
        purchase = product_discovery(product, brand, {})
        rental = product_discovery({**product, 'kind': 'rental'}, brand, {})
        studio = product_discovery({**product, 'name': '나다운 스튜디오', 'kind': 'rental',
                                    'rental': {'service': 'studio'}}, brand, {})
        self.assertIn('구매 안내', purchase['description'])
        self.assertNotIn('영등포 렌탈샵', purchase['search_terms'])
        self.assertIn('렌탈·대여 안내', rental['description'])
        self.assertIn('영등포 렌탈샵', rental['search_terms'])
        self.assertIn('영등포 스튜디오 대여', studio['search_terms'])
        self.assertNotIn('영등포 렌탈샵', studio['search_terms'])
        for discovery in [purchase, rental, studio]:
            self.assertLessEqual(len(discovery['description']), 80)

    def test_all_saved_products_keep_valid_discovery_without_mutation(self):
        catalog = json.loads((ROOT / 'data/catalog/catalog.json').read_text())
        brands = {b['id']: b for b in catalog['brands']}
        categories = {c['id']: c for c in catalog['categories']}
        for product in catalog['products']:
            before = json.dumps(product, ensure_ascii=False, sort_keys=True)
            discovery = product_discovery(product, brands[product['brand_id']], categories)
            self.assertEqual(before, json.dumps(product, ensure_ascii=False, sort_keys=True))
            self.assertTrue(0 < len(discovery['description']) <= 80, product['id'])
            self.assertTrue(2 <= len(discovery['tags']) <= 7, product['id'])
            self.assertNotRegex(' '.join(discovery['tags']), r'검색량|검색순위')

    def test_memory_rental_abbreviations_are_searchable_without_crossing_card_types(self):
        brand = {'name': 'SONY', 'aliases': ['소니']}
        for card_type in ['A', 'B']:
            for name in [f'CFE-{card_type}타입 메모리카드 320GB 대여',
                         f'CFexpress 4.0 Type {card_type} 카드',
                         f'CF EXPRESS {card_type} TYPE 메모리카드']:
                with self.subTest(name=name):
                    result = product_discovery({'name': name, 'category_ids': [], 'kind': 'rental'}, brand, {})
                    self.assertIn(f'CFexpress {card_type}', result['search_terms'])
                    self.assertIn(f'CF익스프레스 {card_type}타입', result['search_terms'])
                    self.assertNotIn(f'CFexpress {"B" if card_type == "A" else "A"}', result['search_terms'])
        unrelated = product_discovery({'name': 'E-IMAGE TYPE A STAND', 'category_ids': [], 'kind': 'purchase'}, brand, {})
        self.assertFalse(any('CFexpress' in term for term in unrelated['search_terms']))

    def test_home_website_identity_and_page_breadcrumb(self):
        title, desc = PAGE_METADATA['index.html']
        graph = self.schemas(page_structured_data('index.html', title, desc, SITE))[0]['@graph']
        website = next(row for row in graph if row['@type'] == 'WebSite')
        self.assertEqual(website['name'], '나다운 스페이스')
        self.assertEqual(website['url'], SITE)
        self.assertIn('나다운 샵', website['alternateName'])
        title, desc = PAGE_METADATA['rental-guide.html']
        graph = self.schemas(page_structured_data('rental-guide.html', title, desc, SITE+'rental-guide.html'))[0]['@graph']
        breadcrumb = next(row for row in graph if row['@type'] == 'BreadcrumbList')
        self.assertEqual(breadcrumb['itemListElement'][-1]['item'], SITE+'rental-guide.html')

    def test_structured_data_is_safe_with_supplier_markup_and_no_indexable_admin(self):
        title = '</script><script>alert(1)</script> & "brand"'
        output = page_structured_data('brands/test.html', title, title, SITE+'brands/test.html', brand=True)
        soup = BeautifulSoup(output, 'html.parser')
        self.assertEqual(len(soup.select('script')), 1)
        self.assertEqual(json.loads(soup.script.string)['@graph'][0]['name'], title)
        for filename in ['admin.html', 'orders.html', 'checkout.html', 'item.html', 'gift-item.html', 'search.html']:
            self.assertEqual(page_structured_data(filename, title, title, SITE+filename), '')

    def test_store_and_studio_floors_and_contacts_remain_separate(self):
        common = self.schemas((TEMPLATES / 'page.html').read_text())[0]
        studio = self.schemas((TEMPLATES / 'studio.html').read_text())[0]['provider']
        self.assertEqual(common['address']['streetAddress'], '영등포로33길 18 1층')
        self.assertEqual(studio['address']['streetAddress'], '영등포로33길 18 2층')
        self.assertEqual(common['telephone'], '0507-1394-6231')
        self.assertEqual(studio['telephone'], '0507-1313-6232')
        self.assertNotIn('aggregateRating', common)
        self.assertNotIn('geo', common)

    def test_rental_guide_links_only_existing_rental_categories_and_preserves_14_days(self):
        page = BeautifulSoup((TEMPLATES / 'rental-guide.html').read_text(), 'html.parser')
        catalog = json.loads((ROOT / 'data/catalog/rental.json').read_text())
        categories = {c['id'] for c in catalog['categories']}
        self.assertEqual(len(page.select('h1')), 1)
        self.assertIn('2주(14일)', page.get_text())
        self.assertTrue(page.select_one('a[href="/shipping.html#rental-period"]'))
        self.assertTrue(page.select_one('a[href="/studio.html"]'))
        count = 0
        for link in page.select('a[href]'):
            parsed = urlsplit(link['href']); query = parse_qs(parsed.query)
            if 'type' in query:
                self.assertEqual(query['kind'], ['rental'])
                self.assertIn(query['type'][0], categories)
                count += 1
        self.assertEqual(count, 7)
        self.assertEqual(self.schemas(str(page))[0]['provider']['@id'], SITE+'#store')

    def test_home_studio_and_footer_discover_rental_guide(self):
        for filename in ['home.html', 'studio.html', 'page.html', 'services.html']:
            soup = BeautifulSoup((TEMPLATES / filename).read_text(), 'html.parser')
            self.assertTrue(soup.select_one('a[href="/rental-guide.html"]'), filename)
        guide = (TEMPLATES / 'services.html').read_text()
        self.assertNotIn('선택하면 나다운기프트로 연결됩니다', guide)
        self.assertIn('최종 가격은 상담으로 확정', guide)

    def test_one_root_sitemap_covers_equipment_and_gift_shards_without_nested_indexes(self):
        import xml.etree.ElementTree as ET
        ns = '{http://www.sitemaps.org/schemas/sitemap/0.9}'
        source = '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><sitemap><loc>https://shop.nadaun.co/gift-sitemap-1.xml</loc></sitemap><sitemap><loc>https://shop.nadaun.co/gift-sitemap-2.xml</loc></sitemap></sitemapindex>'
        root = ET.fromstring(root_sitemap(source))
        self.assertEqual(root.tag, ns+'sitemapindex')
        self.assertEqual([node.text for node in root.iter(ns+'loc')], [SITE+'catalog-sitemap.xml', SITE+'gift-sitemap-1.xml', SITE+'gift-sitemap-2.xml'])
        for invalid in [source.replace('shop.nadaun.co', 'other.invalid'), source.replace('gift-sitemap-1.xml','gift-sitemap.xml'), source.replace('gift-sitemap-2.xml','gift-sitemap-1.xml')]:
            with self.assertRaises(ValueError):root_sitemap(invalid)

    def test_merchant_home_verification_is_in_the_source_head_and_survives_rebuilds(self):
        page = BeautifulSoup((TEMPLATES/'page.html').read_text(), 'html.parser')
        for name in ['google-site-verification', 'naver-site-verification']:
            tags = page.head.select('meta[name="'+name+'"]')
            self.assertEqual(len(tags), 1)
            self.assertTrue(tags[0]['content'])

    @staticmethod
    def schemas(html):
        return [json.loads(node.string) for node in BeautifulSoup(html, 'html.parser').select('script[type="application/ld+json"]')]


if __name__ == '__main__':
    unittest.main()
