import json,unittest,copy
from pathlib import Path
from saeki_detail_parser import parse_detail
from saeki_publication import prepare,validate_candidate,actual_brand
from saeki_categories import product_types
from sync_saeki_catalog import Source
from unittest.mock import Mock

FIXTURES=Path(__file__).with_name('fixtures')/'saeki'

class SaekiTests(unittest.TestCase):
 def fixture(self,pid='PD00041562'):
  return (FIXTURES/(pid+'.html')).read_text(),json.loads((FIXTURES/(pid+'.json')).read_text())
 def parsed(self,pid='PD00041562'):
  return parse_detail(*self.fixture(pid),'2026-10-15T00:00:00+09:00')
 def test_actual_source_detail_shapes(self):
  for pid in [p.stem for p in FIXTURES.glob('*.html')]:
   with self.subTest(pid=pid):self.assertEqual(self.parsed(pid)['detail_status'],'verified')
  self.assertEqual(self.parsed()['sale_price'],1390000)
  self.assertEqual(self.parsed('PD00041926')['status'],'soldout')
  self.assertEqual(self.parsed('PD00007782')['status'],'soldout')
  for pid in ['PD00042994','PD00040026','PD00043223']:self.assertIsNone(self.parsed(pid)['sale_price'])
 def test_identity_price_stock_and_content_fail_closed(self):
  body,listing=self.fixture()
  for field,value in [('itemId','PD00000000'),('itemNm','Different lens'),('brndNm','SONY'),('slprc',999999),('uitemQty',2)]:
   with self.subTest(field=field),self.assertRaises(ValueError):parse_detail(body,{**listing,field:value},'now')
  for bad in [body.replace('data-status="PD004020"','data-status="PD004030"'),body.replace('cdn.saeki.co.kr','unrelated.invalid')]:
   with self.assertRaises(ValueError):parse_detail(bad,listing,'now')
 def test_hidden_inquiry_amount_is_not_published_as_a_price(self):
  body,listing=self.fixture('PD00043223')
  p=parse_detail(body,{**listing,'slprc':25440000,'spprc':25440000},'now')
  for key in ['price','sale_price','source_sale_price']:self.assertIsNone(p[key])
  with self.assertRaises(ValueError):parse_detail(body,{**listing,'slprc':25440000,'prcExpsYn':'Y'},'now')
 def test_brand_is_not_the_company_or_compatible_mount(self):
  p={'brand':'RICOH','source_brand_id':'2','name':'HD PENTAX-FA 50mm F1.4'}
  self.assertEqual(actual_brand(p)[0],'PENTAX')
  self.assertEqual(actual_brand({'brand':'SIGMA','source_brand_id':'1','name':'50mm F1.4 (PENTAX mount)'})[0],'SIGMA')
  self.assertEqual(actual_brand({'brand':'ETC','source_brand_id':'53','name':'SWIT 소니 호환 배터리'})[0],'SWIT')
  self.assertEqual(actual_brand({'brand':'ETC','source_brand_id':'53','name':'범용 클램프'})[0],'기타 브랜드')
 def test_body_accessory_and_film_classification(self):
  cases=[('표준렌즈 50mm F1.4 (SE)',['100002','100026','100124'],'kpp:0320'),
   ('Sennheiser 마이크 액세서리',['100006','100054','100271'],'kpp:0740'),
   ('엔젤버드 CFexpress 카드 리더기',['100001','100024','100258'],'kpp:0960'),
   ('ALEXA 35 Pro System',['100006','100049','100211'],'cinema-camera'),
   ('필름 400/36',['100008','100058','100235'],'film'),
   ('10인치 모니터 후드',['100006','100055'],'monitor-parts')]
  for name,ids,target in cases:self.assertEqual(product_types({'name':name,'source_category_ids':ids}),[target])
 def test_source_types_are_used_after_public_field_projection(self):
  from product_taxonomy import build_taxonomy
  root=Path(__file__).resolve().parents[1]
  catalog=json.loads((root/'data/catalog/catalog.json').read_text())
  categories={c['id']:c for c in catalog['categories']if c.get('scope')not in ('product','rental-product','rental-brand')}
  source=self.parsed();row={k:source[k]for k in ['id','name','kind','price','sale_price','status']}
  row.update(brand_id='sigma',type_ids=[],category_ids=[])
  _,audit=build_taxonomy([row],categories,saeki_products={source['id']:source})
  self.assertIn('type:kpp:0320',row['type_ids'])
  self.assertEqual(audit['assignments'][0]['reason'],'saeki-source-category-and-purpose')
 def test_distinct_source_skus_are_never_merged_by_model_number(self):
  from catalog_dedup import conflict
  a={'id':'saeki-PD1','source_id':'PD1','source':'saeki','brand_id':'smallrig','kind':'purchase','name':'1234 adapter'}
  b={**a,'id':'saeki-PD2','source_id':'PD2'}
  self.assertEqual(conflict(a,b,{}),'distinct_saeki_source_skus')
 def test_supplemental_supplier_stock_does_not_replace_primary_stock(self):
  from catalog_dedup import deduplicate
  a={'id':'smartstore-1','source_id':'1','source':'smartstore','brand_id':'sigma','kind':'purchase','name':'50mm F1.4',
     'status':'sale','supplier_status':None,'source_url':'https://example.test/item','category_ids':[],'type_ids':[],'promotion_ids':[],'offers':[{'id':'smartstore-1'}]}
  b={**a,'id':'saeki-PD1','source_id':'PD1','source':'saeki','status':'soldout','supplier_status':'soldout',
     '_supplemental_source':True,'offers':[{'id':'saeki-PD1'}]}
  rows={p['id']:p for p in [a,b]};details={pid:{'images':{'main':['image'],'detail':['detail']}}for pid in rows}
  redirects,_=deduplicate(rows,details,{'sigma':{'name':'SIGMA'}})
  self.assertEqual(redirects,{'saeki-PD1':'smartstore-1'})
  self.assertIsNone(rows['smartstore-1']['supplier_status'])
  self.assertEqual(rows['smartstore-1']['status'],'sale')
 def candidate(self):
  normal=self.parsed();point=self.parsed('PD00040026');rows={p['id']:p for p in [normal,point]}
  inv={'complete':True,'collected_at':'2026-10-15T00:00:00+09:00','brands':[{'id':'1'},{'id':'3'}],
    'coverage':[{'brand_id':'1','expected':1,'unique':1},{'brand_id':'3','expected':1,'unique':1}],
    'products':{p['source_id']:{}for p in rows.values()}}
  return prepare(inv,rows)
 def test_points_partition_and_complete_coverage(self):
  s=self.candidate();self.assertEqual(s['product_count'],1);self.assertEqual(s['publication']['source_product_count'],2)
  self.assertIn('saeki-PD00040026',s['publication']['excluded']);self.assertTrue(validate_candidate(s))
  for bad in [dict(s,product_count=2),dict(s,complete=False),dict(s,coverage=[])]:
   with self.assertRaises(ValueError):validate_candidate(bad)
  bad=copy.deepcopy(s);next(iter(bad['products'].values()))['detail_status']='pending'
  with self.assertRaises(ValueError):validate_candidate(bad)
 def test_reviewed_content_hold_does_not_claim_full_details(self):
  normal=self.parsed();pid='saeki-PD00024065'
  inv={'complete':True,'collected_at':'now','brands':[{'id':'1'},{'id':'85'}],
   'coverage':[{'brand_id':'1','expected':1,'unique':1},{'brand_id':'85','expected':1,'unique':1}],
   'products':{normal['source_id']:{},'PD00024065':{'itemNm':'Datacolor SpyderCheckr Video','brndId':85}}}
  hold={pid:{'reason':'source_content_unavailable','name':'Datacolor SpyderCheckr Video','source_brand_id':'85',
    'evidence':'source image response 403','checked_at':'now','html_sha256':'a'*64}}
  s=prepare(inv,{normal['id']:normal},hold)
  self.assertFalse(s['details_complete']);self.assertEqual(s['content_hold_count'],1)
  self.assertEqual(s['product_count'],1);self.assertTrue(validate_candidate(s))
  bad=copy.deepcopy(hold);bad[pid]['name']='Another product'
  with self.assertRaises(ValueError):prepare(inv,{normal['id']:normal},bad)
 def test_literal_break_markup_in_source_title_preserves_identity(self):
  body,listing=self.fixture()
  body=body.replace(listing['itemNm'],listing['itemNm'].replace(' | ','<br> | '))
  self.assertEqual(parse_detail(body,listing,'now')['name'],listing['itemNm'])
 def test_empty_brand_response_must_identify_the_requested_brand(self):
  import tempfile
  with tempfile.TemporaryDirectory()as folder:
   source=Source(folder);source.request=Mock(return_value=Mock(json=lambda:{'foSearchCriteria':{'brndIdList':['26']},'itemList':[]}))
   self.assertEqual(source.page('26',1,{},'token')['paginationInfo']['totalRecordCount'],0)
   with self.assertRaises(ValueError):source.page('27',1,{},'token')

if __name__=='__main__':unittest.main()
