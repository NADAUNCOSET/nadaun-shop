"""Captured storefront regressions for the owner-scoped supplier expansion."""
import json,unittest,tempfile
from pathlib import Path
from unittest.mock import patch
import sync_digitalcp_catalog as cp
import sync_sunphoto_catalog as sp
import inline_product_images
import brand_source_policy as policy

FIXTURES=Path(__file__).parent/'fixtures/new-suppliers'

class SupplierRegressionTests(unittest.TestCase):
    def test_scoped_sunphoto_import_does_not_change_existing_cafe24_partner_scope(self):
        self.assertNotIn('sunphoto',sp.cafe.SITES)
        import build_catalog
        self.assertNotIn('sunphoto',build_catalog.CAFE24_SOURCES)
    def digitalcp(self,sid):
        return (FIXTURES/('digitalcp-'+sid+'.html')).read_bytes(),json.loads((FIXTURES/('digitalcp-'+sid+'.json')).read_text())

    def test_visible_inquiry_phone_is_never_treated_as_a_won_price(self):
        p=cp.doc('<span class="pick_list_num"><strong>1</strong></span><div class="goods_list"><div class="item_cont"><div class="item_tit_box"><a href="goods_view.php?goodsNo=123"><span class="item_name">카메라</span></a></div><div class="item_photo_box"><img src="/camera.jpg"></div><span class="item_brand">Nikon</span><span class="item_price">문의 (02-2012-2041)</span></div></div>')
        total,rows=cp.listing(p,'023');self.assertEqual(total,1);self.assertIsNone(rows['123']['sale_price']);self.assertTrue(rows['123']['listed_inquiry'])

    def test_current_selling_price_is_retained_when_source_reference_price_is_lower(self):
        raw,listed=self.digitalcp('584');p=cp.parse_detail(raw,'584',listed)
        self.assertEqual(p['sale_price'],6498000);self.assertEqual(p['price'],6463000);self.assertTrue(p['source_reference_price_below_selling'])
        from reviewed_supplier_sources import retail_product
        self.assertEqual(retail_product(p)['price'],6498000)

    def test_actual_source_placeholder_is_explicit_without_fabricated_product_image(self):
        for sid in ['620','718']:
            raw,listed=self.digitalcp(sid);p=cp.parse_detail(raw,sid,listed)
            self.assertTrue(p['source_image_missing']);self.assertEqual(p['images']['main'],[listed['image']]);self.assertIn('이미지',p['description_notice'])

    def test_own_manufacturer_brand_code_excludes_even_without_visible_brand(self):
        raw,listed=self.digitalcp('584')
        for code in cp.EXCLUDED_CODES:
            changed=raw.replace(b'value="001"',('value="'+code+'"').encode())
            with self.assertRaises(cp.OwnerExcluded):cp.parse_detail(changed,'584',dict(listed,brand=''))
        # A Nikon product with a compatible/excluded brand in its title remains Nikon.
        self.assertFalse(cp.excluded('Nikon'));self.assertTrue(cp.excluded('스몰리그'))

    def test_sunphoto_original_inline_raster_is_preserved_as_immutable_file(self):
        raw=(FIXTURES/'sunphoto-2171.html').read_bytes()
        product={'id':'sunphoto-2171','source':'sunphoto','source_id':'2171','source_url':'https://sunphoto.kr/product/detail.html?product_no=2171','kind':'purchase','brand':'Voigtlander'}
        with tempfile.TemporaryDirectory() as folder,patch.object(inline_product_images,'ROOT',Path(folder)):
            p=sp.reviewed_detail(raw,product,'Voigtlander')
            self.assertEqual(p['detail_status'],'verified');self.assertEqual(p['supplier_status'],'available')
            self.assertEqual(len(p['images']['detail']),1);self.assertTrue(p['images']['detail'][0].startswith(inline_product_images.PUBLIC+inline_product_images.PREFIX+'sunphoto/'))
            self.assertEqual(len(list(Path(folder).rglob('*.png'))),1)

    def test_genuinely_empty_description_keeps_observed_basic_facts_and_notice(self):
        raw=(FIXTURES/'sunphoto-1178.html').read_bytes();product={'id':'sunphoto-1178','source':'sunphoto','source_id':'1178','kind':'purchase','brand':'Voigtlander'}
        p=sp.reviewed_detail(raw,product,'Voigtlander')
        self.assertTrue(p['source_description_empty']);self.assertEqual(p['supplier_status'],'soldout');self.assertIn('원산지: 아시아 일본',p['description_text'])

    def test_global_sales_exclusion_and_pending_source_preserve_rentals_and_other_sources(self):
        choices=policy.selections()
        for source in ['smartstore','digitalcp','avx']:
            self.assertFalse(policy.purchase_source_allowed({'source':source,'brand':'GoPro','kind':'purchase'},choices))
            self.assertTrue(policy.purchase_source_allowed({'source':source,'brand':'GoPro','kind':'rental'},choices))
        self.assertFalse(policy.purchase_source_allowed({'source':'digitalcp','brand':'NovaChips','kind':'purchase'},choices))
        self.assertTrue(policy.purchase_source_allowed({'source':'saeki','brand':'NovaChips','kind':'purchase'},choices))
        self.assertTrue(policy.purchase_source_allowed({'source':'smartstore','brand':'NiSi','kind':'purchase'},choices))

if __name__=='__main__':unittest.main()
