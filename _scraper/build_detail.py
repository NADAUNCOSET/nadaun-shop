# -*- coding: utf-8 -*-
"""[상세페이지 생성기] data/products/*.json -> product/<brand>/<id>.html

각 제품별 정적 상세페이지:
  - R2 이미지: main[] 갤러리(썸네일 스트립+히어로 스왑) + detail[] 롱스크롤
  - SEO: title/description/canonical/OG/Twitter + JSON-LD Product(offers KRW)
  - 렌탈/구매 CTA(전화문의), 브레드크럼, 브랜드/카테고리 칩
  - 디자인 토큰 = catalog와 동일(gold/navy/Pretendard/ease)

공유 CSS 1개(product/_style.css)만 쓰고 페이지는 경량 유지.
경로는 전부 루트-상대(/product/..., /brand/...) → Vercel 루트 서빙 기준.
사용:  python build_detail.py [LIMIT]   (LIMIT 있으면 그 개수만 생성=샘플)
"""
import sys, io, json, html, os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import kpp_classify as K
import tilta_taxonomy as TT
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

ROOT = Path(r"\\Nadaunproject\nadaunproject\_DAVINCI NADAUN PROJECT\_Site\nadaun-shop")
DATA = ROOT / "data" / "products"
OUT  = ROOT / "product"
SITE = "https://shop.nadaun.co"
TEL  = "0507-1394-6231"       # 나다운 스페이스 고객센터
CORP = "(주)레인보우베네"

# 상세페이지 고정 안내문(전 제품 공통). 상단=상세영역 맨 위, 하단=상세이미지 뒤.
# 나중에 하단/렌탈용 추가 시 여기 리스트에만 넣으면 전 페이지 반영.
NOTICE = "https://media.nadaun.co/shop/notice"
TOP_NOTICES = [(f"{NOTICE}/return-policy.webp", "교환 및 반품 불가 안내 — 나다운 스페이스 판매 상품은 미개봉 상품입니다")]
BOTTOM_NOTICES = []

master = json.load(open(ROOT/"data"/"brands.json", encoding="utf-8"))["brands"]
by_slug = {m["slug"]: m for m in master}
FRIENDLY = {"_misc": ("기타", "ETC"), "_custom": ("주문제작", "CUSTOM")}

DAE_NAME = {**TT.DAE, **K.DAE}

def esc(s): return html.escape(str(s or ""), quote=True)

def brand_names(slug, prod_brand):
    m = by_slug.get(slug, {})
    kr = m.get("kr") or FRIENDLY.get(slug, ("", ""))[0] or prod_brand or slug
    en = m.get("en") or FRIENDLY.get(slug, ("", slug.upper()))[1] or slug.upper()
    return kr, en

def categories(slug, name, cat):
    """대분류/중분류(/소분류) 표시명 리스트 반환."""
    if slug == "tilta":
        dc, dn, jc, jn, kc, kn = TT.classify_tilta(name, cat)
    else:
        dc, dn, jc, jn = K.classify(name, cat); kn = ""
    out = [x for x in (dn, jn, kn) if x]
    return out or [cat or "기타"]

# ── 공유 CSS ──────────────────────────────────────────────
CSS = """*{margin:0;padding:0;box-sizing:border-box}
:root{--ink:#141414;--soft:#6b6b6b;--line:#e7e5e0;--gold:#b78a47;--navy:#1b2a4a;--cream:#f6f4f0;--ease:cubic-bezier(.16,1,.3,1)}
html{scroll-behavior:smooth}
body{font-family:Pretendard,system-ui,sans-serif;color:var(--ink);background:#fff;-webkit-font-smoothing:antialiased;line-height:1.5}
a{text-decoration:none;color:inherit}
img{display:block;max-width:100%}
.wrap{max-width:1240px;margin:0 auto;padding:0 clamp(14px,3.5vw,44px)}
header{border-bottom:1px solid var(--line);position:sticky;top:0;background:rgba(255,255,255,.94);backdrop-filter:blur(12px);z-index:30}
.nav{display:flex;align-items:center;justify-content:space-between;height:62px}
.nav .logo{height:19px}
.nav .links{display:flex;gap:20px;font-size:13px;color:var(--soft)}
.nav .links a:hover{color:var(--ink)}
/* 브레드크럼 */
.crumb{font-size:12.5px;color:var(--soft);padding:20px 0 6px;display:flex;flex-wrap:wrap;gap:7px;align-items:center}
.crumb a:hover{color:var(--gold)}
.crumb span.sep{opacity:.5}
/* 히어로 그리드 */
.hero{display:grid;grid-template-columns:1.05fr .95fr;gap:clamp(24px,4vw,60px);padding:14px 0 64px;align-items:start}
@media(max-width:860px){.hero{grid-template-columns:1fr;gap:26px}}
/* 갤러리 */
.gal{position:sticky;top:82px}
@media(max-width:860px){.gal{position:static}}
.gal .stage{border:1px solid var(--line);border-radius:18px;overflow:hidden;background:var(--cream);aspect-ratio:1/1;display:flex;align-items:center;justify-content:center}
.gal .stage img{width:100%;height:100%;object-fit:contain;transition:.5s var(--ease)}
.gal .thumbs{display:flex;gap:10px;margin-top:14px;flex-wrap:wrap}
.gal .thumbs button{width:64px;height:64px;border:1px solid var(--line);border-radius:11px;overflow:hidden;background:var(--cream);cursor:pointer;padding:0;transition:.35s var(--ease)}
.gal .thumbs button.on{border-color:var(--navy)}
.gal .thumbs img{width:100%;height:100%;object-fit:contain}
/* 정보 */
.info .eyebrow{font-size:12px;letter-spacing:.22em;text-transform:uppercase;color:var(--gold);font-weight:700}
.info h1{font-size:clamp(21px,2.7vw,30px);font-weight:800;letter-spacing:-.02em;line-height:1.25;margin:12px 0 18px}
.info .price{font-size:26px;font-weight:800;letter-spacing:-.02em}
.info .price small{font-size:14px;font-weight:600;color:var(--soft);margin-right:7px}
.info .price.ask{font-size:19px;color:var(--navy)}
.chips{display:flex;flex-wrap:wrap;gap:8px;margin:20px 0 26px}
.chips a{font-size:12.5px;color:var(--soft);border:1px solid var(--line);border-radius:999px;padding:6px 13px;transition:.35s var(--ease)}
.chips a:hover{border-color:var(--gold);color:var(--ink)}
.cta{display:flex;gap:11px;flex-wrap:wrap}
.cta a{flex:1;min-width:150px;text-align:center;padding:15px 20px;border-radius:12px;font-weight:700;font-size:14.5px;transition:.45s var(--ease)}
.cta .primary{background:var(--navy);color:#fff}
.cta .primary:hover{background:#132038;transform:translateY(-2px)}
.cta .ghost{border:1px solid var(--line);color:var(--ink)}
.cta .ghost:hover{border-color:var(--navy);transform:translateY(-2px)}
.note{font-size:12.5px;color:var(--soft);margin-top:18px;line-height:1.7}
.note a{color:var(--gold)}
/* 상세 롱스크롤 */
.detail{border-top:1px solid var(--line);padding:44px 0 20px}
.detail h2{font-size:15px;font-weight:700;letter-spacing:.02em;margin-bottom:26px;display:flex;align-items:center;gap:11px}
.detail h2::before{content:"";width:26px;height:2px;background:var(--gold)}
.detail .imgs{display:flex;flex-direction:column;align-items:center;max-width:820px;margin:0 auto}
.detail .imgs img{width:100%;border-radius:6px;margin-bottom:2px}
.detail .empty{color:var(--soft);font-size:14px;text-align:center;padding:30px 0}
/* 고정 안내문 — 상세 이미지와 동일 폭(820px), 모바일 반응형 */
.notice-top{width:100%;max-width:820px;margin:0 auto 30px}
.notice-bot{width:100%;max-width:820px;margin:30px auto 0}
.notice-top img,.notice-bot img{width:100%;border-radius:10px}
/* 푸터 */
footer{border-top:1px solid var(--line);margin-top:60px;background:var(--cream)}
footer .in{padding:40px 0;display:flex;flex-wrap:wrap;gap:22px;justify-content:space-between;font-size:13px;color:var(--soft)}
footer .cs strong{display:block;color:var(--ink);font-size:18px;letter-spacing:-.01em}
footer .cs span{font-size:12px}
footer a:hover{color:var(--ink)}
footer .top{align-self:flex-end}
"""

# ── 페이지 템플릿 ─────────────────────────────────────────
def page_html(p, slug):
    pid   = p["id"]
    name  = p.get("name", "")
    brand = p.get("brand", "")
    kr, en = brand_names(slug, brand)
    cats  = categories(slug, name, p.get("category", ""))
    price = p.get("price") or 0
    imgs  = p.get("images", {}) or {}
    main  = imgs.get("main") or ([imgs["thumb"]] if imgs.get("thumb") else [])
    detail= imgs.get("detail") or []
    thumb = imgs.get("thumb") or (main[0] if main else "")
    hero  = main[0] if main else thumb
    url   = f"{SITE}/product/{slug}/{pid}.html"

    title = f"{name} — {kr} | 나다운 스페이스"
    desc  = f"{kr}({en}) {name} 촬영장비 렌탈·구매. {' · '.join(cats)}. 서울 영등포 나다운 스페이스({CORP}). 고객센터 {TEL}."
    price_str = (f'<span class="price"><small>판매가</small>{price:,}원</span>'
                 if price else '<span class="price ask">가격 문의 · 렌탈 상담</span>')

    # JSON-LD
    ld = {
        "@context": "https://schema.org/", "@type": "Product",
        "name": name, "brand": {"@type": "Brand", "name": kr},
        "category": " > ".join(cats),
        "url": url,
    }
    if hero: ld["image"] = hero
    if price:
        ld["offers"] = {"@type": "Offer", "priceCurrency": "KRW",
                        "price": price, "availability": "https://schema.org/InStock",
                        "seller": {"@type": "Organization", "name": CORP}}
    ldjson = json.dumps(ld, ensure_ascii=False)

    # 갤러리
    thumbs = "".join(
        f'<button class="{"on" if i==0 else ""}" onclick="sw(this,\'{esc(u)}\')">'
        f'<img src="{esc(u)}" alt="{esc(name)} {i+1}" loading="lazy"></button>'
        for i, u in enumerate(main)) if len(main) > 1 else ""
    gallery = (f'<div class="stage"><img id="hero" src="{esc(hero)}" alt="{esc(name)}"></div>'
               f'<div class="thumbs">{thumbs}</div>') if hero else \
              '<div class="stage"><span style="color:var(--soft);font-size:13px">이미지 준비중</span></div>'

    # 상세 이미지
    dimgs = ("".join(f'<img src="{esc(u)}" alt="{esc(name)} 상세 {i+1}" loading="lazy">'
                     for i, u in enumerate(detail))
             if detail else '<p class="empty">상세 이미지는 준비 중입니다. 고객센터로 문의해 주세요.</p>')

    chips = "".join(f'<a href="/catalog.html">{esc(c)}</a>' for c in cats)

    tn = "".join(f'<div class="notice-top"><img src="{esc(u)}" alt="{esc(a)}" loading="lazy"></div>'
                 for u, a in TOP_NOTICES)
    bn = "".join(f'<div class="notice-bot"><img src="{esc(u)}" alt="{esc(a)}" loading="lazy"></div>'
                 for u, a in BOTTOM_NOTICES)

    return f"""<!DOCTYPE html><html lang="ko"><head>
<meta charset="UTF-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>{esc(title)}</title>
<meta name="description" content="{esc(desc)}"/>
<meta name="keywords" content="{esc(name)}, {esc(kr)}, {esc(en)}, 촬영장비 렌탈, {esc(cats[0])}, 나다운 스페이스, 영등포 렌탈스튜디오"/>
<meta name="author" content="{CORP}"/>
<meta name="robots" content="index, follow, max-image-preview:large"/>
<link rel="canonical" href="{url}"/>
<meta property="og:type" content="product"/><meta property="og:site_name" content="나다운 스페이스"/>
<meta property="og:title" content="{esc(name)} — {esc(kr)}"/>
<meta property="og:description" content="{esc(' · '.join(cats))} · 촬영장비 렌탈·구매 · 나다운 스페이스"/>
<meta property="og:url" content="{url}"/>{f'<meta property="og:image" content="{esc(hero)}"/>' if hero else ''}
<meta name="twitter:card" content="summary_large_image"/>
<link rel="icon" href="/brand/favicon.ico"/>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.css"/>
<link rel="stylesheet" href="/product/_style.css"/>
<script type="application/ld+json">{ldjson}</script>
</head><body>
<header><div class="wrap nav">
<a href="/"><img class="logo" src="/brand/logo-black.png" alt="나다운 스페이스"/></a>
<nav class="links"><a href="/catalog.html">브랜드</a><a href="/catalog_category.html">카테고리</a><a href="/">홈</a></nav>
</div></header>
<main class="wrap">
<nav class="crumb">
<a href="/catalog.html">카탈로그</a><span class="sep">/</span>
<a href="/catalog.html">{esc(kr)}</a><span class="sep">/</span>
<span>{esc(' 〉 '.join(cats))}</span>
</nav>
<section class="hero">
<div class="gal">{gallery}</div>
<div class="info">
<div class="eyebrow">{esc(en)}</div>
<h1>{esc(name)}</h1>
{price_str}
<div class="chips">{chips}</div>
<div class="cta">
<a class="primary" href="tel:{TEL}">렌탈 · 구매 문의</a>
<a class="ghost" href="/catalog.html">카탈로그 더보기</a>
</div>
<p class="note">서울 영등포 나다운 스페이스 · {CORP}<br/>촬영장비 <b>렌탈·구매</b> 모두 가능 · 고객센터 <a href="tel:{TEL}">{TEL}</a></p>
</div>
</section>
<section class="detail">
{tn}<h2>상세 정보</h2>
<div class="imgs">{dimgs}</div>
{bn}</section>
</main>
<footer><div class="wrap in">
<div class="cs"><strong>{TEL}</strong><span>나다운 스페이스 고객센터 · {CORP}</span></div>
<a href="/catalog.html">브랜드 카탈로그</a>
<a class="top" href="#">↑ 위로</a>
</div></footer>
<script>function sw(b,u){{document.getElementById('hero').src=u;document.querySelectorAll('.thumbs button').forEach(function(x){{x.classList.remove('on')}});b.classList.add('on')}}</script>
</body></html>"""

# ── 실행 ──────────────────────────────────────────────────
def main():
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    OUT.mkdir(exist_ok=True)
    (OUT / "_style.css").write_text(CSS, encoding="utf-8")

    n = 0; brands_seen = set()
    for f in sorted(DATA.glob("*.json")):
        d = json.load(open(f, encoding="utf-8"))
        slug = d.get("brand_slug") or f.stem
        for p in d.get("products", {}).values():
            s = p.get("brand_slug") or slug
            bdir = OUT / s
            bdir.mkdir(exist_ok=True)
            (bdir / f'{p["id"]}.html').write_text(page_html(p, s), encoding="utf-8")
            n += 1; brands_seen.add(s)
            if limit and n >= limit:
                print(f"[샘플] {n}개 생성 (브랜드 {len(brands_seen)}) → {OUT}")
                return
    print(f"[전체] {n}개 상세페이지 생성 (브랜드 {len(brands_seen)}) → {OUT}")

if __name__ == "__main__":
    main()
