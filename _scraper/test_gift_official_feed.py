import unittest
from gift_official_feed import FIELDS, parse_feed


def feed(*rows):
    return ('\t'.join(FIELDS) + '\n' + '\n'.join('\t'.join(row) for row in rows)).encode('euc-kr')


def product():
    return ['70002', '[10개 세트] 어깨띠', '45760',
            'https://nadaun-gift.com/new/shop/detail.php?code=70002&mode=naver_dburl',
            'https://cloudfront.imggift.com/shop_images/a.jpg', '어깨띠', '신상품',
            '도매', '제조사표기', '', '', 'set', '4400', 'N']


class OfficialFeedTests(unittest.TestCase):
    def test_price_quantity_and_manufacturer_remain_source_values(self):
        rows, errors = parse_feed(feed(product()))
        self.assertFalse(errors)
        self.assertEqual(rows[0]['price_pc'], '45760')
        self.assertEqual(rows[0]['minimum_purchase_quantity'], 'set')
        self.assertEqual(rows[0]['maker'], '제조사표기')
        self.assertNotIn('supplier_id', rows[0])

    def test_extra_tab_is_quarantined_without_shifting_fields(self):
        malformed = product(); malformed.insert(2, 'unintended column')
        rows, errors = parse_feed(feed(product(), malformed))
        self.assertEqual(len(rows), 1)
        self.assertEqual(errors[0]['reason'], 'column_count')
        self.assertEqual(errors[0]['raw_fields'], malformed)

    def test_duplicate_id_stops_import(self):
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            parse_feed(feed(product(), product()))

    def test_wrong_product_url_is_quarantined(self):
        bad = product(); bad[0] = '70003'
        rows, errors = parse_feed(feed(product(), bad))
        self.assertEqual(len(rows), 1)
        self.assertEqual(errors[0]['reason'], 'product_url_identity_mismatch')

    def test_html_response_rejected(self):
        with self.assertRaises(ValueError):
            parse_feed(b'<html>Access denied</html>')


if __name__ == '__main__':
    unittest.main()
