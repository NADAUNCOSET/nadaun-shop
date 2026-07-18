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

### godo/NHN커머스 (3곳) → `godo.py` 템플릿 — ✅ **완료 (2026-07-17, `godo_supervisor.py`)**
| ~~디지털홍일~~ | redsun.co.kr | ✅ 801개 (리벡 58 포함) |
| ~~칼라미디어~~ | callamedia.kr | ✅ 1,264개 (틸타·젠하이저) — 홈메뉴가 이미지라 nav 2-pass 보강 |
| ~~엘디엘마운트~~ | l-mount.co.kr | ✅ 322개 (스탠드·마운트, 브랜드매핑 필요→_misc) |

> godo 함정 메모: godomall CDN이 이미지 Content-Type을 `multipart/form-data`로 반환 → CT검사 대신 디코딩 판정. calla는 og:title=사이트명 → `.item_detail_tit h3` 우선.

### MakeShop (1곳) → `makeshop.py` — 🔄 **실행중 (2026-07-17)**
| 유쾌한생각 | plthink.com | 카테고리 232개(2-pass nav), og:title 접두 제거, 메인=.thumb img, 상세=.ck-content img |

### 자체몰 6곳 — 플랫폼 판별 완료 (2026-07-17), 스크래퍼 완성·큐 대기
| 소스 | 플랫폼 | 스크래퍼 | 메모 |
|------|--------|----------|------|
| AVX | **Firstmall(가비아)** | `firstmall.py avx` | 카탈로그 onclick display_goods_view('N') |
| 오로라몰 | Firstmall | `firstmall.py aurora` | 동일 |
| 사진상사 | Firstmall | `firstmall.py sajin` | href goods/view?no=N |
| 그린촬영시스템 | Firstmall | `firstmall.py green` | 카탈로그 JS렌더 → /goods/search_list AJAX |
| 토브테크 | **WooCommerce** | `woo.py tov` | 공개 Store API /wp-json/wc/store/v1/products, 2,315개 |
| 세기몰 | 자체(Spring) | `saeki.py` | POST search-cate-item-list-json + X-CSRF-TOKEN 메타, 카테고리 SoT=data/_saeki_categories.json(브라우저 DOM 덤프 280개), 리스트 JSON에 브랜드·정가/판매가 포함 |

> Firstmall 함정: 가격=JS `gl_goods_price`(0 초기화 후 재할당→마지막 nonzero), 상세설명=별도 `/goods/view_contents?no=N&zoom=1`, avx는 og:title=사이트명인 페이지 있음.
> 실행 체인(2026-07-17 밤): plthink ALL → firstmall_supervisor(avx→aurora→sajin→green) → woo tov ALL → saeki ALL (브랜드 JSON 동시쓰기 금지 → 순차 큐)

### 네이버 스마트스토어 (3곳) — 안티봇, 최후순위/수동 협의
일렉트로샵(파나소닉), 투데이샵(케이블), DJI 브랜드스토어

## 진행 순서 (대표 2026-07-09: "모든 사이트 스크랩 + 브랜드별 카테고리 완벽이 첫번째 일")
1. KPP 95/95 완료 (실행중)
2. Cafe24 템플릿 → 전용소스 브랜드 사이트부터 (포멕스→HK툴스→삼아→벤로→…) → 종합몰(시네몰·반도)
3. godo 템플릿 3곳 → MakeShop 1곳 → 자체몰 6곳 개별 분석
4. 전 제품 kpp_classify 분류 → 브랜드별 카테고리 검수 → 카탈로그 빌드·배포
