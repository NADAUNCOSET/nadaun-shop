import unittest
from camera_compatibility import associate,title_models,search_terms

class CameraCompatibility(unittest.TestCase):
    def product(self,name,brand='smallrig',**extra):return {'id':'source-1','name':name,'kind':'purchase','brand_id':brand,'type_ids':['type:kpp:0620'],'offers':[{'url':'https://supplier.example/item/1'}],**extra}
    def ids(self,name,brand='smallrig'):return [m['id'] for m in title_models(self.product(name,brand))]
    def test_exact_nikon_zr_and_ta_zr_audio_are_different(self):
        self.assertEqual(self.ids('스몰리그 5467 니콘 ZR 카메라 케이지'),['nikon-zr'])
        self.assertEqual(self.ids('틸타 좀비 리그 붐풀 서포트 TA-ZR 마이크 오디오 거치대'),[])
    def test_sony_generations_and_aliases_do_not_cross(self):
        self.assertEqual(self.ids('스몰리그 SONY A7 IV 케이지'),['sony-a7-iv'])
        self.assertEqual(self.ids('틸타 소니 A7M4 케이지'),['sony-a7-iv'])
        self.assertEqual(self.ids('Sony A7S III 케이지'),['sony-a7s-iii'])
        self.assertEqual(self.ids('소니 A7S3 케이지'),['sony-a7s-iii'])
        self.assertEqual(self.ids('FX30 케이지'),['sony-fx30'])
        self.assertEqual(self.ids('FX3A 케이지'),['sony-fx3a'])
        self.assertEqual(self.ids('RICOH GR IV HDF 카메라','ricoh'),['ricoh-gr-iv-hdf'])
    def test_overlapping_canon_and_panasonic_models_keep_only_specific_generation(self):
        self.assertEqual(self.ids('Canon EOS R5 II 케이지'),['canon-eos-r5-ii'])
        self.assertEqual(self.ids('니콘 Z6 III 케이지'),['nikon-z6-iii'])
        self.assertEqual(self.ids('Panasonic S5 IIX 케이지'),['panasonic-lumix-s5-iix'])
    def test_multiple_explicit_models_can_match(self):
        self.assertEqual(set(self.ids('FX3/FX30 케이지')),{'sony-fx3','sony-fx30'})
    def test_no_compatibility_from_generic_mount_or_description(self):
        p=self.product('스몰리그 범용 케이지',description_text='사용 예시: Nikon ZR')
        registry,audit=associate([p]);self.assertFalse(registry);self.assertFalse(audit)
        p=self.product('소니 E 마운트 렌즈 35mm F1.8',brand='sony',type_ids=['type:mirrorless-lens'])
        self.assertFalse(associate([p])[0])
    def test_body_with_bundled_cage_is_not_an_accessory(self):
        p=self.product('[ZR 한정 프로모션] ZR Body / 틸타 케이지 증정',brand='nikon',type_ids=['type:camera'])
        registry,audit=associate([p]);self.assertEqual(p['camera_model_ids'],['nikon-zr']);self.assertNotIn('compatible_camera_model_ids',p)
        self.assertEqual(audit[0]['role'],'camera')
    def test_negative_compatibility_is_not_recommended(self):
        p=self.product('SmallRig Nikon ZR 호환 불가 케이지');self.assertFalse(associate([p])[0])
        self.assertFalse(associate([self.product('범용 A1 그립 플레이트')])[0])
    def test_cross_brand_accessories_have_camera_search_aliases_and_evidence(self):
        rows=[self.product('스몰리그 니콘 ZR 케이지'),self.product('틸타 Nikon ZR 케이지','tilta',id='source-2')]
        registry,audit=associate(rows);self.assertEqual(len(registry),1);self.assertEqual(len(registry[0]['accessory_product_ids']),2)
        terms=search_terms(rows[0],{m['id']:m for m in registry});self.assertIn('니콘',terms);self.assertIn('ZR',terms)
        self.assertEqual(audit[0]['basis'],'supplier_product_title')
    def test_wooden_camera_exact_models_are_linked_without_inventing_family_generations(self):
        p=self.product('Wooden Camera SONY FX3 액세서리 제품군','wooden-camera',type_ids=['type:camera-rig'])
        registry,audit=associate([p]);self.assertEqual(p['compatible_camera_model_ids'],['sony-fx3']);self.assertEqual(p['compatibility_scope'],'product_family')
        self.assertFalse(associate([self.product('Wooden Camera BLACKMAGIC POCKET CINEMA CAMERA 액세서리 제품군','wooden-camera')])[0])
        self.assertEqual(self.ids('Wooden Camera Sony FX5 Lens Mount Adapters & Supports','wooden-camera'),['sony-fx5'])

    def test_same_product_original_title_restores_abbreviated_primary(self):
        p=self.product('틸타 TA-T16-C-B Pro Kit',brand='tilta',offers=[{'id':'source-1','source':'clmedia','url':'https://cl.example/1'},{'id':'source-2','source':'avx','url':'https://avx.example/2'}])
        registry,audit=associate([p],{'source-1':[{'id':'source-1','name':p['name']},{'id':'source-2','name':'틸타 Sony FX3/FX30 케이지 Pro Kit'}]})
        self.assertEqual(p['compatible_camera_model_ids'],['sony-fx3','sony-fx30'])
        self.assertEqual(audit[0]['title_evidence'][0]['id'],'source-2')
        self.assertEqual(audit[0]['basis'],'matched_supplier_product_titles')
        self.assertEqual(len(registry),2)
    def test_unbound_title_and_cross_title_context_are_ignored(self):
        p=self.product('스몰리그 Sony 범용 케이지',offers=[{'id':'source-2','url':'https://example/2'}])
        registry,audit=associate([p],{'source-1':[{'id':'unrelated','name':'니콘 ZR 케이지'},{'id':'source-2','name':'A1 케이지'}]})
        self.assertFalse(registry);self.assertFalse(audit)
    def test_accessory_cue_does_not_leak_to_non_accessory_original(self):
        p=self.product('스몰리그 범용 케이지',offers=[{'id':'source-2','url':'https://example/2'}])
        self.assertFalse(associate([p],{'source-1':[{'id':'source-2','name':'Sony FX3 카메라 본체'}]})[0])
    def test_bound_negative_title_vetoes_positive_supplier_claim(self):
        p=self.product('SmallRig Nikon ZR 케이지',offers=[{'id':'source-2','url':'https://example/2'}])
        registry,audit=associate([p],{'source-1':[{'id':'source-2','name':'SmallRig Nikon ZR 호환 불가 케이지'}]})
        self.assertFalse(registry);self.assertNotIn('compatible_camera_model_ids',p)
        self.assertEqual(audit[0]['conflicting_camera_model_ids'],['nikon-zr'])
    def test_camera_body_never_inherits_other_supplier_models(self):
        p=self.product('Nikon Z6 III 카메라',brand='nikon',type_ids=['type:camera'],offers=[{'id':'source-2','url':'https://example/2'}])
        associate([p],{'source-1':[{'id':'source-2','name':'Nikon Z8 케이지'}]})
        self.assertEqual(p['camera_model_ids'],['nikon-z6-iii']);self.assertNotIn('compatible_camera_model_ids',p)
