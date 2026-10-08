# KG이니시스 개통·증빙 설정

2026-10-08 대표 확정: 나다운 샵 PG는 **KG이니시스**. 현재 코드 연결과 실제 계약·개통을 구분한다. INIpay PRO(PC/모바일)를 사용하며 운영 결제·발급 키가 없어 공개 주문 접수는 비활성이다.

## 계약 담당자에게 전달할 내용

> 자체 개발 쇼핑몰 https://shop.nadaun.co 에 INIpay PRO를 연결합니다. 카드와 계좌이체, 계좌이체 결제창의 현금영수증 소득공제/사업자 지출증빙을 사용하고 거래조회 INIAPI도 연결합니다. MID, PRO HashKey, INIAPI Key 발급과 심사·현금영수증 계약 범위를 확인해주세요. 서버는 Vercel이며 요청 서버 IP 및 허용 IP 조건도 확인해주세요.

세금계산서는 PG 현금영수증과 별도 전자세금계산서 발급 서비스가 필요하다. 현재 Popbill 어댑터를 비활성으로 준비했으며, 실제 사용 업체는 대표 확인 후 설정한다. 가입·인증서 등록·발급 포인트 구매를 대신 완료하지 않았다.

## 비공개 설정

`_private/commerce/configuration.json`만 사용하며 값은 Git/대화/공개 문서에 복사하지 않는다.

- 기본 주문: `SHOP_CF_ACCOUNT_ID`, `SHOP_D1_DATABASE_ID`, `SHOP_D1_API_TOKEN`, `SHOP_ORDER_DATA_KEY`, `SHOP_SESSION_KEY`, `SHOP_ADMIN_PASSWORD_HASH`.
- PG: `SHOP_PAYMENT_MODE=test|live`, `SHOP_INICIS_MID`, `SHOP_INICIS_HASH_KEY`, `SHOP_INICIS_API_KEY`, `SHOP_INICIS_CLIENT_IP`(실제 서버 IP). 실운영 검증 후에만 `SHOP_INICIS_LIVE_VERIFIED=true`.
- 전자세금계산서: `SHOP_TAX_INVOICE_ENABLED`, `SHOP_TAX_INVOICE_PROVIDER=popbill`, `SHOP_POPBILL_MODE`(PG와 같게), `SHOP_POPBILL_LINK_ID`, `SHOP_POPBILL_SECRET_KEY`, `SHOP_POPBILL_USER_ID`.
- 공급자: `SHOP_SELLER_CORP_NUM`, `SHOP_SELLER_CORP_NAME`, `SHOP_SELLER_CEO_NAME`, `SHOP_SELLER_ADDRESS`, `SHOP_SELLER_BIZ_TYPE`, `SHOP_SELLER_BIZ_CLASS`. 실제 계약 사업자와 일치해야 한다.
- 현재 세금계산서 자동화는 부가세 포함 일반 과세 주문만 지원한다. 해당 판매 범위를 검증한 뒤 `SHOP_TAX_PROFILE=taxable_vat_included`. 면세·영세·혼합 과세 주문은 활성화하지 않는다. 실발급 검증 후 `SHOP_TAX_INVOICE_LIVE_VERIFIED=true`.
- `SHOP_JOBS_SECRET`은 외부 스케줄러가 `/api/commerce-jobs`를 호출할 때 사용하는 서버 전용 비밀값이다. `POST`, `Authorization: Bearer ...`만 받는다.

`node _scraper/commerce_setup.cjs schema`는 기존 주문을 지우지 않고 필요한 컬럼과 증빙 작업 테이블을 추가한다. `check`는 설정 유무와 DB를 확인하며 비밀값을 출력하지 않는다. 설정은 Vercel 서버 환경변수에도 동일하게 등록해야 한다. 마지막에만 `SHOP_ORDERS_ENABLED=true`로 전환한다.

## 고객과 관리자 흐름

1. 배송지와 결제 증빙을 선택해 접수한다. 관리자가 현재 재고·옵션·납기를 확인하고 30분 유효한 견적을 승인한다.
2. 카드 매출전표 선택 시 카드, 현금영수증 또는 세금계산서 선택 시 계좌이체 결제창을 연다.
3. 현금영수증은 PG 결제창에서 소득공제/지출증빙 및 식별번호를 입력한다. 발급 승인번호·용도·금액이 확인되어야 발급 완료로 표시한다. 미입력·실패는 발급 확인 필요로 남기며 임의 발급하지 않는다.
4. 세금계산서 선택은 발급 서비스가 설정된 경우에만 제공한다. PG 현금영수증 UI를 숨기고 별도 발급한다. 서버에서 결제 금액·주문·거래번호를 확인하고 결제와 발급 작업을 함께 저장한다.
5. 전자세금계산서는 주문별 고정 문서번호를 사용한다. 통신이 끊겨도 기존 문서 조회 후 재처리하며 같은 주문을 이중 발급하지 않는다. 공급받는자 이메일로 공급자가 발급 안내를 전송한다. 발급 완료와 국세청 전송 완료는 별도로 표시한다.
6. 증빙 오류로 완료된 결제를 취소하지 않는다. 결제 취소/부분취소를 확인하면 기존 증빙을 검토 상태로 전환한다. 수정세금계산서 사유 결정·발급은 현재 자동 처리하지 않으며 관리자와 발급 서비스에서 처리한다.

## 자동 재처리와 운영 검증

결제 확인 직후 서버가 발급을 시도한다. 중단·실패한 작업은 GitHub Actions `.github/workflows/commerce-documents.yml`에서 5분 간격 예약으로 복구 API를 호출한다. 예약 실행은 공급자 상황에 따라 지연될 수 있으며 정확한 5분 처리를 보장하지 않는다. 결제/사업자 데이터와 PG 키는 Actions에 보내지 않고, 작업 전용 토큰만 저장한다. 요청이 중복되어도 DB 작업 임대와 발급 문서번호가 이중 발급을 차단한다. Mac `co.nadaun.shop.commerce-jobs`의 60초 NAS 워커는 보조 경로다. 재시도는 최대 5회 후 검토 상태이며 관리자 버튼으로 재처리한다. 워크플로 실패 알림은 GitHub 저장소 알림 설정을 따른다. 실제 발급·장애 복구는 계약 설정 후 추가 검증해야 한다.

외부 발급 API가 설정되기 전 자동 검사는 전부 대역을 쓴다. 실제 카드 승인·계좌이체·현금영수증 두 용도·전자세금계산서·국세청 전송·취소·장애 복구를 계약된 테스트 환경에서 검증해야 한다. INICIS 공개 데모는 실승인될 수 있어 실제 결제를 하지 않은 상태로 완료 표시하지 않는다. 개인정보 수탁자·국외 처리 안내는 실제 계약/저장 지역에 맞춰 활성화 전에 확정한다.

공식 근거: [INIpay PRO](https://manual.inicis.com/pay/pro.html), [거래조회](https://manual.inicis.com/pay/etc-inquiry.html), [Popbill 발행](https://developers.popbill.com/reference/taxinvoice/node/api/issue), [발행·국세청 상태](https://developers.popbill.com/reference/taxinvoice/node/response-code).
