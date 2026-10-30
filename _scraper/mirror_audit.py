"""Read-only evidence audit of every saved equipment source and own live catalog.

This never requests suppliers, publishes a candidate, clears a hold, or starts a
schedule. Receipt validity, live parity, freshness and automation are separate.
Run with --live to fetch our three public JSON endpoints; without it live state
is explicitly unverified. The command exits 2 when attention is required.
"""
from collections import Counter, defaultdict
from datetime import datetime, timezone
from html import escape
import argparse
import hashlib
import json
import os
from pathlib import Path
import plistlib
import subprocess
import sys

from sync_shop_sources import ROOT


def read(path, default=None):
    return json.loads(path.read_text()) if path.exists() else ({} if default is None else default)


def dated(value):
    try:
        result = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return result if result.tzinfo is not None else None
    except (AttributeError, ValueError):
        return None


def age_hours(value, now):
    when = dated(value)
    return round((now-when).total_seconds()/3600, 2) if when else None


def source_paths(root):
    from brand_source_policy import RETIRED_SOURCES
    result = {}
    for path in sorted((root/'data/catalog/sources').glob('*.json')):
        name = path.stem
        if name in RETIRED_SOURCES or name in ('nadaun-gift', 'avx-aputure', 'avx-approved'):
            continue
        result[name] = path
    approved = root/'data/catalog/sources/avx-approved.json'
    if approved.exists():
        result['avx'] = approved
    elif 'avx' not in result:
        fallback = root/'data/catalog/sources/avx-aputure.json'
        if fallback.exists():result['avx'] = fallback
    return result


def saved_source(source, snapshot, offers, expected, now, interval=43200):
    """Pure comparison; identical totals can never conceal different identities."""
    products = snapshot.get('products', {})
    ids = [o['id'] for o in offers]
    actual = set(ids)
    age = age_hours(snapshot.get('collected_at'), now)
    problems = []
    if snapshot.get('complete') is not True or type(snapshot.get('product_count')) is not int or snapshot.get('product_count') != len(products):
        problems.append('snapshot_incomplete_or_count_mismatch')
    if any(snapshot.get(k) for k in ('detail_errors', 'content_reviews', 'changed_categories')):
        problems.append('source_content_or_inventory_requires_review')
    if len(ids) != len(actual):problems.append('duplicate_live_offer_ids')
    missing = sorted(expected-actual)
    extra = sorted(actual-expected)
    if missing or extra:problems.append('source_to_live_identity_mismatch')
    if age is None or age < 0:problems.append('source_observation_time_unverified')
    elif age*3600 >= interval:problems.append('source_refresh_overdue')
    dates = [p.get('detail_checked_at') or p.get('observed_at') or p.get('verified_at') for p in products.values()]
    known_dates = [v for v in dates if dated(v)]
    return {'source': source, 'snapshot_products': len(products), 'source_collected_at': snapshot.get('collected_at'),
            'source_age_hours': age, 'refresh_interval_hours': interval/3600,
            'expected_public_offers': len(expected), 'live_offers': len(actual),
            'missing_offer_ids': missing, 'unexpected_offer_ids': extra,
            'policy_excluded_products': len(products)-len(expected),
            'oldest_detail_observed_at': min(known_dates, key=dated, default=None),
            'detail_observation_dates_missing': len(dates)-len(known_dates),
            'snapshot_complete': snapshot.get('complete') is True,
            'live_offer_ids_equal': not missing and not extra and len(ids)==len(actual),
            'issues': problems}


def scheduler_inventory(agents=None, runner=subprocess.run):
    """Observe actual registration; saved loaded=true is not runtime evidence."""
    agents = agents or Path.home()/'Library/LaunchAgents'
    result = {}
    for path in sorted(agents.glob('co.nadaun.shop.*.plist')):
        value = plistlib.loads(path.read_bytes()); label = value['Label']
        try:
            p = runner(['launchctl', 'print', 'gui/'+str(os.getuid())+'/'+label], capture_output=True, text=True, timeout=8)
            lines = [s.strip() for s in p.stdout.splitlines() if any(s.strip().startswith(k) for k in ('state =', 'runs =', 'last exit code ='))]
            result[label] = {'registered': p.returncode==0, 'status': lines,
                             'program_arguments': value.get('ProgramArguments', [])}
        except (OSError, subprocess.TimeoutExpired) as exc:
            result[label] = {'registered': None, 'error': type(exc).__name__}
    return result


def own_live(root, output):
    import requests
    result = {}
    for name, relative in [('catalog', 'data/catalog/catalog.json'), ('status', 'data/catalog/sync-status.json'), ('gift', 'data/gift/catalog.json')]:
        response = requests.get('https://shop.nadaun.co/'+relative, timeout=(10, 90))
        response.raise_for_status()
        payload = response.json()
        raw = response.content
        (output/('live-'+name+'.json')).write_bytes(raw)
        result[name] = {'sha256': hashlib.sha256(raw).hexdigest(), 'http_status': response.status_code,
                        'equal_to_nas': raw==(root/relative).read_bytes(), 'payload': payload}
    return result


def source_controls(root, source, config, schedules):
    state = root/'_scraper/.sync-state'
    folder = state/source
    error = read(folder/'worker-error.json') or read(state/(source+'-worker-error.json'))
    suspension = read(folder/'source-suspended.json')
    generation = read(folder/'generation.json')
    # A directory name in state is untrusted path input.
    directory = generation.get('directory')
    invalid_directory = bool(directory and (Path(directory).name!=directory or directory in ('.', '..')))
    if invalid_directory:directory=None
    progress = read(folder/'progress.json')
    gp = read(folder/directory/'progress.json') if directory else {}
    receipt = read(folder/'published.json')
    labels = (['co.nadaun.shop.catalog-sync'] if source in ('smartstore', 'kpp', 'l-mount') else
              ['co.nadaun.shop.reviewed-'+source+'-sync'] if source in ('digitalcp', 'sunphoto') else
              ['co.nadaun.shop.'+source+'-sync'])
    implemented = bool(config.get('adapter')) or source in ('smartstore', 'kpp', 'l-mount', 'hipixel')
    registered = all(schedules.get(k, {}).get('registered') is True for k in labels) if implemented else False
    suspended = bool(suspension) and suspension.get('suspended', True) is not False
    issues = []
    if suspended:issues.append('source_suspended')
    if error.get('requires_review') and not error.get('resolved'):issues.append('worker_review_latch')
    if invalid_directory:issues.append('invalid_generation_path')
    if not implemented:issues.append('automatic_refresh_not_implemented')
    elif not registered:issues.append('schedule_not_verified_registered')
    if not receipt:issues.append('source_publication_receipt_missing')
    # Source adoption and the latest generation must agree before resumption.
    gp_summary = {k: gp.get(k) for k in ('phase', 'complete', 'errors', 'content_held', 'details_verified', 'verified', 'total') if k in gp}
    return {'scheduler_labels': labels, 'scheduler_registered': registered, 'automatic_refresh_implemented': implemented,
            'source_suspended': suspended, 'source_suspension': suspension,
            'worker_error': error, 'generation': directory, 'generation_progress': gp_summary,
            'provider_phase': progress.get('phase'),
            'receipt_revision': receipt.get('revision'), 'receipt_verified_at': receipt.get('verified_at'),
            'receipt_source_sha256': receipt.get('source_sha256'), 'issues': issues}


def unavailable_exclusions(root, source, products, candidates):
    """Mirror the builder's cached-unavailable rule with its original guard."""
    if source not in ('kpp', 'smartstore'):return {}
    from enrich_shop_sources import shard, source_fingerprint
    buckets = {}
    result = {}
    for pid in sorted(candidates):
        bucket = shard(pid)
        if bucket not in buckets:buckets[bucket] = read(root/'data/catalog/source-details'/source/(bucket+'.json'))
        detail = buckets[bucket].get(pid, {})
        valid = (detail.get('source_fingerprint')==source_fingerprint(products[pid]) if source=='kpp' else
                 detail.get('source_modified_at')==products[pid].get('source_modified_at'))
        if valid and detail.get('detail_status')=='verified' and detail.get('unavailable') is True:
            result[pid] = {'checked_at': detail.get('checked_at'), 'basis': 'guarded_cached_source_unavailable',
                           'cache_bucket': bucket, 'current_source_rechecked': False}
    return result


def pending_runs(root, processes=None):
    """Find the latest private generation without treating saved text as a process."""
    if processes is None:
        observed=subprocess.run(['ps','-axo','pid=,command='],capture_output=True,text=True)
        processes={}
        if observed.returncode==0:
            for line in observed.stdout.splitlines():
                parts=line.strip().split(None,1)
                if len(parts)==2 and parts[0].isdigit():processes[int(parts[0])]=parts[1]
    result={}
    for folder in sorted((root/'_private/catalog').glob('mirror-*')):
        if not folder.is_dir():continue
        jobs={j.get('source'):j for j in read(folder/'START.json').get('jobs',[])}
        for path in folder.glob('*-run.json'):
            data=read(path);source=data.get('source') or path.name.removesuffix('-run.json').removesuffix('-detail')
            p=data.get('result',data)
            times=[dated(v) for v in (data.get('finished_at'),data.get('at'),data.get('started_at'),p.get('at'))]
            updated=max((v for v in times if v),default=datetime.min.replace(tzinfo=timezone.utc))
            pid=jobs.get(source,{}).get('pid');command=processes.get(pid,'')
            in_generation=any(str(value)+'/' in command for value in {folder,folder.resolve()})
            running=bool(command and in_generation and
                         ('collect-'+source+'.py' in command or command.endswith(' '+source)))
            row={'file':str(path),'state':data.get('state',p.get('phase')),
                 'product_count':data.get('product_count',p.get('total')),
                 'verified':p.get('verified'),'errors':p.get('errors'),
                 'finished_at':data.get('finished_at'),'updated_at':updated.isoformat(),
                 'published_flag_in_run':data.get('published'),
                 'historical_run_state_not_live_process':True,
                 'process_observed_running':running,'observed_pid':pid if running else None}
            progress=read(folder/(source+'-fresh')/'progress.json')
            if progress:
                row['collection_progress']={k:progress[k] for k in (
                    'at','checked_at','phase','products_found','details_verified',
                    'verified_details','brands_complete','brands_total',
                    'categories_verified','categories_found','complete') if k in progress}
            prior=result.get(source)
            if not prior or updated >= dated(prior['updated_at']):result[source]=row
    return result


def offer_comparison(root, source, snapshot, offers):
    """Compare public offers to stored source prices, stock and URLs.

    This follows guarded KPP detail prices and reviewed retail pricing; it does
    not turn a cached price or stock state into a fresh supplier observation.
    """
    from enrich_shop_sources import shard, source_fingerprint
    from reviewed_supplier_sources import markup_won
    buckets={};differences=[];checked=0
    for offer in offers:
        raw=snapshot.get('products',{}).get(offer['id'])
        if raw is None:continue
        price=raw.get('sale_price');status=raw.get('status')
        if source=='kpp':
            bucket=shard(offer['id'])
            if bucket not in buckets:buckets[bucket]=read(root/'data/catalog/source-details/kpp'/(bucket+'.json'))
            detail=buckets[bucket].get(offer['id'],{})
            if detail.get('detail_status')=='verified' and detail.get('source_fingerprint')==source_fingerprint(raw):
                price=detail.get('sale_price')
            status='soldout' if raw.get('supplier_status')=='soldout' else 'inquiry'
        elif source=='motion9':price=markup_won(price if price is not None else raw.get('price'))
        elif source=='funomad':price=None;status='inquiry'
        expected={'price':price,'status':status,'url':raw.get('source_url')}
        for field,value in expected.items():
            if offer.get(field)!=value:
                differences.append({'id':offer['id'],'field':field,'source_projection':value,'live':offer.get(field)})
        checked+=1
    return {'checked_offers':checked,'differences':differences,'source_freshness_proven':False}


def completion_issues(report, acceptance, root, now):
    """Only current, content-bound end-to-end evidence can complete the audit."""
    issues=[]
    if not report['live_catalog_equal']:issues.append('live_catalog_not_verified_equal')
    if report['catalog_errors']:issues.append('catalog_errors')
    if any(s['issues'] for s in report['sources']):issues.append('source_attention_items')
    gift=report['gift']
    if not (gift['all_current_details_verified'] and gift['full_source_inventory_verified'] and gift['live_equal_to_nas'] and gift['source_access']=='ready'):
        issues.append('gift_current_source_incomplete')
    expected={s['source']:s['source_sha256'] for s in report['sources']}
    required={'inventory','details','options_prices_stock','images_identity','legacy_links','browser'}
    proofs=acceptance.get('proofs',{})
    if acceptance.get('revision')!=report['revision'] or acceptance.get('source_sha256')!=expected or not required<=proofs.keys():
        issues.append('end_to_end_evidence_missing_or_stale')
    else:
        for scope in required:
            proof=proofs[scope]
            if not isinstance(proof,dict):
                issues.append('invalid_end_to_end_evidence:'+scope);continue
            relative=proof.get('path','');path=root/relative
            age=age_hours(proof.get('checked_at'),now)
            if not relative or not path.resolve().is_relative_to(root.resolve()) or age is None or not 0<=age<=12 or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=proof.get('sha256'):
                issues.append('invalid_end_to_end_evidence:'+scope)
    return sorted(set(issues))


def render(report):
    labels={'source_refresh_overdue':'원본 갱신 기한 경과','source_suspended':'접근 또는 승인 보류',
            'worker_review_latch':'수집 오류 검토 대기','schedule_not_verified_registered':'예약 중지·미등록',
            'automatic_refresh_not_implemented':'정기 갱신 미구현','source_publication_receipt_missing':'개별 게시 영수증 미확보',
            'source_receipt_not_bound_to_saved_snapshot':'영수증과 현재 저장본 연결 미확인','source_to_live_identity_mismatch':'상품번호 불일치',
            'live_not_checked':'운영 미조회','stored_offer_projection_mismatch':'원본 가격·상태·주소 불일치'}
    rows = []
    for s in report['sources']:
        rows.append('<tr>'+''.join('<td>'+escape(str(v))+'</td>' for v in [
            s['name'], s['snapshot_products'], s['expected_public_offers'], s['live_offers'],
            s['source_age_hours'], '일치' if s['live_offer_ids_equal'] else '확인 필요',
            '등록 확인' if s['controls']['scheduler_registered'] else '중지 또는 미등록',
            ', '.join(labels.get(i,i) for i in s['issues']) or '이번 저장본 검사 통과'])+'</tr>')
    return '''<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>전체 미러링 점검</title>
<style>body{font-family:system-ui,sans-serif;line-height:1.6;margin:32px;color:#202020}table{border-collapse:collapse;width:100%}th,td{border:1px solid #ddd;padding:10px;text-align:left}th{background:#243b36;color:white}.scroll{overflow:auto}code{overflow-wrap:anywhere}</style>
<a href="../00_여기서_시작.html">검토자료 첫 화면</a><h1>전체 미러링 점검</h1><p>확인 시각: '''+escape(report['checked_at'])+'''</p><p>현재 운영과 저장 원본의 일치, 원본 확인일, 예약 실행, 오류 보류를 각각 표시합니다. 이번 검사는 공급처 전체를 새로 수집하거나 자동 예약을 재개하지 않습니다.</p>
<p>전체 미러링 완료: <strong>'''+('확인됨' if report['full_mirroring_verified'] else '미완료')+'''</strong> · 운영 JSON과 NAS: '''+escape(str(report['live_catalog_equal']))+''' · 구조 검사: '''+escape(str(report['catalog_errors']))+'''</p>
<div class="scroll"><table><thead><tr><th>공급처</th><th>원본 상품</th><th>정책 적용 대상</th><th>공개 연결</th><th>원본 경과 시간</th><th>상품번호</th><th>예약</th><th>확인할 항목</th></tr></thead><tbody>'''+''.join(rows)+'''</tbody></table></div>
<h2>완료 판정 조건</h2><p>전체 원본 목록·상세·옵션·가격·재고·제조사·분류를 검증하고, 누락·중복·기존 주소를 대조한 뒤 백업·검사·게시·운영 일치까지 확인해야 합니다. 예약 등록이나 상품 수가 같다는 사실만으로 완료 처리하지 않습니다. 가격·사진·의미의 전수 최신 검수 여부는 별도입니다.</p><h2>기프트</h2><pre>'''+escape(json.dumps(report['gift'],ensure_ascii=False,indent=2))+'''</pre><p>세부 근거: NAS <code>'''+escape(report['evidence_path'])+'''</code></p></html>'''


def run(root=ROOT, output=None, live=False, schedules=None):
    from brand_source_policy import publishable_ids, NAMES
    from build_catalog import brand_id
    root = Path(root).resolve()
    now = datetime.now(timezone.utc)
    output = Path(output) if output else root/'_private/catalog/mirror-audit-runs'/now.strftime('%Y%m%dT%H%M%S%fZ')
    output=(root/output).resolve() if not output.is_absolute() else output.resolve()
    if not output.is_relative_to(root):raise ValueError('Audit output must stay inside the NAS project')
    output.mkdir(parents=True, exist_ok=True)
    local = read(root/'data/catalog/catalog.json')
    fetched = own_live(root, output) if live else {}
    catalog = fetched['catalog']['payload'] if live else local
    plans = read(root/'_scraper/partner-sync-plan.json')['sources']
    paths = source_paths(root)
    schedules = scheduler_inventory() if schedules is None else schedules
    grouped = defaultdict(list)
    errors = []
    pids = [p['id'] for p in catalog['products']]
    if len(pids)!=len(set(pids)):errors.append('duplicate_product_ids')
    category_ids = {c['id'] for c in catalog['categories']}
    for product in catalog['products']:
        if set(product.get('category_ids', []))-category_ids:errors.append('missing_category:'+product['id'])
        if not product.get('image'):errors.append('missing_main_image:'+product['id'])
        for offer in product['offers']:grouped[offer['source']].append(offer)
    sources = []
    runs=pending_runs(root)
    for source in sorted(set(paths)|set(plans)|set(catalog['meta'].get('source_counts', {}))|set(runs)):
        config = plans.get(source, {})
        path = paths.get(source)
        snapshot = read(path) if path else {'source': source}
        issues = []
        try:
            expected = publishable_ids(snapshot) if snapshot.get('products') else set()
            # These two builder exclusions precede merge/card deduplication.
            expected = {pid for pid in expected if not (
                source=='dji-official' and brand_id(snapshot['products'][pid]['brand'])!='dji' or
                source not in ('avx', 'dji-official') and 'avx' in paths and snapshot['products'][pid].get('kind')=='purchase' and brand_id(snapshot['products'][pid]['brand'])=='aputure')}
        except (ValueError, KeyError, TypeError) as exc:
            expected = set();issues.append('policy_identity_review:'+type(exc).__name__)
        policy_count=len(expected)
        unavailable=unavailable_exclusions(root,source,snapshot.get('products',{}),expected-{o['id'] for o in grouped[source]})
        expected-=unavailable.keys()
        row = saved_source(source, snapshot, grouped[source], expected, now, config.get('refresh_interval_seconds', 43200))
        row['policy_excluded_products']=len(snapshot.get('products',{}))-policy_count
        row['guarded_unavailable_exclusions']=unavailable
        row['last_private_run']=runs.get(source)
        row['stored_offer_projection']=offer_comparison(root,source,snapshot,grouped[source])
        if row['stored_offer_projection']['differences']:row['issues'].append('stored_offer_projection_mismatch')
        controls = source_controls(root, source, config, schedules)
        row.update(name=config.get('name', NAMES.get(source, '그린촬영 / NiSi' if source=='greenshop' else source)), snapshot_file=str(path) if path else None,
                   source_sha256=hashlib.sha256(path.read_bytes()).hexdigest() if path else None, controls=controls)
        row['receipt_matches_saved_source'] = bool(path and controls['receipt_source_sha256']==row['source_sha256'])
        row['issues'] += issues+controls.pop('issues')
        if not row['receipt_matches_saved_source']:row['issues'].append('source_receipt_not_bound_to_saved_snapshot')
        if not live:row['issues'].append('live_not_checked')
        row['issues'] = sorted(set(row['issues']))
        sources.append(row)
        print(source, row['snapshot_products'], row['live_offers'], ','.join(row['issues']), flush=True)
    gift = read(root/'data/gift/catalog.json').get('meta', {})
    gift_health = read(root/'_private/gift/daily-sync/health.json')
    gift_access = read(root/'_private/gift/daily-sync/source-access.json')
    gift_result = {'products': gift.get('product_count'), 'source_access': gift_access.get('state', 'unverified'),
                   'health_checked_at': gift_health.get('checked_at'), 'health_attention': gift_health.get('attention', []),
                   'all_current_details_verified': gift.get('all_current_details_verified') is True,
                   'full_source_inventory_verified': gift.get('mirror', {}).get('full_source_inventory_verified') is True,
                   'live_equal_to_nas': fetched.get('gift', {}).get('equal_to_nas')}
    live_equal = fetched.get('catalog', {}).get('equal_to_nas')
    if live and not all(v['equal_to_nas'] for v in fetched.values()):errors.append('live_and_nas_differ')
    report = {'schema_version': 1, 'checked_at': now.isoformat(), 'host': __import__('socket').gethostname(),
              'evidence_path':str((output/'audit.json').relative_to(root)),
              'revision': catalog['meta']['revision'], 'products': len(pids), 'source_requests': 0,
              'supplier_full_recrawl_performed': False, 'automatic_schedules_changed': False,
              'live_catalog_equal': live_equal, 'live_verified': bool(live_equal),
              'live_endpoints': {k:{f:v[f] for f in ('sha256','http_status','equal_to_nas')} for k,v in fetched.items()},
              'catalog_errors': sorted(set(errors)), 'sources': sources, 'schedulers': schedules, 'gift': gift_result,
              'remaining_semantic_checks': ['all supplier freshness and pending publications', 'per-option price/stock current-source verification', 'all detail images and compatibility meaning review']}
    report['completion_issues']=completion_issues(report,read(root/'_private/catalog/mirror-acceptance.json'),root,now)
    report['full_mirroring_verified']=not report['completion_issues']
    if report['full_mirroring_verified']:report['remaining_semantic_checks']=[]
    # Never derive complete from structural parity while source/semantic checks remain.
    (output/'audit.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    page = root/'검토자료/12_전체미러링점검/00_전체미러링_현재상태.html'
    page.parent.mkdir(parents=True, exist_ok=True);page.write_text(render(report))
    assert read(output/'audit.json')==report
    pointer={'checked_at':report['checked_at'],'revision':report['revision'],'full_mirroring_verified':report['full_mirroring_verified'],
             'evidence_path':report['evidence_path'],'sha256':hashlib.sha256((output/'audit.json').read_bytes()).hexdigest()}
    latest=root/'_private/catalog/mirror-audit-latest.json'
    latest.write_text(json.dumps(pointer,ensure_ascii=False,indent=2)+'\n');assert read(latest)==pointer
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live', action='store_true')
    parser.add_argument('--output', type=Path)
    args=parser.parse_args()
    result=run(output=args.output, live=args.live)
    print(json.dumps({'revision':result['revision'], 'full_mirroring_verified':result['full_mirroring_verified'],
                      'sources':len(result['sources']), 'catalog_errors':result['catalog_errors']},ensure_ascii=False))
    sys.exit(0 if result['full_mirroring_verified'] else 2)
