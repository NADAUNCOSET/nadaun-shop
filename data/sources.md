# 제품 스크랩 소스 관리

> shop.nadaun.co 제품DB를 채우는 소스 사이트 목록·상태. 각 소스별 스크래퍼 = `_scraper/<소스>.py`.
> 공통 규칙: stable id=`<소스>-<상품번호>`, 브랜드별 JSON(`data/products/<brand>.json`), 이미지 R2(`shop/{thumbnails,images,detail}/<brand>/`), webp 최적화, 증분(이미 올린 것 skip).

| 소스 | 플랫폼 | 용도 | 스크래퍼 | 상태 |
|------|--------|------|----------|------|
| rainbowshop.imweb.me | imweb | 우리 샵 카테고리 뼈대(브랜드 55·대중소) | — | ✅ 트리 추출 완료 (`taxonomy_rainbowshop.md`) |
| clmedia.co.kr | Cafe24 | 종합 촬영장비 제품 데이터 | `_scraper/clmedia.py` | 🔄 진행중 (Lighting 파일럿→전체, 8개 카테고리 예정) |
| **tilta.com** | 미확인(Shopify/자체 추정) | **틸타 본사 글로벌 — 전 제품** | (예정) | ⏳ 대기 (2026-07-04 대표 지정) |

## 앞으로 (대표: "각 사이트마다 가져올 게 정말 많아")
- clmedia 8개 카테고리 완료 후 → 브랜드 본사 사이트들 순차 (tilta.com 우선)
- 규모 수만 개 대비: 소스마다 스크래퍼 추가, 같은 데이터모델·R2 구조로 통합
- 가격/상세 변동 시 = 대표가 알려주면 해당 JSON 수정 (하드코딩 없음)
