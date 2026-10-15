"""Verified Saeki details, actual brands and traceable source category paths."""
from copy import deepcopy
import hashlib,json,re
from urllib.parse import urlparse,parse_qs

# These names appear as the product's own prefix inside the source's ETC menu.
# Never scan arbitrary compatibility text in a lens/mount title for a brand.
PREFIXES={
 'SAMSUNG':'SAMSUNG','FIZLock':'FIZLock','OBSBOT':'OBSBOT','SWIT':'SWIT','Aputure':'Aputure','CURA':'CURA','ESCURA':'ESCURA',
 'Bexel':'BEXEL','CALIBRITE':'Calibrite','KIOXIA':'KIOXIA','HAKUBA':'HAKUBA',
 '젠트리':'GENTREE','두릭스':'DURIX','213LAB':'213LAB','LightPix':'LightPix Labs',
 'COSMOS':'COSMOS','APLOFY':'APLOFY','Arte di mano':'Arte di mano','ROBOCUP':'ROBOCUP',
 '프로딘':'PRODEAN','발렌스':'VALENS','오렌지몽키':'ORANGEMONKIE','파라볼릭스':'PARABOLIX',
 'FARSEEING':'FARSEEING','씨네스틸':'CINESTILL','센도리':'SENDORI','하이퍼씬':'HYPERTHIN',
 '나이트코어':'NITECORE','티브이로직':'TVLOGIC','ADICAM':'ADICAM','힐링쉴드':'HEALING SHIELD',
 'ILFORD':'ILFORD','SANTA COLOR':'SANTA','엑셀라':'EXCELLA',
 'JapanCameraHunter':'Japan Camera Hunter','긴이치':'GINICHI','포니':'PONY',
 'Cameo':'CAMEO','TGS':'TGS',
}
CANONICAL={'B+W':'B+W FILTER','PRO GAFFER':'PRO GAFF','TETHER TOOLS':'TETHERTOOLS','RIP-TIE':'RIPTIE','HARMAN technology':'HARMAN'}

def actual_brand(p):
 original=p['brand'];name=p['name'];bid=str(p['source_brand_id'])
 if bid=='2' and re.search(r'\bPENTAX\b',name,re.I):return 'PENTAX','explicit product brand within RICOH menu'
 if bid=='2' and '힐링쉴드' in name:return 'HEALING SHIELD','explicit screen protector brand'
 if bid=='10':
  if re.match(r'KENTMERE\b',name,re.I):return 'KENTMERE','explicit product brand within HARMAN menu'
  if re.match(r'ILFORD\b',name,re.I):return 'ILFORD','explicit product brand within HARMAN menu'
 if bid=='42' and name.startswith('인스탁스 미니'):return 'FUJIFILM','explicit Instax camera package title'
 if bid=='42' and name.startswith('하만 '):return 'HARMAN','explicit Harman camera package title'
 if bid in {'53','42'}:
  prefix=re.sub(r'^\[[^\]]+\]\s*','',name)
  for token,brand in sorted(PREFIXES.items(),key=lambda x:-len(x[0])):
   if re.match(re.escape(token)+r'(?:\b|\s)',prefix,re.I):return brand,'explicit product title prefix'
  maker=p.get('source_manufacturer','')
  if maker=='LightPix Laps':return 'LightPix Labs','source product manufacturer field'
  from build_catalog import ALIASES
  if maker.casefold() in ALIASES and maker.casefold() not in {'ricoh','harman','saeki','etc'}:
   return maker,'source product manufacturer field'
  if bid=='53':return '기타 브랜드','source does not identify the product brand'
 return CANONICAL.get(original,original),'source brand'


def prepare(inventory,details,holds=None):
 expected={'saeki-'+pid for pid in inventory['products']}
 holds=holds or {}
 if not inventory.get('complete') or set(details)|set(holds)!=expected or set(details)&set(holds):raise ValueError('Saeki inventory/detail coverage differs')
 products={};categories={};excluded=deepcopy(holds)
 for pid,rule in holds.items():
  original=inventory['products'].get(pid.removeprefix('saeki-'),{})
  if (rule.get('reason')!='source_content_unavailable' or rule.get('name')!=original.get('itemNm') or
      rule.get('source_brand_id')!=str(original.get('brndId')) or not rule.get('evidence') or
      not rule.get('checked_at') or not rule.get('html_sha256')):raise ValueError('Unreviewed Saeki content hold')
 for pid,raw in details.items():
  if raw.get('detail_status')!='verified':raise ValueError('Unverified Saeki detail')
  # Loyalty redemptions cannot be mirrored as products bought with KRW.
  if raw.get('source_display_flags',{}).get('pointYn')=='Y':
   excluded[pid]={'reason':'source_loyalty_points_only','name':raw['name'],'source_brand_id':raw['source_brand_id']};continue
  p=deepcopy(raw);p['source_brand']=p['brand'];p['brand'],p['brand_evidence']=actual_brand(p)
  from build_catalog import brand_id
  bid=brand_id(p['brand']);root=bid+':root'
  categories[root]={'id':root,'name':p['brand'],'parent_id':None,'brand':p['brand']}
  parent=root;members=[root]
  for sid,name in zip(p['source_category_ids'],p['source_category_path']):
   key=bid+':'+sid
   node={'id':key,'name':name,'parent_id':parent,'brand':p['brand']}
   if key in categories and categories[key]!=node:raise ValueError('Inconsistent Saeki category ancestry')
   categories[key]=node;members.append(key);parent=key
  p['brand_category_ids']=members;products[pid]=p
 candidate={'source':'saeki','scope':'all_shop_brands','complete':True,'normalized_for_shop':True,
  'details_complete':not holds,'content_hold_count':len(holds),
  'collected_at':inventory['collected_at'],'product_count':len(products),'products':products,
  'brands':inventory['brands'],'coverage':inventory['coverage'],'categories':list(categories.values()),
  'publication':{'full_collection_verified':True,'source_product_count':len(expected),'accepted_product_count':len(products),'excluded':excluded},
  'parser_revision':next(iter(details.values())).get('parser_revision'),
  'brand_classification_revision':hashlib.sha256(__import__('pathlib').Path(__file__).read_bytes()).hexdigest()}
 validate_candidate(candidate)
 return candidate


def validate_candidate(s):
 if s.get('source')!='saeki' or s.get('complete')is not True or not s.get('normalized_for_shop'):raise ValueError('Saeki source not fully verified')
 products=s.get('products',{});coverage=s.get('coverage',[]);publication=s.get('publication',{})
 if (publication.get('full_collection_verified')is not True or s.get('product_count')!=len(products)or not products or
     {x['id']for x in s.get('brands',[])}!={x['brand_id']for x in coverage}or
     any(x['expected']!=x['unique']for x in coverage)or
     sum(x['unique']for x in coverage)!=publication.get('source_product_count')or
     publication.get('accepted_product_count')!=len(products)or
     len(products)+len(publication.get('excluded',{}))!=publication.get('source_product_count')):
  raise ValueError('Saeki source partition or brand coverage is incomplete')
 content_holds={pid:p for pid,p in publication.get('excluded',{}).items()if p.get('reason')=='source_content_unavailable'}
 if s.get('content_hold_count')!=len(content_holds) or s.get('details_complete')!=(not content_holds):raise ValueError('Saeki content hold summary differs')
 for pid,p in publication.get('excluded',{}).items():
  if p.get('reason')not in {'source_loyalty_points_only','source_content_unavailable'}:raise ValueError('Unknown Saeki exclusion')
  if p.get('reason')=='source_content_unavailable' and (not p.get('evidence')or not p.get('checked_at')or not p.get('html_sha256')):raise ValueError('Unverified content exclusion')
 from collections import Counter
 brand_counts=Counter(str(p['source_brand_id'])for p in products.values())
 brand_counts.update(str(p['source_brand_id'])for p in publication.get('excluded',{}).values())
 if any(brand_counts[c['brand_id']]!=c['expected']for c in coverage) or set(brand_counts)-{c['brand_id']for c in coverage}:raise ValueError('Saeki per-brand inventory differs')
 categories={c['id']:c for c in s.get('categories',[])}
 for pid,p in products.items():
  if (p.get('id')!=pid or pid!='saeki-'+p.get('source_id','')or p.get('source')!='saeki' or
      p.get('kind')!='purchase'or p.get('detail_status')!='verified'or not p.get('brand')or
      not p.get('detail_checked_at')or not p.get('images',{}).get('main')or
      not p.get('brand_category_ids')or set(p['brand_category_ids'])-set(categories)):
   raise ValueError('Invalid Saeki product identity/detail: '+pid)
  if any(categories[c]['brand']!=p['brand']for c in p['brand_category_ids']):raise ValueError('Saeki product category belongs to another brand')
  if p['status'] not in {'inquiry','soldout'} or p['supplier_status'] not in {'available','inquiry','soldout'}:raise ValueError('Unknown Saeki sale status')
  url=urlparse(p['source_url'])
  if url.scheme!='https' or url.netloc!='www.saeki.co.kr' or url.path!='/item/itemDetail' or parse_qs(url.query).get('itemId')!=[p['source_id']]:raise ValueError('Invalid Saeki product URL')
  if p.get('source_display_flags',{}).get('pointYn')=='Y':raise ValueError('Loyalty item in KRW shop')
  if p['sale_price']is not None and p['sale_price']<=1:raise ValueError('Placeholder Saeki price')
  if p.get('release_status') not in {None,'coming_soon'}:raise ValueError('Unknown Saeki release state')
  if p.get('source_display_flags',{}).get('commingSoonYn')=='Y' or p.get('release_status')=='coming_soon':
   if (p.get('release_status')!='coming_soon' or p.get('source_display_flags',{}).get('commingSoonYn')!='Y'
       or any(p.get(k)is not None for k in ('price','sale_price','source_sale_price'))
       or p['status']!='inquiry' or p['supplier_status']!='inquiry' or p.get('options_require_confirmation')is not True):
    raise ValueError('Coming-soon product exposed as purchasable or priced')
 for c in categories.values():
  seen=set();cursor=c
  while cursor:
   if cursor['id']in seen:raise ValueError('Saeki category cycle')
   seen.add(cursor['id']);parent=cursor['parent_id']
   if parent and parent not in categories:raise ValueError('Missing Saeki category parent')
   cursor=categories.get(parent)
 return True
