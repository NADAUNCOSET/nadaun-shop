from copy import deepcopy
import unittest
from unittest.mock import patch

from ldnet_identity import classify, resolve, revision, REVIEWED_PRODUCTS
import cafe24_publication as publication
import cafe24_worker as worker
import test_cafe24_publication as fixtures


class IdentityTests(unittest.TestCase):
    def product(self, name, **extra):
        return dict(id='ldnet-1', name=name, brand='(주)엘디네트웍스',
                    brand_category_ids=['534', '50', '540'], **extra)

    def test_explicit_iriver_anyport_and_compatible_device_names(self):
        for name, expected in [
            ('아이리버 Air Lift 50 무선 마우스', 'IRIVER'),
            ('애니포트 AP-KMP500 키보드 마우스 세트', '애니포트'),
            ('[AP-XLR01F] ANYPORT XLR 케이블', '애니포트'),
            ('엘디엘마운트 APL-44PRO LG삼성호환 TV브라켓', '엘디엘마운트'),
            ('E2000/APC 1코어 싱글 광케이블', '기타 브랜드'),
            ('LG 삼성 호환 모니터 거치대', '기타 브랜드'),
        ]:
            with self.subTest(name=name):
                self.assertEqual(resolve(self.product(name), {})[0], expected)

    def test_title_brand_outranks_distributor_brand_menu(self):
        nodes = {'585': {'id': '585', 'parent_id': '581', 'name': 'NETMATE'}}
        p = self.product('MOXA PCI 8포트 CP-118U')
        p['brand_category_ids'] = ['585']
        self.assertEqual(resolve(p, nodes)[0], 'MOXA')
        nodes['582'] = {'id': '582', 'parent_id': '581', 'name': 'NEXT'}
        p['brand_category_ids'] = ['582']; p['name'] = '유가단 5522U3-10G USB 허브'
        self.assertEqual(resolve(p, nodes), ('NEXT', {'method': 'source-brand-category', 'category_id': '582'}))

    def test_supplier_is_preserved_separately_without_becoming_a_brand(self):
        p = self.product('아이리버 무소음 마우스'); classify(p, {})
        self.assertEqual(p['source_manufacturer'], '(주)엘디네트웍스')
        self.assertEqual(p['brand'], 'IRIVER')
        before = deepcopy(p); classify(p, {}); self.assertEqual(before, p)
        self.assertEqual(resolve(self.product('이름 없는 연결 부품'), {})[0], '기타 브랜드')

    def test_banner_alone_does_not_assign_anyport(self):
        p = self.product('연결 부품', images={'detail': ['https://image.fzonesports.co.kr/ANYPORT/topbanner.jpg']})
        self.assertEqual(resolve(p, {})[0], '기타 브랜드')
        p['images']['detail'].append('https://image.fzonesports.co.kr/ANYPORT/TPP-AOC_1.jpg')
        self.assertEqual(resolve(p, {})[0], '애니포트')

    def test_reviewed_product_logos_require_exact_id_title_and_image(self):
        for pid,rule in REVIEWED_PRODUCTS.items():
            p=self.product(rule['name'],images={'detail':[rule['image']]});p['id']=pid
            self.assertEqual(resolve(p,{})[0],rule['brand'])
            self.assertEqual(resolve({**p,'id':'ldnet-unknown'},{})[0],'기타 브랜드')
            with self.assertRaises(ValueError):resolve({**p,'name':'다른 연결부품'},{})
            with self.assertRaises(ValueError):resolve({**p,'images':{'detail':[]}},{})

    def test_normalization_migrates_brand_paths_without_changing_offer_fields(self):
        raw = fixtures.PublicationTests().ldnet_candidate()
        p = raw['products']['ldnet-10']
        p.update(name='아이리버 Air Light Fit 마우스', brand='(주)엘디네트웍스', price=50000,
                 options=[{'sku': 'original', 'price': 50000}], supplier_status='available')
        result = publication.prepare(raw); fixed = result['products']['ldnet-10']
        self.assertEqual(fixed['brand'], 'IRIVER')
        self.assertEqual(fixed['brand_category_ids'], ['iriver:534', 'iriver:46', 'iriver:117'])
        for field in ('id', 'price', 'options', 'supplier_status'):
            self.assertEqual(fixed[field], p[field])
        self.assertEqual(result['original_categories'], raw['categories'])
        self.assertEqual(publication.prepare(result), result)
        self.assertEqual(result['brand_classification_revision'], revision())

    def test_worker_republishes_when_classification_rules_change(self):
        raw = fixtures.PublicationTests().ldnet_candidate()
        with patch.object(worker, 'read') as read, patch.object(worker, 'publish', return_value='republished') as publish, \
                patch.object(worker, 'run_lock'), patch.object(worker, 'parser_revision', return_value='parser'), \
                patch('brand_source_policy.policy_fingerprint', return_value='policy'):
            def response(path):
                name = path.name
                if name == 'catalogue-candidate.json': return raw
                if name == 'published.json': return {'candidate_sha256': publication.digest(raw), 'policy_sha256': 'policy'}
                return {}
            read.side_effect = response
            self.assertEqual(worker.work('ldnet'), 'republished')
            publish.assert_called_once_with(raw)


if __name__ == '__main__':
    unittest.main()
