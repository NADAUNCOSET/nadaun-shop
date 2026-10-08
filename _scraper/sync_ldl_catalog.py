"""LDL's redesigned public catalogue API and product JSON-LD, October 2026."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
import gzip
import hashlib
import json
from pathlib import Path
import re
import threading
import time
from urllib.parse import quote, urljoin, unquote

from bs4 import BeautifulSoup
import requests
from sync_shop_sources import ROOT, OUT, save_json, stamp, clean

BASE = 'https://www.l-mount.co.kr'
STATE = ROOT / '_scraper/.sync-state/l-mount'


def exact_legacy_map(previous, rows):
    """Retain an ID only for an unambiguous, complete model-code match."""
    found = {}
    for product in previous.get('products', {}).values():
        if product.get('model_code'):
            codes = [r['code'] for r in rows if r['code'] == product['model_code']]
        else:
            codes = [r['code'] for r in rows if re.search(
                r'(?<![A-Z0-9-])'+re.escape(r['code'].upper())+r'(?![A-Z0-9-])', product['name'].upper())]
            codes = [code for code in codes if not any(other != code and other.startswith(code+' ') for other in codes)]
        if len(codes) == 1:
            found.setdefault(codes[0], []).append(product['id'])
    return {code: ids[0] for code, ids in found.items() if len(ids) == 1}


def product_detail(raw, row, identity):
    doc = BeautifulSoup(raw, 'lxml')
    schemas = []
    for script in doc.select('script[type="application/ld+json"]'):
        value = json.loads(script.get_text())
        schemas.extend(value if isinstance(value, list) else value.get('@graph', [value]))
    matches = [s for s in schemas if s.get('@type') == 'Product' and s.get('sku') == row['code']]
    if len(matches) != 1:
        raise ValueError('LDL product schema identity mismatch: '+row['code'])
    schema = matches[0]; offer = schema.get('offers', {})
    url = BASE+'/products/'+quote(row['code'], safe='')
    if offer.get('priceCurrency') != 'KRW' or not str(offer.get('price', '')).isdigit():
        raise ValueError('LDL verified KRW price missing: '+row['code'])
    if int(offer['price']) != row['priceVal'] or offer.get('url') != schema.get('url') or unquote(schema.get('url','')) != unquote(url):
        raise ValueError('LDL API/detail price or identity changed: '+row['code'])
    title = doc.select_one('h1')
    identity_labels = doc.select('.detail-info > p, .buybar__code')
    if not title or not (row['code'].casefold() in title.get_text().casefold() or any(clean(x.get_text()).casefold() == row['code'].casefold() for x in identity_labels)):
        raise ValueError('LDL visible product identity missing: '+row['code'])
    body = doc.select_one('#tab-info')
    if not body or not body.get_text(' ', strip=True):
        raise ValueError('LDL description missing: '+row['code'])
    main = list(dict.fromkeys(urljoin(BASE, i['src']) for i in doc.select('#main-img[src], #gallery-thumbs img[src]')))
    if not main: main = schema.get('image') or []
    if not main: raise ValueError('LDL gallery missing: '+row['code'])
    images = list(dict.fromkeys(urljoin(BASE, i.get('data-src') or i.get('src')) for i in body.select('img[src],img[data-src]')))
    category = clean(schema.get('category'))
    if not category: raise ValueError('LDL category missing: '+row['code'])
    colors = [clean(x.get_text()) for x in doc.select('.color-opt span')]
    # The new API has one purchasable model code, with no variant price/stock
    # records. A visual color choice must not become an invented priced option.
    unknown_options = len(colors) > 1 or bool(doc.select('.detail-info select:not([name="rating"])'))
    available = row.get('purchasable') is True and row.get('soldOut') is False
    soldout = row.get('soldOut') is True
    if not isinstance(row.get('purchasable'), bool) or not isinstance(row.get('soldOut'), bool):
        raise ValueError('LDL source availability unknown: '+row['code'])
    cid = 'category-'+hashlib.sha256(category.encode()).hexdigest()[:12]
    return {'id':identity,'source_id':row['code'],'source':'l-mount','model_code':row['code'],
        'source_url':url,'name':clean(schema['name']),'brand':'LDL-MOUNT','kind':'purchase',
        'price':row['priceVal'],'sale_price':row['priceVal'],'status':'soldout' if soldout else 'inquiry',
        'supplier_status':'soldout' if soldout else 'available' if available else 'inquiry',
        'images':{'thumb':main[0],'main':main,'detail':images},
        'description_text':'\n'.join(clean(x.get_text(' ',strip=True)) for x in doc.select('#tab-info,#tab-spec,#tab-install')),
        'options':[],'option_groups':([{'name':'색상','values':[{'name':x,'value':x} for x in colors]}] if unknown_options else []),
        'options_require_confirmation':unknown_options or not available,'detail_status':'verified',
        'detail_checked_at':stamp(),'brand_category_ids':[cid], 'source_category_name':category}, {'id':cid,'name':category,'parent_id':None}


def collect(work=None):
    STATE.mkdir(parents=True, exist_ok=True)
    work = Path(work) if work else STATE / 'current'
    work.mkdir(parents=True, exist_ok=True)
    suspended = STATE/'source-suspended.json'
    if suspended.exists() and json.loads(suspended.read_text()).get('suspended', True):
        raise RuntimeError('LDL source access suspended; review required')
    gate = threading.Lock(); next_request = 0.; stopped = threading.Event()
    def get(path):
        nonlocal next_request
        with gate:
            if stopped.is_set(): raise RuntimeError('LDL requests stopped')
            time.sleep(max(0, next_request-time.monotonic())); next_request = time.monotonic()+1
        response = requests.get(BASE+path, timeout=(10,40), headers={'User-Agent':'NADAUNShopCatalog/1.0 (+https://shop.nadaun.co)'})
        if response.status_code in (403,429):
            stopped.set(); save_json(suspended, {'suspended':True,'at':stamp(),'status':response.status_code,'automatic_resume':False})
            raise RuntimeError('LDL provider protection response')
        response.raise_for_status()
        return response.content
    raw = get('/.netlify/functions/shop-catalog'); value = json.loads(raw)
    rows = value.get('products', [])
    if value.get('ok') is not True or len(rows)<100 or len({r['code'] for r in rows})!=len(rows):
        raise ValueError('LDL public API inventory incomplete')
    previous = json.loads((OUT/'l-mount.json').read_text()) if (OUT/'l-mount.json').exists() else {}
    if len(rows)<previous.get('product_count',0)*.85: raise ValueError('LDL inventory decreased more than 15%')
    mapping = exact_legacy_map(previous, rows); products = {}; categories = {}
    save_json(work/'public-catalog-before.json', value)
    def read(row):
        identity = mapping.get(row['code']) or 'ldl-model-'+hashlib.sha256(row['code'].encode()).hexdigest()[:16]
        f = work/(hashlib.sha256(row['code'].encode()).hexdigest()[:20]+'.html.gz')
        cached=f.exists() and time.time()-f.stat().st_mtime<6*3600
        if cached: page=gzip.decompress(f.read_bytes())
        else:
            page=get('/products/'+quote(row['code'],safe=''));f.write_bytes(gzip.compress(page))
        try:return product_detail(page,row,identity)
        except ValueError:
            if not cached:raise
            page=get('/products/'+quote(row['code'],safe=''));f.write_bytes(gzip.compress(page))
            return product_detail(page,row,identity)
    with ThreadPoolExecutor(max_workers=3) as pool:
        for future in as_completed([pool.submit(read,r) for r in rows]):
            product, category = future.result(); products[product['id']]=product;categories[category['id']]=category
            if len(products)%25==0:print('LDL verified details',len(products),'/',len(rows),flush=True)
    final = json.loads(get('/.netlify/functions/shop-catalog'))
    if final.get('ok') is not True or sorted(final['products'],key=lambda p:p['code']) != sorted(rows,key=lambda p:p['code']):
        raise ValueError('LDL public inventory changed during detail verification')
    result = {'complete':True,'source':'l-mount','source_url':BASE,'collected_at':stamp(),
        'product_count':len(products),'products':products,'categories':list(categories.values()),
        'coverage':[{'category_id':cid,'expected':sum(cid in p['brand_category_ids'] for p in products.values()),'unique':sum(cid in p['brand_category_ids'] for p in products.values())} for cid in categories],
        'integration':'public-catalog-api-jsonld','legacy_ids_preserved':len(mapping)}
    save_json(work/'catalogue-candidate.json',result)
    return result


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--work',type=Path);args=parser.parse_args()
    result=collect(args.work);print('LDL complete',result['product_count'],flush=True)
