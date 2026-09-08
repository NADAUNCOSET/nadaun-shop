"""Render crawlable first responses; JavaScript progressively adds filters."""
from html import escape
from pathlib import Path
import json
from category_gallery import gallery_html


def banner_content():
    banners=json.loads((Path(__file__).resolve().parents[1]/'data/catalog/banners.json').read_text())['banners']
    slides=[]
    for i,b in enumerate(banners):
        if not b['href'].startswith('/') or b['href'].startswith('//'):
            raise ValueError('Banner target must be a shop path')
        slides.append(f'<a class="shop-banner-slide{" is-active" if i==0 else ""}" href="{escape(b["href"])}" data-banner-title="{escape(b["title"])}" aria-label="{escape(b["title"])} 브랜드 상품 보기"'+('' if i==0 else ' inert aria-hidden="true"')+f'><picture><source media="(max-width:700px)" srcset="{escape(b["mobile"])}" width="750" height="600"><img src="{escape(b["desktop"])}" alt="{escape(b["alt"])}" width="1920" height="400" '+('fetchpriority="high"' if i==0 else 'loading="lazy"')+' decoding="async"></picture></a>')
    return '<section class="shop-banner" aria-label="브랜드 소식" aria-roledescription="캐러셀"><div class="shop-banner-stage">'+''.join(slides)+'</div><div class="banner-bar"><span class="banner-caption">'+escape(banners[0]['title'])+'</span><div class="banner-controls" hidden><button type="button" data-banner-prev aria-label="이전 배너">←</button><span class="banner-counter" aria-live="off">01 / '+str(len(banners)).zfill(2)+'</span><button type="button" data-banner-next aria-label="다음 배너">→</button><button type="button" class="banner-accessibility-pause" data-banner-pause aria-pressed="false">배너 자동 넘김 멈추기</button></div><span class="sr" data-banner-status role="status"></span></div><div class="banner-progress" aria-hidden="true"><span></span></div></section>'


def brand_tile(b):
    motion=f' data-motion-image="{escape(b["representative_alternate"])}"' if b.get('representative_alternate') else ''
    mark=f'<span class="brand-mark"><img src="{escape(b["logo"])}" alt="{escape(b["name"])}" loading="lazy" decoding="async"></span>' if b.get('image_kind')=='logo' and not b.get('logo_dark') else f'<span class="brand-mark brand-mark-text">{escape(b["name"])}</span>'
    return f'<a class="brand-tile" data-brand-search="{escape(" ".join([b["name"],*b.get("aliases",[])]))}" href="/brands/{escape(b["id"])}.html" target="_blank" rel="noopener" aria-label="{escape(b["name"])} 브랜드몰 새 창">{mark}<span class="brand-visual brand-object"{motion}><img src="{escape(b["representative_image"])}" alt="{escape(b["representative_name"])}" width="400" height="400" loading="lazy" decoding="async" referrerpolicy="no-referrer"></span><span class="brand-label">{escape(b["name"])}</span><small>{b["purchase_count"] or b["rental_count"]:,} {"PRODUCTS" if b["purchase_count"] else "RENTAL"} <span aria-hidden="true">↗</span></small></a>'


def gift_content():
    data=json.loads((Path(__file__).resolve().parents[1]/'data/gift/manifest.json').read_text())
    roots=[c for c in data['categories'] if not c['parent_ids']]
    tiles=''.join(f'<a class="category-image-tile" href="/gifts.html?category={escape(c["id"])}"><span class="category-image"><img src="{escape(c["image"])}" alt="" loading="lazy" referrerpolicy="no-referrer"></span><strong>{escape(c["name"])}</strong></a>' for c in roots)
    return '<div class="breadcrumb"><a href="/">홈</a><span>›</span>기프트 구매</div><section class="catalog-heading gift-heading"><h1>기프트 구매</h1><p>필요한 종류를 고르고, 수량과 인쇄에 맞는 상품을 찾아보세요.</p></section><nav class="browse-kinds" aria-label="쇼핑 목적"><a href="/catalog.html?kind=purchase">제품 구매</a><a href="/catalog.html?kind=rental">제품 렌탈</a><a href="/gifts.html" aria-current="page">기프트 구매</a></nav><section class="category-gallery"><div class="section-head"><h2>기프트 종류로 찾기</h2></div><nav class="category-image-grid" aria-label="기프트 종류 선택">'+tiles+'</nav></section>'


def card(p):
    price=p.get('sale_price') if any(o['source'] in ('smartstore','imweb') for o in p['offers']) else p.get('price')
    amount=(f'{price:,}원' if price is not None else '가격 문의')+(' <small>/ 대여료 · 기간 확인</small>' if p['kind']=='rental' else '')
    motion=f' data-motion-image="{escape(p["motion_image"])}"' if p.get('motion_image') else ''
    return f'<a class="product-card" href="/item.html?id={escape(p["id"])}"><div class="product-image"{motion}><img src="{escape(p["image"])}" alt="{escape(p["name"])}" loading="lazy" referrerpolicy="no-referrer"></div><h3 class="product-name">{escape(p["name"])}</h3><p class="product-price">{amount}</p></a>'


def content(mode, brands, products, brand=None, category_galleries=None):
    if mode in ('orders','admin'):
        title='주문 조회' if mode=='orders' else '주문 관리'
        description='접수한 주문과 결제·배송 상태를 확인하세요.' if mode=='orders' else '접수 확인부터 금액 확정, 결제 확인과 출고까지.'
        note='<p class="commerce-note">주문한 브라우저에서 조회할 수 있습니다. 다른 기기에서는 주문번호로 고객센터에 문의해주세요.</p>' if mode=='orders' else ''
        return f'<section class="commerce-shell"><header class="commerce-heading"><div><span class="section-index">NADAUN SHOP / ORDERS</span><h1>{title}</h1><p>{description}</p></div><a href="/catalog.html">상품 둘러보기 ↗</a></header>{note}<p id="commerce-status" class="commerce-feedback" role="status" hidden></p><div id="commerce-content" aria-live="polite"><p>주문 서비스 연결을 확인하고 있습니다.</p></div><noscript>주문 조회에는 자바스크립트가 필요합니다.</noscript></section>'
    if mode=='brands':
        cards=''.join(brand_tile(b) for b in brands)
        return f'<div class="breadcrumb"><a href="/">홈</a><span aria-hidden="true">›</span><span aria-current="page">전체 브랜드</span></div><section class="brand-directory" aria-labelledby="brand-directory-title"><div class="section-head"><div><span class="section-index">THE BRAND INDEX</span><h1 id="brand-directory-title">전체 브랜드</h1><p>브랜드의 대표 제품을 보고, 원하는 브랜드몰로 들어가세요.</p></div><span class="brand-total">{len(brands)} BRANDS</span></div><div class="brand-tools"><label class="sr" for="brand-search">브랜드 찾기</label><input type="search" id="brand-search" placeholder="브랜드명으로 찾기" aria-controls="brand-grid" autocomplete="off"><span id="brand-search-status" role="status" aria-live="polite">전체 {len(brands)}개 브랜드</span></div><div class="brand-grid" id="brand-grid">{cards}</div><p class="brand-no-results" id="brand-no-results" hidden>일치하는 브랜드가 없습니다. 다른 이름으로 찾아보세요.</p></section>'
    if mode=='home':
        links=''.join(brand_tile(b) for b in brands[:24])
        # Curated purchase display. Do not label this as measured sales ranking.
        eligible=[p for p in products if p['kind']=='purchase' and p['status']!='soldout' and p.get('listing_id',p['id'])==p['id']]
        selected=[]
        for bid in ['dji','leofoto','hoya','smallrig','tilta','pgytech','nanlite','godox']:
            featured=next((b['representative_id'] for b in brands if b['id']==bid),None)
            chosen=next((p for p in eligible if p['id']==featured),next((p for p in eligible if p['brand_id']==bid),None))
            if chosen:selected.append(chosen)
        rental_rows=[p for p in products if p['kind']=='rental' and p['status']!='soldout' and p.get('listing_id',p['id'])==p['id']]
        rental=[]
        for category in ('rent:1','rent:2','rent:3','rent:4','rent:5','rent:3','rent:4','rent:7'):
            chosen=next((p for p in rental_rows if category in p['type_ids'] and p not in rental),None)
            if chosen:rental.append(chosen)
        page=(Path(__file__).parent/'shop_templates/home.html').read_text()
        for key,value in {'BRAND_COUNT':len(brands)}.items():
            page=page.replace('{{'+key+'}}',escape(str(value)))
        return page.replace('{{BANNERS}}',banner_content()).replace('{{CATEGORY_GALLERY}}',gallery_html((category_galleries or {}).get('purchase',[]))).replace('{{BRANDS}}',links).replace('{{PRODUCTS}}',''.join(card(p) for p in selected if p)).replace('{{RENTALS}}',''.join(card(p) for p in rental))
    if mode in ('catalog','categories'):
        name=(brand['name']+' 브랜드몰') if brand else '전체 상품'
        rows=[p for p in products if (not brand or p['brand_id']==brand['id']) and p.get('listing_id',p['id'])==p['id']]
        kind='rental' if brand and not brand['purchase_count'] else 'purchase'
        rows=[p for p in rows if p['kind']==kind]
        return f'<div class="breadcrumb"><a href="/">홈</a><span>›</span>{escape(name)}</div><div class="catalog-heading"><h1>{escape(name)}</h1></div><div class="product-grid">'+''.join(card(p) for p in rows[:24])+'</div>'
    if mode=='gift':return gift_content()
    if mode in ('cart','checkout'):
        return '<div class="loading" role="status">선택하신 상품을 확인하고 있습니다.</div>'
    return '<div class="loading" role="status"><span></span>상품을 불러오고 있습니다.</div>'
