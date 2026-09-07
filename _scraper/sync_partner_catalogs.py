"""Read-only partner catalogues: complete LDL catalogue and linked gift shop."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import math
import json
import re
import time
from urllib.parse import parse_qs, urljoin, urlparse
from bs4 import BeautifulSoup
from sync_shop_sources import OUT, clean, request, save_json, stamp

LDL = 'https://www.l-mount.co.kr'
GIFT = 'https://www.nadaun-gift.com'


def soup(url, **params):
    r = request('GET', url, params=params)
    r.encoding = r.apparent_encoding if url.startswith(GIFT) else 'utf-8'
    return BeautifulSoup(r.text, 'lxml')


def number(value):
    m = re.search(r'[\d,]+', str(value or ''))
    return int(m[0].replace(',', '')) if m else None


def normalize_ldl_options(p):
    """Godo's gd_goods_view.js: ^|^ separates label; || field 1 is price."""
    groups = []; seen = set(); options = {}
    for group in p.get('option_groups', []):
        identity = tuple(v['value'] for v in group['values'])
        if identity in seen: continue
        seen.add(identity); groups.append(group)
        for value in group['values']:
            parts = value['value'].split('^|^'); fields = parts[0].split('||')
            if len(parts) < 2 or len(fields) < 2 or not re.fullmatch(r'-?\d+(?:\.\d+)?', fields[1]):
                continue
            options[fields[0]] = {'id': fields[0], 'name': clean(parts[1]),
                                  'additional_price': int(float(fields[1]))}
    p['option_groups'] = groups
    p['options'] = list(options.values()) if len(groups) == 1 else []
    p['options_require_confirmation'] = p.get('options_require_confirmation', False) and not p['options']
    return p


def ldl_categories(page):
    cats = {}
    for a in page.select('a[href*="goods_list.php?cateCd="]'):
        cid = parse_qs(urlparse(a['href']).query).get('cateCd', [''])[0]
        if re.fullmatch(r'(\d{3})+', cid) and clean(a.get_text()):
            cats.setdefault(cid, {'id': cid, 'name': clean(a.get_text()), 'parent_id': cid[:-3] or None})
    if not cats or any(c['parent_id'] and c['parent_id'] not in cats for c in cats.values()):
        raise RuntimeError('LDL category hierarchy is incomplete')
    return list(cats.values())


def ldl_list(cid):
    products = {}; total = None; pages = 1; page = 1
    while page <= pages:
        doc = soup(LDL + '/goods/goods_list.php', cateCd=cid, page=page, pageNum=40, sort='date')
        counter = doc.select_one('.pick_list_num strong')
        if counter is None: raise RuntimeError('LDL list total missing: ' + cid)
        count = number(counter.get_text()) or 0
        if total is None: total = count
        if count != total: raise RuntimeError('LDL list changed during collection: ' + cid)
        pages = max(pages, math.ceil(total / 40))
        for a in doc.select('.pagination a[href]'):
            pages = max(pages, int(parse_qs(urlparse(a['href']).query).get('page', ['1'])[0]))
        found = set()
        for node in doc.select('.goods_list .item_cont'):
            a = node.select_one('a[href*="goods_view.php?goodsNo="]')
            if a is None: continue
            sid = parse_qs(urlparse(a['href']).query)['goodsNo'][0]
            name = node.select_one('.item_name'); image = node.select_one('.item_photo_box img')
            if not name or not image: raise RuntimeError('LDL product identity missing: ' + sid)
            found.add(sid)
            products[sid] = {'id': 'ldl-'+sid, 'source_id': sid, 'source': 'l-mount',
                'source_url': LDL+'/goods/goods_view.php?goodsNo='+sid,
                'name': clean(name.get_text()), 'brand': 'LDL-MOUNT', 'kind': 'purchase',
                'status': 'inquiry', 'brand_category_ids': [cid],
                'images': {'thumb': urljoin(LDL, image['src']), 'main': [], 'detail': []}}
        if total and not found: raise RuntimeError('LDL empty page: '+cid+' / '+str(page))
        page += 1
    if len(products) != total:
        raise RuntimeError(f'LDL category coverage mismatch {cid}: {len(products)} / {total}')
    return cid, products, {'category_id': cid, 'expected': total, 'unique': len(products), 'pages': pages}


def ldl_detail(product):
    p = deepcopy(product)
    for attempt in range(3):
        doc = soup(p['source_url'])
        title = doc.select_one('.item_detail_tit h3')
        price = doc.select_one('input[name="set_goods_price"]')
        if title is not None and price is not None:break
        time.sleep(attempt+1)
    if title is None or price is None: raise RuntimeError('LDL detail missing: ' + p['id'])
    p['name'] = clean(title.get_text()); p['price'] = number(price.get('value'))
    p['sale_price'] = p['price']  # Public supplier price; never label it as our discount.
    if p['price'] is None: raise RuntimeError('LDL price missing: ' + p['id'])
    main = [urljoin(LDL, i['src']) for i in doc.select('#mainImage img[src], .slider_goods_nav img[src]')]
    full_gallery=[]
    for script in doc.select('script'):
        for fragment in re.findall(r'detailKeyID\[\d+\]\s*=\s*("(?:\\.|[^"\\])*")',script.get_text()):
            markup=BeautifulSoup(json.loads(fragment),'lxml')
            full_gallery.extend(urljoin(LDL,i['src']) for i in markup.select('img[src]'))
    if full_gallery:main=full_gallery
    detail = [urljoin(LDL, i['src']) for i in doc.select('#detail .detail_explain_box img[src]')]
    p['images']['main'] = list(dict.fromkeys(main))
    p['images']['detail'] = list(dict.fromkeys(u.replace('http://', 'https://', 1) for u in detail))
    desc = doc.select_one('.shortDescription_position')
    text = doc.select_one('#detail .txt-manual')
    p['description_text'] = '\n'.join(clean(n.get_text(' ', strip=True)) for n in [desc, text] if n)
    p['options'] = []; p['option_groups'] = []
    for select in doc.select('select[name^="optionSno"], select[name^="optionNo"]'):
        values = [{'name': clean(o.get_text()), 'value': o.get('value')} for o in select.select('option[value]') if o.get('value')]
        if values: p['option_groups'].append({'name': select.get('title') or '상품 옵션', 'values': values})
    flag = doc.select_one('input[name="optionFl"]')
    p['options_require_confirmation'] = bool(flag and flag.get('value') == 'y')
    p['detail_status'] = 'verified'
    p['supplier_status'] = 'soldout' if doc.select_one('.btn_goods_soldout') else 'inquiry'
    return normalize_ldl_options(p)


def collect_lmount():
    home = soup(LDL+'/main/index.php'); cats = ldl_categories(home)
    products = {}; audit = []
    with ThreadPoolExecutor(max_workers=3) as pool:
        for cid, rows, report in pool.map(ldl_list, [c['id'] for c in cats]):
            audit.append(report)
            for sid, p in rows.items():
                if sid in products: products[sid]['brand_category_ids'].append(cid)
                else: products[sid] = p
    # Root pages and leaf pages are collected independently; each category's
    # advertised total must match before any snapshot replaces the last one.
    print(f'LDL: {len(cats)} categories / {len(products)} unique products; reading details', flush=True)
    complete = {}
    with ThreadPoolExecutor(max_workers=3) as pool:
        for p in pool.map(ldl_detail, products.values()):
            complete[p['id']] = p
            if len(complete) % 50 == 0: print('LDL details:', len(complete), flush=True)
    final_cats = ldl_categories(soup(LDL+'/main/index.php'))
    if cats != final_cats: raise RuntimeError('LDL navigation changed during collection')
    result = {'complete': True, 'source': 'l-mount', 'source_url': LDL, 'collected_at': stamp(),
              'categories': cats, 'products': complete, 'product_count': len(complete), 'coverage': audit}
    save_json(OUT/'l-mount.json', result)
    print('LDL complete:', len(complete), flush=True)
    return result


def collect_gift():
    doc = soup(GIFT+'/'); categories = {}; products = {}
    for a in doc.select('a[href*="/search/allmain.php"]'):
        cid = parse_qs(urlparse(a['href']).query).get('cid', [''])[0]
        name = clean(a.get_text(' ', strip=True))
        if cid.isdigit() and name:
            categories.setdefault(cid, {'id': cid, 'name': name, 'url': urljoin(GIFT, a['href'])})
    for node in doc.select('.gbox'):
        a = node.select_one('a[href*="detail.php?code="]'); im = node.select_one('img[src]')
        if not a or not im: continue
        sid = parse_qs(urlparse(a['href']).query).get('code', [''])[0]
        if not sid.isdigit(): continue
        name = clean(im.get('alt'))
        if not name: continue
        products.setdefault(sid, {'id': sid, 'name': name, 'image': urljoin(GIFT, im['src']),
                                 'url': GIFT+'/new/shop/detail.php?code='+sid})
    if len(categories) < 100 or len(products) < 8: raise RuntimeError('Gift navigation/selection is incomplete')
    previous=OUT/'nadaun-gift.json'
    if previous.exists() and len(categories)<json.loads(previous.read_text())['category_count']*.85:
        raise RuntimeError('Gift category count dropped more than 15%; review before publishing')
    result = {'complete': True, 'source_url': GIFT+'/', 'collected_at': stamp(),
              'integration': 'linked-store', 'categories': list(categories.values()),
              'featured_products': list(products.values()), 'category_count': len(categories)}
    save_json(OUT/'nadaun-gift.json', result)
    print('Gift linked categories / homepage products:', len(categories), len(products), flush=True)
    return result


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(); parser.add_argument('source', choices=['l-mount','gift','all'])
    args = parser.parse_args()
    if args.source in ('l-mount','all'): collect_lmount()
    if args.source in ('gift','all'): collect_gift()
