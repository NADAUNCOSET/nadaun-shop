from copy import deepcopy
import unittest

from hipixel_source import category_payload,category_brand,navigation_role
from sync_cafe24_partners import source_category_tree
from catalog_navigation import arrange_categories
from brand_category_policy import choose_navigation
from cafe24_publication import prepare,validate_candidate
from catalog_dedup import name_key,model_key,conflict
from hipixel_source import product_types,REVIEWED_TYPES,apply_review,blackmagic_type,add_reviewed_navigation
import base64
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from PIL import Image
from inline_product_images import materialize


class HiPixelTests(unittest.TestCase):
    def payload(self):
        return [{'cate_no':n,'name':name,'parent_cate_no':parent} for n,name,parent in [
            (123,'베스트',1),(24,'Blackmagic Design',1),(29,'스위처',24),
            (45,'ATEM Mini',29),(90,'개인결제',1),(901,'개인결제 하위',90),(25,'티브이로직',1)]]

    def test_personal_payment_is_excluded_without_losing_real_categories(self):
        raw=self.payload();before=deepcopy(raw)
        result=category_payload(raw)
        self.assertEqual([r['cate_no'] for r in result],[123,24,29,45,25])
        self.assertEqual(raw,before)
        nodes=source_category_tree('hipixel',raw)
        self.assertEqual(nodes['45']['parent_id'],'29')
        self.assertLess(nodes['29']['position'],nodes['45']['position'])
        self.assertTrue(nodes['1']['synthetic'])

    def test_brand_is_evidenced_by_ancestry_not_merchant_schema_label(self):
        nodes=source_category_tree('hipixel',self.payload())
        self.assertEqual(category_brand(['123','45'],nodes),'Blackmagic Design')
        self.assertEqual(category_brand(['123'],nodes),'')
        with self.assertRaises(ValueError):category_brand(['24','25'],nodes)

    def test_normalization_preserves_order_and_detects_later_corruption(self):
        nodes=source_category_tree('hipixel',self.payload())
        cats=['24','29','45','123']
        raw={'source':'hipixel','complete':True,'product_count':1,'collected_at':'2026-10-18',
            'categories':list(nodes.values()),'coverage':[
                {'id':cid,'expected':int(cid in cats or cid=='1'),'unique':int(cid in cats or cid=='1'),
                 'pages':0 if cid=='1' else 1,'derived_union':cid=='1'} for cid in nodes],
            'products':{'hipixel-2':{'id':'hipixel-2','source':'hipixel','source_id':'2','kind':'purchase',
                'name':'ATEM Mini','brand':'Blackmagic Design','brand_category_ids':cats,
                'detail_status':'verified','detail_checked_at':'2026-10-18'}}}
        prepared=prepare(raw)
        node=next(c for c in prepared['categories'] if c['source_category_id']=='29')
        self.assertEqual(node['position'],nodes['29']['position'])
        self.assertEqual(node['navigation_role'],'category')
        node['position']=999
        with self.assertRaises(ValueError):validate_candidate(prepared)

    def test_collections_do_not_become_brand_product_categories(self):
        cats={f'hipixel:{cid}':{'id':f'hipixel:{cid}','name':n,'parent_id':None,
            'brand_id':'blackmagic','navigation_role':navigation_role(cid)} for cid,n in [('24','Blackmagic'),('123','베스트')]}
        products=[{'id':'p1','kind':'purchase','brand_id':'blackmagic','category_ids':list(cats)}]
        choose_navigation(products,cats,{'blackmagic':{'name':'Blackmagic'}})
        self.assertEqual(products[0]['navigation_category_ids'],['hipixel:24'])

    def test_sibling_source_order_and_parent_child_location_are_stable(self):
        cats={cid:{'id':cid,'name':cid,'brand_id':'blackmagic','parent_id':parent,'position':pos} for cid,parent,pos in [
            ('other:1',None,0),('hipixel:31','hipixel:24',3),('hipixel:24',None,2),
            ('hipixel:29','hipixel:24',1),('hipixel:45','hipixel:29',8)]}
        before=deepcopy(cats)
        arranged=arrange_categories(cats,[{'id':'blackmagic'}],{'brands':{'blackmagic':{'preferred_source':'hipixel'}}})
        self.assertEqual(list(arranged),['hipixel:24','hipixel:29','hipixel:45','hipixel:31','other:1'])
        self.assertEqual(cats,before)
        self.assertEqual(arrange_categories(arranged,[{'id':'blackmagic'}],{'brands':{'blackmagic':{'preferred_source':'hipixel'}}}),arranged)
        cats['hipixel:24']['parent_id']='hipixel:45'
        with self.assertRaises(ValueError):arrange_categories(cats,[{'id':'blackmagic'}],{})

    def test_marketing_labels_do_not_hide_identical_models_but_specs_and_licences_remain(self):
        def p(name):return {'id':'hipixel-1','brand_id':'blackmagic','kind':'purchase','name':name}
        self.assertEqual(name_key(p('[신제품] ATEM Mini')),name_key(p('ATEM Mini')))
        self.assertEqual(name_key(p('Video Assist 5" 3G')),name_key(p('Video Assist 5 3G')))
        for a,b in [('ATEM Television Studio 4K8','ATEM Television Studio 4K8 2TB'),
                    ('PYXIS 6K PL','PYXIS 6K EF'),('Speed Editor','Speed Editor [인증코드 미포함]')]:
            self.assertNotEqual(name_key(p(a)),name_key(p(b)))

    def test_teris_model_suffixes_and_compatible_accessories_never_collapse(self):
        def key(name):return model_key({'kind':'purchase','brand_id':'teris','name':name})
        self.assertEqual(key('TERIS TSN6AL PLUS'),key('TERIS 삼각대 헤드 키트 TSN6AL PLUS'))
        self.assertNotEqual(key('TERIS TS100CF'),key('TERIS TS100CF-Q'))
        self.assertNotEqual(key('TERIS TS350CF'),key('TERIS TS350CF CINE'))
        self.assertNotEqual(key('TERIS TS-TRAVEL 7'),key('TERIS TS-TRAVEL 7 PRO'))
        self.assertIsNone(key('TERIS TS-RH100W 전용 바퀴 세트 TS-WS100'))

    def test_tvlogic_generation_and_accessories_remain_separate(self):
        def key(name):return model_key({'kind':'purchase','brand_id':'tvlogic','name':name})
        self.assertEqual(key('TVlogic LUM-242H'),key('LUM-242H'))
        self.assertNotEqual(key('LUM-430M2'),key('LUM-430M3'))
        self.assertIsNone(key('TVLogic F-10H 필드모니터 액세서리 모음'))

    def test_source_accessories_are_classified_by_actual_purpose_and_title_change_stops_build(self):
        for sid,target in [('452','video-streaming'),('451','electronic-viewfinder'),('311','kpp:0330'),('273','equipment-bag'),('18','ssd')]:
            p={'id':'hipixel-'+sid,'name':REVIEWED_TYPES[sid]['expected_name']}
            self.assertEqual(product_types(p,{}),[target])
            with self.assertRaises(ValueError):product_types({**p,'name':p['name']+' new variant'}, {})
        self.assertEqual(product_types({'id':'hipixel-273','name':'TERIS SB-135'},{}),['equipment-bag'])

    def test_price_inquiry_is_preserved_without_inventing_a_different_model(self):
        a={'id':'hipixel-1','brand_id':'tvlogic','kind':'purchase','name':'LUM-242H','price_inquiry':True,'detail_status':'verified'}
        b={**a,'id':'smartstore-2','price_inquiry':False}
        details={a['id']:{'options_require_confirmation':True}}
        self.assertIsNone(conflict(a,b,details))
        self.assertTrue(details[a['id']]['options_require_confirmation'])
        details[a['id']]['option_groups']=[{'name':'크기'}]
        self.assertEqual(conflict(a,b,details),'unverified_option_equivalence')

    def test_unstated_manufacturer_and_unselectable_lengths_are_honest(self):
        record={'id':'hipixel-361','source_id':'361','name':REVIEWED_TYPES['361']['expected_name'],
            'brand_category_ids':['57','86'],'description_text':'15cm와 30cm 길이 선택',
            'content_issues':['brand_membership_requires_review']}
        schema={'brand':{'name':'Blackmagicdesign_하이픽셀플러스'}}
        apply_review(record,schema)
        self.assertEqual(record['brand'],'브랜드 미표기')
        self.assertTrue(record['options_require_confirmation'])
        self.assertEqual(record['detail_status'],'verified')
        with self.assertRaises(ValueError):apply_review(record,{'brand':{'name':'A newly stated manufacturer'}})

    def test_reviewed_shop_leaves_keep_original_source_membership(self):
        parent='hipixel:b:unbranded:57'
        cats={parent:{'id':parent,'name':'기타장비'}}
        p={'id':'hipixel-359','source_id':'359','source':'hipixel','brand_id':'unbranded',
           'name':REVIEWED_TYPES['359']['expected_name'],'category_ids':[parent]}
        added=add_reviewed_navigation(p,cats)
        self.assertEqual(p['category_ids'],[parent,*added])
        self.assertEqual(cats[added[0]]['navigation_role'],'reviewed-category')
        self.assertEqual(cats[added[0]]['parent_id'],parent)

    def test_manufacturer_families_do_not_match_printer_or_studio_rental_words(self):
        for name,target in [('DeckLink 8K Pro','video-capture'),('UltraStudio 4K Mini','video-capture'),
            ('URSA Cine Mount B4','kpp:0330'),('URSA Live Encoder','video-streaming')]:
            self.assertEqual(blackmagic_type(name),target)
        for sid in ('224','225'):
            self.assertEqual(product_types({'id':'hipixel-'+sid,'name':REVIEWED_TYPES[sid]['expected_name']},{}),['monitor'])

    def test_inline_raster_detail_is_preserved_but_placeholder_or_script_is_rejected(self):
        buf=BytesIO();Image.new('RGB',(64,128),'white').save(buf,format='PNG')
        raw=buf.getvalue();uri='data:image/png;base64,'+base64.b64encode(raw).decode()
        with TemporaryDirectory() as folder:
            url=materialize(uri,'hipixel',root=folder)
            target=Path(folder)/url.removeprefix('https://shop.nadaun.co/')
            self.assertEqual(target.read_bytes(),raw)
            self.assertEqual(materialize(uri,'hipixel',root=folder),url)
            for bad in ['data:image/svg+xml;base64,PHN2Zz4=',uri.replace('png','jpeg'),'data:image/png;base64,YWJj']:
                with self.assertRaises((ValueError,OSError)):materialize(bad,'hipixel',root=folder)

    def test_missing_supplier_description_uses_labelled_manufacturer_summary_only(self):
        p={'source_id':'249','name':'TERIS TS50CF','brand':'TERIS','brand_category_ids':['57','80','28'],
           'content_issues':['description_missing'],'price':714000,'status':'inquiry'}
        apply_review(p,{})
        self.assertEqual(p['price'],714000)
        self.assertEqual(p['status'],'inquiry')
        self.assertIn('2021',p['description_notice'])
        self.assertEqual(p['description_evidence']['source'],'manufacturer_brochure_summary')
        with self.assertRaises(ValueError):apply_review({**p,'name':'TERIS TS50AL','content_issues':['description_missing']},{})


if __name__=='__main__':unittest.main()
