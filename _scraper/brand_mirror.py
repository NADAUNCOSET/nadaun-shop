"""브랜드 단위 미러링 수집기 (2026-08-04 대표 방향 전환)

방식: 넓게 다 긁고 나중에 정리 X → **한 사이트의 브랜드 1개씩** 원본 그대로 미러링하고
      대표 검수 통과분만 확정 카탈로그에 올린다.

    python brand_mirror.py kpp SMALLRIG          # 수집 → _pending/kpp__SMALLRIG.json
    python brand_mirror.py kpp SMALLRIG --limit 20   # 파일럿(카테고리당 20개)

산출물: data/_pending/<site>__<BRAND>.json  (검수 대기)
        검수 통과 후 approve_brand.py 가 data/products/<slug>.json 으로 승격.

수집 원칙:
  - 카테고리 트리 = **소스 사이트 원본 그대로** (추측 분류 금지)
  - 가격/이미지/상세 = 원본 그대로. 없으면 없는 대로 기록(결손을 검수에서 보이게)
  - 렌탈/중고/전시 등 판매 대상 아닌 것은 source_rules.is_junk 로 제외
"""
import sys, os, io, json, re, time, argparse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)

import kpp  # get / parse_item / list_items / clean / absu / upl 재사용
from bs4 import BeautifulSoup

try:
    from source_rules import is_junk
except Exception:
    def is_junk(*a, **k):
        return False

DATA = os.path.abspath(os.path.join(HERE, "..", "data"))
PENDING = os.path.join(DATA, "_pending")
os.makedirs(PENDING, exist_ok=True)


# ───────────────────────── KPP ─────────────────────────
def kpp_brand_categories(brand):
    """brandmall.php?brand=X 에서 **그 브랜드 전용** 카테고리(ca_id→이름)만.

    ⚠️ 페이지 전체에서 ca_id를 긁으면 사이트 공통 GNB(.cate_li_1/.cate_li_2, 158개)까지
       빨려들어 브랜드와 무관한 카테고리가 붙는다 (2026-08-04 SMALLRIG 184개 오수집).
       브랜드 전용 메뉴는 `.brand_main_menu` 컨테이너 안에만 있다 (SMALLRIG=14개, d 접두).
    """
    url = f"{kpp.BASE}/shop/brandmall.php?brand={brand}"
    soup = BeautifulSoup(kpp.get(url).text, "html.parser")
    cats = {}
    for a in soup.select('.brand_main_menu a[href*="ca_id="]'):
        m = re.search(r"ca_id=([0-9a-zA-Z]+)", a.get("href", ""))
        if not m:
            continue
        cid = m.group(1)
        nm = kpp.clean(a.get_text()).lstrip("#")
        if not nm:
            continue
        if cid not in cats or len(nm) > len(cats[cid]):
            cats[cid] = nm
    return cats, url


def collect_kpp(brand, limit=None):
    cats, brand_url = kpp_brand_categories(brand)
    if not cats:
        raise SystemExit(f"[{brand}] 브랜드몰에서 카테고리를 못 찾음 — 브랜드명 확인 필요: {brand_url}")

    print(f"[{brand}] 카테고리 {len(cats)}개")
    for cid, nm in sorted(cats.items()):
        print(f"    {cid}  {nm}")

    products, seen = {}, set()
    for cid, cname in sorted(cats.items()):
        ids = kpp.list_items(cid)
        if limit:
            ids = ids[:limit]
        print(f"  · {cname}({cid}) 제품 {len(ids)}개", flush=True)
        for i, it_id in enumerate(ids, 1):
            pid = f"kpp-{it_id}"
            if pid in seen:
                # 같은 제품이 여러 카테고리에 있으면 카테고리만 추가
                products[pid]["cat_paths"].append([cname])
                continue
            try:
                d = kpp.parse_item(it_id)
            except Exception as e:
                print(f"    !! {it_id} 파싱실패 {e}", flush=True)
                continue
            name = d.get("name") or ""
            # is_junk는 제품 dict를 받는다 (cat_path/category/name 기준)
            if is_junk({"name": name, "cat_path": [cname], "category": cname}):
                continue
            seen.add(pid)
            products[pid] = {
                "id": pid,
                "source": "kpp",
                "source_id": it_id,
                "name": name,
                "brand": brand,
                "cat_path": [cname],          # 소스 원본 카테고리
                "cat_paths": [[cname]],
                "price": d.get("price") or 0,
                "list_price": d.get("list_price") or 0,
                "sale_price": d.get("sale_price") or 0,
                "inquiry": bool(d.get("inquiry")),
                "source_url": d.get("url"),
                "images_src": {              # 원본 URL (승인 후 R2 업로드)
                    "main": d.get("main") or [],
                    "detail": d.get("detail") or [],
                },
            }
            if i % 20 == 0:
                print(f"    … {i}/{len(ids)}", flush=True)
            time.sleep(0.25)

    return {
        "site": "kpp",
        "brand": brand,
        "brand_url": brand_url,
        "categories": cats,
        "collected_at": None,       # 스크립트는 시각을 기록하지 않음(호출부에서 stamp)
        "product_count": len(products),
        "products": products,
    }


COLLECTORS = {"kpp": collect_kpp}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("site", help="소스 사이트 (현재 kpp)")
    ap.add_argument("brand", help="브랜드명 (KPP brandmall의 brand 파라미터, 예 SMALLRIG)")
    ap.add_argument("--limit", type=int, default=None, help="카테고리당 최대 제품수 (파일럿용)")
    a = ap.parse_args()

    fn = COLLECTORS.get(a.site)
    if not fn:
        raise SystemExit(f"미지원 사이트: {a.site} (가능: {', '.join(COLLECTORS)})")

    out = fn(a.brand, a.limit)

    # 결손 통계 — 검수에서 바로 보이도록
    ps = out["products"].values()
    n = len(ps)
    no_price = sum(1 for p in ps if not p["price"])
    no_main = sum(1 for p in ps if not p["images_src"]["main"])
    no_det = sum(1 for p in ps if not p["images_src"]["detail"])
    out["stats"] = {"total": n, "no_price": no_price, "no_main_image": no_main, "no_detail": no_det}

    path = os.path.join(PENDING, f"{a.site}__{a.brand}.json")
    io.open(path, "w", encoding="utf-8").write(json.dumps(out, ensure_ascii=False, indent=1))

    print()
    print(f"=== [{a.site}/{a.brand}] 수집 완료 ===")
    print(f"  제품 {n}개 · 카테고리 {len(out['categories'])}개")
    print(f"  가격없음 {no_price} / 대표이미지없음 {no_main} / 상세없음 {no_det}")
    print(f"  저장: {path}")
    print(f"  → 검수: review.html 에서 확인 후 승인")


if __name__ == "__main__":
    main()
