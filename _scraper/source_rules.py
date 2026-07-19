# -*- coding: utf-8 -*-
"""소스 우선순위 규칙 (대표 지시 2026-07-12): 빌드 단계 필터, 원본 데이터 보존.
   ① 브랜드가 KPP·씨엘미디어에 있으면 → 그 두 곳(+틸타 본사) 제품만 사용, 타소스 제외.
      (tilta.com은 본사 직영이라 1티어 취급 — 틸타 2,027개 보존. 대표 이견시 TIER1에서 빼면 됨)
   ② hktools는 프로포토만 채택, 그 외엔 타소스와 겹치면 hktools분 제외.
   ③ _misc/_custom 같은 가상 브랜드 통은 티어룰 미적용(브랜드가 아님) — hktools룰만.
   모두 동적: 새 소스가 들어오면 다음 빌드에서 자동 반영."""
import json
from collections import defaultdict

TIER1 = {"kpp", "clmedia", "tilta.com"}   # 우선 채택 소스 (tilta.com=본사)
DEMOTED = "hktools"                        # 겹치면 밀리는 소스
DEMOTED_KEEP = {"profoto"}                 # 예외: 이 브랜드는 hktools 유지

def build_index(DATA):
    """data/products/*.json 전체 스캔 → {brand_slug: {source,...}}"""
    srcs = defaultdict(set)
    for f in DATA.glob("*.json"):
        if f.stem == "_index":
            continue
        d = json.load(open(f, encoding="utf-8"))
        top = d.get("brand_slug") or f.stem
        for p in d.get("products", {}).values():
            srcs[p.get("brand_slug") or top].add(p.get("source"))
    return srcs

def allowed(p, slug, srcs):
    """이 제품을 빌드에 포함할지."""
    src = p.get("source")
    s = srcs.get(slug, set())
    if slug in DEMOTED_KEEP:                      # 프로포토: 정식 수입사 hktools 것만 (타소스 오염 차단, 2026-07-20 대표 지적)
        return src == DEMOTED
    if not slug.startswith("_") and (s & TIER1):  # KPP/씨엘미디어 보유 브랜드
        return src in TIER1
    if src == DEMOTED:                            # hktools: 타소스 겹치면 제외
        return not (s - {DEMOTED})
    return True
