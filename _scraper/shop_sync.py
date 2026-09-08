"""Scheduled NAS-source catalogue refresh, scoped Git publish and live verification.

Credentials remain in nadaun_order_sync/.env. This worker never changes supplier
products, customer records, orders or payments. Only its generated files commit.
"""
import argparse
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
from urllib.parse import urlencode
from bs4 import BeautifulSoup
from sync_shop_sources import ROOT,OUT,collect_smartstore,collect_imweb_dji,request,save_json,stamp
from sync_kpp_catalog import collect as collect_kpp
from sync_partner_catalogs import collect_lmount,collect_gift
from enrich_shop_sources import collect as enrich
from prepare_shop_assets import prepare
from build_catalog import build
from sync_gift_inventory import ensure_source_access, GiftSourceSuspended
from source_refresh_state import recent_refresh,record_refresh

STATE=ROOT/'_scraper/.sync-state'
SITE='https://shop.nadaun.co'
GENERATED=['data/catalog','assets/shop/thumbnails','brands','brands.html','index.html','catalog.html','catalog_category.html','item.html','cart.html','checkout.html','payment-test.html','orders.html','admin.html','terms.html','privacy.html','shipping.html','services.html','gifts.html','about.html','studio.html','catalog-sitemap.xml']
CODE=['_scraper/shipping_policy.py','_scraper/test_shop_shipping.py','assets/shop/shipping.js','_scraper/test_shop_taxonomy.py','_scraper/product_taxonomy.py','_scraper/rental_taxonomy.py','_scraper/references/slrrent-categories.json','assets/shop/motion.js','assets/shop/departments','assets/shop/banners.js','data/catalog/banners.json','assets/shop/studio','_scraper/brand_products.py','assets/shop/vendor','assets/shop/brands','data/catalog/partner-image-rules.json','_scraper/sync_partner_catalogs.py','data/catalog/brand-assets.json','_scraper/catalog_seo.py','assets/shop/catalog-tools.js','_scraper/tests','_scraper/test_shop_catalog.py','api','assets/shop/cart.js','_scraper/storefront_pages.py','_scraper/sync_shop_sources.py','_scraper/sync_kpp_catalog.py','_scraper/enrich_shop_sources.py','_scraper/build_catalog.py','_scraper/catalog_dedup.py','_scraper/shop_sync.py','_scraper/prepare_shop_assets.py','_scraper/shop_templates','assets/shop/shop.js','assets/shop/shop.css','data/catalog/overrides.json','data/catalog/dedup-rules.json','vercel.json']

CODE += ['_scraper/gift_product_details.py','_scraper/source_transport.py','_scraper/plthink_checkpoint.py','_scraper/sync_plthink_catalog.py',
         '_scraper/sync_gift_inventory.py','_scraper/partner_worker.py','_scraper/install_partner_workers.py']
CODE += ['server/commerce','assets/shop/commerce.js','assets/shop/commerce.css','_scraper/commerce_setup.cjs']
CODE += ['_scraper/brand_category_policy.py','_scraper/partner_sync_status.py','_scraper/partner-sync-plan.json']
CODE += ['assets/shop/storefront.css','assets/shop/scenes.js','assets/shop/browse.js','_scraper/category_gallery.py','_scraper/sync_avx_catalog.py','_scraper/avx_worker.py','_scraper/test_avx_catalog.py']
CODE += ['_scraper/test_partner_sync_status.py']
CODE += ['_scraper/build_gift_catalog.py','_scraper/brand_source_policy.py','_scraper/test_gift_public_catalog.py','_scraper/test_brand_source_policy.py','data/catalog/brand-source-policy.json','server/gift-catalog.cjs','server/shop-search.cjs']
CODE += ['_scraper/source_refresh_state.py','_scraper/test_source_refresh_state.py']
CODE += ['_scraper/avx_publication.py','_scraper/test_avx_publication.py']
CODE += ['_scraper/rental_content.py','_scraper/test_shop_rental_content.py','assets/shop/rental-content.js']

def command(*args):
    print('Run: '+' '.join(str(a) for a in args[:2]),flush=True)
    try:
        p=subprocess.run(args,cwd=ROOT,text=True,capture_output=True,timeout=900 if args[0]=='git' else 180)
    except subprocess.TimeoutExpired:
        raise RuntimeError(f'{args[0]} {args[1]} timed out; inspect NAS connectivity before retrying') from None
    if p.returncode:raise RuntimeError(f'{args[0]} {args[1]} failed: '+(p.stderr or p.stdout)[-1500:])
    return p.stdout.strip()

def api(path):return json.loads(command('vercel','api',path,'--raw'))

def managed_files():
    """Stage exact generated files, never an arbitrary file in those folders."""
    files=['brands.html','index.html','catalog.html','catalog_category.html','item.html','cart.html','checkout.html','payment-test.html','orders.html','admin.html','terms.html','privacy.html','shipping.html','services.html','gifts.html','about.html','studio.html','catalog-sitemap.xml',
           'data/catalog/catalog.json','data/catalog/rental.json','data/catalog/brands.json','data/catalog/sync-status.json','data/catalog/asset-manifest.json','data/catalog/dedup-audit.json']
    files += ['gift-item.html','search.html','gift-sitemap.xml','data/gift/catalog.json','data/gift/manifest.json']
    files += ['data/catalog/rental-details.json']
    files.extend(p.relative_to(ROOT).as_posix() for p in (ROOT/'data/gift/details').glob('??.json'))
    files.extend(p.relative_to(ROOT).as_posix() for p in ROOT.glob('gift-sitemap-[0-9]*.xml'))
    for source in ('smartstore','imweb-dji','imweb-promotions','kpp','l-mount','nadaun-gift'):
        files.append('data/catalog/sources/'+source+'.json')
    if (OUT/'plthink.json').exists():files.append('data/catalog/sources/plthink.json')
    for source in ('avx','avx-aputure','avx-approved'):
        if (OUT/(source+'.json')).exists():files.append('data/catalog/sources/'+source+'.json')
    for source in ('smartstore','kpp'):
        base=ROOT/'data/catalog/source-details'/source
        files.extend(p.relative_to(ROOT).as_posix() for p in base.glob('??.json'))
        if (base/'failures.json').exists():files.append((base/'failures.json').relative_to(ROOT).as_posix())
    files.extend(p.relative_to(ROOT).as_posix() for p in (ROOT/'data/catalog/details').glob('??.json'))
    catalog=json.loads((ROOT/'data/catalog/catalog.json').read_text())
    files.extend('brands/'+b['id']+'.html' for b in catalog['brands'])
    assets=json.loads((ROOT/'data/catalog/asset-manifest.json').read_text())
    files.extend(a['path'] for a in assets.values())
    return sorted(set(files))

def verify_live(revision):
    for attempt in range(75):
        p=json.loads((ROOT/'.vercel/project.json').read_text())
        query=urlencode({'projectId':p['projectId'],'teamId':p['orgId'],'target':'production','limit':6})
        deployments=api('/v6/deployments?'+query).get('deployments',[])
        head=command('git','rev-parse','HEAD')
        match=next((d for d in deployments if (d.get('meta') or {}).get('githubCommitSha')==head or (d.get('meta') or {}).get('gitCommitSha')==head),None)
        if match and match.get('readyState',match.get('state')) in ('ERROR','CANCELED'):
            detail=api('/v13/deployments/'+match['uid']+'?teamId='+p['orgId'])
            raise RuntimeError('Vercel deployment failed: '+str(detail.get('readyStateReason') or detail.get('errorMessage')))
        if match and match.get('readyState',match.get('state'))=='READY':
            live=request('GET',SITE+'/data/catalog/sync-status.json',params={'verify':revision},headers={'Cache-Control':'no-cache'}).json()
            if live.get('revision')==revision:
                home=request('GET',SITE+'/',params={'verify':revision}).text
                if revision not in home:raise RuntimeError('Live HTML does not match the catalogue revision')
                catalog=json.loads((ROOT/'data/catalog/catalog.json').read_text())
                product=catalog['products'][0]
                page=BeautifulSoup(request('GET',SITE+'/item.html',params={'id':product['id']}).text,'lxml')
                if not page.h1 or page.h1.get_text()!=product['name']:
                    raise RuntimeError('Live product route is not rendering its server-side product content')
                for selector in ('meta[name="description"]','meta[property="og:description"]'):
                    tag=page.select_one(selector)
                    if not tag or not 0<len(tag.get('content',''))<=80:
                        raise RuntimeError('Live product SEO description is missing or exceeds 80 characters')
                if not page.select_one('.product-tags'):
                    raise RuntimeError('Live product discovery links are missing')
                guide=BeautifulSoup(request('GET',SITE+'/services.html',params={'verify':revision}).text,'lxml')
                if not guide.select_one('#production a[href="https://collective.nadaun.co/"]') or revision not in str(guide):
                    raise RuntimeError('Live service guide is missing or stale')
                result={'commit':head,'deployment':match['uid'],'revision':revision,'verified_at':stamp(),'site':SITE}
                from brand_source_policy import verify_audit_live
                all_products=request('GET',SITE+'/data/catalog/catalog.json',params={'verify':revision},headers={'Cache-Control':'no-cache'}).json()
                verify_audit_live(all_products,result)
                return result
        time.sleep(12)
    raise RuntimeError('Vercel/live verification timed out; last good deployment remains available')

def publish_existing():
    status=json.loads((ROOT/'data/catalog/sync-status.json').read_text())
    if command('git','diff','--cached','--name-only'):raise RuntimeError('Unrelated staged changes exist; refusing an automatic commit')
    owned=managed_files()
    command('git','add','--',*owned)
    staged=command('git','diff','--cached','--name-only')
    if set(staged.splitlines())-set(owned):raise RuntimeError('Unrelated changes were staged during sync; refusing an automatic commit')
    # Check the staged snapshot once. Re-reading every NAS file before git add
    # doubles SMB I/O and can time out even when all source data is valid.
    command('git','diff','--cached','--check')
    if staged:command('git','commit','-m','auto(shop): refresh verified brand catalogue')
    command('git','push','origin','HEAD:main')
    command('git','fetch','origin','main')
    if command('git','rev-parse','HEAD')!=command('git','rev-parse','origin/main'):raise RuntimeError('NAS and remote main differ')
    result=verify_live(status['revision']);save_json(STATE/'last-success.json',result)
    print(json.dumps(result,ensure_ascii=False),flush=True)
    return result

def run(publish=True,existing=False):
    STATE.mkdir(parents=True,exist_ok=True)
    lock=STATE/'run.lock'
    if lock.exists():
        old=json.loads(lock.read_text())
        if old.get('host')==socket.gethostname():
            try:os.kill(int(old['pid']),0)
            except ProcessLookupError:
                # Only our own dead process can leave a reclaimable lock.
                save_json(STATE/'recovered-lock.json',{'recovered_at':stamp(),'previous':old})
                lock.unlink()
    try:
        fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY)
    except FileExistsError:raise RuntimeError('Another catalogue sync is running; inspect .sync-state/run.lock') from None
    with os.fdopen(fd,'w') as f:json.dump({'host':socket.gethostname(),'pid':os.getpid(),'started_at':stamp()},f)
    try:
        if command('git','diff','--name-only','--',*CODE):raise RuntimeError('Uncommitted catalogue code or overrides; automatic sync paused')
        if not existing:
            previous=json.loads((ROOT/'data/catalog/sync-status.json').read_text()) if (ROOT/'data/catalog/sync-status.json').exists() else {}
            collect_smartstore();collect_imweb_dji();collect_imweb_dji(promotion=True);collect_kpp();collect_lmount()
            try: ensure_source_access()
            except GiftSourceSuspended:
                # Preserve the linked-store snapshot without blocking other sources.
                save_json(STATE/'gift-refresh-skipped.json', {'at':stamp(), 'reason':'source_suspended',
                    'source_request_made':False, 'previous_snapshot_preserved':True})
                print('Gift refresh suspended; previous linked-store snapshot retained', flush=True)
            else: collect_gift()
            for source,count in previous.get('source_counts',{}).items():
                path=OUT/(source+'.json')
                if source=='avx':path=next(p for p in (OUT/'avx-approved.json',OUT/'avx.json',OUT/'avx-aputure.json') if p.exists())
                new=json.loads(path.read_text())['product_count']
                if new<count*.85:raise RuntimeError(f'{source} count dropped more than 15%; keep live data and review')
            enrich('smartstore');enrich('kpp');prepare()
        build()
        command(sys.executable,'-m','unittest','discover','-s','_scraper','-p','test_shop*.py')
        command(sys.executable,'-m','unittest','discover','-s','_scraper','-p','test_avx*.py')
        command(sys.executable,'-m','unittest','discover','-s','_scraper','-p','test_partner_sync_status.py')
        command(sys.executable,'-m','unittest','discover','-s','_scraper','-p','test_gift_public_catalog.py')
        command(sys.executable,'-m','unittest','discover','-s','_scraper','-p','test_brand_source_policy.py')
        command(sys.executable,'-m','unittest','discover','-s','_scraper','-p','test_source_refresh_state.py')
        command('node','--test','_scraper/tests/gift-search.test.cjs','_scraper/tests/rental-content.test.cjs')
        command('node','--check','assets/shop/shop.js')
        command('node','--check','assets/shop/cart.js')
        command('node','--check','assets/shop/motion.js')
        command('node','--test','_scraper/tests/product-server.test.cjs','_scraper/tests/catalog-tools.test.mjs','_scraper/tests/discovery.test.cjs','_scraper/tests/cart.test.cjs','_scraper/tests/banners.test.mjs','_scraper/tests/motion.test.mjs','_scraper/tests/browse.test.mjs','_scraper/tests/scenes.test.mjs','_scraper/tests/commerce.test.cjs','_scraper/tests/commerce-ui.test.cjs')
        if publish:
            result=publish_existing()
            if not existing:record_refresh(result)
            return result
    except Exception as e:
        save_json(STATE/'last-failure.json',{'failed_at':stamp(),'error':str(e)})
        raise
    finally:
        lock.unlink(missing_ok=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--existing',action='store_true',help='Use already verified source snapshots');p.add_argument('--no-publish',action='store_true');p.add_argument('--verify-revision');p.add_argument('--scheduled',action='store_true');a=p.parse_args()
    if a.scheduled and recent_refresh():
        print('Supplier data was refreshed and live-verified within six hours; skip duplicate startup run.',flush=True)
        sys.exit(0)
    if a.verify_revision:print(json.dumps(verify_live(a.verify_revision),ensure_ascii=False))
    else:run(not a.no_publish,a.existing)
