"""미러링 제품의 카테고리를 원본 사이트 트리(계층) 그대로 복원

KPP ca_id는 접두 계층이다 (d2f0=액세서리, d2f040=액세서리>스트랩&파우치).
brand_mirror 1차 수집본은 말단 이름만 담았으므로, pending의 categories(ca_id→이름)로
접두 계층을 복원해 cat_path를 대>중>소로 채운다. 동시에 mirror 플래그를 세운다.

    python fix_mirror_cats.py SMALLRIG smallrig
"""
import os, io, json, sys

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.abspath(os.path.join(HERE, "..", "data"))


def chain(cid, cats):
    """ca_id 접두 계층 → 이름 리스트 (대>중>소)."""
    anc = sorted([c for c in cats if cid.startswith(c)], key=len)
    return [cats[c] for c in anc]


def run(brand, slug):
    pp = os.path.join(DATA, "_pending", f"kpp__{brand}.json")
    mir = json.load(io.open(pp, encoding="utf-8"))
    cats = mir.get("categories") or {}

    # 이름 → ca_id 역맵 (이름 중복 시 더 짧은 = 상위 우선)
    name2cid = {}
    for cid, nm in sorted(cats.items(), key=lambda x: len(x[0])):
        name2cid.setdefault(nm, cid)

    fixed = 0
    for pid, p in (mir.get("products") or {}).items():
        leaf = (p.get("cat_path") or [""])[0]
        cid = name2cid.get(leaf)
        if not cid:
            continue
        path = chain(cid, cats)
        if path:
            p["cat_path"] = path
            p["ca_id"] = cid
            fixed += 1
    io.open(pp, "w", encoding="utf-8").write(json.dumps(mir, ensure_ascii=False, indent=1))
    print(f"[pending] 계층 복원 {fixed:,}개 / 카테고리 {len(cats)}개")

    # 실데이터 반영
    sp = os.path.join(DATA, "products", f"{slug}.json")
    d = json.load(io.open(sp, encoding="utf-8"))
    prods = d.get("products") or {}
    n = 0
    for pid, p in prods.items():
        if (p.get("source") or "") != "kpp":
            continue
        m = (mir.get("products") or {}).get(pid)
        if not m:
            continue
        p["cat_path"] = m.get("cat_path") or p.get("cat_path") or []
        p["category"] = (p["cat_path"] or [""])[0]
        p["ca_id"] = m.get("ca_id")
        p["mirror"] = "kpp"          # ★ 원본 그대로 미러링임을 표시 (빌더가 추측분류로 덮지 않게)
        n += 1
    io.open(sp, "w", encoding="utf-8").write(json.dumps(d, ensure_ascii=False, indent=1))
    print(f"[{slug}.json] 미러 표기 + 계층 반영 {n:,}개")

    # 결과 트리 미리보기
    from collections import Counter
    c = Counter(" > ".join(p.get("cat_path") or []) for p in prods.values() if p.get("mirror"))
    print(f"\n미러 카테고리 {len(c)}종 (상위 25):")
    for k, v in c.most_common(25):
        print(f"  {v:>5}  {k}")


if __name__ == "__main__":
    run(sys.argv[1] if len(sys.argv) > 1 else "SMALLRIG",
        sys.argv[2] if len(sys.argv) > 2 else "smallrig")
