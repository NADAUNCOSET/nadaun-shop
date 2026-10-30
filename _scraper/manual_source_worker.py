"""Recurring source reads for Motion9 and the approved FUNOMAD product families.

Source prices remain raw here. The shared retail projection applies Motion9
+5% and keeps all FUNOMAD prices inquiry-only. No merchant/order writes.
"""
from copy import deepcopy
from pathlib import Path
from urllib.parse import urljoin,urlsplit,parse_qs
from datetime import datetime,timezone
import argparse,ast,hashlib,json,re,time
from bs4 import BeautifulSoup
from mirror_schedule import ROOT,read,controls,atomic_json
from supplier_banners import Fetcher,decode
from reviewed_supplier_sources import validate_snapshot,ids_digest

def now():return datetime.now(timezone.utc).isoformat()
def pid(url):
    match=re.search(r'/product/[^/]+/(\d+)/?',url)
    return parse_qs(urlsplit(url).query).get('product_no',[match[1] if match else None])[0]
def jsvar(raw,name,default=None):
    match=re.search(r'\bvar\s+'+re.escape(name)+r'\s*=\s*(\'(?:\\.|[^\'\\])*\'|"(?:\\.|[^"\\])*")',raw)
    return ast.literal_eval(match[1]) if match else default
def amount(value):
    if value in (None,''):return None
    if isinstance(value,bool):raise ValueError('Invalid boolean price')
    text=str(value).replace(',','').strip()
    if not re.fullmatch(r'\d+(?:\.0+)?',text):raise ValueError('Unverified numeric source price')
    return int(float(text))
def clean_label(value):
    value=re.sub(r'\(\s*[0-9,]+\s*원\s*\)','',value)
    value=re.sub(r'\s*:\s*[+]?\s*[0-9,]+\s*원?','',value)
    return value.strip('[] ')

class Client:
    def __init__(self,source,folder):self.source=source;self.folder=folder;self.fetcher=Fetcher(5);self.pages=[]
    def get(self,url,allow_missing=False):
        for root in [ROOT,Path(__import__('os').environ.get('NADAUN_SHOP_MASTER_ROOT',ROOT))]:
            if controls(self.source,root).get('blocked'):raise ValueError('Source hold prevents requests')
        response=self.fetcher.get(url)
        if response.status_code in (401,403,429):
            atomic_json(ROOT/'_scraper/.sync-state'/self.source/'source-suspended.json',{'at':now(),'suspended':True,'url':url,'status':response.status_code,'automatic_resume':False});raise ValueError('Provider access protection; source preserved')
        if response.status_code==404 and allow_missing:return None
        if response.status_code!=200:raise ValueError('Source HTTP '+str(response.status_code)+' '+urlsplit(url).path)
        raw=response.content;name=hashlib.sha256(url.encode()).hexdigest()+'.html';(self.folder/name).write_bytes(raw)
        self.pages.append({'url':url,'file':name,'sha256':hashlib.sha256(raw).hexdigest(),'observed_at':now()});atomic_json(self.folder/'pages.json',{'source':self.source,'pages':self.pages})
        return raw
    def image(self,url):
        host=urlsplit(url).hostname
        if host in ('shop.nadaun.co','order.nadaun.co'):raise ValueError('Source images must not be reread through the own shop')
        response=self.fetcher.get(url)
        if response.status_code in (401,403,429):
            atomic_json(ROOT/'_scraper/.sync-state'/self.source/'source-suspended.json',{'at':now(),'suspended':True,'url':url,'status':response.status_code,'automatic_resume':False});raise ValueError('Source image access protected')
        if response.status_code!=200:raise ValueError('Source product image HTTP '+str(response.status_code))
        raw=response.content;info=decode(raw);digest=hashlib.sha256(raw).hexdigest();ext={'JPEG':'jpg','PNG':'png','WEBP':'webp','GIF':'gif','AVIF':'avif'}[info['format']]
        rel='assets/shop/supplier-details/'+self.source+'/'+digest+'.'+ext;path=ROOT/rel;path.parent.mkdir(parents=True,exist_ok=True)
        if not path.exists():path.write_bytes(raw)
        if hashlib.sha256(path.read_bytes()).hexdigest()!=digest:raise ValueError('Product image archive mismatch')
        return 'https://shop.nadaun.co/'+rel

def motion9_detail(raw,url,old=None):
    text=raw.decode('utf-8');doc=BeautifulSoup(raw,'lxml');sid=pid(url)
    schemas=[]
    for node in doc.select('script[type="application/ld+json"]'):
        try:value=json.loads(node.get_text())
        except ValueError:continue
        schemas.extend(value if isinstance(value,list) else value.get('@graph',[]) if isinstance(value,dict) and '@graph'in value else [value])
    schema=next((s for s in schemas if s.get('@type') in ('Product','ProductGroup')),None)
    identity=schema.get('sku') or schema.get('productGroupID') if schema else ''
    if not schema or not sid or not str(identity).endswith('_'+sid):raise ValueError('Motion9 product identity differs from its schema')
    variants=schema.get('hasVariant',[])
    if any(not v.get('sku','').startswith(identity+'_') for v in variants):raise ValueError('Motion9 variant belongs to another product')
    name=schema.get('name','').strip();base=amount(jsvar(text,'product_price'));offer=schema.get('offers',{})
    if isinstance(offer,list):offer=offer[0]
    declared=amount(offer.get('price'))
    if variants:declared=min(amount(v['offers']['price']) for v in variants)
    if base and declared and base!=declared:raise ValueError('Motion9 visible/script/schema prices disagree')
    base=base or declared;stock=json.loads(jsvar(text,'option_stock_data','{}'));mapping=json.loads(jsvar(text,'option_value_mapper','{}'))
    for variant in variants:
        code=variant['sku'][len(identity)+1:]
        if code not in stock or amount(variant['offers']['price'])!=amount(stock[code]['option_price']):raise ValueError('Motion9 variant schema and exact option price disagree')
    groups=[];options=[]
    for select in doc.select('select[id^="product_option_id"]'):
        title=select.get('option_title') or select.get('title') or '구성';required=select.has_attr('required') and select.get('required')!='false';values=[]
        for option in select.select('option[value]'):
            value=option['value'];label=option.get_text(' ',strip=True)
            if value in ('','*','**'):continue
            code=value if value in stock else mapping.get(value)
            row=stock.get(code)
            if not row:raise ValueError('Motion9 option has no exact stock/price identity: '+value)
            original=row.get('option_value_orginal',[])
            if not (value==code or value in original or value==row.get('option_value')):raise ValueError('Motion9 option label/code differs')
            price=amount(row.get('option_price'));unchanged=not required and ('변경사항없음' in label or '기본_튜브타이어' in label)
            if price is None:raise ValueError('Motion9 option price is unverified')
            unavailable=option.has_attr('disabled') or row.get('is_selling')=='F' or row.get('is_display')=='F' or row.get('is_auto_soldout')=='T' or '품절'in label
            o={'id':value,'source_item_code':code,'name':clean_label(label),'label':clean_label(label),'group_name':title.strip('[] '),
                'price':0 if unchanged else price,'source_displayed_price':price,'role':'base' if required else 'addon','unchanged':unchanged,
                'disabled':bool(unavailable),'soldout':bool(unavailable),'displayed':row.get('is_display')!='F','supplier_status':'soldout' if unavailable else 'available',
                'selection':[{'name':title,'value':label}]}
            options.append(o);values.append({'value':clean_label(label),'label':clean_label(label)})
        groups.append({'name':title,'required':required,'values':values})
    if not base:base=min((o['price'] for o in options if o['price']>0 and not o['disabled']),default=None)
    if not base or not name:raise ValueError('Motion9 source price/name unavailable')
    multi=len(groups)>1
    for o in options:o['additional_price']=0 if multi else o['price']-base
    main=schema.get('image',[]);main=[main] if isinstance(main,str) else main
    if not main:
        for variant in variants:
            values=variant.get('image',[]);main.extend([values] if isinstance(values,str) else values)
    detail=doc.select_one('#prdDetail') or doc.select_one('.productDetail')
    images=[]
    if detail:
        for img in detail.select('img'):
            src=img.get('data-src') or img.get('src','')
            if src and not src.startswith('data:'):images.append(urljoin(url,src))
    if not main:raise ValueError('Motion9 product gallery is missing')
    result=deepcopy(old or {})
    result.update(id='motion9-'+sid,source_id=sid,source='motion9',source_url=url,name=name,brand='MOTION9',kind='purchase',
        price=base,sale_price=base,status='inquiry',supplier_status='inquiry',detail_status='verified',detail_checked_at=now(),
        description_text=detail.get_text('\n',strip=True) if detail else '',description_text_alongside_images=True,
        description_notice='모션나인 원본의 제품·옵션 금액입니다. 기본 구성과 독립 추가 구성의 최종 조합·납기는 상담으로 확정합니다.' if multi else '제품 구성·재고·납기는 상담으로 확정합니다.',
        options=options,option_groups=groups,options_require_confirmation=multi,independent_option_groups=multi,evidence_sha256=hashlib.sha256(raw).hexdigest())
    return result,{'main':list(dict.fromkeys(urljoin(url,u) for u in main)),'detail':list(dict.fromkeys(images))}

def collect_motion9(client,previous):
    home=client.get('https://motionnine.cafe24.com/');payload=json.loads(client.get('https://motionnine.cafe24.com/exec/front/Product/SubCategory'))
    if not isinstance(payload,list) or not payload:raise ValueError('Motion9 category API is empty')
    categories=[]
    for row in payload:
        if re.search('개인결제|개별결제|배송비',row['name']):continue
        categories.append({'id':str(row['cate_no']),'name':BeautifulSoup(row['name'],'lxml').get_text(' ',strip=True),'parent_id':str(row.get('parent_cate_no')) if row.get('parent_cate_no') else None,'brand':'MOTION9','position':len(categories)})
    category_ids={c['id'] for c in categories}
    for category in categories:
        if category['parent_id'] not in category_ids:category['parent_id']=None
    if not {c['id'] for c in previous['categories']}<={c['id'] for c in categories}:raise ValueError('Motion9 approved category disappeared; retirement review required')
    members={};coverage=[];urls={}
    for category in categories:
        cid=category['id'];page=1;found={};expected=None
        while True:
            url='https://motionnine.cafe24.com/product/list.html?cate_no='+cid+'&page='+str(page);raw=client.get(url);doc=BeautifulSoup(raw,'lxml')
            count=doc.select_one('.prdCount')
            if not count:raise ValueError('Motion9 category advertised total is missing')
            match=re.search(r'[\d,]+',count.get_text());total=int(match[0].replace(',','')) if match else None
            if total is None or expected is not None and total!=expected:raise ValueError('Motion9 category count changed during collection')
            expected=total;before=len(found)
            for anchor in doc.select('.xans-product-listnormal a[href]'):
                target=urljoin(url,anchor['href']);sid=pid(target)
                if sid:found[sid]=target
            if len(found)>=expected:break
            if len(found)==before or page>=500:raise ValueError('Motion9 inventory pagination is incomplete')
            page+=1
        if len(found)!=expected:raise ValueError('Motion9 category unique count differs')
        coverage.append({'id':cid,'expected':expected,'unique':len(found)})
        for sid,url in found.items():members.setdefault(sid,[]).append(cid);urls[sid]=url
    if not urls:raise ValueError('Motion9 source inventory is empty')
    products={}
    for sid,url in urls.items():
        p,images=motion9_detail(client.get(url),url,previous['products'].get('motion9-'+sid))
        p['brand_category_ids']=members[sid]
        p['images']={role:[client.image(u) for u in values] for role,values in images.items()}
        p['images']['thumb']=p['images']['main'][0];products[p['id']]=p
        atomic_json(client.folder/'progress.json',{'at':now(),'phase':'details','expected':len(urls),'verified':len(products)})
    final_payload=json.loads(client.get('https://motionnine.cafe24.com/exec/front/Product/SubCategory'))
    if payload!=final_payload:raise ValueError('Motion9 category inventory changed during collection')
    result=deepcopy(previous);result.update(collected_at=now(),complete=True,product_count=len(products),products=products,categories=categories,
        coverage={'count':len(products),'ids_sha256':ids_digest(products)},source_category_coverage=coverage,
        evidence={'categories_verified':len(categories),'products_verified':len(products),'source_option_prices':sum(len(p['options']) for p in products.values()),'price_basis':'exact option_stock_data/option_value_mapper and visible select IDs; source amounts before +5% projection'})
    return validate_snapshot(result)

def collect_funomad(client,previous):
    from funomad_source import collect
    return collect(client,previous)

def work(source):
    if controls(source,ROOT).get('blocked'):return {'phase':'source_suspended','requests':0}
    previous=read(ROOT/'data/catalog/sources'/(source+'.json'))
    if not previous.get('complete'):raise ValueError('Approved initial supplier snapshot is required')
    folder=ROOT/'_private/catalog/manual-source-runs'/source/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ');folder.mkdir(parents=True)
    client=Client(source,folder);snapshot=collect_motion9(client,previous) if source=='motion9' else collect_funomad(client,previous)
    atomic_json(folder/'catalogue-candidate.json',snapshot)
    if snapshot['product_count']<previous['product_count']*.85:raise ValueError('Inventory decreased over15%; exact retirement review required')
    from shop_sync import run
    result=run(existing=True,source_updates={source:snapshot})
    from brand_source_policy import policy_fingerprint,publishable_ids
    path=ROOT/'data/catalog/sources'/(source+'.json');expected=publishable_ids(snapshot)
    result.update(source=source,source_collected_at=snapshot['collected_at'],source_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        verified_products=len(expected),excluded_ids=sorted(set(snapshot['products'])-expected),source_verified_products=snapshot['product_count'],policy_sha256=policy_fingerprint())
    atomic_json(ROOT/'_scraper/.sync-state'/source/'published.json',result);return result

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('source',choices=('motion9','funomad'));args=parser.parse_args()
    try:print(json.dumps(work(args.source),ensure_ascii=False),flush=True)
    except Exception as exc:
        atomic_json(ROOT/'_scraper/.sync-state'/args.source/'worker-error.json',{'at':now(),'requires_review':True,'error':type(exc).__name__+': '+str(exc)});raise
