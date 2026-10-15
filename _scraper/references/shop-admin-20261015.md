# 나다운 주문관리 · 공유 미리보기 · SEO — 2026-10-15

## 요청과 적용

대표 요청: 상품 링크의 카카오톡 이미지, 나다운 스페이스·영등포 렌탈샵·스튜디오 검색 정보, 대표 아이디로 쓰는 주문관리, REA로 아임웹 관리자 분석 후 나다운 업무에 맞게 구현.

- 구매 주문은 재고·납기 확인 → 금액 승인 → 결제 확인 → 상품별 부분/전체 출고로 처리한다.
- 렌탈은 방문 일정·전체 기간 요금 확인 → 결제 확인 → 방문 수령 → 반납으로 구분한다. 최대 대여기간은 기존 확정대로 14일이며 서버 생성/승인에도 적용한다.
- 관리자 목록에 업무 탭, 기간·유형·결제·증빙 필터, 주문번호/결제키 검색, 펼침 상세, 내부 메모, 처리자/시간 이력을 연결했다.
- 출고 건별 운송정보 수정, 반품/교환 접수와 회수 상태, 동일 상품·옵션 교환품 재출고를 지원한다. 수량 중복을 거부하며 다른 상품/차액 교환은 별도 주문으로 처리한다. 반품 기록 종결은 PG 환불 완료를 뜻하지 않는다.
- 아직 결제되지 않은 접수 취소는 사유 필수, 결제 흔적·출고가 있으면 차단한다. 실제 환불은 기존 PG 확인 경로와 구분한다.
- Excel은 안내와합계·주문결제·상품·증빙·처리이력·출고내역·반품교환 7시트. 내부 메모/사건 사유는 고객 API에 노출하지 않는다.
- SHOP_ADMIN_EMAIL 설정 시 이메일+기존 비밀번호가 모두 필요하다. 계정 이메일 자체는 공개 config에 노출하지 않는다. 대표 지정 이메일 답변 전에는 기존 계정 유지.
- 상품별 서버 HTML의 OG 이미지 URL은 1차 도메인 JPEG 1200×630이다. 원본 접근 실패 시 로고 대체와 응답 헤더를 명시하며 상품 이미지 성공으로 보고하지 않는다. 카카오 앱 실제 공유 및 과거 캐시 초기화는 별도 확인이다.
- 영등포 장비 렌탈 안내는 /rental-guide.html. 실제 방문 층/스튜디오를 구분하고 확인된 서비스 정보만 쓴다. 검색량·검색 순위를 임의로 주장하지 않는다.

## REA 근거와 한계

실제 rainbowshop.imweb.me/admin은 로그인 화면. 브라우저가 이미 로드한 admin.js, table_list.js, payment.js를 CDP로 읽어 원문과 SHA를 보존했다. 별도 HTTP 요청 403 이후 추가 요청/우회하지 않았다. SMB 메타데이터 변동에 따른 REA 무결성 오류는 SHA가 같은 로컬 임시 사본으로 재현 없이 분석했으며 검증을 끄지 않았다.

REA 6.5.0 analyze-javascript-application evidence_id:
`ev_bad6a09bc3660feab9a73a7c4f2e17ba7a920be3c9ec251d94c3ea2e01264ec1`

세 파일의 정적 분석 성공이며 실제 로그인된 주문관리 전체 코드나 서버 구현을 확보했다는 뜻이 아니다. payment.js의 공통 서비스 결제를 고객 주문 PG로 추정하지 않는다. 현재 구현은 공식 기능 설명과 기존 나다운 주문/렌탈 서버의 독립 구현을 결합했다.

공식 기능 대조:
- https://www.imweb.me/qna?mode=faq&q=72220 — 주문 탭과 조회 구분
- https://imweb.me/qna?mode=faq&q=72247 — 상품/수량별 부분 발송
- https://developers.kakao.com/docs/ko/message-template/common — 공유 정보
- https://developers.kakao.com/docs/ko/tool/common — 캐시 확인 도구

## 검증과 운영

검증 원본: `_private/catalog/sharing-admin-20261015/`. REA 원문, 원본 이미지 점검, OG 렌더 결과, 로컬 가상 주문과 테스트 로그를 보존한다. 실고객 주문/결제/환불을 테스트로 변경하지 않는다.

2026-10-15 13:43 KST 실제 운영 관리자 로그인·조회 성공, 주문 0개. 공개 config는 ordersEnabled=false, rentalRequestsEnabled=false, taxInvoiceEnabled=false, adminEnabled=true, paymentProvider=inicis. 토스페이먼츠 답변/새 PG 개통은 이번 관리자 UI 구현과 별개다.

최종 단계: 코드·전체 필수 검사·가상주문 브라우저 검증·공개 배포·운영 계정 로그인·공유 이미지3종 확인 완료. commit e5132fa9cf9d2c955f52f541fcb140e4d77d0195, deployment dpl_39fGRTbBEP37nhEUnKtxMS2QZNiq, revision fd7494b71810bf12. 대표 지정 이메일과 로그인된 아임웹 화면 추가대조·PG개통/실거래·카카오앱 실공유는 남음. 근거는 RUNBOOK 및 private 영수증을 확인한다.

## 16시 후속 — 실제 로그인된 아임웹 OMS 재확인

대표가 기존 자사몰 로그인 완료를 알리고 REA로 실제 기능을 맞추라고 재지시했다. 같은Chrome 세션에서 나다운 스페이스 관리자 대시보드와 새 OMS 주문관리(iframe app.oms.imweb.me)를 확인했다. Global 요금제는2026-10-06 만료로표시되지만 추가결제없이 주문목록 전체200건·상세·타임라인·필터·레이아웃/컬럼·송장일괄등록·수기주문폼이 열렸다. 앞선 로그인미완료 근거는 당시이력이며 현재접근불가주장은종료한다.

이미로드된OMS JS125개를CDP캐시에서보존, 고객주문API응답·쿠키·인증토큰은수집하지않았다. 실제주문변경/환불/메시지발송0건, 레이아웃토글확인후원복. REA초기87파일 정적분석 ev_ebab6be81a7e8c4cf15bf57207953b35dcd9e69ba3de58a37b02f8a9120e9a68; 큰bundle 그래프예산제한으로일부semantic미시작이있어좁은후속분석진행. 원본서버복제완료가아니다. 근거 `_private/catalog/sharing-admin-20261015/rea-authenticated/`. 현재누락된선택처리·고객/송장검색·배송단계분리·송장미리보기/적용·저장필터/표설정·인쇄는구현중. 완료/배포는후속영수증으로만확정한다.


## 2026-10-15 17시 — OMS 후속 및 CFexpress A (배포 검증 진행)

로그인된 아임웹 OMS의 실제 화면과 이미 로드된 JS를 REA로 대조해 선택 주문 처리/선택 내보내기, 고객·연락처·운송장 검색, 배송준비→배송대기→배송중→배송완료 구분, CSV/XLSX 송장 미리보기·서명된 적용, 표/카드·열·밀도·저장필터, 주문서/거래명세서 인쇄 미리보기를 독립 구현했다. 수기 견적은 암호화된 별도 원장에 초안/검토/취소·버전 이력·상품검색·옵션/기간/요금 검증·견적 출력을 제공한다. 수기 견적 저장은 실제 주문/재고 예약/PG 요청/고객 알림을 만들지 않는다. 아임웹 원본 코드는 private 분석 근거로만 보존하며 제품에 포함하지 않는다.

실서비스 모듈+메모리SQLite의 가상 주문/견적으로 선택/검색, 송장3건12개 적용, 유효/무효 혼합 일괄결과, 구매견적 생성→검토→수정→취소, 렌탈24시간2만원 견적→검토→인쇄미리보기,320/390px 가로넘침 없음을 확인했다. 실제 운영 주문 변경0건. D1 기존 테이블/원장은 보존하고 견적2테이블만 추가, 운영주문/견적 각0건 확인. 자동 publisher 필수검사에 신규3테스트를 연결했다.

대표의 CFexpress A 누락 지적을 네이버 공식 판매자 API(읽기전용)로 확인했다. 오늘16:09~16:14 신규상품3종(13812451915/160GB/10000원,13812459279/320GB/20000원,13812461548/512GB/30000원), 각각 카드1개+리더1개. 대표이미지를 직접 확인해 Sony/Lexar/HOMAN 분류를 맞추며 원본 Sony 공통메타 오류2건은 기대이름/원브랜드를 고정한 검토 override로 교정하고 원본은 보존한다. CFE-A/B 약어에 CFexpress 검색어를 추가하되 A/B를 섞지 않는다. 기존 Type B128/256/512GB는 네이버 최신1/2/3만원,2TB4만원 보존. 금지된 옛A상품은 재활성화하지 않는다.

공식 전체7888원상품 중 공개6874개를 새로 확인, 변경상세654개를 모두 갱신하고6874개 상세수정시각 일치 검증 완료. 공용publisher잠금 아래 원본/상세235개내외 버킷 백업 후 정상snapshot로 반영. 코드92f5802c62d4a2b1f6bc279747ccfe61e3922e92, 자동통합검사/공개배포 진행. 완료는 후속 release.json 및 실제live 대조로 확정한다.

근거: `_private/catalog/rental-cfexpress-a-20261015/`의 source/detail/brand-image-review/promotion/release.log, `_private/catalog/sharing-admin-20261015/rea-authenticated/`의 feature-gap/schema-before/schema-after/synthetic-ui-proof-final. 기프트보호중지/주문접수OFF는 유지.


### 2026-10-15 17:22 KST — OMS 후속·CFexpress A 공개 완료

최종 commit `fb82d82c32ec872339d2a6db676aa96626006b60`, deployment `dpl_6dqjjhbJnL8KjbecXpUpQwnztbhH` READY, revision `5b671ceb05bf96c0`, live 검증 `2026-10-15T08:20:18+00:00`. 정상 publisher 전체 필수 Python/Node 검사 통과 후 정확한 생성물만 커밋/푸시했다. 코드 커밋92f5802c6, 검색 후속3f6c5c7c2. 다른 공급처 offer 추가/삭제/값변경0건. 기존clmedia-3478은 새네이버동일상품 smartstore-13812350366에통합되었고 기존offer/가격/판매상태/redirect보존으로 재확인했다. 최초 보존검사의 canonical ID삭제 경고는 이이유로해결했으며 원문 built-verification.json 보존.

공개 장비 카탈로그29492개, 렌탈216개. CFexpress A160/320/512GB 각1/2/3만원, Sony/Lexar/HOMAN 이미지브랜드 확인. 렌탈 메모리·스토리지 rent:146 포함. 각카드1+리더1 원문구성보존. 스마트스토어전체공개6874상품/현재수정시각에맞는상세6874개, 변경상세654개 검증. 원본/상세 231버킷 백업 후반영. 기존타입B128/256/512GB1/2/3만원과2TB4만원도최신네이버값으로반영.

실제통합검색에서 CFexpress A가 B도포함하는단일문자부분일치오류발견, 웹목록/서버검색공용으로CFexpress와A/B를한검색단위로처리하고discovery검색어를서버에도반영했다. 회귀7개통과, 실제공개A3개/B4개로분리됨확인. screenshot cfexpress-a-live.png, live-search-final.json. 실제상품3개초기HTML가격/SEO설명·OG1200x630 JPEG응답200및product헤더확인. 카카오톡앱실공유는별도미확인.

운영order.nadaun.co기존인증세션으로새배송단계·선택처리·수기견적목록0건열림확인. 실고객테스트변경0건, shop/order의commerce.js/css4자산NAS바이트일치. 비로그인주문/견적API401,private경로404. config ordersEnabled=false,rentalRequestsEnabled=false,adminEnabled=true,adminDraftsEnabled=true,adminLoginRequiresEmail=false,taxInvoiceEnabled=false,paymentProvider=inicis. PG/고객온라인주문·렌탈접수/세금계산서개통을완료로보지않는다. 대표지정계정이메일미확정으로기존로그인유지. 가상QA서버정상종료.

SEO재조회:shop렌탈안내/Collective/Blogspot모두200,제목/설명/canonical존재,Collective와Blogspot의쇼핑몰href는https://shop.nadaun.co/. 실제검색색인·순위·검색량상승미확인. 기프트원본자동갱신OFF/보호중지유지. Windows실기기런타임검수와나다운전체연계사이트의전체기능검수를이번결과로확대해보고하지않는다.

근거: `_private/catalog/rental-cfexpress-a-20261015/`의search-release.json/live-search-final.json/live-product-admin-proof.json/built-verification-final.json, `_private/catalog/sharing-admin-20261015/seo-crosslink-live-20261015.json`, rea-authenticated/admin-live-oms.png/admin-live-drafts.png/synthetic-ui-proof-final.json. NASMac자동기록상태08:13:12Z complete/errors[]/1850files확인. 다른PC실행은미확인.


### 2026-10-15 18:27 KST — 관리자 로그인 필수 재검증

대표가 아무나 관리자 화면을 활용하면 안 된다고 확인 요청. 현재 비밀번호 인증이 필수이며 이메일 추가설정이 없는 것을 로그인 불필요로 혼동하지 않도록 설명한다. 로그인 쿠키 없는 실제운영 GET8종(주문/상세/내보내기/이력/견적/상품검색/견적출력/캘린더) 및 POST3종(배송단계/송장적용/견적생성)이 전부401,가짜세션1종도401. 사업데이터변경0건. 앞선검수에서남아있던정상로그인세션을웹로그아웃버튼으로종료한뒤 실제관리자비밀번호로그인폼만표시됨확인. 인증완료전주문작업실없음. 비밀번호/이메일/인증키변경없음. 근거 shop/_private/commerce/admin-login-access-20261015.json 및 admin-login-required-20261015.png.


### 2026-10-15 19시 — 관리자 비밀번호 원본 저장과 자동 송장 구현

대표 지정 NAS `_PP/_nadaun work/_개인자료/문서화 저장/비밀번호 확인_나다운 디자인.docx`에 나다운 주문관리 로그인 정보를 기존 아임웹 행 다음에 추가했다. 현재 ID 없이 비밀번호 로그인, 주소 https://order.nadaun.co/ 를 구분해 기록했다. 기존222행을 그대로 보존하고223행으로 저장, 다른DOCX ZIP구성원 동일/실제private로그인값 일치/백업/모드600/한글7페이지 렌더 시각검수 확인. 비밀번호 본문은 공용기록에 남기지 않는다. `CLAUDE.md` 상단에 앞으로의 아이디·비밀번호 저장원본 규칙도 반영했다. 기존잠금파일은 보존했고 다른PC의문서실행은확인하지않았다.

대표의 굿스플로처럼 송장 출력 요청에 따라 공식 Sellers Open API용 접수/인쇄URI/번호조회/배송단계 자동반영을 구현했다. 실제 로그인된아임웹 배송설정에서CJ대한통운·로젠승인완료/기본로젠확인. 이는우리몰API키와별도이며아임웹토큰재사용없음. 운영DB에송장조회큐1테이블추가,기존주문0/새큐0건재확인. 관리자로그인·실결제·배송대기·승인계약 검증,중복접수방지,응답유실시같은요청번호조회,인쇄와집하분리,배송완료탭집계/엑셀출처 반영.

외부통신차단실서비스/메모리SQLite 가상주문2건 접수→PRINTED→PICKUP→COMPLETED 검증,기존수동완료1건과합계3건확인. Windows프린터/실제운송장발급은미검증. 320/390px 가로넘침없음. 가상검증서버종료. 최초코드61f00afc4/공개d285c5fea/deployment dpl_8B9dw73Ppi8ZcHgisxeShtmC62tW/revision d22c7596de798b3f,필수검사통과,live검증10:43:56Z. shop/order두도메인새API5종비로그인401,정상로그인후연결대기표시,주문0건,JS바이트일치확인후해당검증세션로그아웃.

현재실제발급은우리몰API키미확보로OFF. 대표에게기존발급여부/저장위치를문의했고응답대기. 고객주문/렌탈접수/PG개통/세금계산서도여전히OFF. Mac기존60초예약작업의송장조회연결과입력창스타일후속배포진행중이며최종영수증은후속기록으로확정한다.

근거원본: shop/_private/commerce/goodsflow-20261015/ 및 _scraper/references/goodsflow-shipping-20261015.md. 비밀번호DOCX검증은해당비공개문서폴더의 _검증_주문관리_20261015/verification.json. Mac자동기록10:41:36Z complete/errors[]/1850files,설치원본확인. 다른PC런타임은미확인.


### 2026-10-15 19:49 KST — 송장 기능 최종 공개 검증

후속코드8897306ad까지백업/커밋하고정상publisher전체필수검사를다시통과했다. Mac60초로컬예약실행기에도송장조회호출을연결했고, 송장계약/박스입력창을기존주문관리스타일·44px터치규격으로마감했다. 최종commit `ebce6be79cdfce21e80a6eb167d705838969d8c3`, deployment `dpl_A7v4MfwCcVQqJTJDiiKDCSx8H4z2` READY, revision `3b4196f2f3041ff7`, 공개검증 `2026-10-15T10:48:35+00:00`. shop/order두도메인JS/CSS4자산NAS바이트일치,고객주문·렌탈접수·세금계산서OFF/관리자ON/비밀번호로그인설정유지. 실제송장API키미확보로자동접수/발급은OFF,실제프린터검수미완료. 운영테스트접수0건. 가상검증서버정상종료,새운영API인증검증세션로그아웃. 완료와연결대기를분리해인계한다.

근거: `shop/_private/commerce/goodsflow-20261015/final-live-proof.json`, `live-proof.json`, `worker-ui-release.json`, `http-qa-proof.json`, `browser-qa-proof.json`. NAS공용지침·지정비밀번호DOCX·프로젝트RUNBOOK·당일노트저장후재조회했다. Obsidian기존타업무충돌3개는보존했으며이번당일노트는사용볼트에반영한다.


### 2026-10-15 22:27 KST — 이니시스 제거·토스 전환 및 HOMAN 256GB 공개 완료

대표 확정에 따라 구매·렌탈 PG 실행 연동을 토스페이먼츠로 변경했다. 코드2be0b02f8, 검색검증3a9101be6, 안내메타데이터e496db197, 최종공개commit `d4cc3e914bca0dc5bdf5159c71fc5bc6b45a6450`, deployment `dpl_4ybMRumwAacULPEPqUQNGPAt3NSU` READY, revision `15149d77c5c301de`, 공개검증 `2026-10-15T13:25:53+00:00`. 정상publisher 전체필수Python/Node검사 통과. 초기Gitindex잠금은활성작업종료후재실행했으며강제제거없음. 검색검증의이전A3개고정조건을실제A256상품·타입분리·웹/서버결과일치로보완했다. 추가점검에서남은결제페이지제목/OG문구도토스로변경후재배포했다.

이니시스실행어댑터/콜백/API와로컬설정6개·운영환경변수5개제거,이전설정은private백업. shop/order두도메인실제config.paymentProvider=toss,이전콜백404/잘못된새콜백303,JS3종+결제안내HTML총8자산NAS바이트일치. 비로그인관리자401/기존비밀번호로그인후주문0건/검증세션로그아웃후401재확인. 관리자/DB암호화키변경없음.

HOMAN CFexpress Type A256GB 렌탈20,000원을네이버공식API로생성/재조회하고자사몰에도공개했다. 원상품13751715557/채널13812942061,자사ID smartstore-13812942061,네이버 https://smartstore.naver.com/rainbowbene/products/13812942061 · 자사몰 https://shop.nadaun.co/item.html?id=smartstore-13812942061 . 브랜드HOMAN/렌탈메모리rent:146/카드1개. 실제공개이미지·가격·검색1건·canonical·OG JPEG1200x630 product응답확인,카카오앱실공유는미검증. 장비29493/렌탈217,기존29492상품객체변경0·누락0. 기존전체수집시각을유지한1상품증분추가이며전체원본재수집완료아님.

미완료:실토스MID·API개별연동키·개통/결제/취소/현금영수증검수. 토스로그인화면로그아웃/지정문서계정없음으로대표로그인요청대기. TossShopping마켓플레이스키와혼용없음. ordersEnabled=false/rentalRequestsEnabled=false/taxInvoiceEnabled=false,adminEnabled=true/adminDraftsEnabled=true유지. 렌탈은일정·재고/전체기간요금승인후결제하며최대14일. PG배포를실결제개통으로보고하지않는다.

실제로그인된아임웹에서CJ·로젠승인계약과계약번호/출고지를확인하고비공개보존,기본로젠. 신규택배승인을받아야한다는단정대신기존계약을사용할Sellers계정/API/서비스연결확인이남은상태다. 자사몰굿스플로enabled=false/configured=false,실송장발급·프린터검수미완료. 외부계약변경/유료플랜가입/고객주문변경0건.

근거: `_private/catalog/homan256-toss-20261015/`의release.json/live-proof.json/catalog-preservation.json/registration-receipt.json/pg-settings-receipt.json/live-product.png/live-toss.png. 상세원문 `_scraper/references/toss-homan256-20261015.md`, 현재설정안내TOSS-SETUP.md. Mac자동기록complete/errors[]/1850files와installation존재확인. 다른PC실행미검증.
