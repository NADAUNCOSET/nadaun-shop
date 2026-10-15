import json,unittest
from pathlib import Path
from urllib.parse import urlsplit,parse_qs
from bs4 import BeautifulSoup
ROOT=Path(__file__).resolve().parents[1]
class EquipmentGuide(unittest.TestCase):
 def test_equipment_guide_links_only_existing_categories_with_matching_inventory(self):
  page=BeautifulSoup((ROOT/'_scraper/shop_templates/equipment-guide.html').read_text(),'html.parser')
  catalog=json.loads((ROOT/'data/catalog/catalog.json').read_text());ids={c['id'] for c in catalog['categories']}
  self.assertEqual(len(page.select('h1')),1)
  self.assertIn('시네마카메라',page.h1.get_text());self.assertIn('2주(14일)',page.get_text())
  for link in page.select('a[href]'):
   query=parse_qs(urlsplit(link['href']).query)
   if 'type' in query:
    category=query['type'][0];kind=query['kind'][0]
    self.assertIn(category,ids)
    self.assertTrue(any(p['kind']==kind and category in p['type_ids'] for p in catalog['products']),category)
 def test_guides_have_a_crawlable_path_and_no_false_readiness_claim(self):
  footer=BeautifulSoup((ROOT/'_scraper/shop_templates/page.html').read_text(),'html.parser')
  for filename in ['equipment-guide.html','billing-guide.html']:
   self.assertTrue(footer.select_one('a[href="/'+filename+'"]'))
  billing=BeautifulSoup((ROOT/'_scraper/shop_templates/billing-guide.html').read_text(),'html.parser')
  self.assertEqual(len(billing.select('h1')),1);self.assertIn('현금영수증',billing.get_text())
  self.assertIn('연결을 준비',billing.get_text());self.assertIn('주문한 브라우저',billing.get_text())
if __name__=='__main__':unittest.main()
