"""Mac five-day supplier queue and always-updated NAS review dashboard."""
from pathlib import Path
from contextlib import contextmanager
from datetime import datetime,timezone
from collections import Counter,defaultdict
import argparse,hashlib,html,json,os,socket,subprocess,sys,time
from mirror_schedule import ROOT,atomic_json,controls,freshness,policy,read,source_path,timestamp

COMMANDS={'plthink':['partner_worker','plthink'],'avx':['avx_worker'],'dji-official':['dji_worker'],
    'saeki':['saeki_worker'],'digitalcp':['reviewed_source_worker','digitalcp'],
    'sunphoto':['reviewed_source_worker','sunphoto'],'motion9':['manual_source_worker','motion9'],
    'funomad':['manual_source_worker','funomad']}
for _source in ('clmedia','hipixel','ldnet','onnoff','cinemall'):COMMANDS[_source]=['cafe24_worker',_source]
BASE_SOURCES={'smartstore','kpp','l-mount'}

def adapter_implemented(source,root=ROOT):
    command=COMMANDS.get(source) or (['shop_sync'] if source in BASE_SOURCES else None)
    return bool(command and (Path(root)/'_scraper'/(command[0]+'.py')).is_file())

def existing_collectors(root=ROOT):
    """Do not overlap already-running maintenance collectors on this Mac."""
    result=subprocess.run(['ps','-axo','pid=,command='],capture_output=True,text=True,check=True)
    found=[];root=str(Path(root).resolve())+'/'
    for line in result.stdout.splitlines():
        bits=line.strip().split(None,1)
        if len(bits)!=2 or not bits[0].isdigit():continue
        command=bits[1]
        if root in command and ('/collect-pending.py ' in command or '/collect-saeki.py' in command or '/capture-greenshop-details.py ' in command or '/_scraper/full_refresh.py' in command or '-m full_refresh --worker ' in command):
            found.append({'host':socket.gethostname(),'pid':int(bits[0]),'script':command.split(root,1)[1]})
    return found

def now():return datetime.now(timezone.utc).isoformat()

@contextmanager
def cycle_lock(root):
    path=Path(root)/'_scraper/.sync-state/mirror-cycle.lock';path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists():
        owner=read(path)
        if owner.get('host')!=socket.gethostname():raise BlockingIOError('Mirror cycle is owned by another computer')
        if owner.get('worker_pid'):
            try:os.kill(int(owner['worker_pid']),0)
            except ProcessLookupError:pass
            else:raise BlockingIOError('The previous mirror child is still active')
        try:os.kill(int(owner['pid']),0)
        except ProcessLookupError:
            atomic_json(path.with_name('mirror-cycle-recovered-lock.json'),{'at':now(),'previous':owner});path.unlink()
        else:raise BlockingIOError('Mac mirror cycle is already active')
    token=os.urandom(16).hex();fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    with os.fdopen(fd,'w') as handle:json.dump({'host':socket.gethostname(),'pid':os.getpid(),'token':token,'started_at':now()},handle)
    try:yield
    finally:
        if path.exists() and read(path).get('token')==token:path.unlink()

def report(root=ROOT):
    root=Path(root).resolve();settings=policy(root);plan=read(root/'_scraper/partner-sync-plan.json')['sources']
    catalog=read(root/'data/catalog/catalog.json');offers=Counter(o['source'] for p in catalog.get('products',[]) for o in p.get('offers',[]))
    directory=root/'_private/catalog/auto-mirror';attempts=read(directory/'attempts.json');runtime=root.with_name(root.name+'-auto')
    immediate=read(root/'_private/catalog/immediate-full-refresh-20261030/queue.json')
    rows=[]
    for source,config in plan.items():
        path=source_path(source,root);snapshot=read(path);f=freshness(snapshot,source,root);hold=controls(source,root)
        automatic_hold=controls(source,runtime) if runtime.is_dir() else {}
        if not hold.get('blocked') and automatic_hold.get('blocked'):hold=automatic_hold
        command=COMMANDS.get(source) or (['shop_sync'] if source in BASE_SOURCES else None)
        prior=attempts.get(source,{})
        implemented=adapter_implemented(source,root)
        phase=hold.get('phase') if hold.get('blocked') else 'adapter_required' if not implemented else 'due' if f['due'] else 'current_saved_snapshot'
        row={'source':source,'name':config['name'],'url':config['url'],**f,'phase':phase,'snapshot_products':snapshot.get('product_count',0),
             'published_offers':offers[source],'last_attempt':prior,'reason':hold.get('reason',''),'automatic_adapter_implemented':implemented,
             'source_sha256':hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None}
        if not implemented:row['reason']='현재 범위에 맞는 수집·매칭 어댑터 검증 필요'
        latest=immediate.get('sources',{}).get(source,{})
        row['immediate_refresh']=latest
        if latest.get('phase')=='collecting' and not hold.get('blocked'):row.update(phase='collecting_private',reason='대표 요청으로 지금 전체 원본 재수집 중 · 게시 전 검증 단계')
        elif latest.get('complete'):row['reason']='최신 비공개 원본 '+str(latest.get('products'))+'개 확보 · 상품 매칭/게시/운영 검증 대기'
        rows.append(row)
    gift=read(root/'_private/gift/daily-sync/source-access.json');installation=read(directory/'installation.json')
    return {'schema_version':1,'checked_at':now(),'host':socket.gethostname(),'existing_collectors':existing_collectors(root),'revision':catalog.get('meta',{}).get('revision'),
        'product_records':len(catalog.get('products',[])),'brands':len(catalog.get('brands',[])),'categories':len(catalog.get('categories',[])),
        'refresh_interval_seconds':settings['refresh_interval_seconds'],'poll_interval_seconds':settings['poll_interval_seconds'],
        'sources':rows,'installation':installation,'immediate_refresh':immediate,'full_mirroring_verified':False,'own_site_http_verified_this_check':False,
        'gift':{'state':gift.get('state','unverified'),'cadence':'Existing daily worker preserved; access protection remains separate'},
        'windows_rental_runtime_changed':False,'review_rule':'모든 갱신 시도 후 상태 HTML, 실제 게시 후 전체 제품·분류·중복 검토 HTML 갱신',
        'unconfirmed_main_sources':'대표 검토 대기; 기존 지정과 가격·제외 정책 유지'}

def render(root,value):
    root=Path(root).resolve();folder=root/'검토자료/14_자동미러링';folder.mkdir(parents=True,exist_ok=True)
    labels={'source_suspended':'원본 접근·대표 검토 보류','error_requires_review':'오류 검토 필요','adapter_required':'수집·매칭 구현 확인 필요','due':'갱신 기한 도래','current_saved_snapshot':'저장 원본 주기 내','collecting':'수집·검증 중','collecting_private':'지금 전체 원본 수집 중','published_review_pending':'게시 완료 · 검수 HTML 확인 필요'}
    rows=[]
    for item in value['sources']:
        attempt=item.get('last_attempt',{});age=item.get('age_seconds');due=item.get('next_due_at') or '미확인'
        state='수집·검증 중' if value.get('active_source')==item['source'] else labels.get(item['phase'],item['phase'])
        details=item.get('reason') or attempt.get('error') or attempt.get('phase','')
        values=[item['name'],str(item['snapshot_products']),str(item['published_offers']),state,item.get('source_collected_at') or '미확인',f'{age/86400:.2f}일' if age is not None else '미확인',due,attempt.get('finished_at') or attempt.get('started_at') or '',details]
        rows.append('<tr>'+''.join('<td>'+html.escape(str(x))+'</td>' for x in values)+'</tr>')
    page='''<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>나다운 사이트별 자동 미러링</title><style>body{margin:0;background:#f5f6f3;color:#202a25;font:15px/1.7 Pretendard,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}header,main{padding:25px;max-width:1700px;margin:auto}header{background:white}h1{font-size:28px}a{color:#17635c}.notice{padding:15px;background:#fff4d7;border:1px solid #dfcfa8}.scroll{overflow:auto}table{border-collapse:collapse;width:100%;background:white;font-size:13px}th,td{padding:10px;border:1px solid #d9dfd6;text-align:left;vertical-align:top}th{background:#24473c;color:white}td:nth-child(5),td:nth-child(7),td:nth-child(8){min-width:160px}td:last-child{min-width:240px}code{overflow-wrap:anywhere}nav{display:flex;gap:16px;flex-wrap:wrap}</style><header><nav><a href="../00_여기서_시작.html">전체 제품·브랜드 검토</a><a href="../11_중복상품과공급처선택/00_겹치는상품_공급처비교.html">메인·중복 원본 선택</a><a href="../13_공급처배너/00_전체배너_검토.html">공급처 배너 원본</a></nav><h1>사이트별 자동 미러링 · 5일 주기</h1><p>CHECK · revision REV · PRODUCTS상품 / BRANDS브랜드 / CATEGORIES분류</p></header><main><p class="notice">원본 확인일로부터 5일이 되면 갱신 대상으로 잡고, 맥이 켜져 있고 NAS가 연결돼 있을 때 순차 처리합니다. 15분마다 대기열을 확인하며, 보류·보호 응답·부분 수집은 기존 상품을 삭제하지 않습니다. 갱신 시도와 전체 최신 검증 완료를 구분합니다. 전체 원본 미러링 완료 판정은 현재 미완료입니다. 윈도우의 렌탈 자동화는 별개로 유지합니다.</p><p>실행 상태: <b>STATE</b> · 수집 중: ACTIVE</p><div class="scroll"><table><thead><tr><th>사이트</th><th>저장 원본 상품</th><th>공개 연결</th><th>현재 상태</th><th>원본 수집 시각</th><th>경과</th><th>다음 갱신 기한</th><th>마지막 실행</th><th>검토·오류</th></tr></thead><tbody>ROWS</tbody></table></div><p>메인 상품·브랜드의 미확정 항목은 대표 검토 대기입니다. HTML의 선택·메모를 자동으로 공급처 정책 변경이나 판매 승인으로 처리하지 않습니다.</p><p>기프트: GIFT. 기존 일일 예약은 유지하며 최신 원본 접근·전체 상세·수량 단가 확인 상태는 별도입니다.</p><p>매번 업데이트할 때 제품 확인·정리검수 HTML을 갱신합니다. 페이지를 다시 열면 최신 저장 결과를 볼 수 있습니다.</p></main></html>'''
    state_labels={'immediate_full_refresh_in_progress':'대표 요청 · 전체 원본 지금 재수집 중 (5일 주기와 별도)',
        'waiting_for_existing_source_collectors':'기존 원본 수집 '+str(len(value.get('existing_collectors',[])))+'개 진행 중 · 새 대기열은 완료 후 처리',
        'checked_scheduler_enabled':'Mac 예약 켜짐 · 사이트별 상태 확인 완료','checked_activation_pending':'사이트별 상태 확인 완료 · 예약 등록 전',
        'waiting_for_due_source_or_review':'다음 갱신 기한 또는 보류 항목 검토 대기','collecting_validating_and_publishing':'원본 수집·검증·게시 처리 중',
        'runtime_preflight_requires_review':'실행 폴더 또는 편집 충돌 검토 필요','published_verified':'원본 게시·검토 HTML 갱신 확인',
        'published_review_pending':'원본 게시 확인 · 검토 HTML 갱신 확인 필요','not_verified_requires_review':'갱신 검증 미완료 · 저장 로그 검토 필요'}
    for key,text in {'CHECK':value['checked_at'],'REV':value.get('revision'),'PRODUCTS':value['product_records'],'BRANDS':value['brands'],'CATEGORIES':value['categories'],'STATE':state_labels.get(value.get('state'),value.get('state','확인 중')),'ACTIVE':value.get('active_source') or '없음','GIFT':value['gift']['state']}.items():page=page.replace(key,html.escape(str(text)))
    page=page.replace('ROWS',''.join(rows));target=folder/'00_사이트별_자동미러링.html';temporary=target.with_name('.'+target.name+'.pending');temporary.write_text(page);os.replace(temporary,target)
    atomic_json(folder/'자동미러링_현재상태.json',value);atomic_json(root/'_private/catalog/auto-mirror/current.json',value)
    return target

def check(root=ROOT,state='checked',active=None):
    value=report(root);value.update(state=state,active_source=active);render(root,value);return value

def run_once(root=ROOT,check_only=False):
    root=Path(root).resolve();directory=root/'_private/catalog/auto-mirror';directory.mkdir(parents=True,exist_ok=True)
    with cycle_lock(root):
        current=check(root,state='checking_all_sites')
        enabled=read(directory/'control.json').get('enabled') is True
        if check_only or not enabled:
            current['state']='checked_scheduler_enabled' if enabled else 'checked_activation_pending';render(root,current);return current
        if current['existing_collectors']:
            current['state']='waiting_for_existing_source_collectors';render(root,current);return current
        if policy(root).get('collect_supplier_banners_on_refresh'):
            from supplier_banners import collect
            # Per-site timestamps are independent from product freshness.
            collect(root)
        retry=policy(root)['retry_interval_seconds'];attempts=read(directory/'attempts.json');clock=time.time()
        ready=[]
        for row in current['sources']:
            if row['phase']!='due' or not row['automatic_adapter_implemented']:continue
            previous=attempts.get(row['source'],{});last=timestamp(previous.get('finished_at'))
            if last is not None and clock-last<retry:continue
            ready.append(row)
        if not ready:
            current['state']='waiting_for_due_source_or_review';render(root,current);return current
        selected=max(ready,key=lambda row:row.get('age_seconds') if row.get('age_seconds') is not None else 10**12)
        source=selected['source'];affected=BASE_SOURCES if source in BASE_SOURCES else {source}
        from mirror_runtime import ensure
        try:runtime=ensure(root)
        except Exception as exc:
            error={'finished_at':now(),'phase':'runtime_preflight_requires_review','error':type(exc).__name__+': '+str(exc)}
            for item in affected:attempts[item]=error
            atomic_json(directory/'attempts.json',attempts);return check(root,state='runtime_preflight_requires_review')
        command=['shop_sync'] if source in BASE_SOURCES else COMMANDS[source]
        folder=directory/'runs'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ');folder.mkdir(parents=True)
        attempt={'started_at':now(),'source':source,'phase':'collecting','runtime':str(runtime),'log':str((folder/'worker.log').relative_to(root)),
            'before_source_sha256':{s:hashlib.sha256(source_path(s,root).read_bytes()).hexdigest() for s in affected if source_path(s,root).is_file()}}
        for item in affected:attempts[item]=attempt
        atomic_json(directory/'attempts.json',attempts);check(root,state='collecting_validating_and_publishing',active=source)
        env=dict(os.environ,NADAUN_SHOP_MASTER_ROOT=str(root),PYTHONUNBUFFERED='1')
        temporary=runtime/'_private/test-tmp';temporary.mkdir(parents=True,exist_ok=True);env['TMPDIR']=str(temporary)
        with (folder/'worker.log').open('w',buffering=1) as log:
            child=subprocess.Popen([sys.executable,'-u','-m',*command],cwd=runtime/'_scraper',env=env,stdout=log,stderr=subprocess.STDOUT)
            lease=root/'_scraper/.sync-state/mirror-cycle.lock';owner=read(lease);owner['worker_pid']=child.pid;atomic_json(lease,owner)
            while child.poll() is None:
                atomic_json(directory/'heartbeat.json',{'at':now(),'source':source,'supervisor_pid':os.getpid(),'worker_pid':child.pid,'log':attempt['log']})
                time.sleep(30)
                check(root,state='collecting_validating_and_publishing',active=source)
        release=read(root/'_scraper/.sync-state/last-success.json');after={s:read(source_path(s,root)) for s in affected}
        observed=timestamp(attempt['started_at']);fresh=all(timestamp(s.get('collected_at')) is not None and timestamp(s['collected_at'])>=observed and s.get('complete') for s in after.values())
        live=timestamp(release.get('verified_at'));verified=child.returncode==0 and fresh and live is not None and live>=observed
        attempt.update(finished_at=now(),exit_code=child.returncode,source_refresh_verified=verified,
            phase='published_verified' if verified and release.get('review_html_updated') else 'published_review_pending' if verified else 'not_verified_requires_review')
        if child.returncode:attempt['error']='Worker failed; see saved log. Previous verified source/publication remains authoritative.'
        if verified:attempt.update(commit=release['commit'],revision=release['revision'],review_html_updated=release.get('review_html_updated',False))
        atomic_json(folder/'result.json',attempt)
        for item in affected:attempts[item]=attempt
        atomic_json(directory/'attempts.json',attempts)
        # The status page is refreshed for success, failure and review holds.
        return check(root,state=attempt['phase'])

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--check-only',action='store_true');args=parser.parse_args()
    try:value=run_once(check_only=args.check_only);print(json.dumps({'state':value['state'],'checked_at':value['checked_at'],'sites':len(value['sources'])},ensure_ascii=False),flush=True)
    except BlockingIOError as exc:print(str(exc),flush=True)
