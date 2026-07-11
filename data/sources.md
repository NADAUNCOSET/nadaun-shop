# 제품 스크랩 소스 관리

> shop.nadaun.co 제품DB를 채우는 소스 사이트 목록·상태. 마스터 리스트 = `_브랜드_리스트업.txt` (대표 확정 25곳).
> 공통 규칙: stable id=`<소스>-<상품번호>`, 브랜드별 JSON(`data/products/<brand>.json`), 이미지 R2(`shop/{thumbnails,images,detail}/<brand>/`), webp 최적화, 증분(이미 올린 것 skip).
> 카테고리 = KPP 택소노미 SoT(`taxonomy_kpp.md`) — kpp 소스는 ca_id 직매핑, 그 외 소스는 `kpp_classify.py` 이름기반 분류.

## 완료/진행

| 소스 | 플랫폼 | 스크래퍼 | 상태 |
|------|--------|----------|------|
| kppkpp.co.kr (KPP) | 영카트 | `kpp.py` + `kpp_supervisor.py` | ✅ **완료 95/95, 2,934개** (2026-07-09 새벽) |
| clmedia.co.kr | Cafe24 | `clmedia.py` | ✅ 8개 카테고리 (기존 라이브 데이터) |
| tilta.com | 자체 | `tilta.py` | ✅ 2,161개 |
| rainbowshop.imweb.me | imweb | — | ✅ 카테고리 뼈대/브랜드 55 (`taxonomy_rainbowshop.md`) |

## 대기 — 플랫폼 정찰 완료 (2026-07-09 자동판별)

### Cafe24 (11곳) → 범용 `cafe24.py` 템플릿 하나로 커버
| 소스 | 도메인 | 대상 브랜드 |
|------|--------|------------|
| ~~포멕스~~ | fomex.co.kr | ✅ **완료 433/433, 2,533개** (2026-07-09 오전). ⚠️_misc 1,696개 → 분류 보정 필요 |
| 🔄HK툴스 | hktools.co.kr | 실행중 (프로포토·테더툴스·파라볼릭스) |
| 벤로코리아 | benrokorea.co.kr | 벤로 삼각대·필터 ★신규 |
| HK툴스 | hktools.co.kr | 프로포토·테더툴스·파라볼릭스 |
| 삼아스토어 | samastore.co.kr | 제네렉·슈어·아투리아·아포지 ★신규 |
| 하이픽셀플러스 | hipixelplus.co.kr | TVLogic·블랙매직 (보강) |
| 머스트컬러 | mustcolor.com | 데이터컬러 스파이더 ★신규 |
| 모션나인 | motionnine.com | 모션나인 슈팅카트 ★신규 |
| 온앤오프미디어 | onnoff.kr | 셔틀러 삼각대·카메라류 |
| 엘디네트웍스 | ldnet.co.kr | 케이블 전제품 (노브랜드多) |
| 시네몰 | cinemall.co.kr | 종합몰 전제품 |
| 반도카메라 | bandocamera.co.kr | 카메라·악세사리 종합 |

### godo/NHN커머스 (3곳) → `godo.py` 템플릿
| 디지털홍일 | redsun.co.kr | 리벡 삼각대 ★신규 |
| 칼라미디어 | callamedia.kr | 틸타(중복소스)·바투 |
| 엘디엘마운트 | l-mount.co.kr | 스탠드·모니터마운트 |

### MakeShop (1곳)
| 유쾌한생각 | plthink.com | 난라이트·난룩스·발렌스·삼각대류 |

### 자체/JS렌더 — 개별 분석 필요 (6곳)
| AVX | avx.co.kr | 어퓨처·아마란 (조명 핵심) |
| 토브테크 | tovmall.co.kr | 세코닉·페리바운스 |
| 사가몰 | sajinsangsa.co.kr | 펠리컨 |
| 그린촬영시스템 | greenshop.co.kr | NiSi |
| 세기몰 | saeki.co.kr | 종합 전제품 |
| 오로라몰 | auroramall.co.kr | 종합 전제품 |

### 네이버 스마트스토어 (3곳) — 안티봇, 최후순위/수동 협의
일렉트로샵(파나소닉), 투데이샵(케이블), DJI 브랜드스토어

## 진행 순서 (대표 2026-07-09: "모든 사이트 스크랩 + 브랜드별 카테고리 완벽이 첫번째 일")
1. KPP 95/95 완료 (실행중)
2. Cafe24 템플릿 → 전용소스 브랜드 사이트부터 (포멕스→HK툴스→삼아→벤로→…) → 종합몰(시네몰·반도)
3. godo 템플릿 3곳 → MakeShop 1곳 → 자체몰 6곳 개별 분석
4. 전 제품 kpp_classify 분류 → 브랜드별 카테고리 검수 → 카탈로그 빌드·배포
