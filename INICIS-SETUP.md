# KG이니시스 개통·증빙 설정

2026-10-12 현재: PG는 KG이니시스이며 실제 고객 주문·결제 접수는 비활성이다. 대표가 새 독립몰용 신청 완료를 전달했고 승인 대기 중이다. 승인·새 MID와 해당 키 발급은 아직 확인되지 않았다. Cloudflare D1 실제 연결, 관리자 전용 https://order.nadaun.co/ 의 HTTPS·로그인·주문 조회·엑셀 5시트, 기존 장비렌탈 캘린더 연결과 Mac 반복 워커는 검증했다. 모바일 주문관리 버튼 수정도 공개했다. 실제 고객 결제 후 전체 흐름, 새 MID/키 연결·요청 서버 IP·승인/현금영수증/취소와 세금계산서 발급 계정·공동인증서·과세 설정은 남아 있다. 키 값은 문서에 기록하지 않는다.

## 2026-10-12 — 새 신청 완료 전달·승인 후 연결

대표 원문 “새로 신청해놨어”, “그거 승인되면 바로 다시 연결하자”를 반영했다. 신청 완료는 대표 전달 기준이며 이니시스 심사 화면에서 승인 상태를 독립 확인한 것은 아니다. 승인 후 새 MID와 그 MID에 대응하는 PRO HashKey·INIAPI Key를 비공개로 함께 교체한다. 실제 요청 서버 IP/허용 조건과 거래 승인·재조회·현금영수증 두 용도·취소 및 주문관리/렌탈 캘린더 종단 확인 이후에 고객 주문을 활성화한다. 기존 아임웹 인증정보는 보존한다.

10/12 04:17 KST 공개 API는 `adminEnabled=true`, `ordersEnabled=false`, `rentalRequestsEnabled=false`, `paymentProvider=inicis`, `taxInvoiceEnabled=false`다. 세금계산서 발급자·사업자 공동인증서·과세 설정·실발급은 별도 남은 단계이며 이를 모든 카드 결제 개통의 필수 장애로 설명하지 않는다. 상세 확인은 [공급처·모바일 현황](SUPPLIER-STATUS.md)을 함께 읽는다.

## 2026-10-11 22:23 KST — 독립몰용 새 INICIS MID 발급 방향 확정

대표가 이니시스 안내 결과를 전달하고 “새아이디”, “MID 새로 제작하면 그걸 해야하는 것 같다”고 명확히 했다. 나다운샵은 기존 아임웹 MID 재사용을 전제로 개통하지 않고, `https://shop.nadaun.co/` 독립몰용 새 MID 발급을 진행하는 방향으로 정리한다. 이는 대표 전달에 따른 결정이며 새 MID 실제 발급·새 계약 제출·심사 승인이 완료됐다는 뜻은 아니다.

공식 신청 경로 `https://www.inicis.com/service-application`를 재조회했고 “직접 쇼핑몰을 구축하여 운영 / 독립형 쇼핑몰 신청” 선택을 확인했다. 요청 내용은 나다운샵 자체 개발 독립몰, 홈페이지 `https://shop.nadaun.co/`, 촬영 장비 판매와 렌탈의 실제 취급 범위, INIpay PRO, 카드·계좌이체 및 현금영수증 소득공제/사업자 지출증빙, 거래 조회·취소용 INIAPI, Vercel 요청 서버 IP/허용 조건이다. 실제 심사 범위와 계약 조건은 이니시스가 확정한다.

다음 단계는 새 MID와 해당 MID에 연결된 PRO HashKey·INIAPI Key를 비공개 설정에 함께 교체하고, 승인·거래 재조회·현금영수증 두 용도·취소와 주문관리/렌탈 캘린더 종단 검증을 완료하는 것이다. 기존 아임웹 MID/키를 임의 폐기하지 않으며 새 키에 기존 키가 그대로 유효하다고 가정하지 않는다. 실제 고객 주문/결제는 검증 전 비활성이다. 전자세금계산서 발급 계정·사업자 공동인증서는 별도 남은 항목이다. 이번 변경은 결정·다음 단계 기록만이며 새 계정 생성 또는 운영 설정 교체는 수행하지 않았다.

## 2026-10-09 기존 아임웹 계정 확인

현재 기존 MID는 사용 상태이며 등록 URL은 `https://rainbowshop.imweb.me/`다. 해당 MID를 새 독립몰 `https://shop.nadaun.co/`에서 바로 쓸 수 있다고 확정하지 않는다. 관리자 `변경/추가 > 결제서비스 변경/추가 > 독립몰 추가 계약 체결` 화면까지 확인했다. 최초 독립몰 신청에 연관리비 33만원 안내가 있으나 현재 계약의 실제 부과 여부는 미확정이다. 약관 동의·신청 제출·비용 결제는 수행하지 않았다. 도메인 변경/상점ID 추가 또는 독립몰 계약 중 적용 절차를 이니시스에 확인해야 한다.

INIAPI 조회의 고도몰 안내는 키 생성 제한이며 닫은 후 기존 Key/IV가 조회됐다. 기존 키를 사용할 수 없다는 중간 안내를 정정했다. 대표가 생성한 모바일 Hash Key는 10자리이며 기존 임의 16자리 최소 검사를 수정했다. 실운영 확인 게이트는 유지한다. 모의검사는 PG 실결제 또는 외부 키 인증 성공 근거가 아니다.

비공개 근거: `_private/commerce/inicis-20261009/`의 백업, Secret 등록 영수증, 계약 화면, 테스트 로그. 주문 접수와 실운영 확인 변수는 모두 `false`다. 계약 서명은 행동 시 확인이 필요하고 실제 금융 결제는 대표가 진행해야 한다(브라우저 제어 확인 규칙).

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

## 사업정보 확인 잔여 사항

현재 공개 페이지에 통신판매업신고번호 `2022-서울영등포-1523`과 `2020-서울강남-01618`이 함께 남아 있다. 계약 사업자의 최신 신고 원문으로 확정한 후 템플릿/전체 페이지를 통일한다. 실제 개인정보 수탁자와 처리 지역도 계약 및 주문 DB 설정에 맞춰 확정한 뒤 주문을 활성화한다. 원문 확인 전 임의 번호로 덮어쓰지 않는다.


## 관리자와 회계 자료

`/admin.html`은 기간·주문번호/PG거래번호·결제환경·주문/배송/증빙 상태 조회, 25건 페이지, 전체 결과 합계와 처리 이력을 제공한다. D1·관리자 설정만 갖추면 공개 결제가 비활성이어도 관리자 조회/다운로드는 가능하다. 엑셀은 안내/합계·주문결제·상품·증빙·처리이력 5개 시트, CSV는 주문결제 전체 행이다. 현재 페이지/최근 100건에 제한하지 않는다. 한 번에 1년·1만건, 응답 4MB를 넘으면 기간을 나눠 다운로드하도록 안내한다.

한국 시간의 주문접수일 또는 서버 결제확정일로 조회한다. PG 승인일은 별도 열이며 확인되지 않은 취소 발생일/부분 환불액/수수료/실입금액을 만들지 않는다. 테스트는 기본 운영 조회와 연간 결제 바로가기에서 제외된다. 원 승인액과 취소 주문 원 승인액은 별도이며 PG 정산명세와 대조해야 한다. CSV 수식 주입을 방지하고 엑셀 문자·숫자 타입을 구분한다. 1,203건 대역 주문으로 전체 자료와 접근 권한을 검증했고 현재 결제/관리자 검사 59개 통과, 의존성 보안검사 0개 취약점이다.


## 2026-10-09 D1 생성 및 렌탈 입력 후속 상태

- Cloudflare 로그인된 현재 계정에 `nadaun-shop-orders` D1을 생성하고 `shop_orders`, `shop_order_events`, `shop_rate_limits`, `shop_documents` 네 테이블을 실제 조회했다. 계정/DB ID는 비공개 configuration.json에 저장했다. 연결 토큰은 미발급 상태다.
- 현재 계정에만 D1 Edit 권한을 주는 `nadaun-shop-d1` User API 토큰 Summary를 준비했다. `Create Token`은 새 인증정보 발급을 대표가 직접 수행해야 하는 브라우저 규칙에 따라 넘겼다. 토큰의 NAS 비공개 설정 및 Vercel Secret 저장·연동 허용을 요청했으며 아직 답변이 없다. 값은 채팅/공용 문서에 붙이지 않는다.
- 관리자 주소 `https://shop.nadaun.co/admin.html`. 인증된 기간별 주문 조회·처리·증빙·연간 XLSX/CSV 코드가 있고, 실제 D1 연결 후 운영 주문 기능을 검증해야 한다.
- 렌탈 시작/종료일·분 단위 방문 시간·수량 입력/이 브라우저 저장, 암호화 접수, 관리자 전체 기간 단가 확정, 실결제 검증 후 수령/반납 및 회계 자료 포함을 구현했다. `SHOP_RENTAL_REQUESTS_ENABLED`는 구매 `SHOP_ORDERS_ENABLED`와 별도이며 아직 비활성이다. 일정 저장은 실제 예약 확정이 아니다.
- MID 새 도메인 사용 승인·실제 요청 서버 IP·카드/계좌이체/현금영수증 소득공제/사업자 지출증빙/취소 검증, 세금계산서 발급자 계정·인증서·과세 설정·실발급 검증이 남아 있다. 기존 MID/key 등록을 개통 완료로 보고하지 않는다.
- INICIS `clientIp`는 가맹점 요청 서버 IP이고, Vercel 일반 출구 IP는 고정으로 취급하지 않는다. 고정 IP가 필요한 허용 방식인지 PG에 확정한 뒤 배포 서버에서 검증한다. 공식 참고: [INICIS 거래조회](https://manual.inicis.com/pay/etc-inquiry.html), [Vercel 출구 IP](https://vercel.com/kb/guide/can-i-get-a-fixed-ip-address). 유료 고정 IP 추가 결제/신청 없음.

렌탈/관리자 최종 코드 공개 검증: 2026-10-09T09:42:19+00:00 · revision 9de9c8fc599f4708. 실제 운영 DB/PG/발급은 위 대기 상태를 유지한다.


## 2026-10-11 로그인 재인증·개통 잔여 확인 및 자동 공개 복구 (진행)

대표가 현재 진행 상태 확인과 빠른 인증·마무리를 요청했고, 등록된 본인 Gmail에서 이니시스 로그인 인증번호를 직접 확인해 달라고 명시했다. 이번에 요청한 최신 메일의 번호로 기존 가맹점관리자 로그인을 완료하고 상점정보와 신청현황을 재조회했다. 인증번호·키 값은 기록하지 않는다. 기존 상점은 사용 상태, 등록 홈페이지는 여전히 아임웹이다. 서비스 신청현황 표에 신청 건이 표시되지 않았으며 독립몰 추가 계약 화면은 최초 신청 연관리비 33만원과 별도 심사/계약 조건을 안내한다. 현재 계약의 실제 비용·새 샵 사용 승인 여부는 미확정이다. 약관 동의·신청 제출·비용 결제·실결제는 하지 않았다.

Cloudflare는 로그인돼 있고 D1·네 테이블 및 계정/DB ID가 준비돼 있으나, 실제 화면은 nadaun-shop-d1 Summary의 Create Token 직전이다. 인증정보 최종 생성은 브라우저 도구의 직접 수행 규칙에 따라 대표에게 넘겼다. 대표가 생성한 뒤 NAS 비공개 설정과 Vercel production Secret에 저장·연동하는 흐름을 안내했다. 설정 검사에서 정확히 SHOP_D1_API_TOKEN 및 SHOP_INICIS_CLIENT_IP가 미등록이다. 기존 MID/HashKey/INIAPI Key·암호화·세션·관리자 비밀값은 등록 상태다. 잘못된 변수명 SHOP_D1_ACCOUNT_ID로 계정 ID가 없다고 판단하지 않으며 실제 변수 SHOP_CF_ACCOUNT_ID는 등록돼 있다.

2026-10-11 15:51 KST 실제 공개 API는 ordersEnabled=false, rentalRequestsEnabled=false, adminEnabled=false, paymentProvider=inicis다. 공개 카탈로그는 10/9 최종 revision 9de9c8fc599f4708, 상품19,566개다. 장바구니/렌탈 입력·관리자·연간 자료 코드 공개와 실제 주문·PG·증빙 개통을 구분한다. 세금계산서 발급자/인증서·과세 설정·실발급, 도메인·요청 서버 IP·카드/이체·현금영수증 두 용도·취소 검증 및 사업/개인정보 원문 확정은 미완료다.

추가 발견: 10/9 19:28 KST 남은 0바이트 Git index.lock 때문에 전체 자동 수집/검사를 통과한 뒤 git add가 실패했고, 미검토 생성물564개 보호 검사로 이후 파트너 승격이 중단됐다. 활성 코드 변경0, staged 변경0, run.lock 없음, 실제 Git 프로세스 및 해당 잠금 파일 소유자 없음 확인. 현재 생성물은 상품 수 변동0·가격 변동0, 기존 상품3개(공급처 품절1·분류2)의 변화다. 운영 워커7개만 일시 중지하고 잠금을 비공개 근거에 보존한 뒤 변경 생성물 백업·전체 필수 검사·기존 검증 원본으로 공개 복구를 진행 중이다. 공개 영수증 전까지 복구 완료로 표시하지 않으며 원래 로드된 워커를 반드시 복원·재조회한다.

근거: shop _private/commerce/activation-20261011/status.json, live-commerce.json, live-catalog.json, mirror-diff-review.json, mirror-recovery.json, mirror-recovery-publication.log, inicis-authenticated-contract-review.png, cloudflare-token-pending.png. 인증번호/비밀번호/API 키는 공개 문서·Git·Obsidian에 보존하지 않는다.


### 2026-10-11 15:58 KST 공개 복구 최종 확인

위 진행 중 배포를 마쳤다. commit `208aaed3c46bea853c532ecc2caac882dcb3f198`, deployment `dpl_C65i3ECh3mNNwmJw7UFec4iKmG98` production READY, revision `440ee33317c2321b`, publisher 라이브 검증 `2026-10-11T06:57:04+00:00`. 필수 전체 검사 및 공개 전체 카탈로그-비공개 출처 장부 전수 대조 통과. 공개19,566개/276브랜드 유지, 미반영3개 상품의 품절/분류 변경 반영. 기존 코드 변경0·원본 삭제0, 이전 생성물564개 백업 및 오래된 잠금 보존. 일시 중지한 Mac 자동 워커7개를 모두 복원하고 각각 실제 로드 재조회했다.

15:58 추가 라이브 확인: cart.js/rental-content.js/commerce.js/shop.css 네 자산이 NAS와 정확히 일치, 운영 revision 일치, 변경 KPP 상품의 실제 supplier_status/status=soldout 확인. 실제 API는 ordersEnabled=false / rentalRequestsEnabled=false / adminEnabled=false / paymentProvider=inicis다. 이니시스 관리자 로그인 이메일 인증은 완료됐지만 PG/주문/증빙 실개통은 미완료다. Cloudflare 화면은 아직 Create Token 직전이며 대표의 직접 생성 후 비공개 저장·D1/관리자 연결을 이어간다. 새 도메인 사용·요청 서버 IP/실거래 검증, 별도 전자세금계산서 발급 설정/검증, 사업정보·개인정보 원문 확정 대기. 추가 파트너 자동 워커의 다음 주기/새 후보 공개는 각각 새 영수증으로 판단하며 워커 로드만으로 새 전수 수집/공개 성공을 주장하지 않는다.

완료4개: 이니시스 관리자 로그인 재인증, 기존 장바구니 개선 공개 유지, 렌탈 일정·관리자/회계 코드 공개 유지, 자동 공개 잠금 복구 및 검증된 상품 변경 공개. 미완료3개: 실제 D1/관리자 운영 연결, PG 실개통·증빙/취소 종단, 별도 세금계산서 실발급. 최종 근거는 `_private/commerce/activation-20261011/final-live-verification.json` 및 `mirror-recovery.json`/`status.json`이다. 현재 Mac NAS 원시 기록 보존 완료/errors=[]와 Obsidian 읽기본 저장·재조회 확인. 다른 PC 실행은 검증하지 않았다.


### 2026-10-11 16:28 KST 대표 마무리 요청 후 최종 공개 검증 진행

대표 원문 “마무리해놔~”에 따라 남은 실제 상태를 재조회했다. Cloudflare는 여전히 nadaun-shop-d1 Summary의 Create Token 직전이며 API 토큰 미등록이다. 새 인증정보 최종 생성은 브라우저 직접 수행 규칙에 따라 대표에게 열린 화면을 넘기고, 생성 후 비공개 저장·D1/관리자 연동을 대기한다. 메일 인증을 완료했던 이니시스 관리자 세션은 이번 재조회에서 로그인 화면으로 만료됐으며, 이전 로그인 성공을 PG 실개통으로 표시하지 않는다. 주문/렌탈/관리자 운영 게이트는 아직 false다.

공정위 현재 사업자번호 조회 상세와 NAS 통신판매업 신고증을 함께 확인해 통신판매번호 2022-서울영등포-1523을 확정했다. 과거 강남번호가 남은 공통 템플릿 하단을 통일할 근거가 확보됐으며 공개 반영은 최종 배포 영수증 이후 완료로 기록한다. 현재 등록 상세는 https://www.ftc.go.kr/www/selectBizCommView.do?pageUnit=10&pageIndex=1&searchCnd=BRNO&searchKrwd=3438701678&key=253&opnSn=2022318024730201466 . 사업장 등록 주소·인터넷도메인은 별도 대조 항목이며 신고번호 확인만으로 새 샵 도메인/주소 변경 신고 완료를 주장하지 않는다.

복원된 기본 수집 워커가 실제 실행 중이며 스마트스토어6917·KPP4040·L-mount345 등 현재 목록/상세 검증을 진행한 뒤 전체 검사 통과·Git 반영 단계로 진입했다. 실제 활성 프로세스 PID40905와 공유 run.lock을 보존했다. 공급처6개 현재 수집완료 후보를 전수 기존 데이터와 비교했으며 상품 ID·가격·상태·내용 변화0, 확인 시각/수집 메타데이터만 갱신됐음을 확인했다. AVX1833 중 공개1359/대표제외472/상세 비어 있는1700·1096 두건 보류는 유지한다. 이전 공개 오류로 대기 중인 후보를 재승격·실제 공개 재검증하고 정상 영수증으로 이전 오류를 해소하는 별도 최종화 스크립트를 NAS 비공개 경로에서 실행했다. 파트너 워커6개는 모두 비실행 상태를 확인한 뒤 일시 중지했고 스크립트 finally에서 원래 로드 상태를 복원·재조회한다. 기본 수집 워커와 보호 응답 중지 장치는 변경하지 않았다.

진행 근거: _private/commerce/activation-20261011/finalize_public_review.py, partner-finalization.log, partner-finalization-paused.json, pending-partner-review.json, ftc-current-business.json/png, cloudflare-final-handoff.png. 공개 성공/복원은 최종화 영수증 전까지 진행 중이다. 인증번호·비밀번호·키 값은 공용 문서에 기록하지 않는다.


2026-10-11 16:34 KST 추가 운영 설정 확인: production 환경변수 목록을 실제 재조회한 결과 기존 INICIS MID/HashKey/INIAPIKey 및 관리자·암호화·세션 Secret은 등록돼 있었으나 Cloudflare 계정 ID와 DB ID는 NAS에만 있고 운영 서버에는 없었다. 두 ID를 Vercel production encrypted 변수로 등록하고 API로 재조회했다. 토큰/요청 서버 IP는 아직 미등록이며 주문·렌탈·관리자 활성 플래그는 변경하지 않았다. Toss 관련 필드는 NAS 활성 configuration, 운영 코드 및 production 환경변수에 모두 없다. 전자세금계산서 발급자 계정/인증서와 공급자·과세 설정은 미등록이다. 새 D1 ID 등록만으로 DB 실제 연결 성공을 표시하지 않는다. 근거: production-secret-presence.json, d1-identity-registration.json.


### 2026-10-11 16:52 KST 최종 공개·운영 설정 확인 및 실개통 잔여

최종 공개 commit `99e1686b685c7012c1db5331888283d27fc75b34`, deployment `dpl_5GnGapoFn8yV5N5CLCNZ2WBFfmk4` production READY, revision `56ddfade5399e4df`, 라이브 검증 `2026-10-11T07:48:10+00:00`. 기본 공급처 새 수집의 공개 commit0dfb12f2 이후, 검증 완료 파트너 후보6개를 기존 출처 기준으로 한 번에 반영한 fa3a977c와 사업자 신고번호 수정을 공개했다. 최종 카탈로그19,566개를 출처 검증 원장과 대조했고 회사소개/약관/개인정보/관리자/홈 및 cart.js/rental-content.js/commerce.js/shop.css 총9개 공개 자산을 승인 배포 바이트와 비교해 모두 일치했다. 브라우저 실제 회사소개 하단에서도 두 위치 모두 2022-서울영등포-1523 표시를 확인했다. 원본에서 과거2020번호를 발견하고 공정위 현재 등록 상세 및 NAS 신고증으로 확정했다.

파트너 검증 공개 offer: PLTHINK6253, 온앤오프1067, 씨엘2146, 시네몰1183, DJI공식925, AVX1359. AVX 전체수집1833 중 대표제외472·원문 상세 비어 있는1700/1096 두건 보류를 그대로 유지했다. 대기 후보들의 상품 ID·가격·상태·내용 변경0, 확인/수집 시각만 갱신됐다. 후보 수집 시각은10/9~10/10이며 오늘 모든 업체의 새 전수 수집이 끝났다고 표시하지 않는다. 7개 Mac 자동 작업을 실제 로드 재확인했고 후속 수집 완료/공개는 각 새 영수증으로 판단한다. 보호 응답 중지 상태는 변경하지 않았다.

추가 복구: 초기 비공개 최종화 검사에서 Git 오류 경로의 상품번호403/429가 보호 응답으로 오인돼 기록 정리가 중단됐다. 실제 오류 유형과 기존 보호 상태를 확인하고 원본 오류를 보존한 뒤 이미 성공한 공개 결과를6개 출처별로 재검증·기록했다. 이어진 중복DJI 승격에서 Git 상태 검사180초 제한이 NAS 읽기로 초과하는 실제 재발을 확인했다. publication_storage의 소유 파일 검사 시간을 공용 publisher와 같은900초로 맞췄고 보호/변경/스테이징 검사는 그대로 유지했다. 기존 저장소10검사·워커6검사 통과, 실제1497개 소유 경로 검사5.265초/생성물변경0 확인. 수정은 위 최종 commit으로 공개·전수 출처 원장 라이브 검증을 통과했다. 과거 오류 기록은 보존하고 resolved 근거를 연결했다.

Toss는 활성 NAS설정·운영 코드·Vercel production 변수에 남아 있지 않다. 확보된 INICIS키/관리자·암호화 Secret은 운영에 있다. NAS에만 있던 Cloudflare 계정/DB ID2개와 사업자등록증명(2026-05-01)의 공급자 법인명·사업자번호·대표자·등록 주소4개를 production encrypted 설정에 등록하고 API재조회했다. 업태/종목·과세 구분은 임의로 확정하지 않았고 발급 인증서를 업로드/결제하지 않았다. 사업자 원문의 법인명/사업자번호는 현재 공정위 등록과 일치하며 공정위 공개 등록의 옛 주소/도메인과 최신 NAS 사업장·새샵은 별도 변경 확인 항목이다. 국세청 현재 등록 상태 재인증이나 새 신고를 완료한 것으로 간주하지 않는다.

실제 운영 API: ordersEnabled=false / rentalRequestsEnabled=false / adminEnabled=false / paymentProvider=inicis. 설정검사 미등록은 SHOP_D1_API_TOKEN, SHOP_INICIS_CLIENT_IP이며 실제 DB조회·PG결제·증빙발급·취소는 미검증이다. Cloudflare는 아직 Summary의 Create Token 직전, 대표 직접 생성 후 비공개 저장·DB/관리자 연결을 기다린다. 기존 이니시스 관리자 메일 재인증 성공과 세션 만료, 계약/새샵 승인·실거래는 구분한다.

완료5개: 카탈로그 허용 자료 공개 대조, 장바구니 개선 공개, 렌탈 일정·관리자/연간 회계 코드 공개, Toss 제거·확보된 INICIS키 운영 등록, 사업자표기 정정·확보된 DB/공급자 설정 운영 등록. 미완료3개: 실제 D1/관리자 연결, 새샵 PG승인/요청 서버IP 및 카드·이체·현금영수증 두 용도·취소 검증, 세금계산서 발급 계정/인증서·과세 설정 및 실발급. 실제 주문/결제 접수는 아직 비활성이다.

근거: _private/commerce/activation-20261011/closing-live-verification.json, partner-finalization-release.json, partner-finalization-receipts.json, nas-timeout-live-release.json, nas-timeout-tests.log, nas-real-inspection.json, closing-worker-proof.json, production-secret-presence.json, d1-identity-registration.json, seller-identity-registration.json, live-registration-footer.png. 공용 문서와 Obsidian에 키·인증번호·비밀번호·법인 등기번호를 복사하지 않는다. 현재 Mac만 검증했으며 다른 PC 실행은 미확인이다.


## 2026-10-11 18:39 KST — 주문관리 전용 주소·D1 실제 연결 및 캘린더 작업

대표가 제공한 Cloudflare 토큰의 active 인증과 D1 실제 조회·스키마 처리가 성공했다. 키는 NAS `_private/commerce/configuration.json`과 Vercel production encrypted 변수에만 저장했다. 토큰 값은 공용 문서에 남기지 않는다. 주문관리 전용 `https://order.nadaun.co/`를 동일 프로젝트에 연결하고 Cloudflare CNAME을 저장·재조회했다. 실제 TLS 호스트 검증, 관리자 로그인, 운영 주문 조회 0건, 엑셀 5시트 다운로드가 성공했다. 배포 d378fcce38319ca6b7bb8f890c09bf60d4cf9265 / dpl_2hXBqN8N7GxjV1PSEbbcMycFB19F. 운영 config는 adminEnabled=true, ordersEnabled=false, rentalRequestsEnabled=false, paymentProvider=inicis, taxInvoiceEnabled=false다. 기존의 D1 토큰 생성 대기 기록은 이번 실제 연결로 해소됐다.

기존 `nadaun_order_sync` Google OAuth 갱신과 장비렌탈 캘린더 소유자 권한을 확인했다. 신규 나다운샵 연동은 실결제가 서버 확인된 렌탈만 등록하고, 구매/테스트/미결제는 제외한다. 주문번호 기반 중복 방지, 방문 시각 분 단위 보존, 수령/반납 업데이트, 전체 취소 제거, 부분 취소·수동 변경 검토, 누락 복구, DB 작업 임대와 관리자 연동 상태 표시를 구현했다. 해당 서비스는 아직 최종 코드 공개 검증 중이며 실제 고객 주문 종단 검증은 미실시다. Mac `co.nadaun.shop.calendar-sync` 60초 워커 실제 로드·API/DB 조회 성공; 다른 PC 실행은 미확인. 내부 연결 검증 일정(고객 예약 아님)은 Google API 실제 등록·조회·시간 변경·취소 후 제거 확인했고 고객 개인정보를 사용하지 않았다.

실결제/온라인 접수는 계속 닫혀 있다. 이니시스 기존 MID의 아임웹→새 독립몰 사용 승인/계약 적용, 실제 요청 서버 IP와 카드·이체·현금영수증 소득공제/지출증빙·취소 검증이 남았다. 세금계산서 발급 서비스·사업자 공동인증서 위치를 대표에게 비동기 확인 중이다. HTTPS 인증서는 실제 검증 완료했으며 전자세금계산서 공동인증서 연결과 구분한다. 세금계산서 선택은 발급자를 갖추기 전 비활성으로 두되, 이것을 모든 카드 주문 개통의 필수 장애로 설명하지 않는다.

근거: `_private/commerce/activation-20261011/`의 d1-token-verification.json, d1-production-registration.json, order-domain-vercel.json, order-domain-live-admin.json, calendar-live-crud.json, 관리자/DNS 스크린샷과 테스트 로그.


### 2026-10-11 18:49 KST 최종 공개 및 반복 실행 검증

최종 운영 공개는 commit a9b9e603b2a67c9b030cb3816759b75c32af9c1a / deployment dpl_3busury7fVLLCsFUeMXE1He5YV4N / revision 44ef0794bd05fcaa다. 상품19,566개의 전체 공개 원본/정책 대조와 필수 Python·Node·구문 검사가 통과했다. 전체 Node138개, 결제/관리자/렌탈/캘린더79개 및 실제 Google API 내부 검증과 실제 관리자 엑셀 검증은 서로 구분한다. 공개 JS 실제 바이트 일치, 기존 /admin.html→order.nadaun.co 연결, 캘린더 마지막 연결 시각 화면을 확인했다. 비로그인 주문/캘린더 조회401, 외부 Origin로그인403, 비공개 설정·서버 코드404를 실제 검증했다.

Mac 새 워커의 최초 실행은 NAS 작업디렉터리/로그 경로 때문에 EX_CONFIG78이었고, 기존 commerce-jobs 방식과 같이 로컬 실행 디렉터리·실행 로그를 사용하도록 수정했다. 원본 코드/인증 설정/작업 결과는 NAS에 유지한다. 수정 후 exit0 반복 실행을 실제 확인했다. 실행 로그는 PC별 경로 `/Users/james/.local/state/nadaun-shop-calendar/`이며 연결 결과는 NAS `_private/commerce/calendar-status.json`과 D1 shop_calendar_health에 남는다. 로드만으로 성공을 판단하지 않는다. 기존 카탈로그 워커의180초 Node검사 시간초과는 NAS 전체 검사에600초 한도를 적용해 복구했고, 동일 필수 검사를 유지한 새 공개/전체 원본 대조 성공으로 해소했다. 원래 실패 및 무주체 Git index.lock은 비공개 근거로 보존했다.

연결 검증 완료3개: 실제 주문DB, 전용 관리자 주소/HTTPS/조회/회계다운로드, 기존 장비렌탈 캘린더/자동 워커. 실운영 개통 미완료2개: INICIS 새샵 계약/승인·요청 서버IP·카드/이체/현금영수증 두 용도·취소 및 고객 주문 종단 검증; 전자세금계산서 발급자/사업자 공동인증서·과세 설정·실발급. 실제 config는 adminEnabled=true, ordersEnabled=false, rentalRequestsEnabled=false, taxInvoiceEnabled=false. 전자세금계산서 비활성만을 모든 카드 주문의 필수 개통 장애로 설명하지 않는다. 공개 개인정보 안내는 실제 거래 개통 전에 처리자·저장/이전 조건과 함께 확정해야 한다. 대표에게 발급 서비스와 공동인증서 위치를 요청한 답변은 아직 없다. 이니시스 고객센터1588-4954(https://www.inicis.com/i_sitemap)로 기존 아임웹MID의 새독립몰 적용/서버IP/현금영수증 계약 조건을 확인하도록 안내했다. 계약 서명/실결제는 수행하지 않았다.


### 2026-10-13 비교 요청 재확인

실제 관리자/DB연결은완료, 고객결제는비활성이다. 대표가 토스페이먼츠와비교를요청했으며현재PG전환승인이나새계약은없다. 기존 독립몰 신규MID 승인대기 기록은실제키수령/승인확인전까지유지한다. 현금영수증소득공제/지출증빙은PG, 고객전자세금계산서는나다운명의별도발급서비스로구분한다. 구체확인·백업·배포근거는RUNBOOK2026-10-13절을따른다.
