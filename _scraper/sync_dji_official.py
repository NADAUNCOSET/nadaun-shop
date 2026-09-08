"""Read the Korean DJI Store's public catalogue APIs, with resumable evidence.

Only GET requests to the same product/list endpoints used by the storefront.
No login, cart, order, customer, or supplier writes. A protected response latches
the source off; a partial collection never replaces the published catalogue.
"""
import argparse
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import time
from urllib.parse import urlencode, urljoin, urlparse

from bs4 import BeautifulSoup
import requests

from sync_shop_sources import ROOT, save_json, stamp

SOURCE = 'dji-official'
STATE = ROOT/'_scraper/.sync-state'/SOURCE
STORE = 'https://store.dji.com'
# Slugs are linked by the Korean store navigation or its public redirect table.
DEPARTMENTS = [('camera-drones', '카메라 드론'), ('handheld', '핸드헬드'),
               ('robot-vacuums', '로봇 청소기'), ('service', '서비스'),
               ('accessories', '액세서리'), ('education-and-industry', '교육 & 산업')]
LOCALE = {'country': 'kr', 'language': 'ko'}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


class SourceSuspended(RuntimeError):
    pass


class Source:
    def __init__(self, folder=STATE, interval=3):
        self.folder = Path(folder)
        self.cache = self.folder/'responses'
        self.cache.mkdir(parents=True, exist_ok=True)
        self.interval = max(3, interval)
        self.last = 0
        self.session = requests.Session()

    def get(self, url, params=None, fresh=False, as_html=False):
        suspended = STATE/'source-suspended.json'
        if suspended.exists():
            raise SourceSuspended('DJI source is suspended; review the provider response before resuming')
        if urlparse(url).hostname not in ('store.dji.com', 'product.dji.com'):
            raise ValueError('Unexpected DJI API host')
        params = {**LOCALE, **(params or {})}
        key = digest([url, params])
        path = self.cache/(key+'.json')
        if path.exists() and not fresh:
            return json.loads(path.read_text())['body']
        time.sleep(max(0, self.interval-(time.monotonic()-self.last)))
        response = self.session.get(url, params=params, timeout=35)
        self.last = time.monotonic()
        if response.status_code in (403, 429) or any(s in response.text[:1500].casefold() for s in ('access denied', '접근 금지', 'captcha')):
            save_json(suspended, {'at': stamp(), 'status': response.status_code, 'url': url, 'automatic_retry': False})
            raise SourceSuspended('DJI public API access protection detected')
        response.raise_for_status()
        body = response.text if as_html else response.json()
        if isinstance(body, dict) and (body.get('success') is False or body.get('status', 200) not in (200, '200')):
            raise ValueError('DJI API rejected request: '+url)
        save_json(path, {'url': url, 'params': params, 'checked_at': stamp(), 'body': body})
        return body


def api_data(body):
    if not isinstance(body, dict) or not body.get('success') or not isinstance(body.get('data'), dict):
        raise ValueError('Invalid DJI catalogue API envelope')
    return body['data']


def image_url(value):
    if not isinstance(value, str) or not value.strip():
        return None
    url = urljoin(STORE, value.strip())
    return url if urlparse(url).scheme == 'https' else None


def text(value):
    if isinstance(value, (list, dict)):
        return '\n'.join(filter(None, (text(x) for x in (value.values() if isinstance(value, dict) else value))))
    return BeautifulSoup(str(value or ''), 'lxml').get_text('\n', strip=True)


def image_values(value):
    """Extract image objects/HTML only, not links to other products or videos."""
    result = []
    if isinstance(value, dict):
        preferred = next((value[k] for k in ('original', 'origin', 'large', 'url', 'src')
                          if isinstance(value.get(k), str) and value[k]), None)
        if preferred and re.search(r'\.(?:png|jpe?g|webp)(?:[?@]|$)', preferred, re.I):
            result.append(image_url(preferred))
        else:
            for item in value.values():
                if isinstance(item, (dict, list)):
                    result.extend(image_values(item))
    elif isinstance(value, list):
        for item in value:
            result.extend(image_values(item))
    elif isinstance(value, str):
        if '<' in value:
            result.extend(image_url(img.get('src')) for img in BeautifulSoup(value, 'lxml').select('img[src]'))
        elif re.search(r'\.(?:png|jpe?g|webp)(?:[?@]|$)', value, re.I):
            result.append(image_url(value))
    return list(dict.fromkeys(x for x in result if x))


def list_key(item):
    if item.get('type') == 'ContentPage' or item.get('render') == 'ContentPage':
        return 'content:'+str(item.get('id') or item.get('slug'))
    ean = str(item.get('ean') or '')
    # Store-created bundles use identifiers such as EAN2026061101.
    if not re.fullmatch(r'[A-Za-z0-9_-]{4,64}', ean) or not item.get('slug') or not isinstance(item.get('variantId'), int):
        raise ValueError('DJI listing identity is missing: '+str(item.get('title')))
    return ean


def listing(source, slug, tab, category=None, fresh=False):
    params = {'tab': str(tab), 'sort': 'recommendation'}
    if category:
        params['category'] = '101='+category
    items, seen, expected, pages = [], set(), None, None
    page = 1
    while pages is None or page <= pages:
        data = api_data(source.get(STORE+'/api/ec-cms/pages/list/'+slug+'/products',
                                   {**params, 'page': page}, fresh=fresh))
        info = data.get('page') or {}
        count, size = info.get('total'), info.get('pageSize')
        if info.get('current') != page or not isinstance(count, int) or not isinstance(size, int) or size < 1:
            raise ValueError('Invalid DJI pagination')
        if expected is None:
            expected, pages = count, max(1, math.ceil(count/size))
        if count != expected:
            raise ValueError('DJI list total changed while reading '+slug)
        current = data.get('items')
        if not isinstance(current, list) or len(current) != min(size, max(0, count-(page-1)*size)):
            raise ValueError('DJI page is incomplete: '+slug+'/'+str(page))
        for item in current:
            key = list_key(item)
            if key in seen:
                raise ValueError('Duplicate DJI list page/item: '+slug+'/'+key)
            seen.add(key)
            items.append(item)
        page += 1
    if len(seen) != expected:
        raise ValueError('DJI total does not match collected cards')
    return [x for x in items if not list_key(x).startswith('content:')], {
        'slug': slug, 'tab': str(tab), 'category': category, 'expected_cards': expected,
        'verified_cards': len(seen), 'product_count': sum(not k.startswith('content:') for k in seen)}


def refurbished_listing(source, fresh=False):
    # The store renders this department as a CMS page, not a paginated list.
    html=source.get(STORE+'/kr/pages/refurbished',fresh=fresh,as_html=True)
    match=re.search(r'window\.__PRELOADED_STATE__\s*=\s*',html)
    if not match:raise ValueError('DJI refurbished page state is missing')
    state,_=json.JSONDecoder().raw_decode(html[match.end():])
    locale=state['localization']
    if (locale['country'],locale['language'],locale['currency']['code'])!=('kr','ko','KRW'):
        raise ValueError('DJI refurbished locale mismatch')
    nodes={'refurbished':{'id':'refurbished','name':'공식 리퍼브 제품','parent_id':None,'brand':'DJI'}}
    rows={};memberships=defaultdict(set)
    def walk(components):
        for component in components:
            children=component.get('items',[])
            product_rows=[c for c in children if c.get('render')=='ProductRow']
            if product_rows:
                headings=[c['item']['title'] for c in children if c.get('render')=='TextSection' and c.get('item',{}).get('title')]
                if len(headings)!=1:raise ValueError('DJI refurbished category heading is ambiguous')
                cid='refurbished:'+component['slug']
                nodes[cid]={'id':cid,'name':text(headings[0]),'parent_id':'refurbished','brand':'DJI'}
                for group in product_rows:
                    for item in group['item']['products']:
                        item={**item,'variantId':item['id'],'type':'SKU'}
                        key=list_key(item);rows[key]=item;memberships[key].update(('refurbished',cid))
            walk(children)
    walk(state['event']['items'])
    urls={urlparse(a['href']).path.rsplit('/',1)[-1] for a in BeautifulSoup(html,'lxml').select('a[href]') if '/kr/product/' in a['href']}
    if not rows or {p['slug'] for p in rows.values()}!=urls:
        raise ValueError('DJI refurbished rendered links and product records differ')
    # CMS prices can be cached; verify the live product API for every listed EAN.
    live=source.get('https://product.dji.com/api/client/v3/variants',{'eans':','.join(sorted(rows)),'platform':'pc'},fresh=fresh)
    if not isinstance(live,list) or {str(p['ean']) for p in live}!=set(rows) or len(live)!=len(rows):
        raise ValueError('DJI refurbished API inventory differs')
    for p in live:
        item=rows[str(p['ean'])]
        if item['slug']!=p['slug']:raise ValueError('DJI refurbished slug mismatch')
        # This endpoint's on_sale means listed for sale, including sold-out
        # products. Preserve the CMS stock code and compare it with full detail.
        item.update(priceCents=p['price_cents'],originalPriceCents=p['original_price_cents'])
    return rows,memberships,nodes


def normalize_product(item, variant, product, categories, checked_at):
    ean = list_key(item)
    # The CMS and product service use different numeric IDs for legacy SKUs.
    # EAN plus the exact canonical product slug identifies the same sellable SKU.
    if (str(variant.get('ean')) != ean or variant.get('slug') != item.get('slug') or
        not isinstance(variant.get('id'), int)):
        raise ValueError('DJI list/detail identity mismatch: '+ean)
    if product.get('id') != variant.get('productId'):
        raise ValueError('DJI variant is attached to a different product: '+ean)
    # KRW has a subunit-to-unit ratio of one. Never divide these values by 100.
    price, original = variant.get('priceCents'), variant.get('originalPriceCents')
    if not isinstance(price, (int, float)) or price < 0 or int(price) != price:
        raise ValueError('Invalid DJI KRW price: '+ean)
    if not isinstance(original, (int, float)) or original < price or int(original) != original:
        raise ValueError('Invalid DJI original price: '+ean)
    if item.get('priceCents') != price:
        raise ValueError('DJI list/detail price mismatch: '+ean)
    status = (variant.get('status') or {}).get('code')
    if status != (item.get('status') or {}).get('code'):
        raise ValueError('DJI list/detail stock status mismatch: '+ean)
    known_statuses = {'on_sale', 'out_of_stock', 'off_sale', 'not_available', 'pre_order', 'open_to_booking'}
    if status not in known_statuses:
        raise ValueError('Unrecognized DJI stock status: '+str(status))
    main = image_values(variant.get('cover'))+image_values(variant.get('carousels'))+image_values(variant.get('photos'))
    main = list(dict.fromkeys(main))
    body = [product.get(k) for k in ('description', 'pcOverview', 'overview', 'structuredOverview', 'techSpecs', 'inTheBox', 'tips')]
    body += [variant.get(k) for k in ('shortSummary', 'coreSpecs', 'bundleDescription', 'footnote')]
    description = '\n\n'.join(dict.fromkeys(text(x) for x in body if text(x)))
    detail_images = list(dict.fromkeys(url for value in body for url in image_values(value)))
    if not main or not (description or detail_images):
        raise ValueError('DJI detailed content is empty: '+ean)
    title = text(variant.get('title'))
    if not title:
        raise ValueError('DJI title missing')
    brand='Lexar' if re.match(r'^Lexar\b',title,re.I) else 'SanDisk' if re.match(r'^SanDisk\b',title,re.I) else 'DJI'
    return {'id': SOURCE+'-'+ean, 'source': SOURCE, 'source_id': str(variant['id']),
            'ean': ean, 'official_slug': item['slug'], 'brand': brand, 'kind': 'purchase',
            'source_url': STORE+'/kr/product/'+item['slug'], 'name': title,
            'price': int(price), 'sale_price': int(price), 'source_original_price': int(original),
            'status': 'soldout' if status in ('out_of_stock', 'off_sale', 'not_available') else 'inquiry',
            'supplier_status': status, 'description_text': description,
            'images': {'thumb': main[0], 'main': main, 'detail': detail_images},
            'brand_category_ids': sorted(categories), 'detail_status': 'verified',
            'detail_checked_at': checked_at, 'options': [],
            'options_require_confirmation': False,
            'source_verification': {'listing_ean': ean, 'listing_variant_id': item['variantId'], 'variant_id': variant['id'],
                                    'product_id': product['id'], 'price_currency': 'KRW'}}


def collect(folder=STATE):
    source = Source(folder)
    folder = Path(folder)
    def progress(phase, **values):
        save_json(STATE/'progress.json', {'at': stamp(), 'phase': phase, **values})
        print(json.dumps({'phase': phase, **values}, ensure_ascii=False), flush=True)
    products, memberships, nodes, checks, menus = {}, defaultdict(set), {}, [], {}
    inventories = []
    for slug, title in DEPARTMENTS:
        menu = api_data(source.get(STORE+'/api/ec-cms/pages/list/'+slug+'/categories'))
        menus[slug] = menu
        tabs = menu.get('tabs') or []
        if not tabs:
            raise ValueError('DJI store department has no tabs: '+slug)
        root_id = slug
        nodes[root_id] = {'id': root_id, 'name': title, 'parent_id': None, 'brand': 'DJI'}
        for tab in tabs:
            code = str(tab['code'])
            tab_root=root_id
            if len(tabs)>1:
                tab_root=slug+':tab:'+code
                nodes[tab_root]={'id':tab_root,'name':tab['title'],'parent_id':root_id,'brand':'DJI'}
            data = menu if len(tabs) == 1 else api_data(source.get(STORE+'/api/ec-cms/pages/list/'+slug+'/categories', {'tab': code}))
            rows, check = listing(source, slug, code)
            checks.append(check)
            inventories.append((slug, code, {list_key(p) for p in rows}))
            for item in rows:
                ean = list_key(item)
                if ean in products and products[ean].get('variantId') != item.get('variantId'):
                    raise ValueError('DJI EAN changes identity across categories: '+ean)
                products.setdefault(ean, item)
                memberships[ean].update((root_id,tab_root))
            series = next((x for x in data.get('categories', []) if str(x['code']) == '101'), None)
            def walk(category, parent, ancestors):
                # Enterprise/education tabs reuse the same series codes.
                cid = slug+':'+code+':'+str(category['code'])
                # The store repeats ROMO / Osmo Nano parent and only-child labels.
                same = nodes[parent]['name'] == category['title']
                if not same:
                    nodes[cid] = {'id': cid, 'name': category['title'], 'parent_id': parent, 'brand': 'DJI'}
                else:
                    cid = parent
                path = set(ancestors)|{cid}
                children = category.get('children') or []
                if children:
                    for child in children:
                        walk(child, cid, path)
                else:
                    leaf_rows, leaf_check = listing(source, slug, code, str(category['code']))
                    checks.append(leaf_check)
                    for item in leaf_rows:
                        ean = list_key(item)
                        if ean not in inventories[-1][2]:
                            raise ValueError('DJI category has a product absent from its department: '+ean)
                        memberships[ean].update(path)
            if series:
                for category in series.get('children') or []:
                    walk(category, tab_root, {root_id,tab_root})
            progress('categories', department=slug, products_found=len(products), category_count=len(nodes))
    refurbished,refurb_memberships,refurb_nodes=refurbished_listing(source)
    nodes.update(refurb_nodes)
    for ean,item in refurbished.items():
        if ean in products:raise ValueError('Refurbished EAN also appears as a regular product')
        products[ean]=item;memberships[ean].update(refurb_memberships[ean])
    checks.append({'slug':'refurbished','category':None,'expected_cards':len(refurbished),'verified_cards':len(refurbished),'product_count':len(refurbished)})
    progress('details', products_found=len(products), details_verified=0)
    variant_cache, product_cache, normalized, errors, fetched_slugs = {}, {}, {}, {}, set()
    for ean, item in products.items():
        cached = variant_cache.get(ean)
        if cached is None:
            result = source.get(STORE+'/klapi/product/'+item['slug'])
            fetched_slugs.add(item['slug'])
            if not isinstance(result.get('variants'), list) or not isinstance(result.get('products'), list):
                raise ValueError('DJI full product API schema missing: '+item['slug'])
            for row in result['products']:
                product_cache[row['id']] = row
            for row in result['variants']:
                if row.get('ean'):
                    variant_cache[str(row['ean'])] = row
            cached = variant_cache.get(ean)
        if not cached or cached.get('productId') not in product_cache:
            raise ValueError('DJI product API did not return requested EAN: '+ean)
        try:
            p = normalize_product(item, cached, product_cache[cached['productId']], memberships[ean], stamp())
        except ValueError as exc:
            # A related-product pool can mark items unavailable in that bundle.
            # One fresh exact lookup also reconciles cached prices on resume.
            result=source.get(STORE+'/klapi/product/'+item['slug'],fresh=True)
            fetched_slugs.add(item['slug'])
            for row in result.get('products',[]):product_cache[row['id']]=row
            exact=next((row for row in result.get('variants',[]) if str(row.get('ean'))==ean),None)
            try:
                if not exact or exact.get('productId') not in product_cache:raise ValueError('Exact DJI detail EAN is missing')
                p=normalize_product(item,exact,product_cache[exact['productId']],memberships[ean],stamp())
                variant_cache[ean]=exact
            except ValueError as exact_error:
                errors[ean]={'slug':item['slug'],'error':str(exact_error)}
                continue
        normalized[p['id']] = p
        if len(normalized) % 20 == 0:
            progress('details', products_found=len(products), details_verified=len(normalized))
            save_json(folder/'verified-details.json', normalized)
    save_json(folder/'detail-review.json', errors)
    if errors:
        # Refresh cached department facts, so a legitimate price change does
        # not trap subsequent resumes on an older listing. Never publish here.
        for slug,tab,_ in inventories:
            listing(source,slug,tab,fresh=True)
        raise ValueError('DJI list/detail reconciliation requires review: '+str(len(errors))+' products')
    # Re-query published inventories; changing pages cannot silently retire stock.
    progress('reconciliation', products_found=len(products), details_verified=len(normalized))
    for slug, tab, expected in inventories:
        rows, check = listing(source, slug, tab, fresh=True)
        if {list_key(p) for p in rows} != expected:
            raise ValueError('DJI final inventory differs: '+slug)
        for item in rows:
            p=normalized[SOURCE+'-'+list_key(item)]
            if p['sale_price']!=item.get('priceCents') or p['supplier_status']!=(item.get('status') or {}).get('code'):
                raise ValueError('DJI price/stock changed during collection: '+list_key(item))
    for slug, expected in menus.items():
        actual = api_data(source.get(STORE+'/api/ec-cms/pages/list/'+slug+'/categories', fresh=True))
        if actual != expected:
            raise ValueError('DJI menu changed during collection: '+slug)
    actual,actual_memberships,actual_nodes=refurbished_listing(source,fresh=True)
    if set(actual)!=set(refurbished) or actual_memberships!=refurb_memberships or actual_nodes!=refurb_nodes:
        raise ValueError('DJI refurbished inventory/categories changed')
    for ean,item in actual.items():
        p=normalized[SOURCE+'-'+ean]
        if p['sale_price']!=item['priceCents'] or p['supplier_status']!=item['status']['code']:
            raise ValueError('DJI refurbished price/stock changed during collection')
    result = {'source': SOURCE, 'complete': True, 'catalogue_complete': True,
              'country': 'kr', 'language': 'ko', 'currency': 'KRW', 'collected_at': stamp(),
              'product_count': len(normalized), 'products': normalized, 'categories': list(nodes.values()),
              'coverage': {'expected': len(products), 'unique': len(normalized)}, 'category_checks': checks,
              'reference_urls': [STORE+'/kr/list/'+s for s, _ in DEPARTMENTS]+[STORE+'/kr/pages/refurbished']}
    validate_snapshot(result)
    save_json(folder/'catalogue-candidate.json', result)
    progress('complete', products_found=len(products), details_verified=len(normalized), category_count=len(nodes), published=False)
    return result


def validate_snapshot(snapshot):
    products=snapshot.get('products') or {}
    count=snapshot.get('product_count')
    if (snapshot.get('source')!=SOURCE or not snapshot.get('complete') or not snapshot.get('catalogue_complete') or
        (snapshot.get('country'),snapshot.get('language'),snapshot.get('currency'))!=('kr','ko','KRW') or
        not products or count!=len(products) or snapshot.get('coverage')!={'expected':count,'unique':count}):
        raise ValueError('DJI snapshot is incomplete or has the wrong locale')
    checks=snapshot.get('category_checks',[])
    if {c['slug'] for c in checks if not c.get('category')}!={s for s,_ in DEPARTMENTS}|{'refurbished'} or any(c['expected_cards']!=c['verified_cards'] for c in checks):
        raise ValueError('DJI department/page coverage is incomplete')
    categories={c['id']:c for c in snapshot['categories']}
    for c in categories.values():
        seen=set();cid=c['id']
        while cid:
            if cid in seen or cid not in categories:raise ValueError('Invalid DJI category ancestry')
            seen.add(cid);cid=categories[cid]['parent_id']
    for pid,p in products.items():
        if (p.get('detail_status')!='verified' or p.get('source')!=SOURCE or p.get('brand') not in ('DJI','Lexar','SanDisk') or p.get('kind')!='purchase' or
            pid!=SOURCE+'-'+p.get('ean','') or not p.get('brand_category_ids') or
            not set(p['brand_category_ids'])<=set(categories) or not p.get('images',{}).get('main') or
            not (p.get('description_text') or p['images'].get('detail')) or
            not p.get('source_url','').startswith(STORE+'/kr/product/') or
            p.get('source_verification',{}).get('price_currency')!='KRW'):
            raise ValueError('Unverified DJI product: '+pid)
    return snapshot


def official_dji_ids(snapshot):
    """Third-party cards remain in source evidence, pending a brand decision."""
    return {pid for pid,p in snapshot['products'].items() if p['brand']=='DJI'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--folder', type=Path, default=STATE)
    args = parser.parse_args()
    try:
        collect(args.folder)
    except Exception as exc:
        save_json(STATE/'worker-error.json', {'at': stamp(), 'error': type(exc).__name__+': '+str(exc), 'published': False})
        raise
