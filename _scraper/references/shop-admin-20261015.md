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

현재 단계: 코드·자동 검사 완료, 최종 브라우저 검증 및 배포 진행 중. 최종 commit/deployment/live 근거는 RUNBOOK과 같은 private 폴더 영수증을 확인한다.
