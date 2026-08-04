"""승인 게이트 공용 모듈 (2026-08-04 대표 룰)

"브랜드마다 하나씩 잡고 넘어가자" — 대표 검수를 통과한 브랜드만 shop.nadaun.co에 노출한다.
데이터는 절대 지우지 않는다("나중에 불러올 수도 있으니까"). 여기서 **표시만** 거른다.

SoT = data/_approved.json
  {"brands": {"<slug>": {"sources": ["kpp","clmedia"], "mirror": "kpp", ...}}}

- brands 가 비었거나 파일이 없으면 게이트 해제(전체 노출) → 실수로 사이트가 비지 않게.
- 빌더(build_shop / build_detail / build_brands)는 모두 이 모듈을 통과시켜야 한다.
  하나라도 빠뜨리면 그 산출물만 전 브랜드가 생성돼 어긋난다 (2026-08-04 detail 36,780개 사고).
"""
import json
from pathlib import Path

ROOT = Path(r"\\Nadaunproject\nadaunproject\_Site\nadaun-shop")
_PATH = ROOT / "data" / "_approved.json"

BRANDS = {}
try:
    if _PATH.exists():
        BRANDS = (json.load(open(_PATH, encoding="utf-8")) or {}).get("brands") or {}
except Exception as e:  # 깨진 파일이면 게이트 해제(안전)
    print(f"[approved_gate] _approved.json 읽기 실패 — 게이트 해제: {e}")
    BRANDS = {}

ON = bool(BRANDS)


def ok(slug, source=None):
    """노출 대상인가? (승인 브랜드 + 그 브랜드에 허용된 소스)"""
    if not ON:
        return True
    e = BRANDS.get(slug)
    if not e:
        return False
    allow = e.get("sources")
    if not allow or source is None:
        return True
    return source in allow


def banner(where=""):
    if ON:
        print(f"[승인게이트 ON{(' · ' + where) if where else ''}] 노출 브랜드 {len(BRANDS)}개: {', '.join(sorted(BRANDS))}")
    else:
        print(f"[승인게이트 OFF{(' · ' + where) if where else ''}] 전체 노출")
