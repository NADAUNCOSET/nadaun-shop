"""미러링 편입 제품의 이미지를 R2에 업로드하고 images_src → images 로 확정

    python upload_images.py smallrig

- images_src(원본 URL)만 있는 제품을 찾아 R2로 올리고 media.nadaun.co URL로 교체
- 이미 R2에 있으면 재업로드 안 함(kpp.upl 이 head_object로 판정) → 재실행이 이어받음
- 진행상황을 주기적으로 저장하므로 중간에 끊겨도 재실행하면 이어서 진행
"""
import os, io, json, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)

import kpp  # upl / to_webp / R2 설정 재사용

DATA = os.path.abspath(os.path.join(HERE, "..", "data", "products"))

THUMB_W = 600
MAIN_W = 1200
DETAIL_W = 1200


def run(slug):
    path = os.path.join(DATA, f"{slug}.json")
    d = json.load(io.open(path, encoding="utf-8"))
    prods = d.get("products") or {}
    todo = [(k, v) for k, v in prods.items() if v.get("images_src") and not v.get("images")]
    print(f"[{slug}] 총 {len(prods):,}개 중 업로드 대상 {len(todo):,}개", flush=True)
    if not todo:
        print("업로드할 것이 없습니다.")
        return

    done = 0
    for i, (pid, p) in enumerate(todo, 1):
        src = p.get("images_src") or {}
        mains = src.get("main") or []
        dets = src.get("detail") or []
        brand = p.get("brand_slug") or slug

        thumb = ""
        if mains:
            thumb = kpp.upl(mains[0], f"shop/thumbnails/{brand}/{pid}.webp", THUMB_W)

        main_urls = []
        for j, u in enumerate(mains[:6], 1):
            r = kpp.upl(u, f"shop/images/{brand}/{pid}/main_{j}.webp", MAIN_W)
            if r:
                main_urls.append(r)

        det_urls = []
        for j, u in enumerate(dets[:25], 1):
            r = kpp.upl(u, f"shop/detail/{brand}/{pid}/{j:02d}.webp", DETAIL_W)
            if r:
                det_urls.append(r)

        if not thumb and main_urls:
            thumb = main_urls[0]
        if not thumb and det_urls:      # 대표이미지 없으면 상세 첫 장 승격
            thumb = det_urls[0]

        p["images"] = {"thumb": thumb, "main": main_urls, "detail": det_urls}
        p.pop("images_src", None)
        done += 1

        if i % 25 == 0:
            io.open(path, "w", encoding="utf-8").write(json.dumps(d, ensure_ascii=False, indent=1))
            print(f"  … {i}/{len(todo)} (저장)", flush=True)
        time.sleep(0.05)

    io.open(path, "w", encoding="utf-8").write(json.dumps(d, ensure_ascii=False, indent=1))
    nothumb = sum(1 for v in prods.values() if not ((v.get("images") or {}).get("thumb")))
    print(f"\n완료 {done:,}개 업로드 · 썸네일 없는 제품 {nothumb:,}개", flush=True)


if __name__ == "__main__":
    run(sys.argv[1] if len(sys.argv) > 1 else "smallrig")
