# -*- coding: utf-8 -*-
"""썸네일 폴백 — 대표이미지(main)가 없지만 상세이미지(detail)가 있는 제품은
   detail[0]을 thumb·main으로 승격. 원본 사이트에 대표이미지 미등록인 제품(예약판매 등)의
   카드가 '이미지 준비중'으로 비는 것 방지 (2026-07-20). R2 재업로드 없음(기존 URL 재사용).
   실행: python thumb_fallback.py [--apply]"""
import sys, io, json, collections
from pathlib import Path
try: sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
except Exception: pass
ROOT = Path(r"\\Nadaunproject\nadaunproject\_Site\nadaun-shop")
DATA = ROOT / "data" / "products"
APPLY = "--apply" in sys.argv

fixed = collections.Counter(); still = collections.Counter()
for f in sorted(DATA.glob("*.json")):
    if f.stem == "_index": continue
    d = json.load(open(f, encoding="utf-8")); changed = False
    for v in d.get("products", {}).values():
        im = v.setdefault("images", {})
        if im.get("thumb") or im.get("main"): continue
        det = im.get("detail") or []
        if det:
            im["thumb"] = det[0]; im["main"] = [det[0]]
            fixed[v.get("source")] += 1; changed = True
        else:
            still[v.get("source")] += 1
    if APPLY and changed:
        json.dump(d, open(f, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

mode = "APPLY" if APPLY else "DRY-RUN"
print(f"=== {mode}: detail[0]→thumb 승격 ===")
print(f"  복구 {sum(fixed.values())}개:", dict(fixed))
print(f"  여전히 이미지전무 {sum(still.values())}개:", dict(still))
