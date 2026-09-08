"""Render crawlable first responses; JavaScript progressively adds filters."""
from html import escape
from pathlib import Path
import json


def banner_content():
    banners=json.loads((Path(__file__).resolve().parents[1]/'data/catalog/banners.json').read_text())['banners']
    slides=[]
    for i,b in enumerate(banners):
        if not b['href'].startswith('/') or b['href'].startswith('//'):
            raise ValueError('Banner target must be a shop path')
        slides.append(f'<a class="shop-banner-slide{" is-active" if i==0 else ""}" href="{escape(b["href"])}" data-banner-title="{escape(b["title"])}" aria-label="{escape(b["title"])} 브랜드 상품 보기"'+('' if i==0 else ' inert aria-hidden="true"')+f'><picture><source media="(max-width:700px)" srcset="{escape(b["mobile"])}" width="750" height="600"><img src="{escape(b["desktop"])}" alt="{escape(b["alt"])}" width="1920" height="400" '+('fetchpriority="high"' if i==0 else 'loading="lazy"')+' decoding="async"></picture></a>')
    return '<section class="shop-banner" aria-label="브랜드 소식" aria-roledescription="캐러셀"><div class="shop-banner-stage">'+''.join(slides)+'</div><div class="banner-bar"><span class="banner-caption">'+escape(banners[0]['title'])+'</span><div class="banner-controls" hidden><button type="button" data-banner-prev aria-label="이전 배너">←</button><span class="banner-counter" aria-live="off">01 / '+str(len(banners)).zfill(2)+'</span><button type="button" data-banner-next aria-label="다음 배너">→</button><button type="button" data-banner-play aria-label="배너 자동 넘김 일시정지">Ⅱ</button></div><span class="sr" data-banner-status role="status"></span></div><div class="banner-progress" aria-hidden="true"><span></span></div></section>'


def brand_tile(b):
    motion=f' data-motion-image="{escape(b["representative_alternate"])}"' if b.get('representative_alternate') else ''
    return f'<a class="brand-tile" data-brand-search="{escape(" ".join([b["name"],*b.get("aliases",[])]))}" href="/brands/{escape(b["id"])}.html" target="_blank" rel="noopener" aria-label="{escape(b["name"])} 브랜드몰 새 창"><span class="brand-visual brand-object"{motion}><img src="{escape(b["representative_image"])}" alt="{escape(b["representative_name"])}" width="400" height="400" loading="lazy" decoding="async" referrerpolicy="no-referrer"></span><span class="brand-label">{escape(b["name"])}</span><small>{b["purchase_count"] or b["rental_count"]:,} {"PRODUCTS" if b["purchase_count"] else "RENTAL"} <span aria-hidden="true">↗</span></small></a>'


def gift_content():
    data=json.loads((Path(__file__).resolve().parents[1]/'data/catalog/sources/nadaun-gift.json').read_text())
    if not data.get('complete'):raise RuntimeError('Gift shop source is incomplete')
    categories=''.join(f'<a href="{escape(c["url"])}" target="_blank" rel="noopener">{escape(c["name"])} <span aria-hidden="true">↗</span></a>' for c in data['categories'])
    products=''.join(f'<a class="product-card" href="{escape(p["url"])}" target="_blank" rel="noopener"><div class="product-image"><img src="{escape(p["image"])}" alt="{escape(p["name"])}" loading="lazy" referrerpolicy="no-referrer"></div><div class="product-brand">NADAUN GIFT</div><h3 class="product-name">{escape(p["name"])}</h3><span class="gift-product-link">수량·인쇄·가격 확인 ↗</span></a>' for p in data['featured_products'][:12])
    return '<div class="breadcrumb"><a href="/">홈</a><span>›</span>기프트·굿즈</div><section class="gift-intro"><span class="section-index">NADAUN GIFT / OBJECTS WITH MEANING</span><h1>물건에 담는,<br>당신의 이야기.</h1><div><p>기업 선물, 브랜드 굿즈, 일상의 작은 기념품.<br>나다운기프트에서 수량과 인쇄, 제작 조건을 확인하세요.</p><a class="art-cta" href="https://www.nadaun-gift.com/" target="_blank" rel="noopener">기프트샵 전체 보기 <span>↗</span></a></div></section><section class="gift-selection"><div class="section-head"><div><span class="section-index">GIFT SELECTION</span><h2>전하고 싶은 마음의 모양.</h2></div><a href="#gift-categories">종류별로 찾기 ↓</a></div><div class="product-grid">'+products+'</div><p class="gift-order-note">기프트 상품의 가격은 주문 수량, 인쇄와 포장에 따라 달라집니다. 선택한 상품은 나다운기프트의 상세·주문 화면으로 연결됩니다.</p></section><section id="gift-categories" class="gift-categories"><div class="section-head"><div><span class="section-index">THE GIFT INDEX</span><h2>무엇을 선물할까요?</h2><p>기프트샵의 전체 상품 분류에서 찾아보세요.</p></div></div><label class="sr" for="gift-search">기프트 카테고리 찾기</label><input id="gift-search" type="search" placeholder="텀블러, 에코가방, 문구, 상패…"><span id="gift-search-status" role="status" aria-live="polite"></span><div class="gift-category-grid">'+categories+'</div></section>'


def card(p):
    price=p.get('sale_price') if any(o['source'] in ('smartstore','imweb') for o in p['offers']) else p.get('price')
    amount=f'{price:,}원' if price is not None else '가격 문의'
    motion=f' data-motion-image="{escape(p["motion_image"])}"' if p.get('motion_image') else ''
    return f'<a class="product-card" href="/item.html?id={escape(p["id"])}"><div class="product-image"{motion}><img src="{escape(p["image"])}" alt="{escape(p["name"])}" loading="lazy" referrerpolicy="no-referrer"></div><h3 class="product-name">{escape(p["name"])}</h3><p class="product-price">{amount}</p></a>'


def content(mode, brands, products, brand=None):
    if mode in ('orders','admin'):
        title='주문 조회' if mode=='orders' else '주문 관리'
        description='접수한 주문과 결제·배송 상태를 확인하세요.' if mode=='orders' else '접수 확인부터 금액 확정, 결제 확인과 출고까지.'
        note='<p class="commerce-note">주문한 브라우저에서 조회할 수 있습니다. 다른 기기에서는 주문번호로 고객센터에 문의해주세요.</p>' if mode=='orders' else ''
        return f'<section class="commerce-shell"><header class="commerce-heading"><div><span class="section-index">NADAUN SHOP / ORDERS</span><h1>{title}</h1><p>{description}</p></div><a href="/catalog.html">상품 둘러보기 ↗</a></header>{note}<p id="commerce-status" class="commerce-feedback" role="status" hidden></p><div id="commerce-content" aria-live="polite"><p>주문 서비스 연결을 확인하고 있습니다.</p></div><noscript>주문 조회에는 자바스크립트가 필요합니다.</noscript></section>'
    if mode=='brands':
        cards=''.join(brand_tile(b) for b in brands)
        return f'<div class="breadcrumb"><a href="/">홈</a><span aria-hidden="true">›</span><span aria-current="page">전체 브랜드</span></div><section class="brand-directory" aria-labelledby="brand-directory-title"><div class="section-head"><div><span class="section-index">THE BRAND INDEX</span><h1 id="brand-directory-title">전체 브랜드</h1><p>브랜드의 대표 제품을 보고, 원하는 브랜드몰로 들어가세요.</p></div><span class="brand-total">{len(brands)} BRANDS</span></div><div class="brand-tools"><label class="sr" for="brand-search">브랜드 찾기</label><input type="search" id="brand-search" placeholder="브랜드명으로 찾기" aria-controls="brand-grid" autocomplete="off"><span id="brand-search-status" role="status" aria-live="polite">전체 {len(brands)}개 브랜드</span></div><div class="brand-grid" id="brand-grid">{cards}</div><p class="brand-no-results" id="brand-no-results" hidden>일치하는 브랜드가 없습니다. 다른 이름으로 찾아보세요.</p></section>'
    if mode=='home':
        links=''.join(brand_tile(b) for b in brands[:18])
        # Curated purchase display. Do not label this as measured sales ranking.
        eligible=[p for p in products if p['kind']=='purchase' and p['status']!='soldout' and p.get('listing_id',p['id'])==p['id']]
        selected=[]
        for bid in ['dji','leofoto','hoya','smallrig','tilta','pgytech','nanlite','godox']:
            featured=next((b['representative_id'] for b in brands if b['id']==bid),None)
            chosen=next((p for p in eligible if p['id']==featured),next((p for p in eligible if p['brand_id']==bid),None))
            if chosen:selected.append(chosen)
        page=(Path(__file__).parent/'shop_templates/home.html').read_text()
        for key,value in {'BRAND_COUNT':len(brands)}.items():
            page=page.replace('{{'+key+'}}',escape(str(value)))
        return page.replace('{{BANNERS}}',banner_content()).replace('{{BRANDS}}',links).replace('{{PRODUCTS}}',''.join(card(p) for p in selected if p))
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
