"""브랜드 메뉴 순서를 원본 사이트 그대로 저장 (2026-08-05 대표 "KPP처럼 똑같이")

brand_mirror 가 brandmall 의 .brand_main_menu 를 **등장 순서대로** 읽으므로
_pending 의 categories 키 순서 = 원본 브랜드몰 메뉴 순서다.
그 순서를 data/products/<slug>.json 의 menu_order 로 박아 빌더가 정렬에 쓴다.

    python save_menu_order.py SMALLRIG smallrig
"""
import os, io, json, sys

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.abspath(os.path.join(HERE, "..", "data"))


def run(brand, slug):
    mir = json.load(io.open(os.path.join(DATA, "_pending", f"kpp__{brand}.json"), encoding="utf-8"))
    cats = mir.get("categories") or {}
    # ca_id 가 짧은 것 = 1차(대분류). 등장 순서 유지.
    tops = [nm for cid, nm in cats.items() if len(cid) <= 4]
    seen, order = set(), []
    for nm in tops:
        if nm not in seen:
            seen.add(nm); order.append(nm)

    sp = os.path.join(DATA, "products", f"{slug}.json")
    d = json.load(io.open(sp, encoding="utf-8"))
    d["menu_order"] = order
    io.open(sp, "w", encoding="utf-8").write(json.dumps(d, ensure_ascii=False, indent=1))

    print(f"[{slug}] 원본 메뉴 순서 {len(order)}개 저장")
    for i, nm in enumerate(order, 1):
        print(f"  {i:>2}. {nm}")


if __name__ == "__main__":
    run(sys.argv[1] if len(sys.argv) > 1 else "SMALLRIG",
        sys.argv[2] if len(sys.argv) > 2 else "smallrig")
