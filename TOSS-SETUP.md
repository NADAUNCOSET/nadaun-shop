# 토스페이먼츠 연결과 렌탈 결제

2026-10-15 대표 확정: 자사몰 구매·렌탈 PG를 토스페이먼츠로 전환하고 이니시스 실행 연동을 제거한다. 이전 이니시스 코드·설정·문서는 `_private/catalog/homan256-toss-20261015/`에 비공개 백업했다. 기존 아임웹이나 네이버의 계약을 해지하는 작업은 하지 않는다.

현재 고객 결제와 렌탈 온라인 접수는 OFF이며 주문관리·DB·캘린더 연결은 유지한다. 코드 전환과 실결제 개통은 별개다. 대표는 토스페이먼츠 상담 답변 대기를 전달했으며 새 독립몰 실계약·MID·API 키·실거래 검증 완료 증거는 아직 없다.

## 구현된 흐름

- 구매와 렌탈 모두 접수 → 재고/일정 및 최종 금액 확인 → 관리자 승인 → 고객 토스 결제 → 서버 승인 검증 → 주문/증빙/렌탈 캘린더 반영.
- 렌탈 최대 14일, 방문 수령·반납 시각 보존. 일정을 확인하기 전 목록 가격만으로 예약을 자동 확정하지 않는다.
- Toss SDK v2의 카드/간편결제 통합결제창 및 계좌이체. 공식 `payment()` API 개별 연동 키를 사용한다. 주문서형 전용 gck/gsk 키와 혼용하지 않는다.
- 서버의 주문번호·금액·키·MID·KRW를 검증한다. 만료되는 서명 토큰, DB의 승인 예약, 고정 멱등키로 중복 승인을 방지한다.
- 승인 결과 저장 실패 시 거래를 조회해 일치하는 결제만 취소한다. 조회/취소 결과가 불명확하면 검토 상태로 보존한다. 승인 재전송으로 복구하지 않는다.
- 현금영수증 소득공제/지출증빙과 별도 전자세금계산서를 구분한다. PG 준비만으로 전자세금계산서 발급 준비가 완료되지는 않는다.

## 비공개 설정

설정 원본: `_private/commerce/configuration.json`. 운영 서버는 Vercel encrypted 환경 변수를 사용한다. 키 본문을 Git·RUNBOOK·Obsidian에 남기지 않는다. 계정 정보의 별도 지정 저장 원본은 NAS 비밀번호 확인 Word 문서다.

필수 PG 항목: `SHOP_TOSS_CLIENT_KEY`, `SHOP_TOSS_SECRET_KEY`, `SHOP_TOSS_MID`, `SHOP_PAYMENT_MODE`. 라이브는 `live_ck_`/`live_sk_`와 `SHOP_TOSS_LIVE_VERIFIED=true`를 요구한다. 테스트 키는 `test_ck_`/`test_sk_`. 실제 계약과 검증 전에는 `SHOP_ORDERS_ENABLED=false`, `SHOP_RENTAL_REQUESTS_ENABLED=false`를 유지한다.

개통 전 카드·계좌이체·현금영수증 두 용도·취소·모바일·구매/렌탈의 주문 종단 흐름을 실제 해당 상점에서 확인해야 한다. 세금계산서 미개통만으로 카드 결제를 막는 조건은 아니다. 기존 관리자 비밀번호와 주문 DB 암호화 키는 변경하지 않는다.

공식 근거: https://docs.tosspayments.com/guides/v2/payment-window/integration · https://docs.tosspayments.com/sdk/v2/js/payment · https://docs.tosspayments.com/reference

## 2026-10-16 승인 전 준비와 고객 증빙

대표는 토스 심사 중이라고 전달했다. 승인 상태는 상점 포털에서 아직 확인하지 못했다. 브라우저 제어 연결 오류이며 비밀번호 오류로 판정하지 않는다. 계정은 대표 지정 NAS 비공개 Word 문서에 저장/대조했다. 승인 알림만으로 우리몰 환경변수나 주문 스위치가 자동 변경되지는 않는다.

`/payment-test.html`은 별도 테스트 상점 연동이다. `SHOP_TOSS_TEST_CLIENT_KEY`(test_ck_), `SHOP_TOSS_TEST_SECRET_KEY`(test_sk_), 선택 `SHOP_TOSS_TEST_MID`를 사용한다. 운영키를 받지 않고 운영 주문/예약 DB에 쓰지 않는다. 서버 상품금액·서명·승인·취소 조회를 검증한다. 운영 주문이 OFF여도 테스트키 설정 후 결제창을 확인할 수 있다. 공개 샘플키를 우리 상점키로 대신하지 않는다. 테스트 창을 실제 열고 카드/계좌이체 승인·취소를 확인하기 전 실검수 완료로 기록하지 않는다.

고객은 주문 시 카드전표/현금영수증/전자세금계산서(발급 서비스 개통 후)를 선택하고, 주문조회에서 영수증 인쇄·증빙 상태 갱신·세금계산서 공급받는자 인쇄를 사용할 수 있다. 본인 주문 세션·결제 완료·금액/거래/발급번호를 재검증한다. 인쇄는 문서 한 건 전용 30초 URL이며 팝빌 로그인 문서함 URL을 제공하지 않는다. 카드·현금영수증과 별도 세금계산서의 중복 발행을 막는다.

전자세금계산서는 기존 팝빌 어댑터를 사용하며 별도 계정·LinkID/비밀키·인증서·포인트·과세 프로필·실발급/국세청 전송 검수가 필요하다. 토스 승인과 별개이며 이 조건 전 taxInvoiceEnabled=false를 유지한다. 사업자/세무정보를 추정하여 활성화하지 않는다. 고객의 세금 신고 전체를 대행하는 기능이 아니라 주문별 증빙 신청·발급·조회를 제공한다.

공식 근거: https://docs.tosspayments.com/guides/v2/get-started/environment · https://docs.tosspayments.com/guides/v2/get-started/payment-products · https://docs.tosspayments.com/reference · https://developers.popbill.com/reference/taxinvoice/node/api/view .
