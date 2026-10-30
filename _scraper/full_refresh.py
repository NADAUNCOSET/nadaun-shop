"""Owner-requested immediate supplier collection, separate from the five-day timer.

Uses existing source collectors in a clean NAS worktree. Candidates, detailed
errors and source times are private. This never calls our public shop, publishes
an incomplete catalogue, changes orders, or treats collection as publication.
"""
from pathlib import Path
from datetime import datetime,timezone
from urllib.parse import urlsplit
from contextlib import contextmanager
import argparse,hashlib,json,os,socket,subprocess,sys,threading,time
from mirror_schedule import ROOT,atomic_json,read,controls,timestamp,source_path
from mirror_runtime import master_for,ensure,head

ORDER=['hipixel','motion9','l-mount','onnoff','dji-official','funomad','clmedia','digitalcp','sunphoto','smartstore','kpp']
BLOCKED_OWN_HOSTS={'shop.nadaun.co','order.nadaun.co','nadaun-gift.com','www.nadaun-gift.com','joagift.co.kr','www.joagift.co.kr'}
def now():return datetime.now(timezone.utc).isoformat()
def master():return master_for(ROOT) or ROOT
def directory():return master()/'_private/catalog/immediate-full-refresh-20261030'

def validate_private_candidate(value,source):
    products=value.get('products',{})
    if value.get('source')!=source or value.get('complete') is not True or not products or value.get('product_count')!=len(products):
        raise ValueError('Private inventory/detail verification is incomplete')
    if any(value.get(k) for k in ('detail_errors','errors','unverified_details')):raise ValueError('Source detail errors require review')
    if timestamp(value.get('collected_at')) is None:raise ValueError('Source observation time is unverified')
    if any(pid!=p.get('id') or p.get('source')!=source for pid,p in products.items()):raise ValueError('Source identities differ')
    return value

def source_delta(previous,current):
    before=previous.get('products',{});after=current['products'];changed=[]
    fields=('name','brand','price','sale_price','status','supplier_status','source_url','brand_category_ids','options','option_groups','options_require_confirmation','images','description_text')
    for pid in sorted(set(before)&set(after)):
        diff=[key for key in fields if before[pid].get(key)!=after[pid].get(key)]
        if diff:changed.append({'id':pid,'name':after[pid].get('name'),'fields':diff})
    return {'compared_at':now(),'source':current['source'],'source_collected_at':current['collected_at'],'basis':'private raw source; retail pricing/dedup/current deployment require separate verification',
        'previous_products':len(before),'current_products':len(after),'added':sorted(set(after)-set(before)),
        'absent_from_new_inventory':sorted(set(before)-set(after)),'changed':changed,'automatic_removal_approved':False,'published':False}

@contextmanager
def request_guard(source,work):
    """Single in-flight request per host and persistent access-protection holds."""
    import requests
    original=requests.sessions.Session.request;gate=threading.Lock();last={};stopped=threading.Event()
    def guarded(session,method,url,**kwargs):
        host=urlsplit(url).hostname
        if host in BLOCKED_OWN_HOSTS:raise RuntimeError('Own/gift site access is outside this supplier collection')
        with gate:
            if stopped.is_set() or controls(source,master()).get('blocked'):raise RuntimeError('Source hold prevents further requests')
            pause=.6 if host=='api.commerce.naver.com' else 5
            time.sleep(max(0,pause-(time.monotonic()-last.get(host,0))))
            # Redirects cannot silently route a supplier request to a blocked own site.
            kwargs['allow_redirects']=False
            response=original(session,method,url,**kwargs);last[host]=time.monotonic()
            if response.status_code in (401,403,429):
                stopped.set();hold={'at':now(),'suspended':True,'url':url,'http_status':response.status_code,'reason':'provider_access_protection','automatic_resume':False}
                atomic_json(work/'source-suspended.json',hold);atomic_json(master()/'_scraper/.sync-state'/source/'source-suspended.json',hold)
            return response
    requests.sessions.Session.request=guarded
    try:yield
    finally:requests.sessions.Session.request=original

def collect_source(source,work):
    work=Path(work).resolve();work.mkdir(parents=True,exist_ok=True)
    if controls(source,master()).get('blocked'):raise RuntimeError('Existing source hold preserved')
    with request_guard(source,work):
        if source in ('hipixel','clmedia','onnoff'):
            from sync_cafe24_partners import Collector
            from cafe24_publication import prepare
            collector=Collector(source,work)
            try:raw=collector.collect()
            finally:
                try:collector.checkpoint_snapshot(force=True)
                finally:collector.db.close()
            value=prepare(raw)
        elif source=='dji-official':
            from sync_dji_official import collect
            value=collect(work)
        elif source in ('digitalcp','sunphoto'):
            from reviewed_source_worker import normalize
            module=__import__('sync_'+source+'_catalog');value=normalize(module.collect(work))
        elif source=='l-mount':
            from sync_ldl_catalog import collect
            value=collect(work)
        elif source in ('motion9','funomad'):
            from manual_source_worker import Client,collect_motion9,collect_funomad
            previous=read(ROOT/'data/catalog/sources'/(source+'.json'));client=Client(source,work)
            value=(collect_motion9 if source=='motion9' else collect_funomad)(client,previous)
        elif source in ('smartstore','kpp'):
            # Redirect only collector outputs and detail cache into this private generation.
            import sync_shop_sources as base,enrich_shop_sources as detail
            out=work/'source-output';out.mkdir(exist_ok=True);base.OUT=out;detail.OUT=out;detail.CACHE=work/'detail-cache'
            if source=='smartstore':base.collect_smartstore()
            else:
                import sync_kpp_catalog as kpp
                kpp.OUT=out;kpp.collect()
            detail.collect(source,force=True);value=read(out/(source+'.json'))
            atomic_json(work/'enrichment.json',{'at':now(),'source':source,'all_details_verified':True,'cache':str(detail.CACHE),'source_observation_preserved':True})
        else:raise ValueError('Unsupported private collector: '+source)
    validate_private_candidate(value,source);target=work/'normalized-candidate.json';atomic_json(target,value)
    delta=source_delta(read(source_path(source,ROOT)),value);atomic_json(work/'source-delta.json',delta)
    result={'at':now(),'source':source,'phase':'collected_pending_publication_review','complete':True,'source_collected_at':value['collected_at'],
        'products':len(value['products']),'categories':len(value.get('categories',[])),'candidate':str(target),
        'source_sha256':hashlib.sha256(target.read_bytes()).hexdigest(),'delta':{'added':len(delta['added']),'absent_requires_review':len(delta['absent_from_new_inventory']),'changed':len(delta['changed'])},'published':False,'own_site_requests':0}
    atomic_json(work/'collection-receipt.json',result);return result

def run():
    root=master();folder=directory();folder.mkdir(parents=True,exist_ok=True)
    lock=folder/'controller.lock'
    if lock.exists():
        owner=read(lock)
        if owner.get('host')!=socket.gethostname():raise RuntimeError('Immediate refresh owned by another computer')
        if owner.get('worker_pid'):
            try:os.kill(int(owner['worker_pid']),0)
            except ProcessLookupError:pass
            else:raise RuntimeError('Previous immediate-refresh child is still active')
        try:os.kill(int(owner['pid']),0)
        except ProcessLookupError:atomic_json(folder/'recovered-controller-lock.json',owner);lock.unlink()
        else:raise RuntimeError('Immediate refresh is already active')
    fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    with os.fdopen(fd,'w')as f:json.dump({'host':socket.gethostname(),'pid':os.getpid(),'at':now()},f)
    state={'requested_at':read(folder/'REQUESTS.json').get('requested_at'),'started_at':now(),'phase':'preparing_clean_runtime','sources':{},'full_mirroring_verified':False,'publication_enabled':False}
    def report():
        state['updated_at']=now();atomic_json(folder/'queue.json',state)
        from mirror_cycle import check
        check(root,state='immediate_full_refresh_in_progress',active=state.get('active_source'))
    child=None
    try:
        report();runtime=ensure(root);state['runtime_commit']=head(runtime)
        from mirror_cycle import existing_collectors
        active=existing_collectors(root)
        for item in active:
            script=item['script']
            source=script.rsplit(' ',1)[-1] if 'collect-pending.py 'in script else 'saeki' if 'collect-saeki.py'in script else 'greenshop' if 'capture-greenshop-details.py'in script else None
            if source:state['sources'][source]={'phase':'existing_collection_running','pid':item['pid'],'published':False}
        for source in ORDER:
            work=folder/'sources'/source
            saved=read(work/'collection-receipt.json')
            if saved.get('complete'):
                state['sources'][source]=saved;report();continue
            hold=controls(source,root)
            if hold.get('blocked'):
                state['sources'][source]={'phase':hold['phase'],'reason':hold.get('reason'),'published':False};report();continue
            state.update(phase='collecting_private_candidates',active_source=source);state['sources'][source]={'phase':'collecting','started_at':now(),'published':False};report()
            work.mkdir(parents=True,exist_ok=True)
            env=dict(os.environ,NADAUN_SHOP_MASTER_ROOT=str(root),PYTHONUNBUFFERED='1');temp=runtime/'_private/test-tmp';temp.mkdir(parents=True,exist_ok=True);env['TMPDIR']=str(temp)
            with (work/'worker.log').open('a',buffering=1)as log:
                child=subprocess.Popen([sys.executable,'-u','-m','full_refresh','--worker',source,'--work',str(work)],cwd=runtime/'_scraper',env=env,stdout=log,stderr=subprocess.STDOUT)
                owner=read(lock);owner['worker_pid']=child.pid;atomic_json(lock,owner)
                state['sources'][source]['pid']=child.pid
                while child.poll()is None:report();time.sleep(30)
            state['sources'][source]=read(work/'collection-receipt.json')or{'phase':'requires_review','exit_code':child.returncode,'log':str(work/'worker.log'),'published':False}
            report()
        for source in ('cinemall','gauphoto','greenshop'):
            hold=controls(source,root);state['sources'][source]={'phase':hold.get('phase','scoped_adapter_pending'),'reason':hold.get('reason','Initial scope matching remains pending'),'published':False}
        state.update(phase='collection_pass_finished_review_and_publication_pending',active_source=None);report()
    finally:
        # A surviving child keeps its lease; a new controller must not duplicate it.
        if child is None or child.poll()is not None:lock.unlink(missing_ok=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--worker',choices=ORDER);parser.add_argument('--work',type=Path);args=parser.parse_args()
    if args.worker:
        try:print(json.dumps(collect_source(args.worker,args.work),ensure_ascii=False),flush=True)
        except Exception as exc:
            if args.work:atomic_json(args.work/'worker-error.json',{'at':now(),'phase':'requires_review','error':type(exc).__name__+': '+str(exc),'published':False})
            raise
    else:run()
