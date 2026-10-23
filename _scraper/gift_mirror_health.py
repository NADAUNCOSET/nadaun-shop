"""Daily read-only audit of the complete saved mirror and our own storefront.

This never requests a supplier site, publishes products or changes orders.
Missing source coverage is an attention item, never a successful full mirror.
"""
from collections import Counter
from datetime import datetime, timedelta, timezone
import hashlib
from html import escape
import json
from pathlib import Path
import re
import requests

KST = timezone(timedelta(hours=9))


def inspect(catalog, details):
    products, categories, meta = catalog['products'], catalog['categories'], catalog['meta']
    ids = [p['id'] for p in products]
    pmap, cids = {p['id']: p for p in products}, {c['id'] for c in categories}
    errors = []
    if len(pmap) != len(ids) or any(not re.fullmatch(r'[1-9][0-9]{0,11}', pid) for pid in ids):
        errors.append('product_identity_conflict')
    if len(cids) != len(categories): errors.append('category_identity_conflict')
    bad_paths = [p['id'] for p in products if not p.get('category_ids') or set(p['category_ids']) - cids]
    if bad_paths or any(set(c.get('parent_ids', [])) - cids for c in categories):
        errors.append('category_reference_missing')
    if set(details) - set(ids): errors.append('detail_product_missing')
    priced, options, tiers, observed = set(), 0, 0, []
    for pid, detail in details.items():
        price = detail.get('pricing')
        if not price: continue
        priced.add(pid)
        if not price.get('revision') or not price.get('observed_at') or not price.get('options'):
            errors.append('price_metadata_invalid:' + pid)
        if price.get('observed_at'): observed.append(price['observed_at'])
        option_ids = [o.get('id') for o in price.get('options', [])]
        if len(set(option_ids)) != len(option_ids) or None in option_ids:
            errors.append('option_identity_conflict:' + pid)
        for option in price.get('options', []):
            options += 1
            quantities = []
            for tier in option.get('tiers', []):
                tiers += 1
                q, unit = tier.get('minimum_quantity'), tier.get('unit_price_ex_vat')
                if type(q) is not int or q <= 0 or type(unit) is not int or unit <= 0:
                    errors.append('price_tier_invalid:' + pid)
                quantities.append(q)
            if not quantities or len(set(quantities)) != len(quantities):
                errors.append('price_tier_identity_conflict:' + pid)
    flagged = {p['id'] for p in products if p.get('pricing_available')}
    if flagged != priced: errors.append('pricing_projection_missing')
    counts = {'products': len(products), 'categories': len(categories), 'details': len(details),
              'priced_products': len(priced), 'unpriced_products': len(products) - len(priced),
              'price_options': options, 'price_tiers': tiers}
    checks = {'product_count': 'products', 'category_count': 'categories', 'detail_count': 'details',
              'priced_product_count': 'priced_products', 'price_option_count': 'price_options', 'price_tier_count': 'price_tiers'}
    for key, count in checks.items():
        if meta.get(key) != counts[count]: errors.append('metadata_count_mismatch:' + key)
    states = Counter(p.get('source_status', 'unverified') for p in products)
    return {'counts': counts, 'source_states': dict(states), 'errors': sorted(set(errors)),
            'invalid_category_product_ids': bad_paths[:100],
            'price_source_oldest': min(observed, default=None), 'price_source_latest': max(observed, default=None)}


def render(report):
    counts = report.get('counts', {})
    cards = [('전체 상품', counts.get('products')), ('가격표 확보', counts.get('priced_products')),
             ('가격표 미확보', counts.get('unpriced_products')), ('공급업체 연결 상품', report.get('supplier_matched_products'))]
    rows = ''.join('<li><strong>'+escape(label)+'</strong> '+escape(str(value if value is not None else '미확인'))+'</li>' for label, value in cards)
    issues = ''.join('<li>'+escape(s)+'</li>' for s in report.get('attention', []))
    errors = ''.join('<li>'+escape(s)+'</li>' for s in report.get('errors', []))
    return '''<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>기프트 매일 점검</title>
<style>body{font-family:system-ui,sans-serif;line-height:1.7;max-width:1000px;margin:40px auto;padding:20px;background:#f8f8f5;color:#202020}a{color:#175da6}li{margin:.5em 0}strong{margin-right:12px}section{background:white;padding:24px;margin:20px 0;border:1px solid #ddd}code{overflow-wrap:anywhere}</style>
<a href="../00_여기서_시작.html">검토자료 첫 화면</a><h1>기프트 매일 점검</h1><p>확인 시각: '''+escape(report['checked_at'])+'''</p><p>현재 Mac이 켜져 있고 NAS가 연결돼 있을 때 하루 한 번 확인합니다. 이 페이지의 점검 시각과 원본 상품 확인일은 별개입니다.</p><section><ul>'''+rows+'''</ul></section><section><h2>남은 확인</h2><ul>'''+issues+'''</ul></section><section><h2>구조·운영 대조 오류</h2><ul>'''+(errors or '<li>이번 대조에서 발견된 오류 없음</li>')+'''</ul></section><p>원본 피드 확인일: '''+escape(str(report.get('source_observed_at')))+'''</p><p>운영 카탈로그 일치: '''+escape(str(report.get('live_catalog_matches')))+''' / 전상품 최신 상세 확보: '''+escape(str(report.get('full_source_complete', False)))+'''</p><p><a href="03_매일미러링_매칭검토.html">전체 상품 검토 목록</a> — 목록은 해당 자료의 생성·원본 시각을 확인해 주세요.</p></html>'''


def run(root, force=False):
    root = Path(root)
    state = root / '_private/gift/daily-sync'
    state.mkdir(parents=True, exist_ok=True)
    target = state / 'health.json'
    now = datetime.now(KST)
    if target.exists() and not force:
        prior = json.loads(target.read_text())
        if prior.get('date_kst') == now.date().isoformat(): return prior
    report = {'checked_at': now.isoformat(), 'date_kst': now.date().isoformat(),
              'source_requests': 0, 'full_source_complete': False, 'errors': [], 'attention': []}
    try:
        raw = (root / 'data/gift/catalog.json').read_bytes()
        catalog = json.loads(raw)
        details = {}
        for p in sorted((root / 'data/gift/details').glob('*.json')):
            chunk = json.loads(p.read_text())
            if set(details) & set(chunk): raise ValueError('Duplicate product in detail buckets')
            details.update(chunk)
        report.update(inspect(catalog, details))
        meta = catalog['meta']
        report['revision'] = meta['revision']
        report['source_observed_at'] = meta.get('official_feed_observed_at')
        if report['source_observed_at']:
            observed = datetime.fromisoformat(report['source_observed_at'].replace('Z', '+00:00'))
            if observed.tzinfo is None: raise ValueError('Source observation has no timezone')
            report['feed_age_hours'] = round((now - observed).total_seconds() / 3600, 1)
            if report['feed_age_hours'] > 36:
                report['attention'].append('공식 피드 마지막 확인 후36시간 경과')
        if not meta.get('all_current_details_verified'):
            report['attention'].append('전상품 최신 상세·수량별 단가·공급가 확보 미완료')
        if not meta.get('mirror', {}).get('full_source_inventory_verified'):
            report['attention'].append('전체 원본 재고·판매 종료 목록 미확인. 네이버 피드 부재만으로 삭제하지 않음')
        access = json.loads((state / 'source-access.json').read_text())
        report['source_access'] = access.get('state', 'unverified')
        if report['source_access'] != 'ready': report['attention'].append('원본 접근 확인 대기: '+report['source_access'])
        response = requests.get('https://shop.nadaun.co/data/gift/catalog.json', timeout=60)
        response.raise_for_status()
        report['live_catalog_matches'] = hashlib.sha256(response.content).digest() == hashlib.sha256(raw).digest()
        if not report['live_catalog_matches']: report['errors'].append('live_catalog_mismatch')
        report['commerce'] = {}
        for host in ['https://shop.nadaun.co', 'https://order.nadaun.co']:
            response = requests.get(host+'/api/orders?action=config', timeout=30)
            response.raise_for_status()
            report['commerce'][host] = response.json()
        cfg = json.loads((root / '_private/commerce/configuration.json').read_text())
        login = {'password': (root / '_private/commerce/owner-login.private').read_text().strip()}
        if cfg.get('SHOP_ADMIN_EMAIL'): login['email'] = cfg['SHOP_ADMIN_EMAIL']
        with requests.Session() as operator:
            host = 'https://order.nadaun.co'
            response = operator.post(host+'/api/orders?action=login', json=login, headers={'Origin': host}, timeout=30)
            response.raise_for_status()
            try:
                response = operator.get(host+'/api/orders?action=admin-gift-products&status=supplier', timeout=30)
                response.raise_for_status()
                result = response.json()
                report['supplier_matched_products'] = result['total']
                report['supplier_unmatched_products'] = len(catalog['products']) - result['total']
                if result['meta']['revision'] != meta['revision']: report['errors'].append('admin_catalog_revision_mismatch')
                if report['supplier_unmatched_products']: report['attention'].append('공급업체 연결 미확인 상품 '+str(report['supplier_unmatched_products'])+'개')
            finally:
                operator.post(host+'/api/orders?action=logout', json={}, headers={'Origin': host}, timeout=30).raise_for_status()
    except Exception as error:
        # Never record credentials, supplier records, cookies or provider bodies.
        report['errors'].append('audit_failed:'+type(error).__name__)
    report['state'] = 'requires_attention' if report['errors'] or report['attention'] else 'verified'
    tmp = target.with_suffix('.pending')
    tmp.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n'); tmp.chmod(0o600); tmp.replace(target)
    assert json.loads(target.read_text()) == report
    page = root / '검토자료/07_기프트미러링/04_매일점검_현재상태.html'
    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_text(render(report))
    return report


if __name__ == '__main__':
    result = run(Path(__file__).resolve().parents[1], force='--force' in __import__('sys').argv)
    print(json.dumps({'state': result['state'], 'counts': result.get('counts'), 'errors': result['errors']}, ensure_ascii=False))
