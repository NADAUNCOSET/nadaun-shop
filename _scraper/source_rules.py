# -*- coding: utf-8 -*-
"""소스 우선순위 규칙 (대표 지시 2026-07-12): 빌드 단계 필터, 원본 데이터 보존.
   ① 브랜드가 KPP·씨엘미디어에 있으면 → 그 두 곳(+틸타 본사) 제품만 사용, 타소스 제외.
      (tilta.com은 본사 직영이라 1티어 취급 — 틸타 2,027개 보존. 대표 이견시 TIER1에서 빼면 됨)
   ② hktools는 프로포토만 채택, 그 외엔 타소스와 겹치면 hktools분 제외.
   ③ _misc/_custom 같은 가상 브랜드 통은 티어룰 미적용(브랜드가 아님) — hktools룰만.
   모두 동적: 새 소스가 들어오면 다음 빌드에서 자동 반영."""
import json, re
from collections import defaultdict

TIER1 = {"kpp", "clmedia", "tilta.com"}   # 우선 채택 소스 (tilta.com=본사)
DEMOTED = "hktools"                        # 겹치면 밀리는 소스
DEMOTED_KEEP = set()                       # (비움 — profoto는 아래 BRAND_SRC로 처리)

# 브랜드별 소스 고정 — 메뉴 세분화가 좋은 소스로 강제 (2026-07-20 대표: profoto 메뉴=fomex 구조)
BRAND_SRC = {"profoto": "fomex"}

# 렌탈/중고/전시류 = 판매 제품 아님, 전역 제외 (2026-07-20 대표 "hktools 렌탈 하지마·쓸데없는거 지워")
JUNK_CAT = ("렌탈", "렌트", "대여", "중고", "전시", "데모", "리퍼", "단순개봉", "반납", "B급")

def is_junk(p):
    cp = " ".join(p.get("cat_path") or []) + " " + (p.get("category") or "")
    if any(w in cp for w in JUNK_CAT):
        return True
    # 제품명에 렌탈/대여/rental (판매 아님, 2026-07-20 대표 "렌탈 관련 다 삭제·구매만")
    if re.search(r"렌탈|대여|rental", p.get("name") or "", re.I):
        return True
    return False

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
    if is_junk(p):                                # 렌탈/중고/전시 = 전역 제외
        return False
    if slug in BRAND_SRC:                         # 소스 고정 브랜드(profoto=fomex)
        return src == BRAND_SRC[slug]
    if not slug.startswith("_") and (s & TIER1):  # KPP/씨엘미디어 보유 브랜드
        return src in TIER1
    if src == DEMOTED:                            # hktools: 타소스 겹치면 제외
        return not (s - {DEMOTED})
    return True
