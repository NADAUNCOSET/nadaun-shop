# Windows 카테고리 이미지 겹침과 PG 배송 문구 — 2026-10-15

Mac·Windows 모두 NAS의 이 프로젝트를 사용한다. 시작점은 `RUNBOOK.md`, 이번 작업의 상세 근거는 `_private/windows-layout-pg-20261015/`다. 별도 PC 사본으로 작업하지 않는다. 대표 요청은 화면 갈라짐의 원인·재발 검증, 수정 전 백업, 이번 변경만 커밋·공개, 배송안내 페이지에 구매 배송 소요기간 및 확정된 렌탈 최대기간 표시다.

## 확인한 원인과 수정

`assets/shop/motion.js`는 `.category-image` 내부에 `position:absolute; inset:0`인 `.motion-plane`을 생성한다. `.category-image`에 위치 기준이 없어 레이어가 viewport를 기준으로 배치됐다. Windows Chrome 2048×1087에서 137×106px 카드의 레이어가 2048×1087px, 내부 이미지가 1761×935px로 계산됐다. 큰 이미지들이 같은 화면 영역에 겹치고 각 이미지의 clip-path·transform 경계가 드러나 조각난 화면처럼 보였다. 최초 55개 카테고리 이미지에서 재현됐고 JavaScript 오류는 없었다.

`assets/shop/storefront.css`의 `.category-image`에 `position:relative`를 추가하여 프레임을 기준으로 배치한다. `.category-image>.motion-plane`을 grid 중앙 정렬해 기존 이미지 배치를 유지한다. 스크롤 타임라인과 링크는 그대로 사용한다. Mac에서 정상으로 보였던 구체 원인은 현재 Windows 검수만으로 확정하지 않는다. 실제 GPU 주사율·하드웨어 화면 tearing을 진단한 기록도 아니다.

## 배송안내

`https://shop.nadaun.co/shipping.html#delivery`에 **구매 후 배송완료까지 1주일 내에 완료됩니다.**를 기재한다. 생성 원본 `_scraper/shop_templates/policies/shipping.html`과 공개 `shipping.html`을 함께 수정해 다음 자동 빌드에도 남긴다. 별도 약정 일정·특수 상품의 기존 안내와 배송비 계산은 보존한다.

2026-10-15 대표가 **최대 2주(14일)**로 확정했다. 같은 배송안내 페이지의 `#rental-period` 절과 상단 바로가기에 명시하고 생성 템플릿·공개 HTML을 함께 수정한다. 최종 백업·브라우저 검증·배포 영수증은 `_private/pg-rental-period-20261015/`를 읽는다. 안내 문구 공개와 실제 PG 승인 결과는 구분한다.

## 백업과 검증

`_private/windows-layout-pg-20261015/before/`의 CSS·배송 템플릿·공개 HTML을 `backup-manifest.json`의 SHA-256·파일크기로 확인한다. 이 폴더는 Git/Vercel에서 제외하는 기존 비공개 원장 안에 있다.

Windows 11에서 별도 headless Chrome 155.0.8059.40 및 Edge 155.0.4283.45로 검증했다. 대표의 열린 앱·브라우저·입력·포커스와 OS 설정은 변경하지 않았다.

- 화면: 2048×1087, 1440×900, 1280×720, 390×844, 320×760.
- `no-preference` 및 `reduce` 각각 검사. 총 20개 조건 × 8개 스크롤/포커스 단계.
- 느린 휠, 큰 휠 이동, 역방향 이동, 창 크기 변경, 키보드 포커스와 호버에서 실제 프레임·레이어 크기와 가로 넘침 대조.
- 수정 전 검사 실패, 수정 후 20개 조건 통과, JavaScript 오류 0. 스크린샷의 본문/메뉴/이미지 정렬 확인.
- 관련 Node 회귀 26개 및 배송비 Python 검사 3개 통과.
- Mac Safari 실제 실행은 미검증. Windows에 있는 WebKit은 Python Playwright 요구 버전과 달라 실행하지 못했으며 Safari 검증으로 표시하지 않는다.

같은 소스의 브라우저 검증 명령(프로젝트 루트에서 실행):

```powershell
python -X utf8 _scraper/verify_storefront_layout.py --phase after --local --browsers chrome,msedge
python -X utf8 _scraper/verify_storefront_layout.py --phase live --browsers chrome,msedge
```

Mac에서는 설치된 Playwright Chromium으로 `python3 _scraper/verify_storefront_layout.py --phase live --browsers chromium`을 실행할 수 있다. 실행되지 않은 OS/브라우저는 완료로 기록하지 않는다. `--local`은 별도 검수 브라우저에서 NAS의 CSS·배송 HTML만 덮어 보여주며 상품 데이터는 다시 생성하지 않는다.

## 공동 작업과 공개 확인

공용 `_scraper/.sync-state/run.lock`을 이번 Windows 프로세스가 소유한 상태에서 백업·수정·커밋·공개 확인한다. 다른 작업의 미커밋 `RUNBOOK.md`·상품 후보·보관 자료를 일괄 스테이징하지 않는다. 기록에 추가한 이번 절만 index에 반영한다. 게시 잠금은 작업 후 이동 로그를 남겨 보존·해제하며 자동 게시 주기와 Mac 실행 프로세스는 변경하지 않는다.

배포 완료 조건은 GitHub의 정확한 커밋에 해당하는 Vercel production READY, 운영 도메인의 수정 CSS·배송 문구 재조회, 운영본 브라우저 검증이다. 최종 커밋·배포 ID·파일 해시·검사 결과는 같은 비공개 원장의 `release.json`과 `live-verification.json`을 읽는다.
