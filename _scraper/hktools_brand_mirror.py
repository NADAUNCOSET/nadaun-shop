# -*- coding: utf-8 -*-
"""hktools 브랜드 미러 — 한 브랜드의 hktools 카테고리 트리(대>중>소)를 그대로 미러링 (2026-07-20 대표).
   hktools는 /category/<name>/<id>/ 커스텀 URL이지만 id=cafe24 cate_no로 접근됨.
   브랜드 루트 cate_no 하위 전 카테고리를 breadcrumb으로 트리화 → 리프 우선 제품 매핑 →
   parse_item(이미지/가격/상세) → data/products/<slug>.json 의 hktools 제품 교체.
   실행: python hktools_brand_mirror.py <slug> <루트cate_no> <브랜드영문명>
   예:   python hktools_brand_mirror.py profoto 2968 Profoto"""
import sys, io, re, json, time
try: sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
except Exception: pass
sys.argv_backup = sys.argv[:]
sys.path.insert(0, r"\\Nadaunproject\nadaunproject\_Site\nadaun-shop\_scraper")
import cafe24 as C
from bs4 import BeautifulSoup
from pathlib import Path

SLUG = sys.argv_backup[1] if len(sys.argv_backup) > 1 else "profoto"
ROOT_CID = sys.argv_backup[2] if len(sys.argv_backup) > 2 else "2968"
BRAND_EN = sys.argv_backup[3] if len(sys.argv_backup) > 3 else "Profoto"
BASE = "https://hktools.co.kr"
DATA = Path(r"\\Nadaunproject\nadaunproject\_Site\nadaun-shop\data\products")

def crumb(cid):
    soup = BeautifulSoup(C.get(f"{BASE}/product/list.html?cate_no={cid}").text, "html.parser")
    for sel in [".xans-product-headcategory a", "ul.xans-product-headcategory li a", ".path a"]:
        ns = [C.clean(a.get_text()) for a in soup.select(sel)]
        ns = [x for x in ns if x and x not in ("홈", "HOME", "Home", ">")]
        if ns: return ns
    return []

# 1) 브랜드 루트 페이지에서 하위 카테고리 id 전부
soup = BeautifulSoup(C.get(f"{BASE}/product/list.html?cate_no={ROOT_CID}").text, "html.parser")
ids = {ROOT_CID}
for a in soup.select('a[href*="/category/"], a[href*="cate_no="]'):
    m = re.search(r"/category/[^/]+/(\d+)", a.get("href", "")) or re.search(r"cate_no=(\d+)", a.get("href", ""))
    if m: ids.add(m.group(1))

# 2) breadcrumb에 브랜드명 있는 카테고리만 = 이 브랜드 하위
cats = {}
for cid in sorted(ids):
    cr = crumb(cid)
    if any(s.lower() == BRAND_EN.lower() for s in cr):
        idx = next(i for i, s in enumerate(cr) if s.lower() == BRAND_EN.lower())
        cats[cid] = cr[idx:]        # 브랜드명부터 (앞의 '1. 조명' 등 제거)
print(f"[{BRAND_EN}] 하위 카테고리 {len(cats)}개", flush=True)
for cid, p in sorted(cats.items(), key=lambda x: len(x[1])):
    print(f"  {cid:<6} {' > '.join(p)}", flush=True)

# 3) 리프 우선(깊은 경로 먼저) 제품→카테고리 매핑 (중복노출 상위 카테고리는 skip)
mem = {}
for cid in sorted(cats, key=lambda c: -len(cats[c])):
    items = C.list_items(BASE, cid)
    for pno in items:
        mem.setdefault(pno, cid)
    print(f"  cate {cid} ({cats[cid][-1]}): {len(items)}개 → 누적 {len(mem)}", flush=True)

# 4) 제품 수집 (이미지 R2 재사용/업로드)
prods = {}
for i, (pno, cid) in enumerate(mem.items(), 1):
    url = f"{BASE}/product/detail.html?product_no={pno}"
    try: d = C.parse_item(BASE, url)
    except Exception as e:
        print(f"  ! {pno} 파싱실패 {e}", flush=True); continue
    path = cats[cid]
    pid = f"hktools-{pno}"
    rec = {"id": pid, "source": "hktools", "source_id": pno, "name": d["name"],
           "brand": BRAND_EN, "brand_slug": SLUG, "category": path[-1], "cat_path": path,
           "cate_no": cid, "price": d["price"], "list_price": d["list_price"],
           "sale_price": d["sale_price"], "inquiry": d["inquiry"], "source_url": url,
           "images": {"thumb": "", "main": [], "detail": []}}
    if d["main"]:
        rec["images"]["thumb"] = C.upl(d["main"][0], f"shop/thumbnails/{SLUG}/{pid}.webp", 600)
    for n, s in enumerate(d["main"], 1):
        u = C.upl(s, f"shop/images/{SLUG}/{pid}/main_{n}.webp", 1600)
        if u: rec["images"]["main"].append(u)
    for n, s in enumerate(d["detail"], 1):
        u = C.upl(s, f"shop/detail/{SLUG}/{pid}/{n:02d}.webp", 1400)
        if u: rec["images"]["detail"].append(u)
    prods[pid] = rec
    if i % 20 == 0: print(f"  … 수집 {i}/{len(mem)}", flush=True)

# 5) <slug>.json 갱신: hktools 제품 전량 교체(기존 hktools 제거 후 새로), 타소스 보존
fp = DATA / f"{SLUG}.json"
pack = json.load(open(fp, encoding="utf-8")) if fp.exists() else {"brand": BRAND_EN, "brand_slug": SLUG, "products": {}}
pack["products"] = {pid: v for pid, v in pack["products"].items() if v.get("source") != "hktools"}
pack["products"].update(prods)
json.dump(pack, open(fp, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

# 카테고리별 개수 요약
import collections
by = collections.Counter()
for v in prods.values():
    cp = v["cat_path"]
    by[cp[1] if len(cp) > 1 else cp[0]] += 1
print(f"\n=== {BRAND_EN} hktools 미러 완료: {len(prods)}개 ===", flush=True)
for c, n in by.most_common():
    print(f"  {n:>3}  {c}", flush=True)
