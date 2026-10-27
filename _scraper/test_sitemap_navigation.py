import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from catalog_seo import static_page_urls, write_sitemaps
import xml.etree.ElementTree as ET

class SitemapNavigationTests(unittest.TestCase):
    def test_future_public_menu_is_discovered_without_listing_its_name(self):
        with TemporaryDirectory(dir=Path(__file__).parent/'tests') as work:
            root=Path(work)
            for name, robots, canonical in [('future-guide.html','index,follow','future-guide.html'),('account.html','noindex','account.html'),('rental.html','index','rental.html'),('gift-item.html','index','gift-item.html'),('alias.html','index','future-guide.html')]:
                (root/name).write_text(f'<meta name="robots" content="{robots}"><link rel="canonical" href="https://shop.nadaun.co/{canonical}">')
            self.assertEqual(static_page_urls(root),['https://shop.nadaun.co/future-guide.html'])

    def test_pages_products_and_images_keep_distinct_namespaces(self):
        with TemporaryDirectory(dir=Path(__file__).parent/'tests') as work:
            root=Path(work)
            (root/'index.html').write_text('<link rel="canonical" href="https://shop.nadaun.co/">')
            (root/'gift-sitemap.xml').write_text('<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><sitemap><loc>https://shop.nadaun.co/gift-sitemap-1.xml</loc></sitemap></sitemapindex>')
            self.assertEqual(write_sitemaps(root,{'brands':[{'id':'sample'}],'products':[{'id':'a','image':'/photo.jpg'}]}),3)
            tree=ET.fromstring((root/'catalog-sitemap.xml').read_text())
            self.assertEqual(len(tree.findall('{http://www.sitemaps.org/schemas/sitemap/0.9}url')),3)
            self.assertEqual(len(tree.findall('.//{http://www.google.com/schemas/sitemap-image/1.1}loc')),1)

if __name__=='__main__':unittest.main()
