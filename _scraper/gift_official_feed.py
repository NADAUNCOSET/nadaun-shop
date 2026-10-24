"""Validate an already downloaded official gift feed without publishing it.

The Naver feed is not a complete supplier registry or a quantity-price table.
Keep each source field unchanged and quarantine malformed rows for review.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
from html import escape
import hashlib
import json
from pathlib import Path
import re
import sqlite3
from urllib.parse import parse_qs, urlsplit

FIELDS = ['id', 'title', 'price_pc', 'link', 'image_link', 'category_name1',
          'condition', 'product_flag', 'maker', 'origin', 'search_tag',
          'minimum_purchase_quantity', 'shipping', 'adult']


def reviewed_row_repairs():
    path = Path(__file__).with_name('gift-reviewed-feed-rows.json')
    if not path.exists(): return {}
    records = json.loads(path.read_text())['rows']; result = {}
    clean = lambda value: re.sub(r'\s+', ' ', value).strip()
    for record in records:
        original, corrected = record['original_fields'], record['canonical_fields']
        sha = hashlib.sha256('\t'.join(original).encode('euc-kr')).hexdigest()
        if (sha != record['source_row_sha256'] or sha in result or len(original) != len(FIELDS)+1
                or len(corrected) != len(FIELDS) or corrected[0] != record['id'] or original[0] != record['id']):
            raise ValueError('Reviewed source row repair identity conflict')
        positions = record['equivalent_merge_positions']
        if not positions: raise ValueError('Reviewed source row repair has no alignment proof')
        for i in positions:
            if type(i) is not int or not 1 <= i < len(original)-1:
                raise ValueError('Invalid reviewed row merge position')
            merged = original[:i]+[original[i]+'\t'+original[i+1]]+original[i+2:]
            if [clean(v) for v in merged] != corrected:
                raise ValueError('Reviewed row repair changed source fields beyond whitespace alignment')
        result[sha] = record
    return result


def parse_feed(raw):
    lines = raw.decode('euc-kr', errors='strict').splitlines()
    if not lines or lines[0].split('\t') != FIELDS:
        raise ValueError('Official feed schema changed or response is not a feed')
    good, rejected, seen = [], [], set()
    repairs = reviewed_row_repairs()
    for line_number, line in enumerate(lines[1:], 2):
        parts = line.split('\t')
        original_parts = parts; repair = None
        if len(parts) != len(FIELDS):
            sha = hashlib.sha256(line.encode('euc-kr')).hexdigest()
            repair = repairs.get(sha)
            if repair is not None and repair['original_fields'] == parts:
                parts = repair['canonical_fields']
        reason = None
        if len(parts) != len(FIELDS):
            reason = 'column_count'
        else:
            row = dict(zip(FIELDS, parts))
            pid = row['id']
            link = urlsplit(row['link'])
            image = urlsplit(row['image_link'])
            if not re.fullmatch(r'[1-9][0-9]{0,11}', pid):
                reason = 'invalid_product_id'
            elif pid in seen:
                raise ValueError('Duplicate product ID in official feed: ' + pid)
            elif (link.scheme != 'https' or link.hostname not in ('nadaun-gift.com', 'www.nadaun-gift.com')
                  or link.path != '/new/shop/detail.php' or parse_qs(link.query).get('code') != [pid]):
                reason = 'product_url_identity_mismatch'
            elif image.scheme not in ('http', 'https') or not image.hostname:
                reason = 'invalid_image_url'
            elif not row['title'] or not row['price_pc'].isdigit() or int(row['price_pc']) <= 0:
                reason = 'invalid_title_or_price'
            else:
                # These are source fields, not approved unit selling prices or suppliers.
                if repair is not None:
                    row['_reviewed_row_repair'] = {'source_row_sha256': repair['source_row_sha256'],
                                                   'original_field_count': len(original_parts)}
                good.append(row)
                seen.add(pid)
        if reason:
            rejected.append({'line_number': line_number, 'reason': reason,
                             'field_count': len(original_parts), 'raw_fields': original_parts})
    if not good:
        raise ValueError('No valid products in official feed')
    return good, rejected


def prepare(feed, inventory, output):
    raw = feed.read_bytes()
    rows, rejected = parse_feed(raw)
    output.mkdir(parents=True, exist_ok=True, mode=0o700)
    with sqlite3.connect(inventory.resolve().as_uri() + '?mode=ro', uri=True) as db:
        prior = {r[0] for r in db.execute('SELECT id FROM products')}
        details = {r[0] for r in db.execute('SELECT id FROM public_details')}
    ids = {r['id'] for r in rows}
    manufacturer_counts = Counter(r['maker'] for r in rows if r['maker'])
    category_counts = Counter(r['category_name1'] for r in rows)
    summary = {
        'parsed_at': datetime.now(timezone.utc).isoformat(),
        'source_file': feed.name, 'source_sha256': hashlib.sha256(raw).hexdigest(),
        'source_rows': len(rows) + len(rejected), 'validated_rows': len(rows),
        'quarantined_rows': len(rejected), 'unique_validated_ids': len(ids),
        'manufacturer_labels': len(manufacturer_counts), 'category_labels': len(category_counts),
        'existing_inventory_ids': len(prior), 'new_ids_vs_saved_inventory': len(ids - prior),
        'saved_inventory_ids_not_in_validated_feed': len(prior - ids),
        'existing_details_for_feed_ids': len(ids & details),
        'feed_ids_without_saved_details': len(ids - details),
        'feed_download_complete': True, 'all_catalog_products_confirmed': False,
        'supplier_contacts_included': False, 'supplier_costs_included': False,
        'quantity_price_tiers_included': False, 'detail_images_included': False,
        'supplier_registry_admin_updated': False, 'published': False,
        'price_semantics': 'Raw Naver price_pc; not an approved per-unit order price.',
        'quantity_semantics': 'Raw field preserved; empty and set/unit labels occur, not a validated MOQ.',
        'absence_semantics': 'Absence from this feed is not proof of discontinuation or deletion.',
    }
    for name, data in [('feed-validation.json', summary), ('feed-quarantine.json', rejected),
                       ('manufacturer-labels.json', [{'label': k, 'products': v, 'supplier_verified': False}
                                                      for k, v in manufacturer_counts.most_common()]),
                       ('feed-category-labels.json', dict(category_counts)),
                       ('feed-new-product-ids.json', sorted(ids - prior)),
                       ('inventory-not-in-feed.json', sorted(prior - ids))]:
        path = output / name
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
        path.chmod(0o600)
    path = output / 'official-feed-products.jsonl'
    with path.open('w') as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + '\n')
    path.chmod(0o600)
    return summary


def build_review(output, target):
    from gift_mirror_review import page
    summary = json.loads((output / 'feed-validation.json').read_text())
    rows = [json.loads(line) for line in (output / 'official-feed-products.jsonl').read_text().splitlines()]
    new_ids = set(json.loads((output / 'feed-new-product-ids.json').read_text()))
    labels = json.loads((output / 'manufacturer-labels.json').read_text())
    rejected = json.loads((output / 'feed-quarantine.json').read_text())
    payload = json.dumps({'rows': [[r['id'], r['title'], r['maker'], r['category_name1'],
                                   r['price_pc'], r['minimum_purchase_quantity'], r['link'],
                                   r['id'] in new_ids] for r in rows],
                          'makers': labels}, ensure_ascii=False, separators=(',', ':')).replace('<', '\\u003c')
    bad_rows = ''.join('<tr><td>' + str(r['line_number']) + '</td><td>' +
                       escape(r['raw_fields'][0]) + '</td><td>' + str(r['field_count']) +
                       '열 / 예상 14열</td></tr>' for r in rejected)
    body = f'''<header><h1>본사 제공 상품 파일 검토</h1><p>2026-10-21 갱신본 · 전체 파일 다운로드 완료</p>
<a href="00_기프트_전체검토.html">기프트 전체 진행내역</a></header><main>
<section><div class="cards"><div><strong>{summary['source_rows']:,}</strong>원본 데이터 행</div>
<div><strong>{summary['validated_rows']:,}</strong>구조·상품번호 검증</div><div><strong>{summary['quarantined_rows']}</strong>형식 검토</div>
<div><strong>{summary['manufacturer_labels']}</strong>제조사 표기</div></div>
<p class="notice">본사 네이버용 파일 전체를 받았습니다. 전체 취급 상품·상세·공급가 확보 완료는 아닙니다.
공급업체 담당자·원가·수량별 가격표·상세 이미지가 포함되지 않았습니다. 제조사 표기는 공급업체 등록 완료를 뜻하지 않습니다.</p>
<p>기존 9월 목록에 없던 상품번호 {summary['new_ids_vs_saved_inventory']:,}개를 별도 목록으로 보존했습니다.
기존 목록 중 이 검증 목록에 없는 {summary['saved_inventory_ids_not_in_validated_feed']:,}개는 삭제·단종으로 처리하지 않습니다.</p>
<p>표의 금액은 원본 <code>price_pc</code> 값입니다. 세트 총액과 개별 단가를 구분해야 하므로 결제 단가로 자동 적용하지 않았습니다.</p>
<a href="본사_전체자료_요청문.md">남은 전체 자료 요청문 (발송 전)</a></section>
<section><h2>검증된 상품 전체</h2><div class="filters"><input id="query" type="search" aria-label="상품번호 상품명 제조사 검색" placeholder="상품번호·상품명·제조사 검색">
<select id="maker" aria-label="제조사 표기"><option value="">전체 제조사 표기</option></select><label><input id="newonly" type="checkbox">기존 목록에 없던 상품번호만</label></div>
<div class="pager"><button id="prev">이전</button><span id="count" role="status"></span><button id="next">다음</button></div>
<div class="scroll"><table><thead><tr><th>상품번호</th><th>상품명</th><th>제조사 표기</th><th>분류</th><th>원본 피드 금액</th><th>수량 필드 원문</th><th>원본</th></tr></thead><tbody id="rows"></tbody></table></div></section>
<section><h2>형식 검토 3행</h2><p>원본을 그대로 보존했으며 필드 위치를 임의로 옮기지 않았습니다.</p><table><thead><tr><th>원본 행</th><th>상품번호</th><th>상태</th></tr></thead><tbody>{bad_rows}</tbody></table></section>
<footer>NAS 내부 검토용 · 공개 카탈로그·기존 상세 DB·공급처 DB 변경 없음</footer></main>'''
    script = '<script id="feed-data" type="application/json">' + payload + '''</script><script>
const data=JSON.parse(document.getElementById('feed-data').textContent),el=id=>document.getElementById(id);let pageNo=0;
for(const m of data.makers){const o=document.createElement('option');o.value=m.label;o.textContent=m.label+' ('+m.products.toLocaleString()+')';el('maker').append(o)}
function draw(){const q=el('query').value.normalize('NFKC').toLowerCase().trim(),m=el('maker').value,n=el('newonly').checked;
const rows=data.rows.filter(r=>(!q||r.slice(0,4).some(x=>x.normalize('NFKC').toLowerCase().includes(q)))&&(!m||r[2]===m)&&(!n||r[7]));
pageNo=Math.max(0,Math.min(pageNo,Math.ceil(rows.length/100)-1));el('rows').replaceChildren();
for(const r of rows.slice(pageNo*100,pageNo*100+100)){const tr=document.createElement('tr');for(const v of r.slice(0,6)){const td=document.createElement('td');td.textContent=v||'미기재';tr.append(td)}const td=document.createElement('td'),a=document.createElement('a');a.href=r[6];a.textContent='상품 보기';a.target='_blank';a.rel='noopener noreferrer';td.append(a);tr.append(td);el('rows').append(tr)}
el('count').textContent=rows.length.toLocaleString()+'개 중 '+(rows.length?pageNo*100+1:0)+'–'+Math.min(rows.length,pageNo*100+100);el('prev').disabled=pageNo===0;el('next').disabled=(pageNo+1)*100>=rows.length}
el('query').oninput=()=>{pageNo=0;draw()};el('maker').onchange=el('newonly').onchange=()=>{pageNo=0;draw()};el('prev').onclick=()=>{pageNo--;draw()};el('next').onclick=()=>{pageNo++;draw()};draw();
</script>'''
    target.write_text(page('나다운 기프트 · 본사 제공 상품 파일', body, script))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--feed', type=Path, required=True)
    parser.add_argument('--inventory', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--review', type=Path)
    args = parser.parse_args()
    print(json.dumps(prepare(args.feed, args.inventory, args.output), ensure_ascii=False, indent=2))
    if args.review:
        build_review(args.output, args.review)
