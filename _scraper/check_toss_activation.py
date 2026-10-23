"""Read-only opening checklist; never enables payments or calls a payment API."""
from datetime import datetime, timedelta, timezone
from html import escape
import json
from pathlib import Path
import subprocess
import requests

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / '_private/commerce/toss-monday-20261026'
KEYS = ['SHOP_TOSS_CLIENT_KEY', 'SHOP_TOSS_SECRET_KEY', 'SHOP_TOSS_MID',
        'SHOP_TOSS_TEST_CLIENT_KEY', 'SHOP_TOSS_TEST_SECRET_KEY', 'SHOP_TOSS_TEST_MID']


def main():
    STATE.mkdir(parents=True, exist_ok=True)
    cfg = json.loads((ROOT / '_private/commerce/configuration.json').read_text())
    report = {'checked_at': datetime.now(timezone(timedelta(hours=9))).isoformat(),
              'owner_expected_approval_date': '2026-10-26', 'approval_verified_with_provider': False,
              'local_key_presence': {key: bool(cfg.get(key)) for key in KEYS},
              'local_mode': cfg.get('SHOP_PAYMENT_MODE'), 'local_live_verified': cfg.get('SHOP_TOSS_LIVE_VERIFIED') == 'true',
              'live_opening_complete': False, 'payment_api_requests': 0, 'real_transactions': 0,
              'merchant_webhook_registration_verified': False, 'commerce': {}}
    project = json.loads((ROOT / '.vercel/project.json').read_text())
    try:
        result = subprocess.run(['vercel', 'api', '/v10/projects/' + project['projectId'] + '/env?teamId=' + project['orgId'], '--raw'],
                                cwd=ROOT, capture_output=True, text=True, timeout=60)
        if result.returncode: raise RuntimeError('Environment metadata unavailable')
        metadata = json.loads(result.stdout)
        names = {entry['key'] for entry in metadata['envs'] if 'production' in entry.get('target', [])}
        report['production_env_declared'] = {key: key in names for key in KEYS}
        report['production_env_values_verified'] = False
    except Exception as error:
        report['production_env_metadata_error'] = type(error).__name__
    for host in ['https://shop.nadaun.co', 'https://order.nadaun.co']:
        response = requests.get(host + '/api/orders?action=config', timeout=30)
        response.raise_for_status(); report['commerce'][host] = response.json()
    response = requests.get('https://shop.nadaun.co/api/toss-webhook', timeout=30)
    report['webhook_get_http_status'] = response.status_code
    report['webhook_route_present'] = response.status_code == 405
    report['implementation'] = {
        'card_and_contracted_easy_pay': 'implemented_real_merchant_verification_pending',
        'account_transfer': 'implemented_real_merchant_verification_pending',
        'virtual_account': 'not_implemented_do_not_enable_without_deposit_expiry_refund_flow',
        'direct_bank_deposit': 'separate_manual_reconciliation_not_toss_automatic',
        'escrow': 'merchant_contract_and_delivery_confirmation_integration_pending',
        'refund_and_purchase_confirmation': 'mock_tests_passed_real_merchant_verification_pending',
    }
    out = STATE / 'preflight.json'
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n'); out.chmod(0o600)
    assert json.loads(out.read_text()) == report
    rows = [
        ('승인 결과·MID·계약 결제수단', '10월26일 승인 예상은 대표 전달. 실제 상점에서 승인·개통 수단 확인 필요'),
        ('우리 상점 테스트·운영 키', 'NAS 설정 '+str(sum(report['local_key_presence'].values()))+'/'+str(len(KEYS))+'개. 동일 상점의 API 개별연동 키·MID와 Vercel 운영 환경의 실제 값을 대조'),
        ('카드·계약된 간편결제·계좌이체', '결제창 구현됨. PC/모바일/앱 복귀, 주문금액·paymentKey·MID·승인 상태·영수증 실제 대조 필요'),
        ('기프트 주문 연결', 'shop 요청 → order 공급처·인쇄·납기·최종금액 확인 → 고객 확정견적 결제 → 양쪽 상태 대조'),
        ('전액·부분 환불', '금액·잔액·멱등성·응답유실·재조회 코드 검사 통과. 실제 상점의 승인·전액/부분 취소와 고객/관리자 금액 일치 확인 필요'),
        ('웹훅·주기 재조회', 'URL https://shop.nadaun.co/api/toss-webhook. 현재 경로 존재 여부와 상점 실제 이벤트 등록은 별도. PAYMENT_STATUS_CHANGED/CANCEL_STATUS_CHANGED 등록·전송 성공·중복 재전송 확인'),
        ('배송·구매확정', '배송 완료·본인 주문·취소/반품 진행 여부 검사. 실결제 후 출고/배송/구매확정 양쪽 상태와 증빙 확인 필요'),
        ('가상계좌·직접 무통장입금', '가상계좌는 발급·입금 대기·입금·만료·환불계좌 처리가 추가로 필요. 일반 직접 통장입금과 구분. 현재 구현 완료로 표시하지 않음'),
        ('에스크로', '계약, 배송 등록과 구매확정·부분 취소 조건을 별도 검증. 현재 자사 구매확정을 에스크로 완료로 표시하지 않음'),
        ('최종 개통', 'MID/키/계약수단, 웹훅, 수단별 실거래 결과와 취소·환불 종료, order 반영, 오류 대기함·영수증 확인 후 개통 영수증 작성'),
    ]
    tests = ''.join('<tr><th>' + escape(k) + '</th><td>' + escape(v) + '</td><td>대기</td></tr>' for k, v in rows)
    active = report['commerce']['https://shop.nadaun.co']['ordersEnabled']
    html = '''<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>토스 승인 후 개통 검토</title><style>body{font:16px/1.7 system-ui,sans-serif;max-width:1100px;margin:40px auto;padding:20px;background:#f8f8f5;color:#222}table{border-collapse:collapse;width:100%;background:white}td,th{padding:15px;border:1px solid #ddd;text-align:left;vertical-align:top}th{width:22%}a{color:#175da6}</style><a href="../00_여기서_시작.html">검토자료 첫 화면</a><h1>10월26일 토스 승인 후 개통 검토</h1><p>현재 확인: ''' + escape(report['checked_at']) + '''. 승인 예상일은 대표께서 전달하신 일정이며 실제 승인 확인은 대기입니다. 운영 결제 플래그: '''+str(active)+'''.</p><p>원본: TOSS-SETUP.md / 비공개 점검 결과: _private/commerce/toss-monday-20261026/preflight.json</p><table><thead><tr><th>항목</th><th>검토할 결과</th><th>실거래 확인</th></tr></thead><tbody>''' + tests + '''</tbody></table><p>공식 기준: <a href="https://docs.tosspayments.com/guides/v2/deploy-checklist">토스 배포 체크리스트</a> · <a href="https://docs.tosspayments.com/guides/v2/webhook">웹훅</a> · <a href="https://docs.tosspayments.com/guides/v2/cancel-payment">취소</a> · <a href="https://docs.tosspayments.com/guides/v2/escrow">에스크로</a></p></html>'''
    page = ROOT / '검토자료/08_주문결제검증/01_토스승인후_개통체크리스트.html'
    page.parent.mkdir(parents=True, exist_ok=True); page.write_text(html)
    print(json.dumps({key: report[key] for key in ['checked_at', 'local_key_presence', 'production_env_declared',
                                               'webhook_route_present', 'commerce', 'real_transactions'] if key in report}, ensure_ascii=False))


if __name__ == '__main__': main()
