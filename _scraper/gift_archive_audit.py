"""Verify every preserved gift source ID and price against the published mirror.

Only --live reads our shop/order APIs. Never requests a source/supplier site,
deletes a product, changes an order, or claims current source completeness.
"""
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import csv
import hashlib
from html import escape
import json
from pathlib import Path
import re
import sqlite3
import sys
import unicodedata
from urllib.parse import parse_qs, urlsplit
import xml.etree.ElementTree as ET
import requests
from gift_official_feed import parse_feed
from gift_pricing_projection import pricing

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/('_private/gift/archive-audit-'+datetime.now().strftime('%Y%m%d'))
REVIEW = ROOT/'검토자료/07_기프트미러링'


def load(path): return json.loads(path.read_text())
def safe_cell(value):
    value = str(value)
    return "'"+value if value.startswith(('=', '+', '-', '@', '\t', '\r')) else value
def save_csv(path, header, rows):
    with path.open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.writer(f); writer.writerow(header)
        for row in rows: writer.writerow([safe_cell(v) for v in row])
    with path.open(encoding='utf-8-sig', newline='') as f:
        return sum(1 for _ in csv.reader(f))-1


def main(live=False):
    OUT.mkdir(parents=True, exist_ok=True); REVIEW.mkdir(parents=True, exist_ok=True)
    private = ROOT/'_private/gift'
    c = load(ROOT/'data/gift/catalog.json'); products = {p['id']: p for p in c['products']}
    errors = []
    if len(products) != len(c['products']): errors.append('duplicate_public_product_id')
    with sqlite3.connect((private/'inventory.sqlite3').resolve().as_uri()+'?mode=ro', uri=True) as db:
        archived = {pid:json.loads(record) for pid,record in db.execute('SELECT id,record_json FROM products')}
        source_details = {pid:json.loads(record) for pid,record in db.execute('SELECT id,record_json FROM public_details')}
        parse_errors = [{'id':pid,'reason':reason} for pid,reason in db.execute('SELECT id,error FROM detail_errors')]
    for record in load(private/'commerce-integration-20261022/verified-public-details.json'):
        source_details[record['product_id']] = record
    with sqlite3.connect((private/'suppliers.sqlite3').resolve().as_uri()+'?mode=ro', uri=True) as db:
        supplier_ids = {row[0] for row in db.execute('SELECT product_id FROM supplier_current')}
    latest = load(private/'full-acquisition-20261021/latest-feed.json')
    raw = (private/'full-acquisition-20261021'/latest['file']).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == latest['sha256']
    assert latest['sha256'] == c['meta']['official_feed_sha256'], 'Select the preserved feed snapshot matching the current catalog before auditing'
    rows, quarantined = parse_feed(raw); feed = {p['id']:p for p in rows}
    source_ids = archived.keys() | feed.keys()
    missing, orphan = source_ids-products.keys(), products.keys()-source_ids
    if missing or orphan: errors.append('archived_source_union_mismatch')
    changed_leaf = [pid for pid,p in archived.items() if p['leaf_category_id'] not in products[pid]['category_ids']]
    if changed_leaf: errors.append('archived_category_changed_requires_review')
    feed_mismatches = []
    for pid,row in feed.items():
        expected = {'name':row['title'].strip(),'image':row['image_link'],
                    'manufacturer_label':row['maker'].strip(),'origin':row['origin'].strip(),
                    'feed_category':row['category_name1'].strip()}
        for key,value in expected.items():
            if products[pid].get(key) != value: feed_mismatches.append({'id':pid,'field':key})
    if feed_mismatches: errors.append('official_feed_field_mismatch')
    details = {}
    for path in sorted((ROOT/'data/gift/details').glob('*.json')):
        values = load(path)
        if details.keys() & values.keys(): errors.append('duplicate_detail_bucket_identity')
        details.update(values)
    price_mismatches = []
    for pid,record in source_details.items():
        if pricing(record) != details.get(pid,{}).get('pricing'): price_mismatches.append(pid)
    if price_mismatches: errors.append('archived_price_projection_mismatch')
    if set(details) != set(source_details): errors.append('detail_source_identity_mismatch')
    cats = {v['id']:v for v in c['categories']}
    active = {pid for pid,p in products.items() if p.get('source_status') != 'withdrawn'}
    cat_counts = Counter(cid for pid in active for cid in products[pid]['category_ids'])
    bad_counts = [cid for cid,v in cats.items() if v['count'] != cat_counts[cid]]
    if bad_counts: errors.append('category_product_count_mismatch')
    sitemap_ids, sitemap_urls = [], []
    for path in ROOT.glob('gift-sitemap-*.xml'):
        sitemap_urls += [n.text for n in ET.fromstring(path.read_bytes()).iter('{http://www.sitemaps.org/schemas/sitemap/0.9}loc')]
    for url in sitemap_urls:
        u = urlsplit(url)
        if u.path == '/gift-item.html': sitemap_ids += parse_qs(u.query).get('id', [])
    if set(sitemap_ids) != active or len(sitemap_ids) != len(active): errors.append('sitemap_product_coverage_mismatch')
    duplicates = defaultdict(list)
    for p in products.values():
        key = re.sub(r'\s+', ' ', unicodedata.normalize('NFKC',p['name'])).strip().casefold()
        duplicates[key].append(p['id'])
    duplicate_groups = [ids for ids in duplicates.values() if len(ids)>1]
    imports = load(private/'commerce-integration-20261022/supplier-import.private.json')
    public_text = json.dumps([c,details],ensure_ascii=False)
    leaks = []
    for record in imports:
        for key in ['phone','mobile','fax','email','business_number']:
            value = str(record.get('supplier',{}).get(key,'')).strip()
            if len(value)>=7 and value in public_text: leaks.append({'id':record['product_id'],'field':key})
    if leaks: errors.append('private_supplier_field_in_public_payload')
    report = {'checked_at':datetime.now().astimezone().isoformat(),'full_current_source_verified':False,
              'source_requests':0,'archived_products':len(archived),'feed_valid_products':len(feed),
              'feed_quarantined_rows':len(quarantined),'feed_source_sha256':latest['sha256'],
              'feed_observed_at':c['meta']['official_feed_observed_at'],
              'source_union_products':len(source_ids),'published_products':len(products),
              'source_products_missing_from_public':sorted(missing),'public_without_source_evidence':sorted(orphan),
              'archived_leaf_category_changed':changed_leaf,'feed_field_mismatches':feed_mismatches,
              'source_price_products':len(source_details),'exact_price_projections':len(source_details)-len(price_mismatches),
              'price_projection_mismatches':price_mismatches,'category_count_mismatches':bad_counts,
              'sitemap_product_urls':len(sitemap_ids),'sitemap_unique_products':len(set(sitemap_ids)),
              'same_name_groups_require_review':len(duplicate_groups),
              'same_name_products_require_review':sum(map(len,duplicate_groups)),
              'same_name_groups_are_not_confirmed_duplicates':True,
              'private_supplier_fields_leaked':leaks,'source_detail_parse_review':parse_errors,
              'supplier_matched_products_archived':len(supplier_ids),'errors':errors}
    report['unpriced_products'] = sum(not d.get('pricing') for pid in products for d in [details.get(pid,{})])
    report['supplier_unmatched_products'] = len(products)-len(supplier_ids & products.keys())
    if live:
        paths=['data/gift/catalog.json','data/gift/manifest.json','data/gift/sync-status.json','assets/shop/gift-pricing.js']
        paths += [p.relative_to(ROOT).as_posix() for p in sorted((ROOT/'data/gift/details').glob('*.json'))]
        def audit(path):
            response=requests.get('https://shop.nadaun.co/'+path,params={'gift_audit':c['meta']['revision']},timeout=60)
            response.raise_for_status();actual=hashlib.sha256(response.content).hexdigest()
            if actual!=hashlib.sha256((ROOT/path).read_bytes()).hexdigest():raise ValueError('Live mirror file mismatch: '+path)
            return {'path':path,'sha256':actual}
        with ThreadPoolExecutor(max_workers=4) as pool: hashes=list(pool.map(audit,paths))
        (OUT/'live-public-hashes.json').write_text(json.dumps(hashes,indent=2)+'\n')
        report['live_public_files_verified']=len(hashes)
        cfg=load(ROOT/'_private/commerce/configuration.json')
        login={'password':(ROOT/'_private/commerce/owner-login.private').read_text().strip()}
        if cfg.get('SHOP_ADMIN_EMAIL'):login['email']=cfg['SHOP_ADMIN_EMAIL']
        with requests.Session() as operator:
            host='https://order.nadaun.co'
            response=operator.post(host+'/api/orders?action=login',json=login,headers={'Origin':host},timeout=30);response.raise_for_status()
            try:
                exact=0;diffs=[]
                for record in imports:
                    response=operator.get(host+'/api/orders',params={'action':'admin-gift-product','id':record['product_id']},timeout=30);response.raise_for_status()
                    actual=response.json()['supplier_record']; fields=[]
                    for group in ['supplier','terms','evidence']:
                        for key,value in record[group].items():
                            if actual.get(group,{}).get(key,'')!=str(value).strip():fields.append(group+'.'+key)
                    if fields:diffs.append({'id':record['product_id'],'fields':fields})
                    else:exact+=1
                report['live_supplier_records_exact']=exact;report['live_supplier_record_differences']=diffs
                if diffs:errors.append('supplier_saved_to_live_field_mismatch')
            finally:
                operator.post(host+'/api/orders?action=logout',json={},headers={'Origin':host},timeout=30).raise_for_status()
    table=[]
    for p in products.values():
        pid=p['id']; price=details.get(pid,{}).get('pricing',{})
        table.append([pid,p['name'],' / '.join(cats[cid]['name'] for cid in p['category_ids']),
                      '확인' if pid in archived else '없음',
                      '확인' if pid in feed else '미확인',
                      len(price.get('options',[])),sum(len(o['tiers']) for o in price.get('options',[])),price.get('observed_at',''),
                      '확인' if pid in supplier_ids else '미확인',
                      'https://shop.nadaun.co/gift-item.html?id='+pid,
                      'https://order.nadaun.co/manage.html?view=gifts&id='+pid])
    csv_path=REVIEW/'05_전체상품_원본매칭과누락.csv'
    assert save_csv(csv_path,['상품번호','상품명','분류','보관목록근거','공식피드근거_확인일별도','옵션수','수량단가수','가격표원본확인일','공급업체근거','샵','오더'],table)==len(products)
    dupe_path=REVIEW/'05_동일상품명_검토필요.csv'
    dupe_rows=[[products[ids[0]]['name'],len(ids),','.join(ids),len({products[pid]['image'] for pid in ids}),'미확정: 구성·옵션·제조사 확인 전 삭제 금지'] for ids in duplicate_groups]
    assert save_csv(dupe_path,['동일상품명','상품수','상품번호목록','대표이미지종류수','판단'],dupe_rows)==len(duplicate_groups)
    (OUT/'audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    counts=[('보관 원본과 번호 일치',len(source_ids)),('우리몰 누락',len(missing)),('원본 근거 없는 등록',len(orphan)),
            ('보관 단가와 정확 일치',report['exact_price_projections']),('동일명 검토 그룹',len(duplicate_groups)),('실제 업체 연결 상품',len(supplier_ids))]
    cards=''.join('<li>'+escape(label)+' <strong>'+str(n)+'</strong></li>' for label,n in counts)
    issues=''.join('<li>'+escape(e)+'</li>' for e in errors) or '<li>이번 구조·원본 대조에서 발견된 오류 없음</li>'
    html='''<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>기프트 보관원본 전수 대조</title><style>body{font:16px/1.75 system-ui,sans-serif;max-width:1100px;margin:32px auto;padding:20px;background:#f8f8f5;color:#222}section{background:white;padding:24px;border:1px solid #ddd;margin:20px 0}li{margin:10px 0}a{color:#175da6}strong{margin-left:15px}.warning{background:#fff4d8}</style><a href="../00_여기서_시작.html">검토자료 첫 화면</a><h1>기프트 보관 원본 전수 대조</h1><p>점검 시각: '''+escape(report['checked_at'])+'''</p><section class="warning">9월 보관 목록과10월21일 공식 피드의 상품번호를 합쳐 우리몰 전수와 대조했습니다. 최신 원본 전체 재고·판매 종료·단가·공급가 확인은 아직 미완료입니다. 동일명 그룹은 중복 확정 건수가 아닙니다.</section><section><ul>'''+cards+'''</ul></section><section><h2>대조 결과</h2><ul>'''+issues+'''</ul><p>원본 상세 파싱 검토3개, 수량별 단가 미확보69,504개, 공급업체 미연결72,932개가 남아 있습니다.</p></section><p><a href="05_전체상품_원본매칭과누락.csv">전체72,935상품 매칭·누락 검토표 CSV</a></p><p><a href="05_동일상품명_검토필요.csv">동일 상품명 검토 목록 CSV</a></p><p><a href="04_매일점검_현재상태.html">매일 점검 결과</a> · <a href="03_매일미러링_매칭검토.html">상품별 보기</a></p></html>'''
    html = html.replace('font:16px/1.75 system-ui,sans-serif', 'font:16px/1.75 Pretendard,-apple-system,BlinkMacSystemFont,sans-serif;letter-spacing:-.02em')
    html = html.replace('원본 상세 파싱 검토3개, 수량별 단가 미확보69,504개, 공급업체 미연결72,932개',
                        '원본 상세 파싱 검토'+str(len(parse_errors))+'개, 수량별 단가 미확보'+format(report['unpriced_products'],',')+'개, 공급업체 미연결'+format(report['supplier_unmatched_products'],',' )+'개')
    html = html.replace('전체72,935상품', '전체'+format(len(products),',')+'상품')
    (REVIEW/'05_보관원본_전수대조.html').write_text(html)
    print(json.dumps({k:v for k,v in report.items() if not isinstance(v,list)},ensure_ascii=False))
    if errors:raise SystemExit('Audit needs review: '+','.join(errors))
    return report


if __name__=='__main__':main(live='--live' in sys.argv)
