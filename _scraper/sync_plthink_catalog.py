"""Read-only PLTHINK brand catalogue. Publish only a fully reconciled snapshot.

The previous makeshop.py records are preserved; this importer owns only the new
data/catalog source. Public category totals and unique IDs are checked together.
"""
from copy import deepcopy
from datetime import datetime, timezone
import json
import re
import threading
import time
from urllib.parse import parse_qs, urljoin, urlparse
from bs4 import BeautifulSoup
import requests
from sync_shop_sources import OUT, ROOT, clean, save_json, stamp
from source_transport import interrupted_get
from plthink_checkpoint import Checkpoint
from sync_gift_inventory import run_lock

BASE = 'https://www.plthink.com'
CHECKPOINT = ROOT / '_scraper/.sync-state/plthink-details.json'
WORK = ROOT / '_scraper/.sync-state/plthink'
RATE_STATE = ROOT / '_scraper/.sync-state/plthink-rate-limit.json'
_rate_lock = threading.Lock()
_halt = threading.Event()
_next_request = 0.0


class SourceRateLimited(RuntimeError):
    pass


def decode_page(content):
    # MakeShop declares UTF-8 even for some CP949 responses. Decode actual bytes
    # strictly so broken Korean can never enter a verified product snapshot.
    for encoding in ('utf-8-sig','cp949'):
        try:return content.decode(encoding)
        except UnicodeDecodeError:continue
    raise ValueError('PLTHINK response encoding could not be verified')


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
            response=interrupted_get(requests.get,url,params=params,timeout=(8,35),allow_redirects=False)
        finally:_next_request=time.monotonic()+2.1
        body=decode_page(response.content) if hasattr(response,'content') else response.text
        if response.status_code in (403,429) or any(s in body for s in ('페이지를 너무 많이 요청','서버보호차원에서 차단')):
            _halt.set()
            retry=response.headers.get('Retry-After','')
            wait=max(3600,int(retry) if retry.isdigit() else 3600)
            save_json(RATE_STATE,{'blocked_at':stamp(),'retry_not_before':time.time()+wait,'reason':'source request rate limit'})
            raise SourceRateLimited('PLTHINK temporarily limited page requests; no snapshot published')
        if response.status_code != 200:raise RuntimeError('PLTHINK source unavailable: HTTP '+str(response.status_code))
        return BeautifulSoup(body,'lxml')


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
        if '\ufffd' in name.get_text() or '\ufffd' in brand['name']:
            raise ValueError('PLTHINK product name contains invalid replacement characters')
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


def collect_brand(brand, checkpoint=None):
    products={}; expected=None; last=1; n=1; categories={}
    while n <= last:
        if n > 1000: raise RuntimeError('PLTHINK pagination exceeded safety limit')
        saved=checkpoint.page(brand['id'],n) if checkpoint else None
        if saved:rows,total,end,cats=saved
        else:
            doc=page(BASE+'/shop/shopbrand.html',type='M',xcode='008',mcode=brand['id'],sort='order',page=n)
            rows,total,end,cats=list_page(doc,brand)
        if expected is None:expected=total
        if total!=expected:raise RuntimeError('PLTHINK source count changed during collection: '+brand['id'])
        if total and not (set(rows)-set(products)):
            raise RuntimeError('PLTHINK empty/repeated page: '+brand['id']+' / '+str(n))
        if set(rows)&set(products):raise RuntimeError('PLTHINK duplicate product across pages: '+brand['id'])
        if checkpoint and not saved:checkpoint.save_page(brand['id'],n,[rows,total,end,cats])
        products.update(rows);categories.update({c['id']:c for c in cats});last=max(last,end)
        n+=1;time.sleep(.12)
    if len(products)!=expected:
        raise RuntimeError(f'PLTHINK coverage mismatch {brand["id"]}: {len(products)} / {expected}')
    return products,list(categories.values()),{'brand_id':brand['id'],'expected':expected,'unique':len(products),'pages':last}


def detail(doc, product):
    p=deepcopy(product);schema=None
    for script in doc.select('script[type="application/ld+json"]'):
        # Some source product names contain literal newlines inside JSON strings.
        # Accept JSON string controls only; never evaluate or repair executable JS.
        try:
            raw=script.get_text()
            # MakeShop also applies PHP-style \' escaping to inch/foot names.
            # Remove only an odd, JSON-invalid escape before an apostrophe.
            raw=re.sub(r"\\+(?=')",lambda m:'\\'*(len(m[0])-len(m[0])%2),raw)
            obj=json.loads(raw,strict=False)
        except (ValueError,TypeError):continue
        candidates=obj if isinstance(obj,list) else obj.get('@graph',[obj])
        schema=next((o for o in candidates if o.get('@type')=='Product'),schema)
    if not schema or not doc.select_one('.thumb img'):
        raise RuntimeError('PLTHINK verified detail missing: '+p['id'])
    if parse_qs(urlparse(str(schema.get('@id',''))).query).get('branduid') != [str(p['source_id'])]:
        raise RuntimeError('PLTHINK detail identity mismatch: '+p['id'])
    p['name']=clean(BeautifulSoup(schema['name'],'html.parser').get_text(' ',strip=True))
    if not p['name']:raise RuntimeError('PLTHINK detail name missing: '+p['id'])
    if '\ufffd' in p['name']:raise ValueError('PLTHINK detail name contains invalid replacement characters')
    offer=schema.get('offers') or {}
    if isinstance(offer,list):offer=offer[0] if offer else {}
    availability=str(offer.get('availability','')).rsplit('/',1)[-1]
    if availability in ('OutOfStock','SoldOut','Discontinued'):
        p['supplier_status']='soldout';p['status']='soldout'
    elif availability in ('InStock','PreOrder','PreSale','BackOrder','LimitedAvailability'):
        p['supplier_status']=availability;p['status']='inquiry'
    else:p['supplier_status']='unknown';p['status']='inquiry'
    # Supplier amounts remain source facts; they do not establish our discount.
    if offer.get('price') is not None:
        amount=float(offer['price'])
        if not amount.is_integer() or amount<0:raise RuntimeError('PLTHINK detail price invalid: '+p['id'])
        p['source_sale_price']=int(amount)
        # MakeShop encodes price-on-request service listings as price 0.
        # Preserve the source fact without advertising a free product.
        p['sale_price']=int(amount) if amount>0 else None
    original=doc.select_one('.table-opt strike')
    p['source_original_price']=number(original.get_text()) if original else p['sale_price']
    p['price']=p['sale_price']
    p['source_sku']=schema.get('sku');p['source_mpn']=schema.get('mpn')
    p['description_text']=clean(BeautifulSoup(schema.get('description',''),'html.parser').get_text(' ',strip=True))
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


def _collect_plthink(checkpoint):
    brands=brand_menu(page(BASE+'/shop/shopbrand.html',xcode='008'))
    try:checkpoint.menu(brands)
    except ValueError:checkpoint.restart(brands)
    products={};categories={};coverage=[]
    for brand in brands:
        rows,cats,audit=collect_brand(brand,checkpoint)
        categories.update({c['id']:c for c in cats});coverage.append(audit)
        for sid,p in rows.items():
            if sid in products:
                products[sid]['brand_category_ids']=list(dict.fromkeys(products[sid]['brand_category_ids']+p['brand_category_ids']))
            else:products[sid]=p
        report('listing',len(coverage),len(brands),len(products),0)
    # Resolve a card's leaf only if that named category exists in the source menu.
    for p in products.values():p['brand_category_ids']=[cid for cid in p['brand_category_ids'] if cid in categories]
    previous=OUT/'plthink.json'
    if previous.exists() and len(products)<json.loads(previous.read_text())['product_count']*.85:
        raise RuntimeError('PLTHINK count dropped more than 15%; review before publishing')
    completed={};failures={};consecutive_errors=0
    for listing in products.values():
        p=checkpoint.detail(listing)
        if p and (p.get('price')==0 or re.search(r'<[^>]+>',p.get('name',''))):p=None
        if p and (datetime.now(timezone.utc)-datetime.fromisoformat(p['detail_checked_at'])).total_seconds()>12*3600:p=None
        if p is None:
            doc=page(listing['source_url'])  # Transport/rate limits still stop the source.
            try:p=detail(doc,listing)
            except (ValueError,RuntimeError,KeyError,TypeError) as exc:
                failures[listing['id']]={'checked_at':stamp(),'error':type(exc).__name__+': '+str(exc)}
                save_json(WORK/'detail-errors.json',{'generation':checkpoint.run,'failures':failures,'published':False})
                consecutive_errors+=1
                if consecutive_errors>=3:raise RuntimeError('PLTHINK consecutive detail format failures; verified records preserved') from exc
                continue
            checkpoint.save_detail(listing,p)
        consecutive_errors=0
        completed[p['id']]=p
        if len(completed)%25==0:report('details',len(brands),len(brands),len(products),len(completed))
    save_json(WORK/'detail-errors.json',{'generation':checkpoint.run,'failures':failures,'published':False})
    if failures:raise RuntimeError(f'PLTHINK {len(failures)} details need review; all other verified records preserved')
    # Re-read every brand count and first page before publishing the generation.
    changed=[]
    for brand,audit in zip(brands,coverage):
        rows,total,_,_=list_page(page(BASE+'/shop/shopbrand.html',type='M',xcode='008',mcode=brand['id'],sort='order',page=1),brand)
        first=checkpoint.page(brand['id'],1)[0]
        if total!=audit['expected'] or set(rows)!=set(first):
            changed.append(brand['id'])
    final_menu=brand_menu(page(BASE+'/shop/shopbrand.html',xcode='008'))
    if brands!=final_menu:
        checkpoint.restart(final_menu)
        raise RuntimeError('PLTHINK brand navigation changed; a new resumable generation is ready')
    if changed:
        checkpoint.restart(brands,changed)
        raise RuntimeError('PLTHINK changed categories queued for reconciliation: '+','.join(changed))
    result={'complete':True,'source':'plthink','source_url':BASE,'collected_at':stamp(),
            'brands':brands,'categories':list(categories.values()),'products':completed,
            'product_count':len(completed),'coverage':coverage}
    save_json(WORK/'catalogue-candidate.json',result)
    checkpoint.finish()
    report('verified',len(brands),len(brands),len(products),len(completed))
    return result


def report(phase,brands,total,products,details):
    status={'checked_at':stamp(),'phase':phase,'brands_checked':brands,'brand_count':total,
            'products_found':products,'details_verified':details,'snapshot_complete':phase=='verified','published':False}
    save_json(WORK/'progress.json',status)
    print(json.dumps(status,ensure_ascii=False),flush=True)


def collect_plthink():
    WORK.mkdir(parents=True,exist_ok=True)
    with run_lock(WORK):
        checkpoint=Checkpoint(WORK/'checkpoint.sqlite3')
        try:return _collect_plthink(checkpoint)
        except Exception as exc:
            save_json(WORK/'last-error.json',{'at':stamp(),'error':type(exc).__name__+': '+str(exc),'published':False})
            raise
        finally:checkpoint.close()


if __name__=='__main__':collect_plthink()
