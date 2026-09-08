"""Read AVX's public Firstmall catalogue, with durable checkpoints and no login.

The public search_list endpoint is the same one used by the shop's own UI.
Only complete, reconciled snapshots are exported. Aputure can finish first;
the full catalogue follows without changing any rental records.
"""
import argparse
from copy import deepcopy
from datetime import datetime
import hashlib
import json
import math
import re
import sqlite3
import time
from urllib.parse import parse_qs, urljoin, urlparse

from bs4 import BeautifulSoup
import requests
from sync_shop_sources import ROOT, OUT, clean, save_json, stamp

BASE = 'https://www.avx.co.kr'
WORK = ROOT / '_scraper/.sync-state/avx'
INTERVAL = 3.0


class SourceSuspended(RuntimeError):
    pass


class CatalogueChanged(ValueError):
    pass


class Source:
    def __init__(self, work=WORK, session=None):
        self.work = work
        work.mkdir(parents=True, exist_ok=True)
        self.session = session or requests.Session()
        self.last = 0

    def get(self, path, **params):
        latch = self.work / 'source-suspended.json'
        if latch.exists():
            raise SourceSuspended('AVX source requires manual provider review')
        time.sleep(max(0, INTERVAL - (time.monotonic() - self.last)))
        try:
            r = self.session.get(urljoin(BASE, path), params=params, timeout=(10, 35))
        finally:
            self.last = time.monotonic()
        r.encoding = 'utf-8'
        if r.status_code in (403, 429) or re.search(
                r'접근\s*금지\s*(?:아이피|IP)|비정상적인\s*접근|초단위로.*많이\s*요청|Access Denied', r.text, re.I):
            save_json(latch, {'at': stamp(), 'http_status': r.status_code,
                             'reason': 'provider_access_protection', 'automatic_resume': False})
            raise SourceSuspended('AVX protection response; no further requests')
        r.raise_for_status()
        return r.text


def number(text):
    value = re.sub(r'[^\d]', '', text or '')
    return int(value) if value else None


def menu(text):
    doc = BeautifulSoup(text, 'lxml')
    cats = {}
    for a in doc.select('a[href*="/goods/catalog"]'):
        cid = parse_qs(urlparse(a['href']).query).get('code', [''])[0]
        name = clean(a.get_text(' ', strip=True))
        if re.fullmatch(r'(\d{4})+', cid) and name:
            cats.setdefault(cid, {'id': cid, 'name': name, 'parent_id': cid[:-4] or None})
    return cats


def parse_list(text):
    doc = BeautifulSoup(text, 'lxml')
    total = re.search(r'total span[.]num["\']\)\.html\(["\']([\d,]+)', text)
    if not total:
        raise ValueError('AVX public list total missing')
    analytics = {}
    match = re.search(r"var items\s*=\s*'(\[.*?\])';", text, re.S)
    if match:
        data = json.loads(match[1].replace("\\'", "'"))
        analytics = {str(p['item_id']): p for p in data}
    products = {}
    for node in doc.select('li.goods_list_style2'):
        a = node.select_one('.goods_name_area a[href]')
        image = node.select_one('.item_img_area > a > img')
        if not a or not image:
            raise ValueError('AVX list item identity missing')
        sid = parse_qs(urlparse(a['href']).query).get('no', [''])[0]
        if not sid.isdigit() or sid in products:
            raise ValueError('AVX duplicate or invalid product ID')
        ga = analytics.get(sid, {})
        brand = node.select_one('.brand_name_area')
        price = node.select_one('.sale_price .num')
        normal = node.select_one('.consumer_price .num')
        name = clean(a.get_text(' ', strip=True))
        raw_brand = clean(brand.get_text()) if brand else clean(ga.get('item_brand'))
        # Unlabelled compatibility products remain unbranded, never claimed as OEM.
        raw_brand = raw_brand or 'AVX 기타'
        state = clean(node.get_text(' ', strip=True) + ' ' + ' '.join(
            str(i.get('alt', '')) for i in node.select('.item_img_area img[alt]')))
        unavailable = bool(re.search(r'품절|재고확보중|판매중지|SOLD\s*OUT', state, re.I))
        value = number(price.get_text()) if price else None
        path = [clean(ga.get('item_category' + (str(i) if i > 1 else ''), '')) for i in range(1, 5)]
        products[sid] = {'id': 'avx-' + sid, 'source': 'avx', 'source_id': sid,
            'source_url': BASE + '/goods/view?no=' + sid, 'name': name, 'brand': raw_brand,
            'kind': 'purchase', 'price': value, 'sale_price': value,
            'source_list_price': number(normal.get_text()) if normal else value,
            'status': 'soldout' if unavailable else 'inquiry',
            'supplier_status': 'soldout' if unavailable else 'available' if value else 'inquiry',
            'source_category_path': [x for x in path if x], 'brand_category_ids': [],
            'images': {'thumb': urljoin(BASE, image['src']), 'main': [], 'detail': []}}
    total = number(total[1])
    if total and not products:
        raise ValueError('AVX empty list with nonzero total')
    return total, products


def parse_detail(product, text, description):
    p = deepcopy(product)
    doc = BeautifulSoup(text, 'lxml')
    sid = p['source_id']
    if not re.search(r'gl_goods_seq\s*=\s*' + re.escape(sid) + r'\s*;', text):
        raise ValueError('AVX detail identity mismatch: ' + sid)
    title = doc.select_one('meta[property="og:title"]')
    if title and title.get('content'):
        p['name'] = clean(title['content'])
    prices = re.findall(r'gl_goods_price\s*=\s*(\d+)\s*;', text)
    if not prices:
        raise ValueError('AVX detail price missing: ' + sid)
    detail_price = int(prices[-1]) or None
    if re.search(r'gl_string_price_use\s*=\s*1\s*;', text):
        # Firstmall keeps a sentinel such as 99,999,999 in JavaScript when
        # the public price is "가격문의". It is not a purchasable price.
        detail_price = None
    if detail_price != p['price']:
        raise CatalogueChanged('AVX list/detail price changed: ' + sid)
    gallery = doc.select_one('#goods_thumbs')
    if gallery is None:
        raise ValueError('AVX main gallery markup missing: ' + sid)
    main = [urljoin(BASE, i['src']) for i in gallery.select('.viewImgWrap img[src]')]
    issues = [] if main else ['source_gallery_empty']
    area = doc.select_one('.goods_buttons_area')
    area_text = area.get_text(' ', strip=True) if area else ''
    if re.search(r'품절|재고확보중|판매중지|SOLD\s*OUT', area_text, re.I):
        p['supplier_status'] = p['status'] = 'soldout'
    desc = BeautifulSoup(description, 'lxml')
    description_area = desc.select_one('.goods_desc_contents.goods_description')
    body = description_area if description_area is not None else desc
    images = []
    for image in body.select('img[src],img[data-src]'):
        url = urljoin(BASE, image.get('data-src') or image.get('src') or '')
        parsed = urlparse(url)
        # AVX also embeds manufacturer-hosted detail images (e.g. Sony).
        # Keep image URLs only; never embed source HTML or scripts.
        if parsed.scheme in ('https', 'http') and parsed.netloc and not parsed.username and not parsed.password:
            images.append(url)
    text_content = clean(body.get_text(' ', strip=True))
    if not images and not text_content:
        if description_area is None:
            raise ValueError('AVX description markup missing: ' + sid)
        issues.append('source_description_empty')
    p['images']['main'] = list(dict.fromkeys(main))
    p['images']['detail'] = list(dict.fromkeys(images))
    p['description_text'] = text_content
    p['content_issues'] = issues
    p['content_status'] = 'review_required' if issues else 'complete'
    groups = []
    for select in doc.select('.goods_option_select_area select'):
        values = [{'value': str(o.get('value', '')), 'name': clean(o.get_text())}
                  for o in select.select('option[value]') if o.get('value')]
        if values:
            groups.append({'name': select.get('name', '옵션'), 'values': values})
    p['option_groups'] = groups
    p['options'] = []
    # Dynamic Firstmall combinations are preserved for review, never guessed.
    p['options_require_confirmation'] = bool(groups or doc.select('.goods_option_select_area input[type="text"]'))
    p['detail_status'] = 'verified'
    p['verified_at'] = stamp()
    return p


class Importer:
    def __init__(self, work=WORK):
        self.work = work
        self.source = Source(work)
        self._last_report = 0
        self._last_phase = None
        self.db = sqlite3.connect(work / 'checkpoint.sqlite3')
        self.db.execute('CREATE TABLE IF NOT EXISTS pages (key TEXT PRIMARY KEY, total INTEGER, payload TEXT)')
        self.db.execute('CREATE TABLE IF NOT EXISTS details (id TEXT PRIMARY KEY, fingerprint TEXT, payload TEXT)')
        self.db.execute('CREATE TABLE IF NOT EXISTS detail_errors (id TEXT PRIMARY KEY, error TEXT, at TEXT)')
        self.db.execute('CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, payload TEXT)')
        self.db.commit()

    def invalidate_listings(self, reason, category=None):
        # A catalogue can change during a long import. Preserve verified details
        # and the live snapshot, but never retry against stale page positions.
        if category is None:
            self.db.execute('DELETE FROM pages')
        else:
            self.db.execute('DELETE FROM pages WHERE key LIKE ?', (category+'/%',))
        self.db.commit()
        save_json(self.work / 'listing-refresh.json', {'at':stamp(), 'reason':reason,
            'category':category, 'verified_details_preserved':True})

    def listing(self, category=''):
        rows = {}; expected = None; page = 1
        while expected is None or page <= math.ceil(expected / 40):
            key = category + '/' + str(page)
            cached = self.db.execute('SELECT total,payload FROM pages WHERE key=?', (key,)).fetchone()
            if cached:
                total, items = cached[0], json.loads(cached[1])
            else:
                html = self.source.get('/goods/search_list', page=page, searchMode='catalog',
                    category='c' + category if category else '', per=40, sorting='regist', auto=1)
                total, items = parse_list(html)
                self.db.execute('INSERT INTO pages VALUES (?,?,?)', (key, total, json.dumps(items, ensure_ascii=False)))
                self.db.commit()
            if expected is None: expected = total
            if total != expected or set(rows) & set(items):
                self.invalidate_listings('inventory_changed_or_duplicate_page', category)
                raise CatalogueChanged('AVX inventory changed or duplicate page: ' + key)
            rows.update(items)
            self.report('listing', category=category, pages=page, found=len(rows), expected=expected)
            page += 1
            if expected == 0: break
        if len(rows) != expected:
            raise ValueError('AVX inventory coverage mismatch: ' + category)
        return rows

    def report(self, phase, **extra):
        now = time.monotonic()
        if (phase == self._last_phase == 'details' and now-self._last_report < 1
                and extra.get('found') != extra.get('expected')):
            return
        self._last_report = now
        self._last_phase = phase
        count = self.db.execute('SELECT count(*) FROM details').fetchone()[0]
        save_json(self.work / 'progress.json', {'at': stamp(), 'phase': phase,
                  'verified_details': count, 'full_catalogue_complete': False, **extra})
        print(phase, count, extra, flush=True)

    def collect(self, scope='all'):
        record = self.db.execute("SELECT payload FROM metadata WHERE key='menu'").fetchone()
        if record: cats = json.loads(record[0])
        else:
            cats = menu(self.source.get('/goods/catalog', code='0020'))
            if '0020' not in cats: raise ValueError('AVX Aputure menu absent')
            self.db.execute('INSERT INTO metadata VALUES (?,?)', ('menu', json.dumps(cats, ensure_ascii=False)))
            self.db.commit()
        ap = self.listing('0020')
        # Read actual AVX series/accessory memberships, including overlapping paths.
        acats = {cid:c for cid,c in cats.items() if cid.startswith('0020')}
        for cid in acats:
            if cid == '0020': continue
            for sid in self.listing(cid):
                if sid not in ap: raise ValueError('AVX child outside Aputure root')
                ap[sid]['brand_category_ids'].append(cid)
        for p in ap.values():
            p['brand_category_ids'].append('0020')
        pending = ap if scope == 'aputure' else self.listing()
        for sid in pending:
            if sid in ap: pending[sid]['brand_category_ids'] = ap[sid]['brand_category_ids']
        done = {}; failures = {}; consecutive_errors = 0
        # Reuse verified rows in memory: per-item SMB reads/progress rewrites
        # make a checkpoint-only replay unnecessarily slow and unstable.
        stored_rows = {sid:(fp,payload) for sid,fp,payload in self.db.execute('SELECT id,fingerprint,payload FROM details')}
        for sid in sorted(pending, key=lambda k:(k not in ap, -int(k))):
            p = pending[sid]
            fp = hashlib.sha256(json.dumps(p, sort_keys=True).encode()).hexdigest()
            stored = stored_rows.get(sid)
            if stored and stored[0] == fp:
                product = json.loads(stored[1])
            else:
                detail = self.source.get('/goods/view', no=sid)
                content = self.source.get('/goods/view_contents', no=sid, zoom=1, view_preload=1)
                try:
                    product = parse_detail(p, detail, content)
                except CatalogueChanged:
                    self.invalidate_listings('detail_price_changed')
                    raise
                except ValueError as exc:
                    failures[sid] = str(exc); consecutive_errors += 1
                    self.db.execute('INSERT OR REPLACE INTO detail_errors VALUES (?,?,?)', (sid, str(exc), stamp()))
                    self.db.commit()
                    self.report('detail_review', scope=scope, failed_product=sid, error=str(exc))
                    if consecutive_errors >= 3:
                        raise ValueError('Three consecutive AVX format errors; inspect source before resuming') from exc
                    continue
                self.db.execute('INSERT OR REPLACE INTO details VALUES (?,?,?)',
                                (sid, fp, json.dumps(product, ensure_ascii=False)))
                self.db.execute('DELETE FROM detail_errors WHERE id=?', (sid,))
                self.db.commit()
            consecutive_errors = 0
            done[sid] = product
            self.report('details', scope=scope, found=len(done), expected=len(pending))
            if set(ap) <= set(done) and not (self.work / 'aputure-complete.json').exists():
                self.export({k:done[k] for k in ap}, cats, 'aputure')
        if failures:
            raise ValueError(f'AVX has {len(failures)} unverified details; complete snapshot withheld')
        return self.export(done, cats, scope)

    def export(self, products, cats, scope):
        # Re-read first page to detect an unstable collection before publication.
        category = '0020' if scope == 'aputure' else ''
        total, first = parse_list(self.source.get('/goods/search_list', page=1, searchMode='catalog',
            category='c'+category if category else '', per=40, sorting='regist', auto=1))
        original = self.db.execute('SELECT total,payload FROM pages WHERE key=?', (category+'/1',)).fetchone()
        if not original or total != len(products) or first != json.loads(original[1]):
            previous = json.loads(original[1]) if original else {}
            save_json(self.work/'reconciliation-change.json',{'at':stamp(),'category':category,
                'expected_total':len(products),'observed_total':total,
                'added_first_page_ids':sorted(set(first)-set(previous)),
                'removed_first_page_ids':sorted(set(previous)-set(first)),
                'changed_first_page_fields':{sid:[k for k in set(previous[sid])|set(first[sid]) if previous[sid].get(k)!=first[sid].get(k)]
                    for sid in set(first)&set(previous) if first[sid]!=previous[sid]}})
            self.invalidate_listings('final_inventory_changed', category)
            raise CatalogueChanged('AVX final inventory reconciliation failed')
        categories = {}; rows = {}
        for sid, value in products.items():
            p = deepcopy(value); p['brand_category_ids'] = []
            # Series trees belong to the labelled brand, not every compatible item.
            if value['brand'].casefold() == 'aputure' and value['brand_category_ids']:
                for cid in value['brand_category_ids']:
                    while cid:
                        c = cats[cid]; key = 'aputure:' + cid
                        categories[key] = {'id':key,'name':c['name'],'brand':'Aputure',
                            'parent_id':'aputure:'+c['parent_id'] if c['parent_id'] else None}
                        p['brand_category_ids'].append(key); cid = c['parent_id']
            else:
                # Original product metadata supplies the taxonomy path for other brands.
                path = value.get('source_category_path') or [value['brand']]
                parent = None
                for n in range(len(path)):
                    key = hashlib.sha256((value['brand']+'|'+ '/'.join(path[:n+1])).encode()).hexdigest()[:16]
                    categories[key] = {'id':key,'name':path[n],'brand':value['brand'],'parent_id':parent}
                    p['brand_category_ids'].append(key); parent = key
            p['brand_category_ids'] = list(dict.fromkeys(p['brand_category_ids']))
            rows[p['id']] = p
        snapshot = {'source':'avx','scope':scope,'complete':True,'catalogue_complete':scope=='all',
            'collected_at':stamp(),'product_count':len(rows),'products':rows,
            'categories':list(categories.values()), 'coverage':{'expected':total,'unique':len(rows)},
            'brands':sorted({p['brand'] for p in rows.values()})}
        # Full AVX imports remain private candidates until the owner chooses
        # the source for each overlapping brand. Aputure is already approved.
        path = OUT/'avx-aputure.json' if scope == 'aputure' else self.work/'catalogue-candidate.json'
        if path.exists():
            previous = json.loads(path.read_text())
            if len(rows) < previous['product_count'] * .85:
                raise ValueError('AVX source decreased more than 15%; preserve previous snapshot for review')
        save_json(path, snapshot)
        save_json(self.work / (scope+'-complete.json'), {'at':stamp(),'path':str(path.relative_to(ROOT)),
            'product_count':len(rows),'source_sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
        self.report('complete', scope=scope, found=len(rows), expected=total,
                    full_catalogue_complete=scope=='all')
        return snapshot


def collect(scope='all'):
    importer = Importer()
    try: return importer.collect(scope)
    finally: importer.db.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scope', choices=('aputure','all'), default='all')
    args = parser.parse_args()
    collect(args.scope)
