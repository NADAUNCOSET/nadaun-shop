"""Resume a complete read-only gift inventory scan; never publish partial data.

This is the public product index stage. It does not claim that option tiers,
supplier contacts, stock quantities or checkout have been synchronized.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import argparse
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import time
from urllib.parse import parse_qs, urljoin, urlparse

from bs4 import BeautifulSoup
import requests
from gift_supplier_registry import PRIVATE_ROOT, private_path

BASE = 'https://www.nadaun-gift.com'
LIST_URL = BASE + '/new/search/allmain.php'


def stamp():
    return datetime.now(timezone.utc).isoformat()


def document(text):
    return BeautifulSoup(text, 'lxml')


def root_categories(doc):
    roots = []
    for a in doc.select('a[href]'):
        u = urlparse(urljoin(BASE, a['href']))
        q = parse_qs(u.query)
        if u.hostname not in ('www.nadaun-gift.com', 'nadaun-gift.com'):
            continue
        cid = q.get('cid', [''])[0]
        if u.path == '/new/search/allmain.php' and cid.isdigit() and q.get('main_cid') == [cid]:
            if cid not in roots:
                roots.append(cid)
    if len(roots) < 10:
        raise ValueError('Gift root navigation is incomplete')
    return roots


def parse_page(doc, cid, page):
    area = doc.select_one('#allview_list')
    heading = area.select_one('h3') if area else None
    match = re.search(r'카테고리\s*내\s*([\d,]+)\s*개의\s*상품', heading.get_text(' ', strip=True) if heading else '')
    if not match:
        raise ValueError('Gift category total is missing')
    total = int(match[1].replace(',', ''))
    name = heading.select_one('font').get_text(strip=True)
    ends = [int(parse_qs(urlparse(a['href']).query).get('p', ['1'])[0])
            for a in area.select('.paging_new a[href*="p="]')]
    last = max([1, math.ceil(total / 30), *ends])
    active = {a.get_text(strip=True) for a in area.select('.paging_new a.std')}
    if total and active != {str(page)}:
        raise ValueError('Gift source returned the wrong page')
    rows = []
    for li in area.select('.productList > ul > li'):
        a = li.select_one('a.link[href]')
        image = a.select_one('img.thum[src]') if a else None
        number = a.select_one('.gno span') if a else None
        title = a.select_one('.title') if a else None
        if not a or not image or not number or not title:
            raise ValueError('Gift product identity is incomplete')
        pid = number.get_text(strip=True)
        if not re.fullmatch(r'[1-9]\d{0,11}', pid):
            raise ValueError('Gift product number is invalid')
        q = parse_qs(urlparse(a['href']).query)
        if q.get('code') != [pid]:
            raise ValueError('Gift displayed ID and product link disagree')
        photo = urljoin(LIST_URL, image['src'])
        if urlparse(photo).scheme not in ('https', 'http'):
            raise ValueError('Gift image URL is invalid')
        price = a.select_one('.price, .price_b')
        amount = re.search(r'[\d,]+', price.get_text()) if price else None
        rows.append({'product_id': pid, 'name': title.get_text(' ', strip=True),
                     'image_alt': image.get('alt', ''), 'image': photo,
                     'source_url': BASE + '/new/shop/detail.php?code=' + pid,
                     'listed_price': int(amount[0].replace(',', '')) if amount else None,
                     'leaf_category_id': q.get('cid', [cid])[0],
                     'observed_at': stamp(), 'detail_complete': False})
    if len({r['product_id'] for r in rows}) != len(rows):
        raise ValueError('Duplicate gift products on one page')
    expected = min(30, max(0, total - (page - 1) * 30))
    if len(rows) != expected:
        raise ValueError('Gift page count does not match its advertised total')
    return {'id': cid, 'name': name, 'total': total, 'last_page': last, 'rows': rows}


@contextmanager
def run_lock(root):
    path = root / 'inventory.lock'
    with path.open('a+b') as handle:
        if os.name == 'nt':
            import msvcrt
            if handle.tell() == 0:
                handle.write(b'0'); handle.flush()
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            if os.name == 'nt':
                handle.seek(0); msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


class Source:
    def __init__(self, root):
        self.root = root
        self.next_request = time.monotonic() + 2.1
        self.session = requests.Session()
        self.session.headers['User-Agent'] = 'NADAUNShopCatalog/1.0 (+https://shop.nadaun.co)'

    def get(self, url, **params):
        cooldown = self.root / 'inventory-cooldown.json'
        if cooldown.exists() and time.time() < json.loads(cooldown.read_text())['retry_not_before']:
            raise RuntimeError('Gift source cooldown is active; no requests made')
        time.sleep(max(0, self.next_request - time.monotonic()))
        try:
            response = self.session.get(url, params=params, timeout=(10, 40), allow_redirects=False)
        finally:
            self.next_request = time.monotonic() + 2.1
        response.encoding = 'euc-kr'
        blocked = response.status_code in (403, 429) or any(x in response.text for x in
                   ('페이지를 너무 많이 요청', '서버보호차원에서 차단', '비정상적인 접근'))
        if blocked:
            retry = response.headers.get('Retry-After', '')
            try:
                wait = int(retry) if retry.isdigit() else parsedate_to_datetime(retry).timestamp()-time.time()
            except (ValueError, TypeError):
                wait = 3600
            cooldown.write_text(json.dumps({'blocked_at': stamp(), 'retry_not_before': time.time()+max(3600, wait)}))
            raise RuntimeError('Gift source limited requests; scan paused without publishing')
        if response.status_code != 200 or not response.content:
            raise RuntimeError('Gift source response is unavailable; existing inventory preserved')
        return document(response.text)


class Inventory:
    def __init__(self, root=PRIVATE_ROOT):
        self.root = private_path(root)
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.db = sqlite3.connect(private_path(self.root/'inventory.sqlite3'), timeout=30)
        self.db.execute('PRAGMA journal_mode=DELETE')
        self.db.execute('PRAGMA synchronous=FULL')
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS roots (
                id TEXT PRIMARY KEY, name TEXT, total INTEGER, last_page INTEGER,
                next_page INTEGER NOT NULL DEFAULT 1, complete INTEGER NOT NULL DEFAULT 0,
                first_ids TEXT
            );
            CREATE TABLE IF NOT EXISTS products (id TEXT PRIMARY KEY, record_json TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS memberships (root_id TEXT, product_id TEXT,
                PRIMARY KEY(root_id,product_id));
            CREATE TABLE IF NOT EXISTS pages (root_id TEXT, page INTEGER, observed_at TEXT,
                PRIMARY KEY(root_id,page));
            CREATE TABLE IF NOT EXISTS scan_state (key TEXT PRIMARY KEY, value TEXT);
        ''')
        (self.root/'inventory.sqlite3').chmod(0o600)

    def save_page(self, info, page):
        cid = info['id']
        old = self.db.execute('SELECT total,next_page FROM roots WHERE id=?', (cid,)).fetchone()
        if old and (old[0] is not None and old[0] != info['total'] or old[1] != page):
            raise ValueError('Gift count or cursor changed; review the preserved scan')
        with self.db:
            self.db.execute("INSERT INTO scan_state VALUES('final_verified','0') ON CONFLICT(key) DO UPDATE SET value='0'")
            self.db.execute('INSERT OR IGNORE INTO roots(id) VALUES(?)', (cid,))
            for row in info['rows']:
                prior = self.db.execute('SELECT 1 FROM memberships WHERE root_id=? AND product_id=?',
                                        (cid, row['product_id'])).fetchone()
                if prior:
                    raise ValueError('Repeated gift product across pages; scan needs reconciliation')
                self.db.execute('INSERT INTO products VALUES(?,?) ON CONFLICT(id) DO UPDATE SET record_json=excluded.record_json',
                                (row['product_id'], json.dumps(row, ensure_ascii=False)))
                self.db.execute('INSERT INTO memberships VALUES(?,?)', (cid, row['product_id']))
            self.db.execute('INSERT INTO pages VALUES(?,?,?)', (cid, page, stamp()))
            self.db.execute('UPDATE roots SET name=?,total=?,last_page=?,next_page=? WHERE id=?',
                            (info['name'], info['total'], info['last_page'], page+1, cid))
            if page == 1:
                self.db.execute('UPDATE roots SET first_ids=? WHERE id=?',
                                (json.dumps([r['product_id'] for r in info['rows']]), cid))

    def verify_root(self, info):
        cid = info['id']
        old = self.db.execute('SELECT total,last_page,next_page,first_ids FROM roots WHERE id=?', (cid,)).fetchone()
        count = self.db.execute('SELECT COUNT(*) FROM memberships WHERE root_id=?', (cid,)).fetchone()[0]
        if not old or old[0] != info['total'] or count != info['total'] or old[2] <= old[1]:
            raise ValueError('Gift root coverage is incomplete')
        if json.loads(old[3]) != [r['product_id'] for r in info['rows']]:
            raise ValueError('Gift newest products changed while scanning; reconcile before publishing')
        with self.db:
            self.db.execute('UPDATE roots SET complete=1 WHERE id=?', (cid,))

    def finalize(self, verified_roots):
        rows=list(self.db.execute('SELECT id,complete FROM roots ORDER BY rowid'))
        if not rows or verified_roots != [r[0] for r in rows] or not all(r[1] for r in rows):
            raise ValueError('Final navigation and complete category coverage are required')
        with self.db:
            self.db.execute("INSERT INTO scan_state VALUES('final_verified','1') ON CONFLICT(key) DO UPDATE SET value='1'")

    def status(self):
        roots = [dict(zip(('id','name','total','last_page','next_page','complete'), row))
                 for row in self.db.execute('SELECT id,name,total,last_page,next_page,complete FROM roots ORDER BY rowid')]
        final=self.db.execute("SELECT value FROM scan_state WHERE key='final_verified'").fetchone()
        dates=self.db.execute('SELECT MIN(observed_at), MAX(observed_at) FROM pages').fetchone()
        return {'checked_at':stamp(), 'source':BASE,
                'snapshot_started_at':dates[0], 'snapshot_last_page_at':dates[1],
                'unique_products':self.db.execute('SELECT COUNT(*) FROM products').fetchone()[0],
                'pages_collected':self.db.execute('SELECT COUNT(*) FROM pages').fetchone()[0],
                'expected_category_memberships':sum(r['total'] or 0 for r in roots),
                'roots':roots, 'inventory_complete':bool(final and final[0]=='1' and roots) and all(r['complete'] for r in roots),
                'details_complete':False,'suppliers_complete':False,'published':False}

    def report(self, error=None):
        status = self.status()
        if error: status['error'] = error
        path = self.root/'inventory-progress.json'
        path.write_text(json.dumps(status, ensure_ascii=False, indent=2)+'\n')
        print(json.dumps({k:v for k,v in status.items() if k!='roots'}, ensure_ascii=False), flush=True)

    def scan(self):
        source = Source(self.root)
        with run_lock(self.root):
            with self.db:
                self.db.execute("INSERT INTO scan_state VALUES('final_verified','0') ON CONFLICT(key) DO UPDATE SET value='0'")
            roots = root_categories(source.get(BASE+'/'))
            saved = [r[0] for r in self.db.execute('SELECT id FROM roots ORDER BY rowid')]
            if saved and roots != saved:
                raise ValueError('Gift root navigation changed; preserve and reconcile this scan')
            with self.db:
                self.db.executemany('INSERT OR IGNORE INTO roots(id) VALUES(?)', [(cid,) for cid in roots])
            # Read every root's first page before traversing any long category.
            for cid in roots:
                if self.db.execute('SELECT next_page FROM roots WHERE id=?',(cid,)).fetchone()[0] == 1:
                    self.save_page(parse_page(source.get(LIST_URL,cid=cid,main_cid=cid,sort=5,p=1),cid,1),1)
                    self.report()
            for cid in roots:
                row = self.db.execute('SELECT next_page,last_page,complete FROM roots WHERE id=?',(cid,)).fetchone()
                if row[2]: continue
                for page in range(row[0], row[1]+1):
                    self.save_page(parse_page(source.get(LIST_URL,cid=cid,main_cid=cid,sort=5,p=page),cid,page),page)
                    if page % 10 == 0: self.report()
                self.verify_root(parse_page(source.get(LIST_URL,cid=cid,main_cid=cid,sort=5,p=1),cid,1))
                self.report()
            final_roots=root_categories(source.get(BASE+'/'))
            if final_roots != roots:
                with self.db:self.db.execute('UPDATE roots SET complete=0')
                raise ValueError('Gift root navigation changed during the scan')
            self.finalize(final_roots)
            self.report()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=('scan','status'))
    args=parser.parse_args(); inventory=Inventory()
    try:
        if args.command=='scan':inventory.scan()
        else:inventory.report()
    except Exception as exc:
        inventory.report(type(exc).__name__+': '+str(exc))
        raise
    finally:inventory.db.close()


if __name__=='__main__':main()
