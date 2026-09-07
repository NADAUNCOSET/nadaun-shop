"""Read-only PLTHINK brand catalogue. Publish only a fully reconciled snapshot.

The previous makeshop.py records are preserved; this importer owns only the new
data/catalog source. Public category totals and unique IDs are checked together.
"""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
import re
import threading
import time
from urllib.parse import parse_qs, urljoin, urlparse
from bs4 import BeautifulSoup
import requests
from sync_shop_sources import OUT, ROOT, clean, save_json, stamp

BASE = 'https://www.plthink.com'
CHECKPOINT = ROOT / '_scraper/.sync-state/plthink-details.json'
RATE_STATE = ROOT / '_scraper/.sync-state/plthink-rate-limit.json'
_rate_lock = threading.Lock()
_halt = threading.Event()
_next_request = 0.0


class SourceRateLimited(RuntimeError):
    pass


def page(url, **params):
    global _next_request
    with _rate_lock:
        if _halt.is_set():raise SourceRateLimited('PLTHINK paused after source rate limit')
        if RATE_STATE.exists():
            state=json.loads(RATE_STATE.read_text())
            if time.time()<state.get('retry_not_before',0):
                raise SourceRateLimited('PLTHINK source cooldown is still active')
        time.sleep(max(0,_next_request-time.monotonic()))
        try:
            response=requests.get(url,params=params,timeout=(8,35))
        finally:_next_request=time.monotonic()+2.1
        response.encoding=response.apparent_encoding
        if response.status_code==429 or any(s in response.text for s in ('페이지를 너무 많이 요청','서버보호차원에서 차단')):
            _halt.set()
            retry=response.headers.get('Retry-After','')
            wait=max(3600,int(retry) if retry.isdigit() else 3600)
            save_json(RATE_STATE,{'blocked_at':stamp(),'retry_not_before':time.time()+wait,'reason':'source request rate limit'})
            raise SourceRateLimited('PLTHINK temporarily limited page requests; no snapshot published')
        response.raise_for_status()
        return BeautifulSoup(response.text,'lxml')


def absolute(value):
    value = re.sub(r'^https?://(https?://)', r'\1', value or '')
    return urljoin(BASE, value).replace('http://', 'https://', 1)


def number(value):
    match = re.search(r'\d[\d,]*', clean(value))
    return int(match[0].replace(',', '')) if match else None


def brand_menu(doc):
    brands = {}
    for a in doc.select('.brand-category a[href*="shopbrand.html"]'):
        q = parse_qs(urlparse(a['href']).query)
        if q.get('xcode') != ['008'] or not q.get('mcode'): continue
        label = clean(a.get_text(' ', strip=True))
        if not label: continue
        cid = q['mcode'][0]
        brands[cid] = {'id': cid, 'name': label.split('(')[0].strip(), 'label': label}
    if len(brands) < 100: raise RuntimeError('PLTHINK brand menu is incomplete')
    return list(brands.values())


def list_page(doc, brand):
    count = doc.select_one('#productClass .item-total')
    if count is None: raise RuntimeError('PLTHINK category count missing: '+brand['id'])
    total = number(count.get_text())
    if total is None: raise RuntimeError('PLTHINK category count invalid: '+brand['id'])
    products = {}
    for node in doc.select('#productClass .item-list-2021 > .item-list'):
        a = node.select_one('a[href*="shopdetail.html?branduid="]')
        name = node.select_one('h3'); im = node.select_one('.item-img img')
        if a is None or name is None or im is None:
            raise RuntimeError('PLTHINK product identity missing in '+brand['id'])
        q = parse_qs(urlparse(a['href']).query); sid = q['branduid'][0]
        price = node.select_one('.price h4'); original = node.select_one('.price strike')
        sale = number(price.get_text()) if price else None
        cats = [brand['id']]
        if q.get('mcode') == [brand['id']] and q.get('scode'):
            cats.append(brand['id']+':'+q['scode'][0])
        products[sid] = {'id':'plthink-'+sid,'source':'plthink','source_id':sid,
            'source_url':BASE+'/shop/shopdetail.html?branduid='+sid,
            'name':clean(name.get_text()),'brand':brand['name'],'kind':'purchase',
            'brand_category_ids':cats,'price':number(original.get_text()) if original else sale,
            'sale_price':sale,'status':'inquiry',
            'images':{'thumb':absolute(im.get('src')),'main':[],'detail':[]}}
    pages = [int(parse_qs(urlparse(a['href']).query).get('page',['1'])[0])
             for a in doc.select('#productClass .paging a[href*="page="]')]
    cats = [{'id':brand['id'],'name':brand['label'],'parent_id':None,'brand':brand['name']}]
    for a in doc.select('#productClass .class-list a[href*="scode="]'):
        q = parse_qs(urlparse(a['href']).query)
        if q.get('mcode') == [brand['id']] and q.get('scode'):
            cats.append({'id':brand['id']+':'+q['scode'][0],'name':clean(a.get_text()),
                         'parent_id':brand['id'],'brand':brand['name']})
    return products, total, max(pages, default=1), cats


def collect_brand(brand):
    products={}; expected=None; last=1; n=1; categories={}
    while n <= last:
        if n > 1000: raise RuntimeError('PLTHINK pagination exceeded safety limit')
        doc=page(BASE+'/shop/shopbrand.html',type='M',xcode='008',mcode=brand['id'],sort='order',page=n)
        rows,total,end,cats=list_page(doc,brand)
        if expected is None:expected=total
        if total!=expected:raise RuntimeError('PLTHINK source count changed during collection: '+brand['id'])
        if total and not (set(rows)-set(products)):
            raise RuntimeError('PLTHINK empty/repeated page: '+brand['id']+' / '+str(n))
        products.update(rows);categories.update({c['id']:c for c in cats});last=max(last,end)
        n+=1;time.sleep(.12)
    if len(products)!=expected:
        raise RuntimeError(f'PLTHINK coverage mismatch {brand["id"]}: {len(products)} / {expected}')
    return products,list(categories.values()),{'brand_id':brand['id'],'expected':expected,'unique':len(products),'pages':last}


def detail(doc, product):
    p=deepcopy(product);schema=None
    for script in doc.select('script[type="application/ld+json"]'):
        try:obj=json.loads(script.get_text())
        except (ValueError,TypeError):continue
        candidates=obj if isinstance(obj,list) else obj.get('@graph',[obj])
        schema=next((o for o in candidates if o.get('@type')=='Product'),schema)
    if not schema or not doc.select_one('.thumb img'):
        raise RuntimeError('PLTHINK verified detail missing: '+p['id'])
    if str(p['source_id']) not in str(schema.get('@id','')):
        raise RuntimeError('PLTHINK detail identity mismatch: '+p['id'])
    p['name']=clean(schema['name'])
    offer=schema.get('offers') or {}
    if isinstance(offer,list):offer=offer[0] if offer else {}
    availability=str(offer.get('availability','')).rsplit('/',1)[-1]
    if availability in ('OutOfStock','SoldOut','Discontinued'):
        p['supplier_status']='soldout';p['status']='soldout'
    elif availability in ('InStock','PreOrder','PreSale','BackOrder','LimitedAvailability'):
        p['supplier_status']=availability;p['status']='inquiry'
    else:p['supplier_status']='unknown';p['status']='inquiry'
    # Supplier amounts remain source facts; they do not establish our discount.
    if offer.get('price') is not None:p['sale_price']=int(float(offer['price']))
    original=doc.select_one('.table-opt strike')
    p['price']=number(original.get_text()) if original else p['sale_price']
    p['source_sku']=schema.get('sku');p['source_mpn']=schema.get('mpn')
    p['description_text']=clean(schema.get('description',''))
    p['images']['main']=list(dict.fromkeys(absolute(i['src']) for i in doc.select('.thumb img[src]')))
    body=doc.select_one('.detail-con-img')
    if body is None:raise RuntimeError('PLTHINK description region missing: '+p['id'])
    text=clean(body.get_text(' ',strip=True))
    if text:p['description_text']+='\n'+text
    raw=list(dict.fromkeys(absolute(i.get('src') or i.get('data-src')) for i in body.select('img[src],img[data-src]')))
    p['source_detail_images']=raw
    p['images']['detail']=[u for u in raw if not re.search(r'all_common|/event/|/delay/|makeshop-notice|/homepage/',u,re.I)]
    # Keep complex MakeShop combinations for a later reviewed option adapter.
    groups=[]
    for select in doc.select('#optionWrap select'):
        values=[{'name':clean(o.get_text()),'value':o.get('value')} for o in select.select('option[value]') if o.get('value')]
        if values:groups.append({'name':select.get('name') or '상품 옵션','values':values})
    option_data=re.search(r'var\s+optionJsonData\s*=\s*([^;]*);',str(doc))
    encoded=option_data[1].strip() if option_data else ''
    p['option_groups']=groups;p['options']=[]
    p['options_require_confirmation']=bool(groups or encoded not in ('','null','[]','{}','undefined'))
    p['source_option_data']=encoded
    p['detail_status']='verified';p['detail_checked_at']=stamp()
    return p


def collect_plthink():
    brands=brand_menu(page(BASE+'/shop/shopbrand.html',xcode='008'))
    products={};categories={};coverage=[]
    with ThreadPoolExecutor(max_workers=3) as pool:
        for rows,cats,audit in pool.map(collect_brand,brands):
            categories.update({c['id']:c for c in cats});coverage.append(audit)
            for sid,p in rows.items():
                if sid in products:
                    products[sid]['brand_category_ids']=list(dict.fromkeys(products[sid]['brand_category_ids']+p['brand_category_ids']))
                else:products[sid]=p
            print('PLTHINK brands:',len(coverage),'/',len(brands),'products:',len(products),flush=True)
    # Resolve a card's leaf only if that named category exists in the source menu.
    for p in products.values():p['brand_category_ids']=[cid for cid in p['brand_category_ids'] if cid in categories]
    previous=OUT/'plthink.json'
    if previous.exists() and len(products)<json.loads(previous.read_text())['product_count']*.85:
        raise RuntimeError('PLTHINK count dropped more than 15%; review before publishing')
    completed={}
    # Checkpoint belongs to this exact listing and this run date; stale data is
    # never silently accepted as a fresh inventory check after an interrupted run.
    cache=json.loads(CHECKPOINT.read_text()) if CHECKPOINT.exists() else {}
    day=stamp()[:10]
    def one(p):
        old=cache.get(p['id'])
        if old and old.get('detail_checked_at','').startswith(day) and old.get('listing')==p:
            return old['product']
        result=detail(page(p['source_url']),p);time.sleep(.12);return result
    try:
        with ThreadPoolExecutor(max_workers=3) as pool:
            for p in pool.map(one,products.values()):
                completed[p['id']]=p
                cache[p['id']]={'listing':products[p['source_id']],'product':p,'detail_checked_at':p['detail_checked_at']}
                if len(completed)%100==0:
                    print('PLTHINK details:',len(completed),'/',len(products),flush=True)
                    save_json(CHECKPOINT,cache)
    finally:save_json(CHECKPOINT,cache)
    if brands!=brand_menu(page(BASE+'/shop/shopbrand.html',xcode='008')):
        raise RuntimeError('PLTHINK brand navigation changed during collection')
    result={'complete':True,'source':'plthink','source_url':BASE,'collected_at':stamp(),
            'brands':brands,'categories':list(categories.values()),'products':completed,
            'product_count':len(completed),'coverage':coverage}
    save_json(OUT/'plthink.json',result)
    print('PLTHINK complete:',len(completed),flush=True)
    return result


if __name__=='__main__':collect_plthink()
