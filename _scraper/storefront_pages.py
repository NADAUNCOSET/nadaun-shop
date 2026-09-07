"""Render crawlable first responses; JavaScript progressively adds filters."""
from html import escape
from pathlib import Path


def card(p):
    price=p.get('sale_price') if any(o['source'] in ('smartstore','imweb') for o in p['offers']) else p.get('price')
    amount=f'{price:,}원' if price is not None else '가격 문의'
    return f'<a class="product-card" href="/item.html?id={escape(p["id"])}"><div class="product-image"><img src="{escape(p["image"])}" alt="{escape(p["name"])}" loading="lazy" referrerpolicy="no-referrer"></div><h3 class="product-name">{escape(p["name"])}</h3><p class="product-price">{amount}</p></a>'


def content(mode, brands, products, brand=None):
    if mode=='home':
        links=''.join(f'<a class="brand-tile" href="/brands/{escape(b["id"])}.html" target="_blank" rel="noopener"><span class="brand-word">'+(f'<img src="{escape(b["logo"])}" alt="{escape(b["name"])}" loading="lazy" referrerpolicy="no-referrer">' if b.get('logo') else escape(b['name']))+f'</span><small>{b["count"]:,} PRODUCTS ↗</small></a>' for b in brands[:21])
        dji=next((p for p in products if p['brand_id']=='dji' and 'Action 6' in p['name'] and p['kind']!='rental'),next(p for p in products if p['brand_id']=='dji'))
        rig=next(p for p in products if p['brand_id']=='smallrig' and '케이지' in p['name'] and p['status']!='soldout')
        selected=[next((p for p in products if p['brand_id']==bid and p['kind']!='rental' and p['status']!='soldout'),None) for bid in ['dji','leofoto','hoya','smallrig','tilta','pgytech','nanlite','godox']]
        page=(Path(__file__).parent/'shop_templates/home.html').read_text()
        for key,value in {'DJI_IMAGE':dji['image'],'DJI_NAME':dji['name'],'RIG_IMAGE':rig['image'],'BRAND_COUNT':len(brands)}.items():
            page=page.replace('{{'+key+'}}',escape(str(value)))
        return page.replace('{{BRANDS}}',links).replace('{{PRODUCTS}}',''.join(card(p) for p in selected if p))
    if mode=='catalog':
        name=(brand['name']+' 브랜드몰') if brand else '전체 상품'
        rows=[p for p in products if (not brand or p['brand_id']==brand['id']) and p.get('listing_id',p['id'])==p['id']]
        kind='rental' if brand and not brand['purchase_count'] else 'purchase'
        rows=[p for p in rows if p['kind']==kind]
        return f'<div class="breadcrumb"><a href="/">홈</a><span>›</span>{escape(name)}</div><div class="catalog-heading"><h1>{escape(name)}</h1></div><div class="product-grid">'+''.join(card(p) for p in rows[:24])+'</div>'
    if mode in ('cart','checkout'):
        return '<div class="loading" role="status">선택하신 상품을 확인하고 있습니다.</div>'
    if mode=='categories':
        return '<section class="brand-section"><h1>브랜드별로 장비를 찾아보세요.</h1><p>제품 종류별 통합 카테고리는 준비 중입니다.</p><a href="/#brands">브랜드 전체 보기 →</a></section>'
    return '<div class="loading" role="status"><span></span>상품을 불러오고 있습니다.</div>'
