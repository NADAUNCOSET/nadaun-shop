# 토스페이먼츠 개통 상담 메모

- 사이트: https://shop.nadaun.co
- 연결 방식: 자체 개발 쇼핑몰, Toss Payments JavaScript SDK v2 **주문서형** (`widgets`, `renderPaymentMethods`, `renderAgreement`).
- 사전 확인 화면: https://shop.nadaun.co/payment-test.html
- 상품 주문서: https://shop.nadaun.co/checkout.html (상품을 장바구니에 담은 뒤 확인)
- 현재 공개 화면은 문서용 키로 결제수단과 인증 화면을 확인하는 테스트다. 실제 승인·주문 접수·배송은 하지 않는다.

상담 시 이렇게 설명한다:

> 자체 개발 쇼핑몰 shop.nadaun.co에 토스페이먼츠 v2 주문서형 위젯을 연결했습니다. 현재 문서용 테스트 키로 화면을 확인할 수 있습니다. 상점 신청과 카드사 심사를 진행하려고 합니다. 상점 MID와 주문서형·결제창형 연동용 테스트 키 발급 절차를 안내해주세요.

## 발급 이후 연결

운영 주문용 설정 원본은 사이트 프로젝트 내부 비공개 폴더 `_private/commerce/configuration.json`이다. 시크릿 키를 채팅·공개 코드·Git에 붙이지 않는다.

- 주문서형 테스트 키 쌍: `test_gck_…`, `test_gsk_…`
- 계약 후 라이브 키 쌍: `live_gck_…`, `live_gsk_…`
- 주문 DB 연결, 실제 상점 테스트 키로 승인/조회/실패 복구 검증, 운영 약관/정보 확인 후 실결제를 연다.

현재 문서용 테스트 화면이 열리는 것만으로 상점 계약·카드사 심사·실결제 개통 또는 주문 운영 전체가 완료된 것은 아니다. 최신 절차/구현 범위는 `COMMERCE-PLAN.md`를 따른다.
