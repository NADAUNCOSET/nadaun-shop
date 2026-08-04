"""브랜드 확정 적용 — 허용 소스만 남기고, KPP 미러링으로 교체

대표 룰 (2026-08-04): 브랜드마다 **허용 소스를 고정**하고 그 외 소스 제품은 삭제한다.
  예) SMALLRIG = clmedia + kpp 만. hktools/plthink/saeki/avx/bando 는 전량 삭제.

    python apply_brand.py smallrig --keep clmedia --mirror SMALLRIG --dry
    python apply_brand.py smallrig --keep clmedia --mirror SMALLRIG --apply

동작:
  1) 현재 data/products/<slug>.json 에서 --keep 소스 제품만 보존
  2) --mirror 가 있으면 _pending/kpp__<BRAND>.json 을 **KPP 소스의 진실원본**으로 사용
     (기존 kpp 제품은 전부 버리고 미러링 것으로 교체 → KPP에서 내려간 제품 자동 제거)
  3) 삭제되는 제품의 R2 이미지 키 목록을 _archive/r2_purge_<slug>_<날짜>.json 으로 남김
     (실제 R2 삭제는 대표 승인 후 별도 스크립트)
"""
import os, io, json, sys, argparse, shutil

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.abspath(os.path.join(HERE, "..", "data"))
PROD = os.path.join(DATA, "products")
PEND = os.path.join(DATA, "_pending")
ARCH = os.path.abspath(os.path.join(HERE, "..", "_archive"))
os.makedirs(ARCH, exist_ok=True)


def r2_keys(p):
    """제품 하나가 쓰는 R2(media.nadaun.co) 키들."""
    out = []
    imgs = p.get("images") or {}
    for v in [imgs.get("thumb")] + list(imgs.get("main") or []) + list(imgs.get("detail") or []):
        if v and "media.nadaun.co/" in v:
            out.append(v.split("media.nadaun.co/", 1)[1])
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("slug")
    ap.add_argument("--keep", default="", help="유지할 소스 (쉼표구분). kpp는 --mirror 로 별도 처리")
    ap.add_argument("--mirror", default=None, help="KPP 미러링 브랜드명 (예 SMALLRIG)")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()

    keep = {s.strip() for s in a.keep.split(",") if s.strip()}
    cur_path = os.path.join(PROD, f"{a.slug}.json")
    cur = json.load(io.open(cur_path, encoding="utf-8"))
    prods = cur.get("products") or {}

    by_src = {}
    for k, v in prods.items():
        by_src.setdefault(v.get("source") or "?", []).append((k, v))

    print(f"[{a.slug}] 현재 {len(prods):,}개")
    for s in sorted(by_src, key=lambda x: -len(by_src[x])):
        mark = "유지" if s in keep else ("미러링교체" if (s == "kpp" and a.mirror) else "삭제")
        print(f"   {s:<12} {len(by_src[s]):>6,}  → {mark}")

    kept, purged = {}, []
    for k, v in prods.items():
        s = v.get("source") or "?"
        if s in keep:
            kept[k] = v
        else:
            purged.append(v)   # kpp 포함 (미러링으로 교체되므로 옛 kpp 레코드는 버림)

    # 미러링 편입
    added = 0
    if a.mirror:
        mp = os.path.join(PEND, f"kpp__{a.mirror}.json")
        mir = json.load(io.open(mp, encoding="utf-8"))
        brand_name = cur.get("brand") or a.mirror
        slug = cur.get("brand_slug") or a.slug
        for pid, p in (mir.get("products") or {}).items():
            kept[pid] = {
                "id": pid, "source": "kpp", "source_id": p.get("source_id"),
                "name": p.get("name"), "brand": brand_name, "brand_slug": slug,
                "category": (p.get("cat_path") or [""])[0],
                "cat_path": p.get("cat_path") or [],
                "price": p.get("price") or 0,
                "source_url": p.get("source_url"),
                # 이미지: 승인 후 R2 업로드 전까지 원본 URL 유지 (업로드 단계에서 교체)
                "images_src": p.get("images_src") or {},
            }
            added += 1

    print(f"\n결과: 유지 {len(kept):,}개  (기존보존 {len(kept)-added:,} + 미러링 {added:,})")
    print(f"      삭제 {len(purged):,}개")

    keys = []
    for p in purged:
        keys.extend(r2_keys(p))
    print(f"      R2 정리 후보 키 {len(keys):,}개")

    if not a.apply:
        print("\n--dry (미적용). 실제 반영하려면 --apply")
        return

    # 백업
    bak = os.path.join(ARCH, f"{a.slug}_before_apply.json")
    shutil.copy2(cur_path, bak)

    cur["products"] = kept
    io.open(cur_path, "w", encoding="utf-8").write(json.dumps(cur, ensure_ascii=False, indent=1))

    io.open(os.path.join(ARCH, f"r2_purge_{a.slug}.json"), "w", encoding="utf-8").write(
        json.dumps({"slug": a.slug, "count": len(keys), "keys": keys}, ensure_ascii=False, indent=1))

    print(f"\n적용 완료")
    print(f"  백업     : {bak}")
    print(f"  R2 후보  : {os.path.join(ARCH, f'r2_purge_{a.slug}.json')}  (실제 삭제는 승인 후 별도)")


if __name__ == "__main__":
    main()
