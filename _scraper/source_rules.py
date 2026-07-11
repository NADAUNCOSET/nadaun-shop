# -*- coding: utf-8 -*-
"""소스 우선순위 규칙 (대표 지시 2026-07-12): hktools는 프로포토만 채택,
   타소스와 겹치는 브랜드의 hktools 물량은 빌드에서 제외.
   hktools 단독 브랜드는 다른 소스가 생길 때까지 유지 — 새 소스가 같은 브랜드를
   가져오면 다음 빌드에서 hktools분이 자동 제외됨(동적). 원본 데이터는 보존."""
import json
from collections import defaultdict

DEMOTED = "hktools"          # 겹치면 밀리는 소스
DEMOTED_KEEP = {"profoto"}   # 예외: 이 브랜드는 hktools 유지

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
    """이 제품을 빌드에 포함할지. hktools 외 소스는 무조건 통과."""
    if p.get("source") != DEMOTED:
        return True
    if slug in DEMOTED_KEEP:
        return True
    return not (srcs.get(slug, set()) - {DEMOTED})
