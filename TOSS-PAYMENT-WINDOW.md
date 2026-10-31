# 토스 결제창형 키 연결 — 2026-10-31

대표가 제공한 키 형식에 맞춰 기존 개별 연동과 결제창형 연동을 구분한다. `test_gck_`/`test_gsk_`, `live_gck_`/`live_gsk_`는 각각 같은 환경·제품군으로만 사용한다. `ck`/`sk`와 섞으면 서버가 거절한다.

새 클라이언트 키는 `widgets()` → `setAmount()` → `renderPaymentWindow()` → 구매자의 `paymentRequest` 이벤트 → `requestPayment()` 순서로 연결한다. 기존 `ck` 키의 `payment()` 흐름은 유지한다. 결제창에서 선택한 수단은 서명된 서버 요청의 카드/계좌이체와 같아야 한다. 새 SDK에 개별 연동 전용 `method`, `amount`, `card.flowMode`, `transfer.cashReceipt`를 전달하지 않는다.

이 작업으로 가상계좌·에스크로·직접 무통장입금의 자동 확인을 개통하지 않는다. 새 결제창 키의 세금계산서 결제는 현금영수증 중복 발행 방식을 별도로 검증하기 전 거절한다. `SHOP_ORDERS_ENABLED=false`, `SHOP_TOSS_LIVE_VERIFIED=false`는 보존한다.

별도 테스트 상점은 `SHOP_TOSS_TEST_CLIENT_KEY`/`SHOP_TOSS_TEST_SECRET_KEY`만 사용하며 운영 DB 주문을 만들지 않는다. 서버 등록·소스 커밋·배포 상태의 원본은 NAS 비공개 `_private/commerce/toss-connection-20261030/server-registration.json`이다. 환경변수는 Vercel production 대상 Secret으로 등록하며 시크릿 키 본문은 서버에서만 접근한다. 등록 후 재배포가 필요하다.

검증: 카드·계좌이체/신규·기존 키/금액·주문·소유권/중복 요청·취소/결제창 닫기/오류 후 재시도 포함 Node 94검사 통과. 공급사 응답과 SDK는 모의 객체이며 실제 PG 승인을 뜻하지 않는다. 비공개 입력·등록 코드의 별도 12검사도 통과했다. 키 본문은 Git·문서·로그에 기록하지 않는다. 환경변수 등록, 실제 PG 결제창 승인·취소 검수, 라이브 개통은 별도로 확인한다.

공식 근거: [API 키](https://docs.tosspayments.com/reference/using-api/api-keys), [결제창형 SDK](https://docs.tosspayments.com/sdk/v2/js/payment-window), [결제창형 가이드](https://docs.tosspayments.com/guides/v2/payment-widget/integration-window).
