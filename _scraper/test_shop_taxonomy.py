"""Classification and inventory conservation gates for both browsing facets."""
import json
import unittest
from copy import deepcopy
from pathlib import Path
from product_taxonomy import build_taxonomy
from rental_taxonomy import build_rental_taxonomy

ROOT=Path(__file__).resolve().parents[1]

class ShopTaxonomy(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog=json.loads((ROOT/'data/catalog/catalog.json').read_text())
        cls.source_categories={c['id']:c for c in cls.catalog['categories'] if c.get('scope') not in ('product','rental-product','rental-brand')}

    def classify(self,names,kind='purchase'):
        rows=[dict(id=str(i),name=name,brand_id='test-brand',kind=kind,type_ids=[],category_ids=[],price=12500,status='soldout') for i,name in enumerate(names)]
        before=deepcopy(rows)
        nodes,_=build_taxonomy(rows,self.source_categories)
        cats={**self.source_categories,**{c['id']:c for c in nodes}}
        rentals,_=build_rental_taxonomy(rows,cats)
        for a,b in zip(rows,before):
            self.assertEqual({k:v for k,v in a.items() if k not in ('type_ids','category_ids')},{k:v for k,v in b.items() if k not in ('type_ids','category_ids')})
        return rows,{**cats,**{c['id']:c for c in rentals}}

    def test_accessories_do_not_become_camera_bodies(self):
        rows,_=self.classify(['SMALLRIG SONY FX3 케이지','소니 SONY FX3+28-135G','소니 SONY AX700+삼각대','캐논 R5+RF100500'],kind='rental')
        self.assertIn('rent:135',rows[0]['type_ids']);self.assertNotIn('rent:11',rows[0]['type_ids'])
        self.assertIn('rent:11',rows[1]['type_ids']);self.assertIn('rent:10',rows[1]['type_ids'])
        self.assertIn('rent:26',rows[2]['type_ids']);self.assertNotIn('rent:127',rows[2]['type_ids'])
        self.assertIn('rent:24',rows[3]['type_ids'])

    def test_optical_mount_names_are_lenses_and_battery_mounts_are_power(self):
        names=['Laowa 15mm F5 Cookie FF (FE/Z/RF/L/M-MOUNT)','TOKINA CINEMA Vista Prime 135mm T1.5 PL mount','SMALLRIG 1.33X Anamorphic Lens (T-mount)','BSL2680 15mm LWS 렌즈 서포트','SWIT MINO-S140 V마운트 배터리']
        rows,_=self.classify(names)
        for p,key in zip(rows,['type:kpp:03','type:kpp:04','type:phone-lens','type:rig-mounts','type:v-mount']):self.assertIn(key,p['type_ids'],p['name'])
        for p in rows[:3]:self.assertNotIn('type:rig-mounts',p['type_ids'])

    def test_camera_mounting_and_audio_adapters_are_not_camera_bodies(self):
        names=['[Manfrotto] 맨프로토 208 카메라 마운팅 어댑터','SMALLRIG FX6 핸드그립용 로제트 어댑터 SR3403','[COMICA] CVM-CPX 3.5mm 스마트폰 카메라 변환 어댑터','카메라 렌즈 어댑터','카메라 전원 어댑터']
        rows,_=self.classify(names)
        for p,target in zip(rows,['mount-adapter','mount-adapter','audio-adapter','kpp:0330','power-parts']):
            self.assertIn('type:'+target,p['type_ids'],p['name']);self.assertNotIn('type:camera',p['type_ids'],p['name'])

    def test_camera_compatibility_does_not_turn_filters_grips_or_storage_into_bodies(self):
        names=['카메라 DSLR 우측 우든그립','B+W Soft Pro BASIC 52mm 카메라 렌즈 필터','LEXAR CF익스프레스 니콘 캐논 카메라 호환 1TB','KUPO KS-168 CAMERA T MARKER 티마커','[FALCAM] 카메라 F38 퀵릴리즈 키트','카메라 제습함 50L','카메라 팬틸트 헤드 키트']
        rows,_=self.classify(names)
        for p,target in zip(rows,['kpp:0650','kpp:02','cf-card','camera-markers','kpp:0140','dry-cabinet','pan-head']):
            self.assertIn('type:'+target,p['type_ids'],p['name']);self.assertNotIn('type:camera',p['type_ids'],p['name'])

    def test_camera_body_and_rental_bundles_remain_cameras(self):
        rows,_=self.classify(['SONY ILCE-7M4 미러리스 카메라','Reloadable 35mm 필름카메라 마그네틱 필터 3종 키트'])
        for p in rows:self.assertIn('type:camera',p['type_ids'])
        rentals,_=self.classify(['캐논 R6M2+R어댑터+EF70200 ii','NIKON 니콘 ZR 케이지 세트 미러리스 RAW촬영 캠 렌탈'],kind='rental')
        for p in rentals:self.assertIn('type:camera',p['type_ids'])

    def test_aputure_optics_and_mounts_stay_with_lighting_and_rentals_keep_their_paths(self):
        names=['Aputure Spotlight Max ETC Lens Adapter','Aputure F10 프리즈넬 렌즈',
               'Aputure Light Box 30x120','Aputure STORM 80c','Aputure INFINIMAT 4x4',
               'Aputure INFINIBAR PB12','Aputure NOVA II 1x1','Aputure LS600 cable']
        rows=[dict(id=str(i),name=n,brand_id='aputure',kind='purchase',type_ids=[],category_ids=[]) for i,n in enumerate(names)]
        build_taxonomy(rows,self.source_categories)
        for p in rows:
            self.assertIn('type:kpp:07',p['type_ids'])
            self.assertNotIn('type:camera',p['type_ids']);self.assertNotIn('type:kpp:03',p['type_ids'])
        for p,target in zip(rows,['light-grip','light-lens','softbox','continuous','mat-light','tube-light','panel-light','light-power']):
            self.assertIn('type:'+target,p['type_ids'])
        rentals=[p for p in self.catalog['products'] if p['brand_id']=='aputure' and p['kind']=='rental']
        self.assertEqual(len(rentals),9)
        self.assertTrue(all(all(o['source']=='smartstore' for o in p['offers']) for p in rentals))

    def test_rental_medium_format_lights_and_support_have_specific_paths(self):
        rows,_=self.classify(['PHASEONE LS 35mm F3.5','PHASEONE XF IQ2 60MP KIT','APUTURE Amaran 300C','EDELKRONE 에델크론 슬라이더+헤드플러스+V마운트 키트','EDELKRONE 에델크론 달리','KUPO KAB-41K NESTING APPLE BOX','레인보우 시네새들','DJI TWIST DUAL GRIP'],kind='rental')
        for p,key in zip(rows,['medium-lens','medium-camera','102','133','133','270','140','135']):self.assertIn('rent:'+key,p['type_ids'],p['name'])

    def test_category_addition_preserves_native_source_membership(self):
        p=dict(id='fixture',name='unknown model',brand_id='test-brand',kind='purchase',type_ids=['kpp:p:0110'],category_ids=['brand-path'])
        nodes,audit=build_taxonomy([p],self.source_categories)
        self.assertEqual(p['category_ids'],['brand-path']);self.assertIn('kpp:p:0110',p['type_ids']);self.assertIn('type:kpp:01',p['type_ids']);self.assertIn('type:kpp:0110',p['type_ids'])
        self.assertEqual(audit['assignments'][0]['reason'],'kpp-membership')

    def test_all_slr_product_types_survive_and_brand_leaves_are_separate(self):
        reference=json.loads((ROOT/'_scraper/references/slrrent-categories.json').read_text())
        expected={c['id'] for c in reference['categories'] if c['depth']<2 or c['parent_id'] in ('13','26','120','140','56')}
        cats=[c for c in self.catalog['categories'] if c.get('scope')=='rental-product']
        self.assertEqual(expected,{c['source_id'] for c in cats if c.get('source_id')})
        self.assertEqual(len([c for c in cats if not c['parent_id']]),9)
        self.assertTrue(all(c['brand_id'] is None for c in cats))

    def test_each_inventory_item_keeps_ancestors_and_brand_isolation(self):
        cats={c['id']:c for c in self.catalog['categories']}
        for p in self.catalog['products']:
            self.assertTrue(any(c.startswith('type:') for c in p['type_ids']),p['id'])
            if p['kind']=='rental':
                self.assertTrue(any(c.startswith('rent:') for c in p['type_ids']),p['id'])
                self.assertTrue(any(c.startswith('rental-brand:') for c in p['category_ids']),p['id'])
            else:self.assertFalse(any(c.startswith('rent:') for c in p['type_ids']),p['id'])
            for field in ('type_ids','category_ids'):
                for cid in p[field]:
                    if cats[cid].get('scope') not in ('product','rental-product','rental-brand'):continue
                    path=set();current=cid
                    while current:
                        self.assertNotIn(current,path,cid);path.add(current)
                        self.assertIn(current,p[field],p['id'])
                        if field=='category_ids':self.assertEqual(cats[current]['brand_id'],p['brand_id'])
                        current=cats[current]['parent_id']

    def test_lightweight_rental_payload_is_an_exact_inventory_subset(self):
        rental=json.loads((ROOT/'data/catalog/rental.json').read_text())
        expected=[p for p in self.catalog['products'] if p['kind']=='rental']
        self.assertEqual(rental['products'],expected)
        self.assertEqual(rental['meta']['product_count'],len(expected))
        self.assertEqual(rental['meta']['listing_count'],len({p.get('listing_id',p['id']) for p in expected}))
        self.assertEqual(rental['meta']['revision'],self.catalog['meta']['revision'])
        cats={c['id'] for c in rental['categories']}
        self.assertTrue(all(set(p['category_ids']+p['type_ids'])<=cats for p in expected))
        self.assertLess((ROOT/'data/catalog/rental.json').stat().st_size,(ROOT/'data/catalog/catalog.json').stat().st_size/4)

    def test_invalid_review_override_fails_instead_of_losing_items(self):
        p=dict(id='fixture',name='unknown',brand_id='test',kind='purchase',type_ids=[],category_ids=[])
        with self.assertRaises(ValueError):build_taxonomy([p],self.source_categories,{'fixture':['missing-category']})
