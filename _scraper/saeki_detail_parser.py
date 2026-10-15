"""Validate a Saeki storefront item against its public brand listing."""
import json,re,html
from urllib.parse import urljoin,urlparse,parse_qs
from bs4 import BeautifulSoup
BASE='https://www.saeki.co.kr'
# Exact source-linked JPEGs verified on 2026-10-15. The HTTP entries have
# independently verified identical HTTPS paths; this is not a host-wide upgrade.
# Request/status/dimensions/SHA evidence: private catalogue sharing-admin-20261015
# /saeki-image-verification.json. Unreviewed paths on these hosts remain blocked.
REVIEWED_IMAGE_URLS = {'https://photonart747.godohosting.com/data/goods/polaroid/pl_all_end.jpg': 'https://photonart747.godohosting.com/data/goods/polaroid/pl_all_end.jpg',
 'https://photonart747.godohosting.com/data/goods/durix_paper/05_pm230_all.jpg': 'https://photonart747.godohosting.com/data/goods/durix_paper/05_pm230_all.jpg',
 'https://photonart747.godohosting.com/data/goods/durix_paper/04_glacier_all.jpg': 'https://photonart747.godohosting.com/data/goods/durix_paper/04_glacier_all.jpg',
 'https://photonart747.godohosting.com/data/goods/durix_paper/02_satin_all.jpg': 'https://photonart747.godohosting.com/data/goods/durix_paper/02_satin_all.jpg',
 'https://photonart747.godohosting.com/data/goods/durix_paper/01_glossy_all.jpg': 'https://photonart747.godohosting.com/data/goods/durix_paper/01_glossy_all.jpg',
 'https://shop-phinf.pstatic.net/20241125_181/1732527109692esO4T_JPEG/fx.jpg?type=w860': 'https://shop-phinf.pstatic.net/20241125_181/1732527109692esO4T_JPEG/fx.jpg?type=w860',
 'https://muhan88.imghost.cafe24.com/homepage/muhanmedia/escura/heisei_01.jpg': 'https://muhan88.imghost.cafe24.com/homepage/muhanmedia/escura/heisei_01.jpg',
 'https://muhan88.imghost.cafe24.com/homepage/muhanmedia/escura/heisei_02.jpg': 'https://muhan88.imghost.cafe24.com/homepage/muhanmedia/escura/heisei_02.jpg',
 'https://muhan88.imghost.cafe24.com/homepage/muhanmedia/escura/heisei_03.jpg': 'https://muhan88.imghost.cafe24.com/homepage/muhanmedia/escura/heisei_03.jpg',
 'https://muhan88.imghost.cafe24.com/homepage/muhanmedia/escura/heisei_04.jpg': 'https://muhan88.imghost.cafe24.com/homepage/muhanmedia/escura/heisei_04.jpg',
 'https://muhan88.imghost.cafe24.com/homepage/muhanmedia/escura/heisei_05.jpg': 'https://muhan88.imghost.cafe24.com/homepage/muhanmedia/escura/heisei_05.jpg',
 'https://muhan88.imghost.cafe24.com/homepage/muhanmedia/escura/heisei_06.jpg': 'https://muhan88.imghost.cafe24.com/homepage/muhanmedia/escura/heisei_06.jpg',
 'https://muhan88.imghost.cafe24.com/homepage/muhanmedia/escura/heisei_07.jpg': 'https://muhan88.imghost.cafe24.com/homepage/muhanmedia/escura/heisei_07.jpg',
 'https://muhan88.imghost.cafe24.com/homepage/muhanmedia/escura/heisei_08.jpg': 'https://muhan88.imghost.cafe24.com/homepage/muhanmedia/escura/heisei_08.jpg',
 'https://muhan88.imghost.cafe24.com/homepage/muhanmedia/escura/heisei_09.jpg': 'https://muhan88.imghost.cafe24.com/homepage/muhanmedia/escura/heisei_09.jpg',
 'https://muhan88.imghost.cafe24.com/homepage/muhanmedia/escura/heisei_10.jpg': 'https://muhan88.imghost.cafe24.com/homepage/muhanmedia/escura/heisei_10.jpg',
 'https://muhan88.imghost.cafe24.com/homepage/muhanmedia/escura/heisei_11.jpg': 'https://muhan88.imghost.cafe24.com/homepage/muhanmedia/escura/heisei_11.jpg',
 'https://muhan88.imghost.cafe24.com/homepage/muhanmedia/escura/heisei_12.jpg': 'https://muhan88.imghost.cafe24.com/homepage/muhanmedia/escura/heisei_12.jpg',
 'http://cdn.saeki.co.kr/malluploadfile/public/saeki/brand/2014_contents_img/140609_LL_LS2352N_777_01.jpg': 'https://cdn.saeki.co.kr/malluploadfile/public/saeki/brand/2014_contents_img/140609_LL_LS2352N_777_01.jpg',
 'http://cdn.saeki.co.kr/malluploadfile/public/saeki/brand/2014_contents_img/140609_LL_LS2352N_777_02.jpg': 'https://cdn.saeki.co.kr/malluploadfile/public/saeki/brand/2014_contents_img/140609_LL_LS2352N_777_02.jpg',
 'http://cdn.saeki.co.kr/malluploadfile/public/saeki/brand/2014_contents_img/140609_LL_LS2352N_777_04.jpg': 'https://cdn.saeki.co.kr/malluploadfile/public/saeki/brand/2014_contents_img/140609_LL_LS2352N_777_04.jpg'}
def clean(v):return re.sub(r'\s+',' ',re.sub(r'<br\s*/?>','',html.unescape(str(v or '')),flags=re.I)).strip()
def photo(url):
 u=urljoin(BASE,url)
 if u in REVIEWED_IMAGE_URLS:return REVIEWED_IMAGE_URLS[u]
 p=urlparse(u)
 # This exact source notice is still linked over HTTP. Its HTTPS JPEG was
 # verified directly; do not upgrade arbitrary unreviewed external URLs.
 if p.scheme=='http' and p.netloc=='ai.esmplus.com' and p.path=='/kppshop/KPP/as_guide/as_guide.jpg' and not p.query and not p.fragment:
  u='https:'+u[5:];p=urlparse(u)
 if p.scheme!='https' or p.hostname not in {'cdn.saeki.co.kr','www.saeki.co.kr','ai.esmplus.com','cdn.dev.saeki.co.kr'} or p.username or p.password:raise ValueError('Unexpected product image origin')
 return u

def parse_detail(body,listing,checked_at):
 d=BeautifulSoup(body,'lxml');pid=listing['itemId'];hidden=d.select_one('#major #itemId');title=d.select_one('#major #itemNm')
 if not hidden or hidden.get('value')!=pid or not title:raise ValueError('Detail item identity/name differs from listing')
 name_matches=clean(title.get('value'))==clean(listing['itemNm'])
 # Source HTML fails to escape inch marks in this hidden attribute. Require
 # the exact quote-truncated prefix AND the independent full schema name.
 inch_attribute=('"' in listing['itemNm'] and clean(title.get('value'))==clean(listing['itemNm'].split('"',1)[0]))
 if not name_matches and not inch_attribute:raise ValueError('Detail item identity/name differs from listing')
 rows=[]
 for s in d.select('script[type="application/ld+json"]'):
  value=json.loads(s.get_text());rows.extend(value if isinstance(value,list) else [value])
 schemas=[x for x in rows if x.get('@type')=='Product']
 if len(schemas)!=1:raise ValueError('Missing unambiguous Product schema')
 schema=schemas[0];offer=schema.get('offers',{})
 if not isinstance(offer,dict) or parse_qs(urlparse(offer.get('url','')).query).get('itemId')!=[pid]:raise ValueError('Schema product URL differs')
 if clean(schema.get('name'))!=clean(listing['itemNm']) or clean(schema.get('brand',{}).get('name')).casefold()!=clean(listing['brndNm']).casefold():raise ValueError('Schema product brand/name differs')
 if offer.get('priceCurrency')!='KRW':raise ValueError('Unexpected currency')
 rawprice=int(listing['slprc']);schema_price=float(offer['price'])
 quote=any(listing.get(k)=='Y' for k in ('prcInqYn','commingSoonYn','pointYn')) or listing.get('prcExpsYn')=='N'
 # Inquiry pages deliberately hide KRW pricing. The list API can contain
 # either placeholder 1 or a hidden amount; never publish either as a price.
 coming_soon=listing.get('commingSoonYn')=='Y'
 if coming_soon:
  visible=[clean(n.get_text()) for n in d.select('.btn-area.type-ui.w100 a.btn')]
  if (listing.get('prcExpsYn')!='N' or schema_price!=0 or '출시예정상품' not in visible
      or d.select_one('#orderItemArea')):raise ValueError('Unverified coming-soon state')
 placeholder=(coming_soon or (quote and listing.get('prcExpsYn')=='N' and listing.get('prcInqYn')=='Y'
              and schema_price==0 and d.select_one('#btnPriceInquiry')))
 if schema_price!=rawprice and not placeholder:raise ValueError('Listing/detail price changed')
 if listing.get('itemClCd') not in {'PD002001','PD002002','PD002003','PD002006','PD002008','PD002009','PD002010'}:raise ValueError('Unknown source product class')
 if listing.get('uitemQty')!=1:raise ValueError('Multiple item SKUs need explicit option verification')
 known_soldout=listing.get('soldOutYn')=='Y' or listing.get('finishYn')=='Y'
 stock=offer.get('availability','').rsplit('/',1)[-1]
 if stock not in {'InStock','OutOfStock','Discontinued','PreOrder'}:raise ValueError('Unknown source availability')
 if known_soldout and stock=='InStock':raise ValueError('Source stock fields disagree')
 # Some special-order list rows say available while the actual SKU is sold out.
 # Resolve only after schema and selected SKU independently agree below.
 quote=any(listing.get(k)=='Y' for k in ('prcInqYn','commingSoonYn','pointYn')) or listing.get('prcExpsYn')=='N'
 selected=[n for n in d.select('#orderItemArea .ui-price-group') if n.get('data-id')==pid]
 if not quote:
  if len(selected)!=1:raise ValueError('Main item SKU selection absent')
  n=selected[0];state=n.get('data-status')
  if state not in {'PD004020','PD004030','PD004040','PD004050'}:raise ValueError('Unreviewed sale status: '+str(state))
  if int(n.get('data-price','').replace(',',''))!=rawprice:raise ValueError('Selected SKU price differs')
  detail_soldout=state in {'PD004030','PD004040','PD004050'}
  if detail_soldout!=(stock in {'OutOfStock','Discontinued'}):raise ValueError('Selected SKU stock disagrees with schema')
  known_soldout=detail_soldout
  if not n.get('data-uid') and listing['itemClCd']!='PD002006':raise ValueError('Selected SKU identity missing')
 elif not known_soldout and listing.get('prcInqYn')=='Y' and not d.select_one('#btnPriceInquiry'):
  raise ValueError('Inquiry-only source has no inquiry action')
 main=list(dict.fromkeys(photo(x['src']) for x in d.select('#imageArea img.prd-main-img[src]')))
 detail=list(dict.fromkeys(photo(x.get('src') or x.get('data-src')) for x in d.select('.detail-img img[src],.detail-img img[data-src]')))
 if not main:raise ValueError('Product gallery missing')
 if schema.get('image') and photo(schema['image'][0]) not in main:raise ValueError('Schema image differs from gallery')
 description=clean(' '.join(x.get_text(' ',strip=True) for x in d.select('.edit-type.editor-cont, .detail-img')))
 if not detail and not description:raise ValueError('Product description missing')
 # Related mount/colour variants are distinct source products; never collapse
 # them into price-less purchase options or merge their identities.
 variants=[]
 for n in d.select('.ui-color-select-wrap li'):
  a=n.select_one('a[href]');label=n.select_one('.prd-name')
  if a:
   target=parse_qs(urlparse(a['href']).query).get('itemId',[''])[0]
   if re.fullmatch(r'PD\d+',target):variants.append({'id':'saeki-'+target,'name':clean(label.get_text()) if label else ''})
 additions=[]
 for n in d.select('.select-ui.add button[data-id]'):
  target=n.get('data-id','')
  if not target:continue
  if not re.fullmatch(r'PD\d+',target):raise ValueError('Invalid additional product ID')
  entry={'id':'saeki-'+target,'name':clean(n.get('data-name')),'price':int(n.get('data-price','0').replace(',','')),'source_status':n.get('data-status')}
  if entry not in additions:additions.append(entry)
 paths=[]
 for level in ('Lcl','Mcl','Scl'):
  cid=listing.get('dspCate'+level+'Id');name=listing.get('dspCate'+level+'Nm')
  if bool(cid)!=bool(name):raise ValueError('Incomplete source category path')
  if cid:paths.append({'id':str(cid),'name':clean(name)})
 if not paths:
  for crumb in [r for r in rows if r.get('@type')=='BreadcrumbList']:
   for entry in crumb.get('itemListElement',[]):
    item=entry.get('item',{});cid=parse_qs(urlparse(item.get('@id','')).query).get('dspCateId',[''])[0]
    if cid and item.get('name'):paths.append({'id':cid,'name':clean(item['name'])})
 if not paths:raise ValueError('Missing source product category')
 manufacturer=''
 for row in d.select('#tab01 tr'):
  label=row.select_one('th');value=row.select_one('td')
  if label and value and clean(label.get_text())=='제조사/수입사':manufacturer=clean(value.get_text()).split('/',1)[0].strip()
 bid=str(listing['brndId']);brand=clean(listing['brndNm'])
 status='soldout' if known_soldout and not coming_soon else 'inquiry';sale=None if quote else rawprice
 if sale is not None and sale<=1:raise ValueError('Placeholder sale price without explicit inquiry condition')
 price=None if quote else max(int(listing.get('spprc') or 0),rawprice)
 note='재고와 납기는 상담 후 확정됩니다.'
 if coming_soon:note='출시 예정 상품입니다. 가격은 아직 공개되지 않았으며 현재 구매할 수 없습니다. 출시 일정은 상담으로 확인해 주세요.'
 elif listing['itemClCd'] in {'PD002002','PD002010'}:note='예약 판매 상품입니다. 입고 일정과 주문 조건은 상담 후 확정됩니다.'
 elif listing['itemClCd']=='PD002009':note='스페셜 오더 상품입니다. 주문 가능 여부와 납기는 상담 후 확정됩니다.'
 elif listing['itemClCd']=='PD002008':note='전시·리퍼 또는 박스 훼손 상품입니다. 상품명에 표시된 상태와 실제 구성을 상담에서 확인해 주세요.'
 if additions:note+=' 추가 구성품은 별도 상품이며 기본 구성에 포함되지 않습니다.'
 return {'id':'saeki-'+pid,'source':'saeki','source_id':pid,'source_url':BASE+'/item/itemDetail?itemId='+pid,
  'name':clean(listing['itemNm']),'brand':brand,'kind':'purchase','price':price,'sale_price':sale,'status':status,
  'supplier_status':'inquiry' if coming_soon else 'soldout' if known_soldout else 'inquiry' if quote or listing['itemClCd'] in {'PD002002','PD002009','PD002010'} else 'available',
  'brand_category_ids':[bid,*[bid+':'+x['id'] for x in paths]],'source_category_path':[x['name'] for x in paths],
  'source_category_ids':[x['id'] for x in paths], 'source_brand_id':bid,'source_product_class':listing['itemClCd'],
  **({'release_status':'coming_soon'} if coming_soon else {}),
  'source_display_flags':{k:listing.get(k) for k in ('prcExpsYn','prcInqYn','commingSoonYn','pointYn','finishYn','soldOutYn')},
  'source_sale_price':None if quote else rawprice,'source_sku':selected[0].get('data-uid') if selected else None,
  'source_manufacturer':manufacturer,'manufacturer_code':clean(schema.get('mpn')),'source_variants':variants,'source_additional_products':additions,
  'images':{'thumb':main[0],'main':main,'detail':detail},'description_text':description,
  'description_notice':note,'detail_status':'verified','options':[],'option_groups':[],
  'options_require_confirmation':bool(additions) or coming_soon,'detail_checked_at':checked_at}
