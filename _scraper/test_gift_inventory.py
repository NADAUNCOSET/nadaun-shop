from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from sync_gift_inventory import Inventory, Source, document, parse_page


def page_html(ids, total=31, page=1, last=2):
    rows=''.join(f'<li><a class="link" href="../shop/detail.php?code={pid}&amp;cid=109"><img class="thum" src="https://example.test/{pid}.jpg" alt="상품"><span class="gno"><span>{pid}</span></span><span class="title">같은 상품명</span><span class="price">4,500 원</span></a></li>' for pid in ids)
    return f'<div class="choiceList"><a href="detail.php?code=999999">추천 상품</a></div><div id="allview_list"><h3><font>생활용품</font><span>카테고리 내 <font>{total}</font>개의 상품이 있습니다.</span></h3><div class="paging_new"><a class="std">{page}</a><a href="?p={last}">마지막</a></div><div class="productList"><ul>{rows}</ul></div></div>'


class ParserTest(unittest.TestCase):
    def test_last_page_not_just_visible_page_window(self):
        result=parse_page(document(page_html(range(1,31),26165,1,873)),'1',1)
        self.assertEqual(result['last_page'],873)
        self.assertEqual(result['total'],26165)
        self.assertEqual(len(result['rows']),30)
        self.assertNotIn('999999',[r['product_id'] for r in result['rows']])
        self.assertEqual(result['rows'][0]['listed_price'],4500)

    def test_wrong_page_count_and_id_mismatch_stop_scan(self):
        for text in [page_html(range(1,30)), page_html(range(1,31),page=2),
                     page_html(range(1,31)).replace('code=1&amp;','code=999&amp;')]:
            with self.assertRaises(ValueError):parse_page(document(text),'1',1)


class InventoryTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.inventory=Inventory(Path(self.temp.name))

    def tearDown(self):
        self.inventory.db.close(); self.temp.cleanup()

    def test_resume_is_exact_and_only_verified_root_becomes_complete(self):
        first=parse_page(document(page_html(range(1,31))),'1',1)
        self.inventory.save_page(first,1)
        self.assertFalse(self.inventory.status()['inventory_complete'])
        self.inventory.db.close()
        self.inventory=Inventory(Path(self.temp.name))
        last=parse_page(document(page_html([31],page=2)),'1',2)
        self.inventory.save_page(last,2)
        self.assertFalse(self.inventory.status()['inventory_complete'])
        self.inventory.verify_root(first)
        self.assertFalse(self.inventory.status()['inventory_complete'])
        self.inventory.finalize(['1'])
        self.assertTrue(self.inventory.status()['inventory_complete'])
        self.assertFalse(self.inventory.status()['suppliers_complete'])
        self.assertFalse(self.inventory.status()['published'])
        self.assertEqual(self.inventory.status()['unique_products'],31)

    def test_duplicate_page_preserves_cursor_and_previous_inventory(self):
        self.inventory.save_page(parse_page(document(page_html(range(1,31))),'1',1),1)
        duplicate=parse_page(document(page_html([1],page=2)),'1',2)
        with self.assertRaises(ValueError):self.inventory.save_page(duplicate,2)
        result=self.inventory.status()
        self.assertEqual(result['unique_products'],30)
        self.assertEqual(result['roots'][0]['next_page'],2)

    def test_count_change_never_marks_missing_products_deleted(self):
        self.inventory.save_page(parse_page(document(page_html(range(1,31))),'1',1),1)
        changed=parse_page(document(page_html([31,32],total=32,page=2)),'1',2)
        with self.assertRaises(ValueError):self.inventory.save_page(changed,2)
        self.assertEqual(self.inventory.status()['unique_products'],30)

    def test_same_product_in_two_categories_is_one_product_with_two_memberships(self):
        for cid in ('1','2'):
            data=parse_page(document(page_html([1],total=1,last=1)),cid,1)
            self.inventory.save_page(data,1)
            self.inventory.verify_root(data)
        self.assertEqual(self.inventory.status()['unique_products'],1)
        self.assertEqual(self.inventory.status()['expected_category_memberships'],2)

    def test_changed_first_page_blocks_completion(self):
        first=parse_page(document(page_html([1],total=1,last=1)),'1',1)
        self.inventory.save_page(first,1)
        changed=parse_page(document(page_html([2],total=1,last=1)),'1',1)
        with self.assertRaises(ValueError):self.inventory.verify_root(changed)
        self.assertFalse(self.inventory.status()['inventory_complete'])

    def test_final_navigation_failure_cannot_claim_a_complete_inventory(self):
        first=parse_page(document(page_html([1],total=1,last=1)),'1',1)
        self.inventory.save_page(first,1)
        self.inventory.verify_root(first)
        with self.assertRaises(ValueError):self.inventory.finalize(['1','2'])
        self.assertFalse(self.inventory.status()['inventory_complete'])

    def test_rate_limit_stops_subsequent_requests_and_preserves_cooldown(self):
        source=Source(Path(self.temp.name))
        response=SimpleNamespace(status_code=429,headers={'Retry-After':'7200'},text='',content=b'blocked')
        with patch.object(source.session,'get',return_value=response) as get, patch('sync_gift_inventory.time.sleep'):
            with self.assertRaises(RuntimeError):source.get('https://www.nadaun-gift.com/')
            with self.assertRaises(RuntimeError):source.get('https://www.nadaun-gift.com/')
            self.assertEqual(get.call_count,1)


if __name__=='__main__':unittest.main()
