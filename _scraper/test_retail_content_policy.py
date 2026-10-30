import copy,json,unittest
from pathlib import Path
from retail_content_policy import sanitize_detail,assert_clean,load_rules

class RetailContentPolicy(unittest.TestCase):
    def test_datacolor_trade_in_banner_is_removed_and_product_instructions_remain(self):
        banner='https://mustcolor2.openhost.cafe24.com/event/mustcolor/brand_notice/datacolor_notice_partners.jpg'
        instructions='https://mustcolor2.openhost.cafe24.com/product/datacolor/SpyderShelf_detail.jpg'
        original={'images':{'detail':[banner,instructions]},'description_text':'스파이더 셸프 장착 방법'}
        result,audit=sanitize_detail({'id':'saeki-PD00023673','kind':'purchase'},original)
        self.assertEqual(result['images']['detail'],[instructions])
        self.assertEqual(result['description_text'],original['description_text'])
        self.assertIn(banner,original['images']['detail'])
        self.assertEqual(audit[0]['rule'],'datacolor-external-trade-in-promotion')

    def test_dealer_module_removed_across_sources_without_changing_raw_or_product_photos(self):
        urls=[row['url'] for row in load_rules()[0].values()]
        original={'images':{'main':['https://maker.example/camera.jpg'],'detail':[urls[0],'https://maker.example/specs.jpg',urls[1]]},
                  'description_text':'제조사 Nikon. 센서 45MP. 안전을 위해 설명서를 읽으세요.'}
        saved=copy.deepcopy(original)
        detail,audit=sanitize_detail({'id':'smartstore-1','kind':'purchase'},original)
        self.assertEqual(original,saved)
        self.assertEqual(detail['images']['detail'],['https://maker.example/specs.jpg'])
        self.assertEqual(detail['images']['main'],saved['images']['main'])
        self.assertEqual(detail['description_text'],saved['description_text'])
        self.assertEqual(len(audit),2)
        assert_clean({'id':'smartstore-1','kind':'purchase'},detail)
        with self.assertRaises(ValueError):assert_clean({'id':'smartstore-1','kind':'purchase'},original)

    def test_sales_contact_removed_but_firmware_and_technical_content_preserved(self):
        original={'description_text':'6K 24p 촬영. 제품 상담 : 02-2265-0032, 010-6280-3541, sjh@avx.co.kr Firmware 링크 : https://av.jpn.support.panasonic.com/support/global/cs/dsc/download/index4.html'}
        result,_=sanitize_detail({'id':'avx-841','kind':'purchase'},original)
        self.assertNotIn('sjh@avx',result['description_text'])
        self.assertIn('6K 24p',result['description_text'])
        self.assertIn('https://av.jpn.support.panasonic.com',result['description_text'])
        self.assertNotIn('제품 상담',result['description_text'])

    def test_manufacturer_warranty_service_and_own_contacts_are_not_blanket_deleted(self):
        value='품질보증기준 구입일부터 1년. A/S 책임자와 전화번호 KCR : 02-753-1341. 수입자 썬포토. https://www.blackmagicdesign.com/kr/support/faq/59028 안전: 배터리를 분해하지 마십시오. 나다운 문의 0507-1394-6231. 레인보우베네 070-8830-4568'
        result,audit=sanitize_detail({'id':'sunphoto-1','kind':'purchase'},{'description_text':value})
        self.assertEqual(value,result['description_text']);self.assertFalse(audit)

    def test_repair_invitation_does_not_consume_following_product_specs(self):
        value='Sachtler ACE 플레이트. 온앤오프미디어 에서는 셔틀러 수리도 겸하고 있으니, 직접수리가 어려우신경우 고객전화 (02-337-0100) 으로 문의 주시면 친절히 상담해 드리겠습니다. 셔틀러, 소니의 다른제품 수리/판매도 가능합니다 ^^ 플레이트 결합시 나사가 분리되지 않습니다.'
        result,_=sanitize_detail({'id':'onnoff-191','kind':'purchase'},{'description_text':value})
        self.assertNotIn('온앤오프',result['description_text']);self.assertNotIn('02-337',result['description_text'])
        self.assertIn('플레이트 결합시 나사가 분리되지 않습니다.',result['description_text'])

    def test_unreviewed_product_images_and_manufacturer_logos_remain(self):
        detail={'images':{'main':['https://sunphoto.kr/product/camera.jpg'],'detail':['https://sunphoto.co.kr/spec/tamron/tamron_warranty.jpg','https://maker.example/logo.png']}}
        result,audit=sanitize_detail({'id':'sunphoto-1','kind':'purchase'},detail)
        self.assertEqual(detail,result);self.assertFalse(audit)

    def test_rental_original_is_preserved(self):
        value={'description_text':'자체 대여 원장','images':{'detail':[next(iter(load_rules()[0].values()))['url']]}}
        result,audit=sanitize_detail({'id':'rental-1','kind':'rental'},value)
        self.assertEqual(result,value);self.assertFalse(audit)

    def test_dealer_module_cannot_become_the_only_product_photo(self):
        url=next(iter(load_rules()[0].values()))['url']
        with self.assertRaises(ValueError):sanitize_detail({'id':'source-1','kind':'purchase'},{'images':{'main':[url],'thumb':url}})

    def test_sanitation_is_idempotent(self):
        value={'description_text':'문의 : 02-591-2593 본 상품은 예약판매상품 입니다.'}
        once,audit=sanitize_detail({'id':'clmedia-1','kind':'purchase'},value)
        twice,again=sanitize_detail({'id':'clmedia-1','kind':'purchase'},once)
        self.assertTrue(audit);self.assertFalse(again);self.assertEqual(once,twice)
