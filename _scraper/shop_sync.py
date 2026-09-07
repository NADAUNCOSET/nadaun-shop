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
from sync_shop_sources import ROOT,OUT,collect_smartstore,collect_imweb_dji,request,save_json,stamp
from sync_kpp_catalog import collect as collect_kpp
from enrich_shop_sources import collect as enrich
from prepare_shop_assets import prepare
from build_catalog import build

STATE=ROOT/'_scraper/.sync-state'
SITE='https://shop.nadaun.co'
GENERATED=['data/catalog','assets/shop/thumbnails','brands','index.html','catalog.html','catalog_category.html','item.html','catalog-sitemap.xml']
CODE=['_scraper/sync_shop_sources.py','_scraper/sync_kpp_catalog.py','_scraper/enrich_shop_sources.py','_scraper/build_catalog.py','_scraper/shop_sync.py','_scraper/prepare_shop_assets.py','_scraper/shop_templates','assets/shop/shop.js','assets/shop/shop.css','data/catalog/overrides.json','vercel.json']

def command(*args):
    p=subprocess.run(args,cwd=ROOT,text=True,capture_output=True,timeout=180)
    if p.returncode:raise RuntimeError(f'{args[0]} {args[1]} failed: '+(p.stderr or p.stdout)[-1500:])
    return p.stdout.strip()

def api(path):return json.loads(command('vercel','api',path,'--raw'))

def managed_files():
    """Stage exact generated files, never an arbitrary file in those folders."""
    files=['index.html','catalog.html','catalog_category.html','item.html','catalog-sitemap.xml',
           'data/catalog/catalog.json','data/catalog/sync-status.json','data/catalog/asset-manifest.json']
    for source in ('smartstore','imweb-dji','kpp'):
        files.append('data/catalog/sources/'+source+'.json')
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
                return {'commit':head,'deployment':match['uid'],'revision':revision,'verified_at':stamp(),'site':SITE}
        time.sleep(12)
    raise RuntimeError('Vercel/live verification timed out; last good deployment remains available')

def publish_existing():
    status=json.loads((ROOT/'data/catalog/sync-status.json').read_text())
    if command('git','diff','--cached','--name-only'):raise RuntimeError('Unrelated staged changes exist; refusing an automatic commit')
    owned=managed_files()
    command('git','diff','--check','--',*owned)
    command('git','add','--',*owned)
    staged=command('git','diff','--cached','--name-only')
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
            collect_smartstore();collect_imweb_dji();collect_kpp()
            for source,count in previous.get('source_counts',{}).items():
                new=json.loads((OUT/(source+'.json')).read_text())['product_count']
                if new<count*.85:raise RuntimeError(f'{source} count dropped more than 15%; keep live data and review')
            enrich('smartstore');enrich('kpp');prepare()
        build()
        command(sys.executable,'-m','unittest','discover','-s','_scraper','-p','test_shop_catalog.py')
        command('node','--check','assets/shop/shop.js')
        if publish:return publish_existing()
    except Exception as e:
        save_json(STATE/'last-failure.json',{'failed_at':stamp(),'error':str(e)})
        raise
    finally:
        lock.unlink(missing_ok=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--existing',action='store_true',help='Use already verified source snapshots');p.add_argument('--no-publish',action='store_true');p.add_argument('--verify-revision');p.add_argument('--scheduled',action='store_true');a=p.parse_args()
    if a.scheduled and (STATE/'last-success.json').exists():
        last=json.loads((STATE/'last-success.json').read_text())
        age=time.time()-datetime.fromisoformat(last['verified_at']).timestamp()
        if age<6*3600:
            print('Catalogue was verified within six hours; skip duplicate startup run.',flush=True)
            sys.exit(0)
    if a.verify_revision:print(json.dumps(verify_live(a.verify_revision),ensure_ascii=False))
    else:run(not a.no_publish,a.existing)
