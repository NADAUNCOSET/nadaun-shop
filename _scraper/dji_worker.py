"""Resume the official Korean DJI catalogue and refresh every twelve hours."""
from datetime import datetime
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import sys
import time

from sync_dji_official import STATE, SOURCE, collect, validate_snapshot, official_dji_ids
from sync_shop_sources import ROOT, OUT, save_json, stamp
from brand_source_policy import policy_fingerprint, selections


def receipt(snapshot, release, catalog):
    validate_snapshot(snapshot)
    products=[p for p in catalog['products'] if p['brand_id']=='dji' and p['kind']=='purchase']
    offers=[o for p in products for o in p['offers']]
    expected=official_dji_ids(snapshot)
    if {o['id'] for o in offers}!=expected or any(o['source']!=SOURCE for o in offers):
        raise RuntimeError('Live DJI purchase products differ from the official snapshot')
    for p in products:
        original=snapshot['products'][p['id']]
        if (p['name']!=original['name'] or p['sale_price']!=original['sale_price'] or
            p['status']!=original['status'] or p['supplier_status']!=original['supplier_status'] or
            not p.get('navigation_category_ids') or
            any(not cid.startswith(SOURCE+':') for cid in p['navigation_category_ids'])):
            raise RuntimeError('Live DJI fields or categories differ: '+p['id'])
    result={**release,'scope':'official-dji-purchases','verified_products':len(products),'source_verified_products':snapshot['product_count'],
        'held_other_brand_ids':sorted(set(snapshot['products'])-expected),
        'source_collected_at':snapshot['collected_at'],'policy_sha256':policy_fingerprint(),
        'source_sha256':hashlib.sha256((OUT/(SOURCE+'.json')).read_bytes()).hexdigest()}
    save_json(STATE/'published.json',result)
    return result


def publish(snapshot):
    from shop_sync import run, request, SITE
    validate_snapshot(snapshot)
    if selections().get('dji',{}).get('source')!=SOURCE:
        raise RuntimeError('Official DJI source is not selected by the owner')
    path=OUT/(SOURCE+'.json')
    previous=json.loads(path.read_text()) if path.exists() else {}
    if snapshot['product_count']<previous.get('product_count',0)*.85:
        raise RuntimeError('Official DJI inventory decreased more than 15%; review before publication')
    release=run(existing=True,source_updates={SOURCE:snapshot})
    live=request('GET',SITE+'/data/catalog/catalog.json',params={'verify':release['revision']}).json()
    return receipt(snapshot,release,live)


def work():
    STATE.mkdir(parents=True,exist_ok=True)
    with (STATE/'worker.lock').open('a+') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:return
        pointer=STATE/'generation.json'
        folder=STATE/json.loads(pointer.read_text())['directory'] if pointer.exists() else STATE
        path=folder/'catalogue-candidate.json'
        snapshot=json.loads(path.read_text()) if path.exists() else None
        prior=json.loads((STATE/'published.json').read_text()) if (STATE/'published.json').exists() else {}
        if snapshot:
            validate_snapshot(snapshot)
            if prior.get('source_collected_at')!=snapshot['collected_at'] or prior.get('policy_sha256')!=policy_fingerprint():
                return publish(snapshot)
            if time.time()-datetime.fromisoformat(snapshot['collected_at']).timestamp()<43200:
                save_json(STATE/'steady-state.json',{'checked_at':stamp(),'state':'up_to_date','source_collected_at':snapshot['collected_at'],'revision':prior['revision']})
                return
            folder=STATE/('generation-'+datetime.now().strftime('%Y%m%d-%H%M%S'))
            folder.mkdir()
            save_json(pointer,{'directory':folder.name,'started_at':stamp()})
        return publish(collect(folder))


def install():
    label='co.nadaun.shop.dji-official-sync'
    target=Path.home()/'Library/LaunchAgents'/(label+'.plist')
    loaded=subprocess.run(['launchctl','print',f'gui/{os.getuid()}/{label}'],capture_output=True)
    if loaded.returncode==0:raise RuntimeError('DJI worker is already installed; inspect before replacing')
    awake=shutil.which('caffeinate')
    if not awake:raise RuntimeError('caffeinate is required')
    logs=Path.home()/'Library/Logs/NADAUN/shop';logs.mkdir(parents=True,exist_ok=True)
    definition={'Label':label,'ProgramArguments':[awake,'-i',sys.executable,str(Path(__file__).resolve())],
        'WorkingDirectory':str(Path.home()),'RunAtLoad':True,'StartInterval':600,'ProcessType':'Standard',
        'StandardOutPath':str(logs/'dji-official.stdout.log'),'StandardErrorPath':str(logs/'dji-official.stderr.log'),
        'EnvironmentVariables':{'PATH':os.environ.get('PATH','/usr/bin:/bin'),'PYTHONUNBUFFERED':'1'}}
    target.parent.mkdir(parents=True,exist_ok=True)
    with target.open('wb') as f:plistlib.dump(definition,f)
    subprocess.run(['launchctl','bootstrap',f'gui/{os.getuid()}',str(target)],check=True)
    output=subprocess.check_output(['launchctl','print',f'gui/{os.getuid()}/{label}'],text=True)
    if str(Path(__file__).resolve()) not in output:raise RuntimeError('DJI NAS entrypoint is not loaded')
    save_json(STATE/'schedule.json',{'at':stamp(),'label':label,'resume_seconds':600,'refresh_seconds':43200,
        'request_interval_seconds':3,'requires':'Mac awake, NAS mounted, network available'})


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--install',action='store_true');args=parser.parse_args()
    try:install() if args.install else work()
    except Exception as exc:
        save_json(STATE/'worker-error.json',{'at':stamp(),'error':type(exc).__name__+': '+str(exc),'published':False})
        raise
